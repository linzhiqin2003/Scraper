#!/usr/bin/env python3
"""Reply to WeChat messages with wxauto/wxauto4.

This script is intended to run on Windows with the WeChat desktop client open.
It supports:
1. one-shot replies to a target chat
2. listener mode that auto-replies to new inbound messages
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any

import requests


class SafeFormatDict(dict[str, str]):
    """Preserve unknown placeholders instead of failing format()."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Use wxauto to send or auto-reply to WeChat messages.",
        epilog=(
            "Examples:\n"
            "  python scripts/wxauto_reply.py --who \"张三\" --reply \"我先忙，晚点回你。\"\n"
            "  python scripts/wxauto_reply.py --who \"张三\" --reply \"收到：{content}\" --listen\n"
            "  python scripts/wxauto_reply.py --who \"张三\" --reply-file reply.txt --listen --match \"在吗\"\n"
            "  python scripts/wxauto_reply.py --who \"张三\" --listen --ai --persona \"冷淡但不失礼貌\""
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--who", required=True, help="Chat name shown in WeChat session list.")
    parser.add_argument("--reply", help="Reply text or template. Supports {sender}, {content}, {chat}.")
    parser.add_argument("--reply-file", type=Path, help="Read reply text from a UTF-8 text file.")
    parser.add_argument("--ai", action="store_true", help="Generate replies with an OpenAI-compatible chat API.")
    parser.add_argument("--persona", default="自然、简短、像本人回复微信。", help="Short style instruction for AI replies.")
    parser.add_argument("--system-prompt", help="Override the default AI system prompt.")
    parser.add_argument("--system-prompt-file", type=Path, help="Read the AI system prompt from a UTF-8 text file.")
    parser.add_argument("--model", help="Override OPENAI_MODEL for AI replies.")
    parser.add_argument("--listen", action="store_true", help="Keep listening and auto-reply to new messages.")
    parser.add_argument("--match", help="Only auto-reply when the inbound message contains this keyword.")
    parser.add_argument("--exact", action="store_true", help="Use exact match when opening the chat for one-shot send.")
    parser.add_argument("--typing", action="store_true", help="Use SendTypingText when supported.")
    parser.add_argument(
        "--history-size",
        type=int,
        default=8,
        help="How many recent turns to include when generating AI replies.",
    )
    parser.add_argument(
        "--cooldown",
        type=float,
        default=3.0,
        help="Minimum seconds between duplicate auto replies in listener mode.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print what would be sent without sending it.")
    args = parser.parse_args()
    if not args.ai and not args.reply and not args.reply_file:
        parser.error("one of --reply, --reply-file, or --ai is required")
    return args


def load_reply_text(args: argparse.Namespace) -> str:
    if args.reply_file:
        return args.reply_file.read_text(encoding="utf-8").strip()
    assert args.reply is not None
    return args.reply.strip()


def load_system_prompt(args: argparse.Namespace) -> str:
    if args.system_prompt_file:
        return args.system_prompt_file.read_text(encoding="utf-8").strip()
    if args.system_prompt:
        return args.system_prompt.strip()
    return (
        "你在代替用户回复微信消息。\n"
        "要求：\n"
        f"1. 风格：{args.persona}\n"
        "2. 回复要像真人聊天，优先简短，通常不超过两句话。\n"
        "3. 不要提你是 AI，不要解释你的推理。\n"
        "4. 如果对方只是寒暄，就自然接话；如果对方在施压、操控、越界，要保持边界。\n"
        "5. 除非对方明确问到，否则不要擅自承诺时间、金钱、见面或敏感信息。\n"
        "6. 只输出最终要发出的微信回复，不要加引号。"
    )


def render_reply(template: str, *, sender: str, content: str, chat: str) -> str:
    return template.format_map(
        SafeFormatDict(
            sender=sender,
            content=content,
            chat=chat,
        )
    )


def get_chat_completion(
    *,
    model: str,
    system_prompt: str,
    history: list[dict[str, str]],
    sender: str,
    content: str,
    chat: str,
) -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for --ai mode.")

    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            *history,
            {
                "role": "user",
                "content": (
                    f"当前聊天对象：{chat}\n"
                    f"对方昵称：{sender}\n"
                    f"对方刚发来的消息：{content}"
                ),
            },
        ],
    }
    response = requests.post(
        f"{base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    message = data["choices"][0]["message"]["content"]

    if isinstance(message, str):
        return message.strip()

    if isinstance(message, list):
        parts = [item.get("text", "") for item in message if isinstance(item, dict)]
        return "".join(parts).strip()

    raise RuntimeError(f"Unsupported completion payload: {message!r}")


def import_wx_backend() -> tuple[type[Any], type[Any] | None, str]:
    attempts = [
        ("wxauto", "wxauto.msgs"),
        ("wxauto4", "wxauto4.msgs"),
    ]
    errors: list[str] = []

    for module_name, msgs_name in attempts:
        try:
            module = importlib.import_module(module_name)
            msgs_module = importlib.import_module(msgs_name)
        except Exception as exc:  # pragma: no cover - depends on local env
            errors.append(f"{module_name}: {exc}")
            continue

        wechat_cls = getattr(module, "WeChat", None)
        friend_message_cls = getattr(msgs_module, "FriendMessage", None)
        if wechat_cls is not None:
            return wechat_cls, friend_message_cls, module_name

    details = "; ".join(errors) if errors else "unknown import error"
    raise RuntimeError(
        "Cannot import wxauto backend. Install `wxauto` (WeChat 3.x) or `wxauto4` (WeChat 4.x). "
        f"Import details: {details}"
    )


def is_inbound_friend_message(msg: Any, friend_message_cls: type[Any] | None) -> bool:
    if friend_message_cls is not None and isinstance(msg, friend_message_cls):
        return True

    attr = str(getattr(msg, "attr", "")).lower()
    if "friend" in attr:
        return True

    return msg.__class__.__name__.lower().startswith("friend")


def send_message(chat: Any, text: str, *, typing: bool, who: str | None = None, exact: bool = False) -> Any:
    if typing and hasattr(chat, "SendTypingText"):
        if who is None:
            return chat.SendTypingText(msg=text, clear=True)
        return chat.SendTypingText(msg=text, who=who, clear=True, exact=exact)

    if who is None:
        return chat.SendMsg(msg=text, clear=True)
    return chat.SendMsg(msg=text, who=who, clear=True, exact=exact)


def run_once(args: argparse.Namespace) -> int:
    wechat_cls, _, backend_name = import_wx_backend()
    wx = wechat_cls()
    if args.ai:
        system_prompt = load_system_prompt(args)
        model = args.model or os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
        text = get_chat_completion(
            model=model,
            system_prompt=system_prompt,
            history=[],
            sender=args.who,
            content="请发一条自然的开场白或回应消息。",
            chat=args.who,
        )
    else:
        text = load_reply_text(args)

    if args.dry_run:
        print(f"[dry-run] backend={backend_name} who={args.who} text={text}")
        return 0

    result = send_message(wx, text, typing=args.typing, who=args.who, exact=args.exact)
    print(f"sent via {backend_name}: {result}")
    return 0


def run_listener(args: argparse.Namespace) -> int:
    wechat_cls, friend_message_cls, backend_name = import_wx_backend()
    wx = wechat_cls()
    template = load_reply_text(args) if not args.ai else ""
    system_prompt = load_system_prompt(args) if args.ai else ""
    model = args.model or os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
    last_message_key: tuple[str, str, str] | None = None
    last_reply_at = 0.0
    history: deque[dict[str, str]] = deque(maxlen=max(args.history_size, 0) * 2)

    def on_message(msg: Any, chat: Any) -> None:
        nonlocal last_message_key, last_reply_at

        try:
            if not is_inbound_friend_message(msg, friend_message_cls):
                return

            content = str(getattr(msg, "content", "")).strip()
            sender = str(getattr(msg, "sender", "")).strip() or args.who
            msg_type = str(getattr(msg, "type", "")).strip()

            if args.match and args.match not in content:
                return

            message_key = (sender, content, msg_type)
            now = time.monotonic()

            if message_key == last_message_key and now - last_reply_at < args.cooldown:
                return

            if args.ai:
                reply_text = get_chat_completion(
                    model=model,
                    system_prompt=system_prompt,
                    history=list(history),
                    sender=sender,
                    content=content,
                    chat=args.who,
                )
            else:
                reply_text = render_reply(template, sender=sender, content=content, chat=args.who)

            history.append({"role": "user", "content": f"{sender}: {content}"})

            if args.dry_run:
                print(f"[dry-run] inbound from {sender}: {content}")
                print(f"[dry-run] reply to {args.who}: {reply_text}")
                history.append({"role": "assistant", "content": reply_text})
                last_message_key = message_key
                last_reply_at = now
                return

            result = send_message(chat, reply_text, typing=args.typing)
            print(f"[{backend_name}] inbound from {sender}: {content}")
            print(f"[{backend_name}] replied: {reply_text} -> {result}")
            history.append({"role": "assistant", "content": reply_text})
            last_message_key = message_key
            last_reply_at = now
        except Exception as exc:
            print(f"[error] failed to handle message for {args.who}: {exc}", file=sys.stderr)

    if args.dry_run:
        print(f"[dry-run] listening to {args.who} with backend {backend_name}")
    else:
        print(f"listening to {args.who} with backend {backend_name}")

    wx.AddListenChat(args.who, on_message)
    wx.KeepRunning()
    return 0


def main() -> int:
    if sys.platform != "win32":
        print("This script must run on Windows with the WeChat desktop client open.", file=sys.stderr)
        return 1

    args = parse_args()
    if args.listen:
        return run_listener(args)
    return run_once(args)


if __name__ == "__main__":
    raise SystemExit(main())

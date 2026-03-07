#!/usr/bin/env python3
"""Test Exa search API. Usage: python test_exa.py <query> [--num N] [--category CAT]"""

import argparse
import os
import sys
import time


def main():
    parser = argparse.ArgumentParser(description="Test Exa search API")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--num", type=int, default=5, help="Number of results (default: 5)")
    parser.add_argument(
        "--category",
        default=None,
        choices=["news", "research paper", "company", "tweet", "people"],
        help="Optional category filter",
    )
    parser.add_argument(
        "--type",
        dest="search_type",
        default="auto",
        choices=["auto", "fast"],
        help="Search type (default: auto)",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=5000,
        help="Max characters of full text per result (default: 5000)",
    )
    args = parser.parse_args()

    api_key = os.environ.get("EXA_API_KEY")
    if not api_key:
        print("[ERROR] EXA_API_KEY environment variable not set")
        sys.exit(1)

    try:
        from exa_py import Exa
    except ImportError:
        print("[ERROR] exa-py not installed. Run: pip install exa-py")
        sys.exit(1)

    exa = Exa(api_key=api_key)

    print(f"Query    : {args.query}")
    print(f"Type     : {args.search_type}")
    print(f"Category : {args.category or '(none)'}")
    print(f"Results  : {args.num}")
    print(f"Max chars: {args.max_chars}")
    print("=" * 60)

    t0 = time.time()
    try:
        kwargs = dict(
            query=args.query,
            type=args.search_type,
            num_results=args.num,
            contents={"text": {"max_characters": args.max_chars}},
        )
        if args.category:
            kwargs["category"] = args.category

        response = exa.search(**kwargs)
        elapsed = time.time() - t0
    except Exception as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    results = response.results
    print(f"[OK] {len(results)} results in {elapsed:.1f}s\n")

    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")  # DeepSeek tokenizer approximation
    except Exception:
        enc = None

    token_counts = []

    for i, r in enumerate(results, 1):
        print(f"── [{i}] {r.title or '(no title)'}")
        print(f"  URL       : {r.url}")
        if hasattr(r, "published_date") and r.published_date:
            print(f"  Published : {r.published_date}")
        if hasattr(r, "score") and r.score:
            print(f"  Score     : {r.score:.4f}")
        text = getattr(r, "text", None) or ""
        if text:
            toks = len(enc.encode(text)) if enc else len(text) // 4
            token_counts.append(toks)
            print(f"  Chars     : {len(text)}  |  Tokens: {toks:,}")
            print(f"  Content preview:\n{text[:5000]}")
        else:
            token_counts.append(0)
        print()

    # ── Token summary ──────────────────────────────────────────
    total_tokens = sum(token_counts)
    print("=" * 60)
    print("  Token estimate (DeepSeek / cl100k_base approximation)")
    print("=" * 60)
    for i, (r, toks) in enumerate(zip(results, token_counts), 1):
        title = (r.title or "(no title)")[:50]
        print(f"  [{i}] {toks:>6,}  {title}")
    print(f"  {'─' * 46}")
    print(f"  Total  {total_tokens:>6,} tokens")
    if enc:
        # DeepSeek V3 pricing: $0.07/M input tokens (cache miss)
        cost_usd = total_tokens / 1_000_000 * 0.07
        print(f"  Cost   ~${cost_usd:.4f} USD  (DeepSeek V3 $0.07/M input)")
    print("=" * 60)


if __name__ == "__main__":
    main()

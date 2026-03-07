"""Global scraper configuration backed by ~/.web_scraper/config.json."""

import json
from pathlib import Path
from typing import Dict, List, Optional

from .browser import DEFAULT_DATA_DIR

CONFIG_PATH = DEFAULT_DATA_DIR / "config.json"

# All known sources and their default enabled state
_ALL_SOURCES: Dict[str, bool] = {
    "reuters": False,
    "wsj": False,
    "scholar": False,
    "zhihu": False,
    "dianping": False,
    "serper": False,
    "google": False,
}


class ScraperConfig:
    """Read/write ~/.web_scraper/config.json.

    Schema::

        {
          "sources": {
            "serper": true,
            "google": true,
            "reuters": false,
            ...
          }
        }
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = path or CONFIG_PATH
        self._data = self._load()

    # ── persistence ─────────────────────────────────────

    def _load(self) -> dict:
        if self._path.exists():
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                # Merge with defaults so new sources get their default state
                sources = {**_ALL_SOURCES, **raw.get("sources", {})}
                return {"sources": sources}
            except Exception:
                pass
        return {"sources": dict(_ALL_SOURCES)}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── public API ──────────────────────────────────────

    def is_enabled(self, source: str) -> bool:
        """Return True if *source* is enabled."""
        return bool(self._data["sources"].get(source, False))

    def enabled_sources(self) -> List[str]:
        """Return list of enabled source names."""
        return [s for s, on in self._data["sources"].items() if on]

    def set_enabled(self, source: str, enabled: bool) -> None:
        """Enable or disable *source* and persist the change."""
        if source not in _ALL_SOURCES:
            raise ValueError(
                f"Unknown source '{source}'. "
                f"Available: {', '.join(sorted(_ALL_SOURCES))}"
            )
        self._data["sources"][source] = enabled
        self._save()

    def all_sources(self) -> Dict[str, bool]:
        """Return mapping of source → enabled."""
        return dict(self._data["sources"])

    @property
    def path(self) -> Path:
        return self._path


# Module-level singleton (lazy-loaded on first access)
_instance: Optional[ScraperConfig] = None


def get_config() -> ScraperConfig:
    """Return the module-level config singleton."""
    global _instance
    if _instance is None:
        _instance = ScraperConfig()
    return _instance


def reload_config() -> ScraperConfig:
    """Force reload config from disk."""
    global _instance
    _instance = ScraperConfig()
    return _instance

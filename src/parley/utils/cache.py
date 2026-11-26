"""
Persistent disk cache with TTL and schema versioning.
"""

import json
import time
from pathlib import Path
from typing import Any, Optional
from parley.config import BASE_DIR, CACHE_VERSION

CACHE_FILE = BASE_DIR / "cache.json"
TTL_SECONDS = 6 * 3600  # 6 hours


def _fresh_cache() -> dict:
    return {"version": CACHE_VERSION, "timestamp": time.time(), "form": {}}


def load_cache() -> dict:
    """Load persistent disk cache from cache.json if it exists, is current and is valid."""
    if not CACHE_FILE.exists():
        return _fresh_cache()
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("version") != CACHE_VERSION:
            return _fresh_cache()
        if time.time() - data.get("timestamp", 0) > TTL_SECONDS:
            return _fresh_cache()
        return data
    except Exception:
        return _fresh_cache()


def save_cache(cache_data: dict) -> None:
    """Save persistent disk cache to cache.json with the current schema version."""
    try:
        cache_data["version"] = CACHE_VERSION
        cache_data["timestamp"] = cache_data.get("timestamp", time.time())
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

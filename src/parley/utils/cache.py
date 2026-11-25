"""
Persistent disk cache with TTL.
"""

import json
import time
from pathlib import Path
from typing import Any, Optional
from parley.config import BASE_DIR

CACHE_FILE = BASE_DIR / "cache.json"
TTL_SECONDS = 6 * 3600  # 6 hours


def load_cache() -> dict:
    """Load persistent disk cache from cache.json if it exists and is valid."""
    if not CACHE_FILE.exists():
        return {"timestamp": time.time(), "form": {}}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if time.time() - data.get("timestamp", 0) > TTL_SECONDS:
                return {"timestamp": time.time(), "form": {}}
            return data
    except Exception:
        return {"timestamp": time.time(), "form": {}}


def save_cache(cache_data: dict) -> None:
    """Save persistent disk cache to cache.json."""
    try:
        cache_data["timestamp"] = cache_data.get("timestamp", time.time())
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

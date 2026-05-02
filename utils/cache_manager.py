"""
utils/cache_manager.py — LRU cache with TTL for API responses.
"""
import time
import json
import hashlib
from pathlib import Path
from collections import OrderedDict
from typing import Any, Optional

# Anchor cache to project root regardless of where the module is imported from
CACHE_DIR = Path(__file__).parent.parent / ".cache"
CACHE_DIR.mkdir(exist_ok=True)


class LRUCache:
    """
    In-memory LRU cache with TTL support.
    Falls back to disk cache for persistence across restarts.
    """

    def __init__(self, max_size: int = 256, ttl_seconds: int = 86400):
        self.max_size = max_size
        self.ttl = ttl_seconds
        self._cache: OrderedDict[str, dict] = OrderedDict()

    def _key(self, *args) -> str:
        raw = json.dumps(args, sort_keys=True)
        return hashlib.md5(raw.encode()).hexdigest()

    def get(self, *args) -> Optional[Any]:
        key = self._key(*args)
        # Check memory
        if key in self._cache:
            entry = self._cache[key]
            if time.time() - entry["ts"] < self.ttl:
                self._cache.move_to_end(key)
                return entry["value"]
            else:
                del self._cache[key]
        # Check disk
        disk_path = CACHE_DIR / f"{key}.json"
        if disk_path.exists():
            try:
                data = json.loads(disk_path.read_text())
                if time.time() - data["ts"] < self.ttl:
                    self._cache[key] = data
                    return data["value"]
                else:
                    disk_path.unlink(missing_ok=True)
            except Exception:
                pass
        return None

    def set(self, value: Any, *args) -> None:
        key = self._key(*args)
        entry = {"value": value, "ts": time.time()}
        self._cache[key] = entry
        self._cache.move_to_end(key)
        if len(self._cache) > self.max_size:
            self._cache.popitem(last=False)
        # Persist to disk
        try:
            (CACHE_DIR / f"{key}.json").write_text(json.dumps(entry))
        except Exception:
            pass

    def clear(self) -> None:
        self._cache.clear()
        for f in CACHE_DIR.glob("*.json"):
            f.unlink(missing_ok=True)


# Singleton instance used across the app
cache = LRUCache(max_size=512, ttl_seconds=86400)

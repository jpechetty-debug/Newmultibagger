# worker/redis_cache.py
"""
Sovereign AI Trading Engine v4.0 — Redis Caching Layer
High-performance in-memory cache for frequently accessed data:
  - Market regime state
  - Stock scores
  - API response deduplication
  - Rate-limit tracking
"""
import os
import json
import hashlib
from datetime import datetime
from typing import Any, Optional

try:
    import redis
except ImportError:
    redis = None
    print("Warning: redis package not installed. Caching disabled. Install: pip install redis")


REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
DEFAULT_TTL = 300  # 5 minutes
REGIME_TTL = 120   # 2 minutes
SCORE_TTL = 600    # 10 minutes
API_RESPONSE_TTL = 900  # 15 minutes


class SovereignCache:
    """
    Redis-backed caching layer with namespace isolation and TTL management.
    Falls back to an in-memory dictionary when Redis is unavailable.
    """

    def __init__(self, namespace: str = "sovereign"):
        self.namespace = namespace
        self._fallback_cache = {}
        self._redis = None

        if redis is not None:
            try:
                self._redis = redis.from_url(
                    REDIS_URL,
                    decode_responses=True,
                    socket_connect_timeout=2,
                    socket_timeout=2,
                    retry_on_timeout=True,
                )
                self._redis.ping()
            except Exception as e:
                print(f"Redis connection failed ({e}). Using in-memory fallback.")
                self._redis = None

    def _key(self, key: str) -> str:
        return f"{self.namespace}:{key}"

    def get(self, key: str) -> Optional[Any]:
        """Retrieve a cached value. Returns None if expired or missing."""
        full_key = self._key(key)
        if self._redis:
            try:
                raw = self._redis.get(full_key)
                return json.loads(raw) if raw else None
            except Exception:
                return None
        else:
            entry = self._fallback_cache.get(full_key)
            if entry and entry["expires_at"] > datetime.utcnow().timestamp():
                return entry["value"]
            return None

    def set(self, key: str, value: Any, ttl: int = DEFAULT_TTL):
        """Store a value with TTL (seconds)."""
        full_key = self._key(key)
        if self._redis:
            try:
                self._redis.setex(full_key, ttl, json.dumps(value, default=str))
            except Exception:
                pass
        else:
            self._fallback_cache[full_key] = {
                "value": value,
                "expires_at": datetime.utcnow().timestamp() + ttl,
            }

    def delete(self, key: str):
        """Invalidate a specific cache entry."""
        full_key = self._key(key)
        if self._redis:
            try:
                self._redis.delete(full_key)
            except Exception:
                pass
        else:
            self._fallback_cache.pop(full_key, None)

    def invalidate_pattern(self, pattern: str):
        """Invalidate all keys matching a glob pattern."""
        full_pattern = self._key(pattern)
        if self._redis:
            try:
                keys = self._redis.keys(full_pattern)
                if keys:
                    self._redis.delete(*keys)
            except Exception:
                pass
        else:
            to_delete = [k for k in self._fallback_cache if k.startswith(full_pattern.replace("*", ""))]
            for k in to_delete:
                del self._fallback_cache[k]

    # --- Convenience Methods ---

    def cache_regime(self, regime_data: dict):
        """Cache market regime state."""
        self.set("regime:current", regime_data, ttl=REGIME_TTL)

    def get_regime(self) -> Optional[dict]:
        """Retrieve cached market regime."""
        return self.get("regime:current")

    def cache_stock_score(self, symbol: str, score_data: dict):
        """Cache a stock's composite score."""
        self.set(f"score:{symbol}", score_data, ttl=SCORE_TTL)

    def get_stock_score(self, symbol: str) -> Optional[dict]:
        """Retrieve a stock's cached composite score."""
        return self.get(f"score:{symbol}")

    def cache_api_response(self, url: str, response_data: Any):
        """Cache an external API response (deduplicated by URL hash)."""
        url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
        self.set(f"api:{url_hash}", response_data, ttl=API_RESPONSE_TTL)

    def get_api_response(self, url: str) -> Optional[Any]:
        """Retrieve a cached API response."""
        url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
        return self.get(f"api:{url_hash}")

    def is_connected(self) -> bool:
        """Check if Redis is available."""
        if self._redis:
            try:
                return self._redis.ping()
            except Exception:
                return False
        return False

    def get_stats(self) -> dict:
        """Return cache diagnostics."""
        if self._redis:
            try:
                info = self._redis.info("memory")
                return {
                    "backend": "Redis",
                    "connected": True,
                    "used_memory_mb": round(info.get("used_memory", 0) / 1024 / 1024, 2),
                    "keys": self._redis.dbsize(),
                }
            except Exception:
                return {"backend": "Redis", "connected": False}
        return {
            "backend": "InMemory (Fallback)",
            "connected": False,
            "keys": len(self._fallback_cache),
        }


# Singleton instance
cache = SovereignCache()

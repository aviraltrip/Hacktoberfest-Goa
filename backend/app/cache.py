"""
SHA-256 caching subsystem for DemoToSkill.
Caches LLM inferences by (prompt_text + image_hashes + model_id)
to conserve API rate limits and avoid duplicate compute during retries and re-runs.
"""

import hashlib
from typing import Optional, Any


class ResponseCache:
    """In-memory key-value cache keyed by SHA-256 digests."""

    def __init__(self, max_size: int = 500):
        self._cache: dict[str, dict[str, Any]] = {}
        self._max_size = max_size

    def compute_key(
        self,
        prompt: str,
        image_hashes: Optional[list[str]] = None,
        model: str = ""
    ) -> str:
        """Constructs a deterministic SHA-256 cache key."""
        imgs_str = "|".join(sorted(image_hashes or []))
        payload = f"{model}:::{prompt}:::{imgs_str}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Optional[dict[str, Any]]:
        """Retrieves cached response dict or None."""
        return self._cache.get(key)

    def set(self, key: str, value: dict[str, Any]):
        """Stores a response in cache, evicting oldest if max_size is reached."""
        if len(self._cache) >= self._max_size:
            first_key = next(iter(self._cache))
            del self._cache[first_key]
        self._cache[key] = value

    def has(self, key: str) -> bool:
        """Returns True if key is present in cache."""
        return key in self._cache

    def clear(self):
        """Empties the cache."""
        self._cache.clear()

    def size(self) -> int:
        """Returns the number of cached items."""
        return len(self._cache)


llm_cache = ResponseCache()


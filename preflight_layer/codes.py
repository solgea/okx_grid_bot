from typing import Dict, Optional
import time
from preflight_layer.domain import InstrumentMetadata

class MetadataCache:
    def __init__(self, ttl_seconds: int = 3600):
        self._cache: Dict[str, InstrumentMetadata] = {}
        self._timestamps: Dict[str, float] = {}
        self.ttl_seconds = ttl_seconds

    def get(self, instrument_id: str) -> Optional[InstrumentMetadata]:
        if instrument_id not in self._cache:
            return None
        if time.time() - self._timestamps.get(instrument_id, 0) > self.ttl_seconds:
            self.invalidate(instrument_id)
            return None
        return self._cache[instrument_id]

    def set(self, instrument_id: str, metadata: InstrumentMetadata):
        self._cache[instrument_id] = metadata
        self._timestamps[instrument_id] = time.time()

    def invalidate(self, instrument_id: str):
        self._cache.pop(instrument_id, None)
        self._timestamps.pop(instrument_id, None)

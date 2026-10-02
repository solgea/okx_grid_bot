import json
import os
from typing import Any, Optional

import aiofiles


async def save_state(path: str, state: dict[str, Any]) -> None:
    """Persist bot state atomically so an interrupted write cannot corrupt it."""
    temporary_path = f"{path}.tmp"
    async with aiofiles.open(temporary_path, "w", encoding="utf-8") as file:
        await file.write(json.dumps(state, separators=(",", ":"), sort_keys=True))
    os.replace(temporary_path, path)


async def load_state(path: str) -> Optional[dict[str, Any]]:
    try:
        async with aiofiles.open(path, "r", encoding="utf-8") as file:
            return json.loads(await file.read())
    except FileNotFoundError:
        return None

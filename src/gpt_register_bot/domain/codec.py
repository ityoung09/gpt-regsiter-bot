from __future__ import annotations

import base64
import json
from typing import Any


def decode_jwt_segment(segment: str) -> dict[str, Any]:
    """Decode a single base64url JSON segment (e.g. a signed-cookie payload)."""
    raw = (segment or "").strip()
    if not raw:
        return {}
    pad = "=" * ((4 - (len(raw) % 4)) % 4)
    try:
        decoded = base64.urlsafe_b64decode((raw + pad).encode("ascii"))
        return json.loads(decoded.decode("utf-8"))
    except Exception:
        return {}

"""RunPod serverless queue handler for the character reel renderer.

Returns job metadata plus base64-encoded MP4s so n8n can upload to PostForMe
without fetching worker-local FileResponse URLs (those die on scale-to-zero).
"""
from __future__ import annotations

import base64
import logging
import traceback
from pathlib import Path

import runpod

from app.models import RenderRequest
from app.render import render

log = logging.getLogger("handler")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

MAX_BASE64_BYTES = 20 * 1024 * 1024


def pack_outputs(result: dict, include_base64: bool = True) -> dict:
    packed = {}
    for name, meta in (result.get("outputs") or {}).items():
        item = {k: v for k, v in dict(meta).items() if k != "path"}
        path = Path(meta["path"]) if meta.get("path") else None
        if path and path.is_file():
            item["bytes"] = path.stat().st_size
            item["media_type"] = "video/mp4"
            item["filename"] = name
            if include_base64 and item["bytes"] <= MAX_BASE64_BYTES:
                item["base64"] = base64.b64encode(path.read_bytes()).decode("ascii")
            elif include_base64:
                item["base64_skipped"] = f"file exceeds {MAX_BASE64_BYTES} bytes"
        packed[name] = item
    out = dict(result)
    out["outputs"] = packed
    return out


def handler(event):
    try:
        payload = event.get("input") if isinstance(event, dict) else None
        if not isinstance(payload, dict):
            return {"error": "Job input must be an object"}
        payload = dict(payload)
        include_base64 = bool(payload.pop("include_base64", True))
        result = render(RenderRequest(**payload))
        return pack_outputs(result, include_base64)
    except Exception as exc:
        log.exception("Render failed")
        return {"error": str(exc), "error_type": type(exc).__name__, "traceback": traceback.format_exc()[-4000:]}


runpod.serverless.start({"handler": handler})

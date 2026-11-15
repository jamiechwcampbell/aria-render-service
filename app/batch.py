"""Multi-job batch execution for one RunPod request (batch-render Phase 2).

One request carries {"jobs": [...]}, so exactly one worker renders every job
back to back and the endpoint cannot overshoot to several idle workers.

Pure logic: render, upload and clock functions are injected so this module is
testable without torch, kokoro, pydantic or network access.

Output delivery per job, in order of preference:
1. upload_url present: PUT the MP4 there (presigned S3/Drive-proxy URL made by
   n8n), report sha256 + bytes, no base64.
2. no upload_url: inline base64 while the whole result stays under the 20 MB
   RunPod result cap; otherwise "base64_skipped" so n8n re-runs that job alone.
A failing job never aborts the batch. A job is not started once the batch
deadline would be passed; it is returned as "not_started" for requeue.
"""
from __future__ import annotations

import base64
import hashlib
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable

RESULT_CAP_BYTES = 20 * 1024 * 1024
# base64 grows data by 4/3; keep headroom for JSON metadata.
INLINE_BUDGET_BYTES = int(RESULT_CAP_BYTES * 0.70)
MAX_JOBS = 12
DEFAULT_EST_SECONDS = 90
CONTROL_KEYS = {"job_id", "upload_url", "upload_headers", "est_seconds", "include_base64_files"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def http_put(url: str, path: Path, headers: dict | None = None, timeout: int = 300) -> int:
    data = path.read_bytes()
    req = urllib.request.Request(url, data=data, method="PUT")
    req.add_header("Content-Type", "video/mp4")
    for k, v in (headers or {}).items():
        req.add_header(str(k), str(v))
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (URL supplied by n8n)
        return int(resp.status)


def validate_batch(payload: dict) -> list[dict]:
    jobs = payload.get("jobs")
    if not isinstance(jobs, list) or not jobs:
        raise ValueError("jobs must be a non-empty list")
    if len(jobs) > MAX_JOBS:
        raise ValueError(f"at most {MAX_JOBS} jobs per batch")
    seen = set()
    for i, job in enumerate(jobs):
        if not isinstance(job, dict):
            raise ValueError(f"jobs[{i}] must be an object")
        jid = str(job.get("job_id") or "").strip()
        if not jid:
            raise ValueError(f"jobs[{i}].job_id is required")
        if jid in seen:
            raise ValueError(f"duplicate job_id {jid}")
        seen.add(jid)
        url = job.get("upload_url")
        if url is not None and not str(url).startswith("https://"):
            raise ValueError(f"jobs[{i}].upload_url must be https")
    return jobs


def run_batch(
    payload: dict,
    render_fn: Callable[[dict], dict],
    put_fn: Callable[..., int] = http_put,
    clock: Callable[[], float] = time.monotonic,
) -> dict:
    """render_fn takes the job's render fields and returns {"outputs": {name: {"path": ...}}}."""
    jobs = validate_batch(payload)
    deadline_s = float(payload.get("deadline_s") or 0)
    include_base64 = bool(payload.get("include_base64", True))
    start = clock()
    inline_used = 0
    results: list[dict[str, Any]] = []

    for job in jobs:
        jid = str(job["job_id"])
        est = float(job.get("est_seconds") or DEFAULT_EST_SECONDS)
        if deadline_s and (clock() - start) + est > deadline_s:
            results.append({"job_id": jid, "status": "not_started", "reason": "batch_deadline"})
            continue
        fields = {k: v for k, v in job.items() if k not in CONTROL_KEYS}
        t0 = clock()
        try:
            rendered = render_fn(fields)
        except Exception as exc:  # isolate per job
            results.append({"job_id": jid, "status": "failed", "error": str(exc)[:2000],
                            "error_type": type(exc).__name__, "seconds": round(clock() - t0, 2)})
            continue

        wanted = set(job.get("include_base64_files") or ["full.mp4"])
        outputs: dict[str, dict] = {}
        upload_error = None
        for name, meta in (rendered.get("outputs") or {}).items():
            item = {k: v for k, v in dict(meta).items() if k != "path"}
            path = Path(meta["path"]) if meta.get("path") else None
            if path and path.is_file():
                size = path.stat().st_size
                item.update(bytes=size, filename=name, media_type="video/mp4")
                if name in wanted:
                    item["sha256"] = sha256_file(path)
                    if job.get("upload_url"):
                        try:
                            item["upload_status"] = put_fn(job["upload_url"], path, job.get("upload_headers"))
                            item["uploaded"] = 200 <= item["upload_status"] < 300
                            if not item["uploaded"]:
                                upload_error = f"upload HTTP {item['upload_status']}"
                        except Exception as exc:
                            item["uploaded"] = False
                            upload_error = f"upload failed: {type(exc).__name__}"
                    elif include_base64:
                        if inline_used + size <= INLINE_BUDGET_BYTES * 3 // 4:
                            item["base64"] = base64.b64encode(path.read_bytes()).decode("ascii")
                            inline_used += size
                        else:
                            item["base64_skipped"] = "batch result cap; rerun alone or use upload_url"
            outputs[name] = item

        entry = {"job_id": jid, "status": "failed" if upload_error else "succeeded",
                 "seconds": round(clock() - t0, 2), "outputs": outputs}
        if upload_error:
            entry.update(error=upload_error, error_class="infra")
        for k, v in rendered.items():
            if k != "outputs":
                entry.setdefault(k, v)
        results.append(entry)

    counts: dict[str, int] = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {"batch": True, "jobs": results, "counts": counts, "seconds": round(clock() - start, 2)}

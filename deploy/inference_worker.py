"""Asculto inference worker — the service boundary for the report engine.

The API gateway (Cloudflare Worker / Hono) never runs Python/Torch; it forwards
report jobs here. This process:

  * runs the parametrized report engine (`webapp.app.report`) with either the
    Torch registry or the quantized ONNX backend (`ASCULTO_BACKEND=onnx`);
  * exposes an HTTP contract for Cloudflare Containers / Stage-2 pods;
  * can also pull jobs from a queue (`--queue`) for Stage-2 batch workers.

Endpoints:
  GET  /health -> {status, backend, loaded_heads, errors}
  POST /run    -> {"audio_url"|"audio_b64", "filename", "options": {...}} -> report JSON
  POST /batch  -> {"jobs": [ ...same... ]} -> {"count", "results": [...]}

Run:
  ASCULTO_BACKEND=onnx uvicorn deploy.inference_worker:app --host 0.0.0.0 --port 8080
  python deploy/inference_worker.py --queue          # pull-consumer mode
"""
from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
from typing import Dict, List, Optional

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (REPO, os.path.join(REPO, "ml")):
    if p not in sys.path:
        sys.path.insert(0, p)

from webapp.app import report as report_mod  # noqa: E402
from webapp.app.config import DISCLAIMER  # noqa: E402
from webapp.app.inference import get_registry  # noqa: E402

try:
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
except Exception:  # pragma: no cover - FastAPI is a runtime dep of the worker image
    FastAPI = None


def _options(raw: Optional[Dict]) -> report_mod.ReportOptions:
    raw = raw or {}
    return report_mod.ReportOptions(
        heads=list(raw.get("heads") or report_mod.DEFAULT_HEADS),
        explanation=raw.get("explanation", "standard"),
        figures=raw.get("figures", "all"),
        include_disclaimer=bool(raw.get("include_disclaimer", True)),
        audio_playback=bool(raw.get("audio_playback", False)),
        temporal=bool(raw.get("temporal", False)),
        window_s=float(raw.get("window_s", 3.0)),
        hop_s=float(raw.get("hop_s", 0.5)),
        temporal_mode=raw.get("temporal_mode", "single"),
        scales=list(raw.get("scales") or [1.0, 3.0, 15.0]),
        patient_context=str(raw.get("patient_context", "")),
        ai_narrative=bool(raw.get("ai_narrative", True)),
    )


def _materialize(job: Dict) -> str:
    """Return a local path for the job's audio (downloads presigned URLs)."""
    if job.get("audio_b64"):
        data = base64.b64decode(job["audio_b64"])
    elif job.get("audio_url"):
        import urllib.request

        req = urllib.request.Request(job["audio_url"], headers={"User-Agent": "asculto-worker"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
    else:
        raise ValueError("job needs audio_b64 or audio_url")
    suffix = os.path.splitext(job.get("filename") or "clip.wav")[1] or ".wav"
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    return path


def run_job(job: Dict) -> Dict:
    path = _materialize(job)
    try:
        rep = report_mod.analyze_file(path, _options(job.get("options")))
        rep["filename"] = job.get("filename") or os.path.basename(path)
        rep["size_bytes"] = os.path.getsize(path)
        rep["disclaimer"] = DISCLAIMER
        return rep
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def _queue_mode() -> int:
    """Stage-2 pull consumer. Reads newline-delimited jobs from stdin or a
    queue URL in ASCULTO_QUEUE_URL, writes newline-delimited results to stdout.

    Wire to SQS/Kafka/Cloudflare Queues as needed; kept transport-agnostic so the
    same image works on GKE/DOKS.
    """
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            job = json.loads(line)
            print(json.dumps({"ok": True, "result": run_job(job)}), flush=True)
        except Exception as e:  # pragma: no cover - worker-facing
            print(json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"}), flush=True)
    return 0


if FastAPI is not None:
    app = FastAPI(title="Asculto inference worker", version="0.1.0")

    @app.get("/health")
    def health() -> JSONResponse:
        reg = get_registry()
        return JSONResponse({
            "status": "ok",
            "backend": os.environ.get("ASCULTO_BACKEND", "torch"),
            "loaded_heads": reg.available(),
            "errors": reg.errors,
        })

    @app.post("/run")
    def run(payload: Dict) -> JSONResponse:
        return JSONResponse(run_job(payload))

    @app.post("/batch")
    def batch(payload: Dict) -> JSONResponse:
        jobs: List[Dict] = payload.get("jobs") or []
        out = []
        for job in jobs:
            try:
                out.append(run_job(job))
            except Exception as e:  # pragma: no cover - worker-facing
                out.append({"error": f"{type(e).__name__}: {e}", "filename": job.get("filename")})
        return JSONResponse({"count": len(out), "results": out})


def main(argv=None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="Asculto inference worker")
    p.add_argument("--queue", action="store_true", help="pull-consumer mode (stdin -> stdout)")
    args = p.parse_args(argv)
    if args.queue:
        return _queue_mode()
    print("Use `uvicorn deploy.inference_worker:app` to serve HTTP, or --queue.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

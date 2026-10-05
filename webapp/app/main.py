"""CardiaSense web app: Inference-as-a-Service + Educational Interactive.

Run:  uvicorn webapp.app.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import base64
import os
import sys
import tempfile
from typing import List, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

HERE = os.path.dirname(os.path.abspath(__file__))
WEBAPP = os.path.dirname(HERE)

from . import game  # noqa: E402
from . import inference, report  # noqa: E402
from .config import DISCLAIMER  # noqa: E402

app = FastAPI(title="CardiaSense — Inference as a Service", version="0.1.0")
app.mount("/static", StaticFiles(directory=os.path.join(WEBAPP, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(WEBAPP, "templates"))


@app.on_event("startup")
def _startup() -> None:
    inference.get_registry()  # warm-load checkpoint ensembles


def _opts(heads: List[str], explanation: str, figures: str, disclaimer: bool, audio: bool,
          temporal: bool = False, window_s: float = 3.0, hop_s: float = 0.5,
          temporal_mode: str = "single", scales: str = "1,3,15") -> report.ReportOptions:
    valid = [h for h in heads if h in report.DEFAULT_HEADS] or list(report.DEFAULT_HEADS)
    try:
        scale_list = [max(0.5, min(float(s), 60.0)) for s in str(scales).split(",") if s.strip()]
    except ValueError:
        scale_list = [1.0, 3.0, 15.0]
    if not scale_list:
        scale_list = [1.0, 3.0, 15.0]
    return report.ReportOptions(
        heads=valid,
        explanation=explanation if explanation in ("brief", "standard", "detailed") else "standard",
        figures=figures if figures in ("none", "key", "all") else "all",
        include_disclaimer=disclaimer,
        audio_playback=audio,
        temporal=temporal,
        window_s=max(0.5, min(float(window_s or 3.0), 10.0)),
        hop_s=max(0.1, min(float(hop_s or 0.5), 5.0)),
        temporal_mode=temporal_mode if temporal_mode in ("single", "multiscale") else "single",
        scales=scale_list,
    )


def _save_upload(upload: UploadFile) -> str:
    suffix = os.path.splitext(upload.filename or "clip.wav")[1] or ".wav"
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(upload.file.read())
    return path


def _audio_data_uri(path: str) -> Optional[str]:
    try:
        with open(path, "rb") as f:
            data = f.read()
        mime = "audio/wav" if path.lower().endswith(".wav") else "audio/octet-stream"
        return f"data:{mime};base64," + base64.b64encode(data).decode()
    except OSError:
        return None


@app.get("/health")
def health() -> JSONResponse:
    reg = inference.get_registry()
    return JSONResponse({
        "status": "ok",
        "device": str(reg.device),
        "loaded_heads": reg.available(),
        "errors": reg.errors,
        "data_dir": os.path.basename(inference.config.DATA_DIR),
    })


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    reg = inference.get_registry()
    return templates.TemplateResponse(request, "index.html", {
        "heads": [h for h in inference.config.model_registry()],
        "loaded": reg.available(),
        "errors": reg.errors,
        "disclaimer": DISCLAIMER,
        "domains": game.DOMAINS,
    })


@app.post("/analyze", response_class=HTMLResponse)
async def analyze(
    request: Request,
    files: List[UploadFile] = File(...),
    heads: List[str] = Form(default=[]),
    explanation: str = Form("standard"),
    figures: str = Form("all"),
    include_disclaimer: bool = Form(True),
    audio_playback: bool = Form(True),
    temporal: bool = Form(False),
    window_s: float = Form(3.0),
    hop_s: float = Form(0.5),
    temporal_mode: str = Form("single"),
    scales: str = Form("1,3,15"),
):
    opts = _opts(heads, explanation, figures, include_disclaimer, audio_playback, temporal, window_s, hop_s,
                 temporal_mode, scales)
    results = []
    for up in files:
        path = _save_upload(up)
        try:
            rep = report.analyze_file(path, opts)
            rep["audio_uri"] = _audio_data_uri(path) if audio_playback and len(files) == 1 else None
            rep["size_bytes"] = os.path.getsize(path)
            results.append(rep)
        except Exception as e:  # pragma: no cover - user-facing error
            results.append({"filename": up.filename, "error": f"{type(e).__name__}: {e}"})
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    if len(results) == 1:
        return templates.TemplateResponse(request, "report.html", {
            "report": results[0], "disclaimer": DISCLAIMER,
        })
    rows = [report.batch_row(r) for r in results if "error" not in r]
    errors = [r for r in results if "error" in r]
    return templates.TemplateResponse(request, "batch.html", {
        "rows": rows, "errors": errors, "n": len(results),
        "disclaimer": DISCLAIMER,
    })


@app.post("/api/analyze")
async def api_analyze(
    files: List[UploadFile] = File(...),
    heads: str = Form(""),
    explanation: str = Form("standard"),
    figures: str = Form("all"),
    temporal: bool = Form(False),
    window_s: float = Form(3.0),
    hop_s: float = Form(0.5),
    temporal_mode: str = Form("single"),
    scales: str = Form("1,3,15"),
):
    """Programmatic Inference-as-a-Service endpoint (JSON)."""
    opts = _opts([h for h in heads.split(",") if h], explanation, figures, True, False,
                 temporal, window_s, hop_s, temporal_mode, scales)
    out = []
    for up in files:
        path = _save_upload(up)
        try:
            rep = report.analyze_file(path, opts)
            out.append(rep)
        except Exception as e:
            out.append({"filename": up.filename, "error": f"{type(e).__name__}: {e}"})
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
    return JSONResponse({"count": len(out), "results": out})


@app.get("/game", response_class=HTMLResponse)
def game_page(request: Request):
    return templates.TemplateResponse(request, "game.html", {
        "domains": game.DOMAINS, "disclaimer": DISCLAIMER,
    })


@app.get("/api/game/round")
def game_round(domain: str = "heart_types") -> JSONResponse:
    try:
        return JSONResponse(game.new_round(domain))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/game/answer")
async def game_answer(payload: dict) -> JSONResponse:
    rid = payload.get("round_id")
    answer = payload.get("answer")
    if not rid or answer is None:
        raise HTTPException(status_code=400, detail="round_id and answer are required")
    return JSONResponse(game.grade(rid, answer))


@app.get("/game/audio/{sample_id}")
def game_audio(sample_id: str, task: str = "heart", scheme: str = "10class"):
    path = game.resolve_audio_path(sample_id, task, scheme)
    if not path:
        raise HTTPException(status_code=404, detail="clip not found")
    return FileResponse(path, media_type="audio/wav")


@app.get("/demo/report", response_class=HTMLResponse)
def demo_report(request: Request, sample_id: str = "", task: str = "sound", scheme: str = "binary",
                heads: str = "", temporal_mode: str = "multiscale", explanation: str = "detailed",
                figures: str = "all"):
    """Render a full report for a built-in dataset clip (shareable + screenshot-friendly)."""
    if not sample_id:
        manifest = game._manifest(task, scheme)
        sample_id = str(manifest.iloc[0]["sample_id"])
    path = game.resolve_audio_path(sample_id, task, scheme)
    if not path:
        raise HTTPException(status_code=404, detail=f"sample {sample_id} not found for {task}/{scheme}")
    opts = _opts([h for h in heads.split(",") if h] or list(report.DEFAULT_HEADS),
                 explanation, figures, True, True, True, 3.0, 0.5, temporal_mode, "1,3,15")
    rep = report.analyze_file(path, opts)
    rep["audio_uri"] = _audio_data_uri(path)
    rep["demo"] = {"sample_id": sample_id, "task": task, "scheme": scheme}
    return templates.TemplateResponse(request, "report.html", {"report": rep, "disclaimer": DISCLAIMER})


@app.get("/demo/batch", response_class=HTMLResponse)
def demo_batch(request: Request, n: int = 4):
    """Render a batch table over a few built-in dataset clips."""
    opts = _opts(list(report.DEFAULT_HEADS), "standard", "all", True, False, False)
    picks = [("sound", "binary"), ("heart", "binary"), ("lung", "binary"), ("heart", "10class"), ("lung", "6class")]
    results = []
    for task, scheme in picks[: max(1, min(n, len(picks)))]:
        manifest = game._manifest(task, scheme)
        sid = str(manifest.iloc[0]["sample_id"])
        path = game.resolve_audio_path(sid, task, scheme)
        if path:
            results.append(report.analyze_file(path, opts))
    rows = [report.batch_row(r) for r in results]
    return templates.TemplateResponse(request, "batch.html", {
        "rows": rows, "errors": [], "n": len(rows), "disclaimer": DISCLAIMER,
    })

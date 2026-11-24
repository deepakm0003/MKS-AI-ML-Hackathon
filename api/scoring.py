"""Upload & score: run the frozen model on the user's own CSV files.

    POST /score/uploads           multipart file (+ kind=history|request) -> upload id + what the file looks like
    POST /score/jobs              {history_upload?, request_upload?, cutoff?} -> job id (runs in the background)
    GET  /score/jobs/{id}         status and per-step progress
    GET  /score/jobs/{id}/result  the result payload (KPIs, charts, accuracy, data checks)
    GET  /score/jobs/{id}/files/{name}   CSV downloads (submission, detail, series, issues, rejected rows)
    GET  /score/templates/{kind}.csv     small sample files in the train.csv / test.csv formats

This is the only part of the API that accepts data. It never touches the frozen outputs: uploads
and results live under outputs/scoring/ (gitignored), and the model is only read.
"""
from __future__ import annotations

import json
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from celeris import scoring as sc
from celeris.config import RAW, ROOT

router = APIRouter(prefix="/score", tags=["upload & score"])
BASE = ROOT / "outputs" / "scoring"
UPLOADS, JOBS = BASE / "uploads", BASE / "jobs"
MAX_BYTES = 200 * 1024 * 1024
ID = re.compile(r"^[0-9a-f]{32}$")
FILES = {"submission.csv", "forecast_detail.csv", "series_summary.csv", "rejected_rows.csv", "dq_issue_log.csv",
         "anomaly_register.csv"}
STEPS = [("read", "Read and check the files"), ("clean", "Clean the sales history"),
         ("recover", "Recover true demand (stockouts, anomalies)"), ("features", "Build model features"),
         ("score", "Score with the frozen model + business rules"), ("evaluate", "Bands, revenue and accuracy")]

_pool = ThreadPoolExecutor(max_workers=1)      # one scoring run at a time: each uses all cores briefly
_jobs: dict[str, dict] = {}
_lock = threading.Lock()


def _check_id(i: str) -> str:
    if not ID.match(i or ""):
        raise HTTPException(404, "unknown id")
    return i


@router.post("/uploads")
async def upload(file: UploadFile = File(...), kind: str = Form("auto")):
    """Store one CSV and report what it looks like (format, rows, months, series, missing columns)."""
    if kind not in ("auto", "history", "request"):
        raise HTTPException(400, "kind must be history, request or auto")
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, f"file is larger than {MAX_BYTES // 2**20} MB")
    if not data.strip():
        raise HTTPException(400, "the file is empty")
    uid = uuid.uuid4().hex
    UPLOADS.mkdir(parents=True, exist_ok=True)
    path = UPLOADS / f"{uid}.csv"
    path.write_bytes(data)
    try:
        info = sc.inspect(sc.read_csv(path))
    except sc.ScoringError as e:
        path.unlink(missing_ok=True)
        raise HTTPException(400, str(e)) from e
    kind = info["detected_kind"] if kind == "auto" else kind
    need = info["missing_history_columns"] if kind == "history" else info["missing_request_columns"]
    meta = {"upload_id": uid, "filename": file.filename, "bytes": len(data), "kind": kind, **info,
            "ok": not need, "problem": f"missing required columns: {', '.join(need)}" if need else None}
    (UPLOADS / f"{uid}.json").write_text(json.dumps(meta, default=str), encoding="utf-8")
    return meta


class JobRequest(BaseModel):
    history_upload: str | None = None
    request_upload: str | None = None
    cutoff: str | None = None


def _load_upload(uid: str | None, kind: str):
    if not uid:
        return None
    _check_id(uid)
    p = UPLOADS / f"{uid}.csv"
    if not p.exists():
        raise HTTPException(404, f"{kind} upload not found - upload it again")
    return sc.read_csv(p)


def _run(job_id: str, req: JobRequest) -> None:
    job = _jobs[job_id]
    t_step = {"t": time.time()}

    def progress(step: str, state: str) -> None:
        with _lock:
            s = next(x for x in job["steps"] if x["id"] == step)
            if state == "running":
                t_step["t"] = time.time()
            s["state"] = state
            if state == "done":
                s["seconds"] = round(time.time() - t_step["t"], 1)

    try:
        job["status"] = "running"
        progress("read", "running")
        hist = _load_upload(req.history_upload, "history")
        rows = _load_upload(req.request_upload, "rows-to-forecast")
        progress("read", "done")
        out = sc.score(hist, rows, req.cutoff or None, progress=progress)
        d = JOBS / job_id
        d.mkdir(parents=True, exist_ok=True)
        for name, df in out["tables"].items():
            df.to_csv(d / name, index=False)
        (d / "result.json").write_text(json.dumps(out["result"], default=str), encoding="utf-8")
        job["status"], job["seconds"] = "done", out["result"]["seconds"]
    except sc.ScoringError as e:
        job["status"], job["error"] = "error", str(e)
    except HTTPException as e:
        job["status"], job["error"] = "error", str(e.detail)
    except Exception as e:  # noqa: BLE001 - report, never crash the worker
        job["status"], job["error"] = "error", f"scoring failed: {type(e).__name__}: {e}"
    finally:
        for s in job["steps"]:
            if s["state"] == "running":
                s["state"] = "failed" if job["status"] == "error" else "done"


@router.post("/jobs")
def start_job(req: JobRequest):
    """Start scoring in the background; poll GET /score/jobs/{id}."""
    for uid, kind in [(req.history_upload, "history"), (req.request_upload, "request")]:
        if uid:
            _check_id(uid)
            if not (UPLOADS / f"{uid}.csv").exists():
                raise HTTPException(404, f"{kind} upload not found - upload it again")
    if req.cutoff and not re.match(r"^\d{4}-\d{2}$", req.cutoff):
        raise HTTPException(400, "cutoff must look like 2026-10")
    job_id = uuid.uuid4().hex
    _jobs[job_id] = {"job_id": job_id, "status": "queued", "error": None, "created": time.time(),
                     "request": req.model_dump(),
                     "steps": [{"id": i, "label": label, "state": "pending", "seconds": None} for i, label in STEPS]}
    _pool.submit(_run, job_id, req)
    return _jobs[job_id]


@router.get("/jobs/{job_id}")
def job_status(job_id: str):
    _check_id(job_id)
    if job_id in _jobs:
        return _jobs[job_id]
    if (JOBS / job_id / "result.json").exists():          # finished before an API restart
        return {"job_id": job_id, "status": "done", "error": None, "steps": []}
    raise HTTPException(404, "unknown job")


@router.get("/jobs/{job_id}/result")
def job_result(job_id: str):
    _check_id(job_id)
    p = JOBS / job_id / "result.json"
    if not p.exists():
        job = _jobs.get(job_id)
        raise HTTPException(409 if job and job["status"] in ("queued", "running") else 404,
                            "the job has not finished" if job else "unknown job")
    return json.loads(p.read_text(encoding="utf-8"))


@router.get("/jobs/{job_id}/files/{name}")
def job_file(job_id: str, name: str):
    _check_id(job_id)
    if name not in FILES:
        raise HTTPException(404, "unknown file")
    p = JOBS / job_id / name
    if not p.exists():
        raise HTTPException(404, "this run produced no such file")
    return FileResponse(p, media_type="text/csv", filename=name)


@router.get("/templates/{name}")
def template(name: str):
    """Small samples of the two formats, cut from the official raw files (header + a few series)."""
    import pandas as pd
    if name not in ("train_format_sample.csv", "test_format_sample.csv"):
        raise HTTPException(404, "unknown template")
    src = RAW / ("train.csv" if name.startswith("train") else "test.csv")
    df = pd.read_csv(src, dtype=str, nrows=200_000)
    keep = df[["SKU_ID", "Region"]].drop_duplicates().head(3)
    sample = df.merge(keep, on=["SKU_ID", "Region"]).head(120)
    return Response(sample.to_csv(index=False), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


def job_dir(job_id: str) -> Path:
    return JOBS / _check_id(job_id)

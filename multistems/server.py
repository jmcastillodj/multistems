from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .catalog import FAMILIES, get_model, load_catalog
from .jobs import JobManager

app = FastAPI(title="MultiStems")
jobs = JobManager()
STATIC = Path(__file__).parent / "static"


def _public(job: dict) -> dict:
    return {k: v for k, v in job.items() if k != "options" or True}


@app.get("/api/models")
def models():
    return {"families": FAMILIES, "models": load_catalog()}


@app.get("/api/jobs")
def list_jobs():
    return [_public(j) for j in jobs.list()]


@app.get("/api/jobs/{jid}")
def get_job(jid: str):
    j = jobs.get(jid)
    if not j:
        raise HTTPException(404, "Job no encontrado")
    return _public(j)


@app.post("/api/jobs")
async def create_job(file: UploadFile = File(...), model: str = Form(...), format: str = Form("wav"),
                     shifts: int = Form(1), overlap: float = Form(0.25), two_stems: str = Form(""),
                     single_stem: str = Form(""), denoise: bool = Form(False), tta: bool = Form(False)):
    try:
        get_model(model)
    except KeyError:
        raise HTTPException(400, f"Modelo desconocido: {model}")
    if format.lower() not in ("wav", "flac", "mp3"):
        raise HTTPException(400, "Formato no soportado")
    data = await file.read()
    opts = {"format": format.lower(), "shifts": shifts, "overlap": overlap, "two_stems": two_stems or None,
            "single_stem": single_stem or None, "denoise": denoise, "tta": tta}
    job = jobs.create(file.filename or "audio", lambda p: p.write_bytes(data), model, opts)
    return _public(job)


@app.delete("/api/jobs/{jid}")
def delete_job(jid: str):
    if not jobs.get(jid):
        raise HTTPException(404)
    jobs.delete(jid)
    return {"ok": True}


@app.post("/api/jobs/{jid}/cancel")
def cancel_job(jid: str):
    if not jobs.get(jid):
        raise HTTPException(404)
    jobs.cancel(jid)
    return {"ok": True}


@app.get("/api/jobs/{jid}/files/{stem}")
def get_file(jid: str, stem: str, download: bool = False):
    j = jobs.get(jid)
    if not j or stem not in j["files"]:
        raise HTTPException(404)
    p = jobs._path(jid) / j["files"][stem]
    return FileResponse(p, filename=p.name if download else None)


@app.get("/api/jobs/{jid}/zip")
def get_zip(jid: str):
    j = jobs.get(jid)
    if not j or j["status"] != "done":
        raise HTTPException(404)
    return FileResponse(jobs.zip_path(jid), filename=f"{Path(j['filename']).stem}_stems.zip")


app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")

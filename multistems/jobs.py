"""Cola de trabajos (un worker: los modelos saturan CPU/GPU) con estado persistente en disco."""
from __future__ import annotations

import json
import os
import queue
import shutil
import threading
import time
import traceback
import uuid
import zipfile
from pathlib import Path

from .engines import Cancelled, Ctx, separate

DATA_DIR = Path(os.environ.get("MULTISTEMS_DATA", Path(__file__).resolve().parent.parent / "data"))
JOBS_DIR = DATA_DIR / "jobs"


class JobManager:
    def __init__(self):
        JOBS_DIR.mkdir(parents=True, exist_ok=True)
        self.jobs: dict[str, dict] = {}
        self.ctxs: dict[str, Ctx] = {}
        self.q: queue.Queue[str] = queue.Queue()
        self.lock = threading.Lock()
        self._load()
        threading.Thread(target=self._worker, daemon=True).start()

    # -- persistencia
    def _path(self, jid: str) -> Path:
        return JOBS_DIR / jid

    def _save(self, job: dict):
        (self._path(job["id"]) / "job.json").write_text(json.dumps(job, ensure_ascii=False, indent=1))

    def _load(self):
        for f in JOBS_DIR.glob("*/job.json"):
            try:
                job = json.loads(f.read_text())
            except Exception:
                continue
            if job["status"] in ("queued", "running"):
                job["status"], job["error"] = "error", "Interrumpido por reinicio del servidor"
            self.jobs[job["id"]] = job

    # -- API
    def create(self, filename: str, data_writer, model_id: str, opts: dict) -> dict:
        jid = uuid.uuid4().hex[:10]
        d = self._path(jid)
        (d / "input").mkdir(parents=True)
        safe = "".join(c if c.isalnum() or c in "._- " else "_" for c in filename) or "audio"
        src = d / "input" / safe
        data_writer(src)
        job = {"id": jid, "filename": safe, "model": model_id, "options": opts, "status": "queued",
               "progress": 0.0, "message": "En cola", "error": None, "files": {}, "log": [],
               "created": time.time()}
        with self.lock:
            self.jobs[jid] = job
            self._save(job)
        self.q.put(jid)
        return job

    def get(self, jid: str) -> dict | None:
        return self.jobs.get(jid)

    def list(self) -> list[dict]:
        return sorted(self.jobs.values(), key=lambda j: -j["created"])

    def cancel(self, jid: str):
        job = self.jobs[jid]
        if job["status"] == "queued":
            job["status"], job["message"] = "cancelled", "Cancelado"
            self._save(job)
        elif job["status"] == "running" and jid in self.ctxs:
            self.ctxs[jid].cancel()

    def delete(self, jid: str):
        self.cancel(jid)
        self.jobs.pop(jid, None)
        shutil.rmtree(self._path(jid), ignore_errors=True)

    def zip_path(self, jid: str) -> Path:
        job = self.jobs[jid]
        zp = self._path(jid) / f"{Path(job['filename']).stem}_stems.zip"
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_STORED) as z:
            for stem, rel in job["files"].items():
                z.write(self._path(jid) / rel, arcname=Path(rel).name)
        return zp

    # -- worker
    def _worker(self):
        while True:
            jid = self.q.get()
            job = self.jobs.get(jid)
            if not job or job["status"] != "queued":
                continue
            ctx = self.ctxs[jid] = Ctx()
            job["status"], job["message"] = "running", "Iniciando (la primera vez descarga el modelo)…"
            self._save(job)

            def progress(f, msg, job=job):
                job["progress"], job["message"] = round(f, 3), msg

            def log(line, job=job):
                job["log"] = (job["log"] + [line])[-80:]

            try:
                d = self._path(jid)
                res = separate(job["model"], d / "input" / job["filename"], d / "work", job["options"], ctx,
                               progress, log)
                out = d / "output"
                out.mkdir(exist_ok=True)
                stem_name = Path(job["filename"]).stem
                files = {}
                for stem, p in res.items():
                    dest = out / f"{stem_name}_{stem}{p.suffix}"
                    shutil.copy2(p, dest)
                    files[stem] = str(dest.relative_to(d))
                shutil.rmtree(d / "work", ignore_errors=True)
                if not files:
                    raise RuntimeError("El modelo no generó archivos.")
                job.update(status="done", progress=1.0, message="Listo", files=files)
            except Cancelled:
                job.update(status="cancelled", message="Cancelado")
            except Exception as e:
                job.update(status="error", error=str(e), message="Error")
                job["log"] = (job["log"] + traceback.format_exc().splitlines())[-80:]
            finally:
                self._save(job)
                self.ctxs.pop(jid, None)

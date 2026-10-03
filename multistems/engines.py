"""Ejecuta modelos como subprocesos (cancelables, con progreso) y devuelve {stem: ruta}."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

from .catalog import PIPELINES, get_model

AUDIO_EXT = {".wav", ".flac", ".mp3", ".ogg", ".m4a"}
MODELS_DIR = Path(os.environ.get("MULTISTEMS_MODELS", Path(__file__).resolve().parent.parent / "models"))
_PCT = re.compile(r"(\d{1,3})%\|")

def _launcher(target: str) -> list[str]:
    """Comando para ejecutar un módulo/función en un subproceso, también dentro de la .app congelada
    (donde sys.executable es el propio binario de la app, no un intérprete de Python)."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "_run", target]
    return [sys.executable, "-m", "multistems", "_run", target]


Progress = Callable[[float, str], None]


class Cancelled(Exception):
    pass


class Ctx:
    """Estado compartido de un job: proceso activo y flag de cancelación."""

    def __init__(self):
        self.proc: subprocess.Popen | None = None
        self.cancelled = False

    def cancel(self):
        self.cancelled = True
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()


def _run(cmd: list[str], ctx: Ctx, on_pct: Callable[[float], None], log: Callable[[str], None]):
    log("$ " + " ".join(cmd))
    ctx.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                bufsize=1, universal_newlines=True)
    buf = ""
    while True:
        ch = ctx.proc.stdout.read(1)
        if not ch:
            break
        if ch in "\r\n":
            line, buf = buf.strip(), ""
            if line:
                m = _PCT.search(line)
                if m:
                    on_pct(min(int(m.group(1)), 100) / 100)
                else:
                    log(line)
        else:
            buf += ch
    rc = ctx.proc.wait()
    if ctx.cancelled:
        raise Cancelled()
    if rc != 0:
        raise RuntimeError(f"El comando falló (código {rc}). Mira el log del job.")


def _stem_from_name(path: Path) -> str:
    m = re.search(r"_\(([^)]+)\)", path.name)
    return (m.group(1) if m else path.stem).strip().lower().replace(" ", "_")


def _collect(directory: Path, demucs: bool = False) -> dict[str, Path]:
    out = {}
    for p in sorted(directory.rglob("*")):
        if p.suffix.lower() in AUDIO_EXT:
            out[p.stem.lower() if demucs else _stem_from_name(p)] = p
    return out


def _device_flag() -> str:
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


def _separate_demucs(model: dict, src: Path, out: Path, o: dict, ctx: Ctx, on_pct, log) -> dict[str, Path]:
    cmd = _launcher("demucs.separate") + ["-n", model["filename"], "-o", str(out),
           "--shifts", str(o.get("shifts", 1)), "--overlap", str(o.get("overlap", 0.25)),
           "-d", _device_flag(), "-j", "0"]
    fmt = o.get("format", "wav").lower()
    if fmt == "mp3":
        cmd += ["--mp3", "--mp3-bitrate", str(o.get("bitrate", 320))]
    elif fmt == "flac":
        cmd += ["--flac"]
    if o.get("two_stems"):
        cmd += ["--two-stems", o["two_stems"]]
    cmd.append(str(src))
    _run(cmd, ctx, on_pct, log)
    return _collect(out / model["filename"], demucs=True)


def _separate_asep(model: dict, src: Path, out: Path, o: dict, ctx: Ctx, on_pct, log) -> dict[str, Path]:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    cmd = _launcher("audio_separator.utils.cli:main") + [str(src), "--output_dir", str(out), "--output_format", o.get("format", "wav").upper(),
           "--model_file_dir", str(MODELS_DIR), "--log_level", "info"]
    if model["kind"] == "ensemble":
        cmd += ["--ensemble_preset", model["filename"]]
    else:
        cmd += ["-m", model["filename"]]
    arch = model["arch"]
    if o.get("single_stem"):
        cmd += ["--single_stem", o["single_stem"]]
    if o.get("overlap") is not None and arch in ("MDXC",):
        cmd += ["--mdxc_overlap", str(int(max(2, min(50, o["overlap"])))) ]
    if arch == "MDX" and o.get("denoise"):
        cmd += ["--mdx_enable_denoise"]
    if arch == "VR" and o.get("tta"):
        cmd += ["--vr_enable_tta"]
    _run(cmd, ctx, on_pct, log)
    return _collect(out)


def separate(model_id: str, src: Path, out: Path, opts: dict, ctx: Ctx, progress: Progress,
             log: Callable[[str], None]) -> dict[str, Path]:
    """Devuelve {stem: ruta} para un modelo, ensemble o pipeline."""
    model = get_model(model_id)
    out.mkdir(parents=True, exist_ok=True)
    if model["kind"] == "pipeline":
        steps = PIPELINES[model_id]["steps"]
        stems: dict[str, Path] = {}
        for i, step in enumerate(steps):
            base, span = i / len(steps), 1 / len(steps)
            inp = src if step["input"] == "mix" else stems.get(step["input"])
            if inp is None:
                raise RuntimeError(f"El paso {i + 1} necesita el stem '{step['input']}', que el paso anterior no produjo.")
            sub = out / f"step{i + 1}"
            res = separate(step["model"], inp, sub, {**opts, "single_stem": None, "two_stems": None}, ctx,
                           lambda f, m, b=base, s=span: progress(b + f * s, f"[{i + 1}/{len(steps)}] {m}"), log)
            for k, v in res.items():
                stems.setdefault(k, v)
        return stems

    label = model["name"]
    on_pct = lambda f: progress(f, label)
    sub = out / "raw"
    shutil.rmtree(sub, ignore_errors=True)
    if model["engine"] == "demucs":
        return _separate_demucs(model, src, sub, opts, ctx, on_pct, log)
    return _separate_asep(model, src, sub, opts, ctx, on_pct, log)

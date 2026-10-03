"""Catálogo de modelos: Demucs nativo + todo el catálogo de audio-separator,
agrupado en las mismas familias que muestra MVSep (https://mvsep.com/es/algorithms)."""
from __future__ import annotations

import functools
import re

# ---- Demucs oficial (facebookresearch/demucs) -------------------------------------------
DEMUCS = [
    # id, nombre, stems, nota
    ("htdemucs_ft", "Demucs4 HT fine-tuned (htdemucs_ft)", ["vocals", "drums", "bass", "other"],
     "Mejor calidad de la familia HT, 4x más lento."),
    ("htdemucs", "Demucs4 HT (htdemucs)", ["vocals", "drums", "bass", "other"], "Rápido, buena calidad."),
    ("htdemucs_6s", "Demucs4 HT 6 stems (htdemucs_6s)",
     ["vocals", "drums", "bass", "guitar", "piano", "other"], "Añade guitarra y piano (piano flojo)."),
    ("hdemucs_mmi", "Demucs3 Hybrid MMI (hdemucs_mmi)", ["vocals", "drums", "bass", "other"], ""),
    ("mdx_extra", "Demucs3 MDX Extra (mdx_extra)", ["vocals", "drums", "bass", "other"],
     "Ganador MDX 2021 con datos extra."),
    ("mdx_extra_q", "Demucs3 MDX Extra cuantizado (mdx_extra_q)", ["vocals", "drums", "bass", "other"], "Más ligero."),
    ("mdx", "Demucs3 MDX (mdx)", ["vocals", "drums", "bass", "other"], ""),
    ("mdx_q", "Demucs3 MDX cuantizado (mdx_q)", ["vocals", "drums", "bass", "other"], ""),
]

# ---- Familias (orden = orden de aparición en la UI) --------------------------------------
FAMILIES = [
    "Ensembles y pipelines",
    "Demucs4 HT / Demucs",
    "BS Roformer SW (6 stems)",
    "BS Roformer",
    "MelBand Roformer",
    "MDX23C",
    "MDX-Net (MDX B)",
    "UVR VR",
    "Karaoke (lead/back)",
    "DrumSep",
    "De-reverb / De-echo / Denoise",
    "Crowd / Male-Female / Otros",
]

_RULES = [  # (regex sobre filename+nombre, familia) – primero que coincide gana
    (r"BS-Roformer-SW", "BS Roformer SW (6 stems)"),
    (r"drumsep", "DrumSep"),
    (r"karao|kara_|kara\.|karokee|HP-Karaoke|BVE", "Karaoke (lead/back)"),
    (r"dereverb|deverb|de-reverb|de-echo|deecho|reverb|denoise|debleed|bleed", "De-reverb / De-echo / Denoise"),
    (r"crowd|male|chorus|female|aspiration|Wind", "Crowd / Male-Female / Otros"),
    (r"^htdemucs|^hdemucs|demucs", "Demucs4 HT / Demucs"),
    (r"bs[_-]roformer|BS-Roformer", "BS Roformer"),
    (r"roformer", "MelBand Roformer"),
    (r"^MDX23C|MDX23C", "MDX23C"),
    (r"\.onnx\b", "MDX-Net (MDX B)"),
    (r"\.pth\b", "UVR VR"),
]


def _family(filename: str, name: str) -> str:
    text = f"{filename} {name}"
    for rx, fam in _RULES:
        if re.search(rx, text, re.I):
            return fam
    return "Crowd / Male-Female / Otros"


def _best_sdr(scores: dict) -> float | None:
    vals = [v.get("SDR") for v in (scores or {}).values() if isinstance(v, dict) and v.get("SDR")]
    return round(max(vals), 2) if vals else None


# ---- Pipelines / ensembles (estilo "Ensemble" y "All-In" de MVSep) ------------------------
# Cada paso: model = id del catálogo, input = "mix" | nombre de stem de un paso anterior
PIPELINES = {
    "pipe:all_in_lite": {
        "name": "All-In Lite: vocals, bass, drums (kick/snare/toms/hh/ride/crash), guitar, piano, other",
        "note": "BS-Roformer-SW (6 stems) y después DrumSep (MDX23C) sobre la batería. Versión local del 'Ensemble All-In' de MVSep.",
        "stems": ["vocals", "bass", "drums", "guitar", "piano", "other", "kick", "snare", "toms", "hh", "ride", "crash"],
        "steps": [{"model": "asep:BS-Roformer-SW.ckpt", "input": "mix"},
                  {"model": "asep:MDX23C-DrumSep-aufr33-jarredou.ckpt", "input": "drums"}],
    },
    "pipe:vocal_lead_back": {
        "name": "Voz principal / coros (extrae voz y luego Karaoke)",
        "note": "MelBand Roformer vocals → Karaoke Roformer sobre la voz: lead + back vocals.",
        "stems": ["vocals", "instrumental", "lead", "back"],
        "steps": [{"model": "asep:mel_band_roformer_vocals_becruily.ckpt", "input": "mix"},
                  {"model": "asep:mel_band_roformer_karaoke_gabox_v2.ckpt", "input": "vocals"}],
    },
    "pipe:demucs_ft_plus_vocals": {
        "name": "4 stems con voz de Roformer + Demucs HT FT",
        "note": "Voz/instrumental con BS-Roformer y bass/drums/other con htdemucs_ft sobre el instrumental.",
        "stems": ["vocals", "bass", "drums", "other"],
        "steps": [{"model": "asep:model_bs_roformer_ep_317_sdr_12.9755.ckpt", "input": "mix"},
                  {"model": "demucs:htdemucs_ft", "input": "instrumental"}],
    },
}

# Presets de ensemble de audio-separator (varios modelos mezclados con un algoritmo)
ENSEMBLE_NOTES = {
    "instrumental_clean": "Instrumental más limpio (mínimo bleed de voz)",
    "instrumental_full": "Instrumental más completo",
    "instrumental_balanced": "Instrumental equilibrado",
    "instrumental_low_resource": "Instrumental, bajo consumo",
    "vocal_balanced": "Voz equilibrada",
    "vocal_clean": "Voz limpia (sin bleed)",
    "vocal_full": "Voz completa (fullness)",
    "vocal_rvc": "Voz para entrenar RVC",
    "karaoke": "Karaoke: voz principal vs resto",
}


@functools.lru_cache(maxsize=1)
def load_catalog() -> list[dict]:
    items: list[dict] = []
    for mid, name, stems, note in DEMUCS:
        items.append({"id": f"demucs:{mid}", "engine": "demucs", "arch": "Demucs", "name": name,
                      "family": "Demucs4 HT / Demucs", "stems": stems, "sdr": None, "filename": mid,
                      "note": note, "kind": "model"})

    try:
        from audio_separator.separator import Separator
        listing = Separator(info_only=True, log_level=40).list_supported_model_files()
    except Exception as e:  # sin audio-separator instalado → solo Demucs
        listing = {}
        print(f"[catalog] audio-separator no disponible: {e}")

    seen = set()
    for arch, models in listing.items():
        for name, info in models.items():
            fn = info["filename"]
            if fn.endswith(".yaml") and fn.startswith(("htdemucs", "hdemucs")):
                continue  # Demucs lo cubrimos con el motor nativo
            if fn in seen:
                continue
            seen.add(fn)
            short = name.split(": ", 1)[-1].replace(" | ", " – ")
            stems = [s for s in info.get("stems", []) if s]
            fam = _family(fn, short)
            items.append({"id": f"asep:{fn}", "engine": "asep", "arch": arch, "name": short, "family": fam,
                          "stems": stems, "sdr": _best_sdr(info.get("scores")), "filename": fn,
                          "note": "", "kind": "model"})

    for pid, p in PIPELINES.items():
        items.append({"id": pid, "engine": "pipeline", "arch": "Pipeline", "name": p["name"],
                      "family": "Ensembles y pipelines", "stems": p["stems"], "sdr": None,
                      "filename": pid, "note": p["note"], "kind": "pipeline"})
    try:
        import json, os, audio_separator
        path = os.path.join(os.path.dirname(audio_separator.__file__), "ensemble_presets.json")
        for key, pr in json.load(open(path))["presets"].items():
            items.append({"id": f"ens:{key}", "engine": "ensemble", "arch": f"Ensemble ({pr['algorithm']})",
                          "name": f"Ensemble · {pr['name']}", "family": "Ensembles y pipelines",
                          "stems": ["vocals", "instrumental"] if not key.startswith("karaoke") else ["lead", "instrumental"],
                          "sdr": None, "filename": key,
                          "note": pr["description"] + " [" + " + ".join(m.split(".")[0] for m in pr["models"]) + "]",
                          "kind": "ensemble"})
    except Exception as e:
        print(f"[catalog] sin presets de ensemble: {e}")
    return items


def get_model(model_id: str) -> dict:
    for m in load_catalog():
        if m["id"] == model_id:
            return m
    raise KeyError(model_id)

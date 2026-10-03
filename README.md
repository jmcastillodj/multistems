# MultiStems

App local para extraer stems (voz, batería, bajo, guitarra, piano, instrumental, kick/snare…) con **~185 modelos open-source**:
Demucs (Facebook Research) + el catálogo de [python-audio-separator](https://github.com/nomadkaraoke/python-audio-separator)
(BS-Roformer, MelBand Roformer, MDX23C, MDX-Net/UVR, VR, DrumSep, Karaoke, De-reverb, Crowd, Male/Female…),
agrupados en las mismas familias que [MVSep](https://mvsep.com/es/algorithms).

## Instalación
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt      # GPU NVIDIA: cambia a audio-separator[gpu]
```
Necesitas `ffmpeg` en el PATH para mp3/flac. Los pesos se descargan solos la primera vez (carpeta `models/`).

## Uso
```bash
python -m multistems serve            # web en http://127.0.0.1:8000
python -m multistems list --family roformer
python -m multistems separate cancion.mp3 -m demucs:htdemucs_ft -o salida
python -m multistems separate cancion.mp3 -m asep:BS-Roformer-SW.ckpt     # 6 stems
python -m multistems separate cancion.mp3 -m pipe:all_in_lite             # 12 stems
```

## Qué incluye
- **Demucs nativo**: htdemucs, htdemucs_ft, htdemucs_6s, hdemucs_mmi, mdx(_extra)(_q), con `shifts`, `overlap`, `--two-stems`.
- **Roformer / MDX23C / MDX-Net / VR / DrumSep / Karaoke / De-reverb…** vía audio-separator, con SDR publicado cuando existe.
- **Pipelines** (versión local del "Ensemble All-In" de MVSep): `All-In Lite` (BS-Roformer-SW + DrumSep), `Voz lead/back`, `Roformer + Demucs HT FT`.
- **Ensembles** de varios modelos (presets de audio-separator: instrumental_clean, vocal_balanced, karaoke…).
- Web con búsqueda, filtro por familia, cola de trabajos, progreso, reproductor por stem y descarga en ZIP.

## Limitaciones conocidas
- Los modelos propios de MVSep (SCNet XL, BS PolarFormer, MVSep Choir/Piano/Keys/Organ/Synth/Rhodes, Medley Vox…) no tienen pesos
  públicos en las librerías usadas; no están incluidos. Del sitio de MVSep solo se revisó la página 1 de 3.
- Sin GPU, los Roformer grandes tardan varios minutos por canción.

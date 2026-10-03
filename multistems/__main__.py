import argparse
import sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(prog="multistems", description="Extractor de stems multi-modelo")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("serve", help="Lanza la web app")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    l = sub.add_parser("list", help="Lista los modelos")
    l.add_argument("--family")
    r = sub.add_parser("separate", help="Separa un archivo desde la terminal")
    r.add_argument("input")
    r.add_argument("-m", "--model", default="demucs:htdemucs")
    r.add_argument("-o", "--out", default="separated")
    r.add_argument("--format", default="wav")
    r.add_argument("--shifts", type=int, default=1)
    r.add_argument("--overlap", type=float, default=0.25)
    r.add_argument("--two-stems")
    a = ap.parse_args()

    if a.cmd == "list":
        from .catalog import load_catalog
        for m in load_catalog():
            if a.family and a.family.lower() not in m["family"].lower():
                continue
            sdr = f"SDR {m['sdr']}" if m["sdr"] else ""
            print(f"{m['id']:<70} {m['family']:<32} {','.join(m['stems']):<40} {sdr}")
    elif a.cmd == "separate":
        import shutil
        from .engines import Ctx, separate
        src, out = Path(a.input).resolve(), Path(a.out).resolve()
        res = separate(a.model, src, out / ".work", dict(format=a.format, shifts=a.shifts, overlap=a.overlap,
                       two_stems=a.two_stems), Ctx(), lambda f, m: print(f"\r{f:5.0%} {m}", end="", file=sys.stderr), print)
        for stem, p in res.items():
            dest = out / f"{src.stem}_{stem}{p.suffix}"
            shutil.copy2(p, dest)
            print(f"\n{dest}")
        shutil.rmtree(out / ".work", ignore_errors=True)
    else:
        import uvicorn
        host = getattr(a, "host", "127.0.0.1")
        port = getattr(a, "port", 8000)
        uvicorn.run("multistems.server:app", host=host, port=port)


main()

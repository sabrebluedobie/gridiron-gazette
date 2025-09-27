# scripts/flatten_pdf.py
import subprocess, shlex, tempfile, os
from pathlib import Path

def flatten_pdf(src: str, dst: str, dpi: int = 200) -> None:
    src_p = Path(src); dst_p = Path(dst)
    work = Path(tempfile.mkdtemp(prefix="flatten_"))
    try:
        # 1) PDF → PNG frames
        base = work / "page"
        cmd1 = f'pdftoppm -png -r {dpi} {shlex.quote(str(src_p))} {shlex.quote(str(base))}'
        subprocess.check_call(cmd1, shell=True)

        # 2) PNGs → single PDF
        pngs = sorted(str(p) for p in work.glob("page-*.png"))
        if not pngs:
            # Some poppler versions name files page-1.png, page-2.png...
            pngs = sorted(str(p) for p in work.glob("page*.png"))
        cmd2 = "img2pdf " + " ".join(shlex.quote(p) for p in pngs) + f" -o {shlex.quote(str(dst_p))}"
        subprocess.check_call(cmd2, shell=True)
    finally:
        # cleanup temp dir
        try:
            for p in work.glob("*"): p.unlink()
            work.rmdir()
        except Exception:
            pass

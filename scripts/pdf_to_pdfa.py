# scripts/pdf_to_pdfa.py
# Normalizes a PDF to PDF/A-2b via Ghostscript (requires gs installed)
import subprocess, shlex
from pathlib import Path

def pdf_to_pdfa(input_pdf: str, output_pdf: str) -> str:
    inp = Path(input_pdf).resolve()
    out = Path(output_pdf).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    # Use Ghostscript PDF/A-2b (no external color profile required for DeviceRGB)
    # PDFACompatibilityPolicy=1 -> fail on noncompliance instead of silently downgrading
    cmd = (
        "gs -dBATCH -dNOPAUSE -dNOOUTERSAVE "
        "-sDEVICE=pdfwrite "
        "-dPDFA=2 -dPDFACompatibilityPolicy=1 "
        "-dProcessColorModel=/DeviceRGB -dUseCIEColor "
        f"-sOutputFile={shlex.quote(str(out))} {shlex.quote(str(inp))}"
    )
    subprocess.run(cmd, shell=True, check=True)
    if not out.exists():
        raise FileNotFoundError(f"PDF/A not created: {out}")
    return str(out)

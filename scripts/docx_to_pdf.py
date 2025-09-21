# scripts/docx_to_pdf.py
# Converts DOCX -> PDF using LibreOffice headless (fast, robust in CI)
import subprocess, shlex
from pathlib import Path

def docx_to_pdf(docx_path: str, out_dir: str | None = None) -> str:
    docx = Path(docx_path).resolve()
    out_dir = Path(out_dir).resolve() if out_dir else docx.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    # Use soffice (LibreOffice) headless export
    cmd = (
        f'soffice --headless --nologo --nolockcheck '
        f'--convert-to pdf --outdir {shlex.quote(str(out_dir))} {shlex.quote(str(docx))}'
    )
    subprocess.run(cmd, shell=True, check=True)

    pdf_path = out_dir / (docx.stem + ".pdf")
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not created: {pdf_path}")
    return str(pdf_path)

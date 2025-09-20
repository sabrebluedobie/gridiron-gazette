# scripts/pdf_export.py
import subprocess, shlex, os
from pathlib import Path

def _soffice_bin() -> str:
    mac = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
    return mac if Path(mac).exists() else "soffice"

def docx_to_pdf_a(docx_path: str, out_dir: str) -> str:
    """
    Exports DOCX to PDF/A-1b with fonts embedded using LibreOffice headless.
    Returns the output PDF path.
    """
    docx = Path(docx_path); out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    export = (
        'pdf:writer_pdf_Export:'
        '{"SelectPdfVersion":{"type":"long","value":"1"},'
        '"UseTaggedPDF":{"type":"boolean","value":"true"},'
        '"EmbedStandardFonts":{"type":"boolean","value":"true"}}'
    )
    cmd = (
        f'{_soffice_bin()} --headless --convert-to {shlex.quote(export)} '
        f'--outdir {shlex.quote(str(out))} {shlex.quote(str(docx))}'
    )
    subprocess.check_call(cmd, shell=True)
    return str(out / (docx.stem + ".pdf"))

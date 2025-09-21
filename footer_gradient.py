# footer_gradient.py
# Adds a diagonal gradient strip to the footer using an inline image in a table.
# This avoids floating shapes that drift in DOCX/PDF.

from docx import Document
from docx.shared import Mm
from pathlib import Path

def add_footer_gradient(docx_path: str, gradient_png: str = "./logos/footer_gradient_diagonal.png",
                        bar_height_mm: float = 12.0) -> None:
    docx_path = str(docx_path)
    gradient_png = str(gradient_png)
    doc = Document(docx_path)

    for section in doc.sections:
        # Anchor layout so Word/PDF doesn’t "nudge" footer
        section.bottom_margin = Mm(15)       # ~0.59"
        section.footer_distance = Mm(8)      # ~0.31"
        section.different_first_page_header_footer = False

        footer = section.footer

        # Clear legacy paragraphs/shapes in footer to avoid conflicts
        for p in list(footer.paragraphs):
            p._element.getparent().remove(p._element)

        # Footer table (2 rows): gradient strip on top, text row below
        tbl = footer.add_table(rows=2, cols=1)
        tbl.autofit = True

        # Row 1: insert gradient strip as inline picture
        run = tbl.rows[0].cells[0].paragraphs[0].add_run()
        pic = run.add_picture(gradient_png)
        pic.height = Mm(bar_height_mm)  # width auto-scales

        # Row 2: reserved for your existing footer text (leave blank if managed by template)
        tbl.rows[1].cells[0].paragraphs[0].add_run("")

    doc.save(docx_path)

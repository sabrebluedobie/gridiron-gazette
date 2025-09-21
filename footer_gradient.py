# footer_gradient.py
from docx import Document
from docx.shared import Mm

def add_footer_gradient(docx_path: str, gradient_png: str, bar_height_mm: float = 12.0):
    doc = Document(docx_path)
    for section in doc.sections:
        section.bottom_margin = Mm(15)      # ~0.59"
        section.footer_distance = Mm(8)     # ~0.31"
        section.different_first_page_header_footer = False

        footer = section.footer

        # Clear old paragraphs in footer (we're moving to table-based footer)
        for p in list(footer.paragraphs):
            p._element.getparent().remove(p._element)

        # 2-row table: gradient strip + footer text
        tbl = footer.add_table(rows=2, cols=1)
        tbl.autofit = True

        # Row 1: gradient strip image
        run = tbl.rows[0].cells[0].paragraphs[0].add_run()
        pic = run.add_picture(gradient_png)
        pic.height = Mm(bar_height_mm)  # width will scale

        # Row 2: keep for your footer text (or leave blank)
        tbl.rows[1].cells[0].paragraphs[0].add_run("")
    doc.save(docx_path)

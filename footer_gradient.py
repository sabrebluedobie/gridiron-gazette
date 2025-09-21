# --- in build_gazette.py (or footer_gradient.py if you split it) ---
from docx import Document
from docx.shared import Mm

def add_footer_gradient(docx_path, gradient_png, bar_height_mm: float = 12.0) -> None:
    doc = Document(str(docx_path))

    for section in doc.sections:
        # Anchor layout so Word/PDF doesn’t nudge the footer
        section.bottom_margin = Mm(15)         # ~0.59"
        section.footer_distance = Mm(8)        # ~0.31"
        section.different_first_page_header_footer = False

        footer = section.footer

        # Clear legacy paragraphs/shapes
        for p in list(footer.paragraphs):
            p._element.getparent().remove(p._element)

        # Calculate content width (page width minus left/right margins)
        content_width = section.page_width - section.left_margin - section.right_margin

        # Some python-docx builds require width=... for add_table on headers/footers
        tbl = footer.add_table(rows=2, cols=1, width=content_width)
        tbl.autofit = False

        # Force the single column to the full content width
        tbl.columns[0].width = content_width
        for row in tbl.rows:
            row.cells[0].width = content_width

        # Row 1: gradient strip as inline picture
        cell = tbl.rows[0].cells[0]
        run = cell.paragraphs[0].add_run()
        try:
            pic = run.add_picture(str(gradient_png))
            # Keep a shallow bar height; width will naturally fill the cell
            pic.height = Mm(bar_height_mm)
        except Exception as e:
            # If the gradient is missing, just leave a blank row
            print(f"[footer] Could not add gradient image: {e}")

        # Row 2: reserved for footer text (or leave blank for template text)
        tbl.rows[1].cells[0].paragraphs[0].add_run("")

    doc.save(str(docx_path))

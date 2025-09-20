# scripts/lock_pdf.py
from pikepdf import Pdf, Encryption, Permissions
from pathlib import Path

def lock_pdf(src: str, dst: str, owner: str = "owner-secret") -> None:
    perms = Permissions(
        extract=False, modify_annotation=False, modify_form=False,
        modify_other=False, print_lowres=False, print_highres=False
    )
    with Pdf.open(src) as pdf:
        pdf.save(dst, encryption=Encryption(owner=owner, user="", allow=perms))

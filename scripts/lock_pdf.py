# scripts/lock_pdf.py (resilient)
# Tries to lock PDF with pikepdf; if unavailable, falls back to a no-op copy
# so builds never fail during CI/beta.
from pathlib import Path
import shutil

def _lock_with_pikepdf(src: str, dst: str, owner: str = "owner-secret") -> None:
    from pikepdf import Pdf, Encryption, Permissions  # imported lazily
    perms = Permissions(
        extract=False, modify_annotation=False, modify_form=False,
        modify_other=False, print_lowres=False, print_highres=False
    )
    with Pdf.open(src) as pdf:
        pdf.save(dst, encryption=Encryption(owner=owner, user="", allow=perms))

def lock_pdf(src: str, dst: str, owner: str = "owner-secret") -> None:
    try:
        _lock_with_pikepdf(src, dst, owner=owner)
    except ModuleNotFoundError:
        # Graceful fallback: copy without locking (non-fatal)
        # CI log line so you can see why it's unlocked
        print("[lock_pdf] pikepdf not installed; emitting UNLOCKED PDF:", dst)
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    except Exception as e:
        # Any other failure -> also fallback to unlocked copy
        print(f"[lock_pdf] lock failed ({e}); emitting UNLOCKED PDF: {dst}")
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)

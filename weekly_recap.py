# ... keep everything I sent earlier, but replace _attach_images() with this version:
def _attach_images(ctx: Dict[str, Any]) -> None:
    from docxtpl import DocxTemplate, InlineImage
    from docx.shared import Mm

    # Prepare a temp template for InlineImage construction
    t = DocxTemplate("recap_template.docx") if Path("recap_template.docx").exists() else DocxTemplate.__new__(DocxTemplate)

    # League and sponsor
    league_name = str(ctx.get("LEAGUE_NAME") or "")
    sponsor_name = str(ctx.get("SPONSOR_NAME") or "Gridiron Gazette")

    lg = logos.league_logo(league_name)
    if lg and Path(lg).exists():
        ctx["LEAGUE_LOGO"] = InlineImage(t, lg, width=Mm(25))

    sp = logos.sponsor_logo(sponsor_name)
    if sp and Path(sp).exists():
        ctx["SPONSOR_LOGO"] = InlineImage(t, sp, width=Mm(25))

    # Matchup team logos
    for i in range(1, 8):
        hkey, akey = f"MATCHUP{i}_HOME", f"MATCHUP{i}_AWAY"
        if hkey in ctx and ctx[hkey]:
            hp = logos.team_logo(str(ctx[hkey]))
            if hp and Path(hp).exists():
                ctx[f"MATCHUP{i}_HOME_LOGO"] = InlineImage(t, hp, width=Mm(22))
        if akey in ctx and ctx[akey]:
            ap = logos.team_logo(str(ctx[akey]))
            if ap and Path(ap).exists():
                ctx[f"MATCHUP{i}_AWAY_LOGO"] = InlineImage(t, ap, width=Mm(22))

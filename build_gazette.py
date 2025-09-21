#!/usr/bin/env python3

import os
import json, shlex, subprocess
import argparse
from pathlib import Path
from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm
from functools import lru_cache
from glob import glob
import re
import sys
import traceback
from scripts.lock_pdf import lock_pdf

def _soffice_bin():
    mac = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
    return mac if Path(mac).exists() else "soffice"

def export_pdf_a(docx_path: str, out_dir: str) -> Path:
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    export = ('pdf:writer_pdf_Export:'
              '{"SelectPdfVersion":{"type":"long","value":"1"},'
              '"UseTaggedPDF":{"type":"boolean","value":"true"},'
              '"EmbedStandardFonts":{"type":"boolean","value":"true"}}')
    cmd = f'{_soffice_bin()} --headless --convert-to {shlex.quote(export)} ' \
          f'--outdir {shlex.quote(str(out))} {shlex.quote(str(docx_path))}'
    subprocess.check_call(cmd, shell=True)
    return out / (Path(docx_path).stem + ".pdf")

def flatten_pdf(src_pdf: Path, dst_pdf: Path, dpi: int = 200) -> None:
    tmp = Path("frames"); tmp.mkdir(exist_ok=True)
    base = tmp / "page"
    subprocess.check_call(f'pdftoppm -png -r {dpi} {shlex.quote(str(src_pdf))} {shlex.quote(str(base))}', shell=True)
    pngs = sorted(p for p in tmp.glob("page*.png"))
    cmd = "img2pdf " + " ".join(shlex.quote(str(p)) for p in pngs) + f" -o {shlex.quote(str(dst_pdf))}"
    subprocess.check_call(cmd, shell=True)
    for p in pngs: p.unlink()
    tmp.rmdir()

def finalize_pdf_for_league(docx_path: str, league_id: int, season: int, week: int) -> Path:
    """DOCX -> PDF/A -> image-only PDF, stored using league_id slug and week number."""
    pdf_a = export_pdf_a(docx_path, "out_pdf")
    out_dir = Path(f"public/gazettes"); out_dir.mkdir(parents=True, exist_ok=True)
    final_path = out_dir / f"{league_id}-w{week:02}.pdf"
    flatten_pdf(pdf_a, final_path, dpi=200)  # truly non-editable
    return final_path

# --- LLM client (uses OPENAI_API_KEY) ---
try:
    from openai import OpenAI
    _openai_available = True
except Exception:
    _openai_available = False
    OpenAI = None

def _make_openai_client():
    if not _openai_available:
        return None
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        return OpenAI()
    except Exception:
        return None

# ----------------------------------------

def get_openai_key():
    return os.getenv("OPENAI_API_KEY")

def get_espn_credentials():
    return {
        'espn_s2': os.getenv("ESPN_S2"),
        'swid': os.getenv("SWID")
    }

def load_league_config():
    """Load league configuration from leagues.json"""
    try:
        with open('leagues.json', 'r') as f:
            leagues = json.load(f)
        return leagues[0]  # Assuming single league for now
    except Exception as e:
        print(f"Error loading leagues.json: {e}")
        raise

def _normalize_name(s: str) -> str:
    """
    Normalize team names and filenames for matching:
    - lowercase
    - replace non-alphanumerics with spaces
    - collapse spaces
    """
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

@lru_cache(maxsize=1)
def _build_logo_index(root="logos/team_logos"):
    """
    Scan logos/team_logos and build a dict of normalized_name -> full path.
    Supports common raster formats.
    """
    root_path = Path(root)
    exts = {".png", ".jpg", ".jpeg", ".webp"}
    index = {}
    if root_path.exists():
        for p in root_path.rglob("*"):
            if p.is_file() and p.suffix.lower() in exts:
                key = _normalize_name(p.stem)
                index[key] = str(p)
    return index

def get_team_logo_path(team_name: str) -> str:
    """
    Fuzzy match the ESPN team name to a file in logos/team_logos/.
    Returns a concrete file path if found; otherwise a benign fallback.
    """
    index = _build_logo_index()
    if not team_name:
        return "logos/team_logos/default_team_logo.png"

    norm = _normalize_name(team_name)

    # Exact normalized match
    if norm in index:
        return index[norm]

    # Try singular (drop trailing 's')
    if norm.endswith("s") and norm[:-1] in index:
        return index[norm[:-1]]

    # Try progressive shortening (drop last tokens)
    parts = norm.split()
    while len(parts) > 1:
        parts.pop()
        cand = " ".join(parts)
        if cand in index:
            return index[cand]

    # Last-resort contains/startswith style scan
    for k, v in index.items():
        if norm in k or k in norm:
            return v

    # Fallback
    return "logos/team_logos/default_team_logo.png"

def find_or_create_logo(logo_path, fallback_name):
    """Find an existing logo or skip if not found"""
    if not logo_path:
        return None

    path = Path(logo_path)

    # If the exact path exists and is an image file, use it
    if path.exists() and path.suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp', '.gif'}:
        return str(path)

    # Try to find similar image files in the directory
    if path.parent.exists():
        stem = path.stem.lower()
        for file in path.parent.glob("*"):
            if (
                file.is_file()
                and file.suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp', '.gif'}
                and stem in file.stem.lower()
            ):
                print(f"Found similar logo: {file} for {logo_path}")
                return str(file)

    print(f"No image file found for {logo_path} - skipping logo")
    return None

def _is_starter(box_player):
    slot = getattr(box_player, "slot_position", "") or ""
    return slot not in {"BE", "IR"}

def _fmt_pts(x):
    try:
        return f"{float(x):.1f}"
    except Exception:
        return str(x)

def _best_player(lineup):
    starters = [p for p in lineup if _is_starter(p)]
    return max(starters, key=lambda p: getattr(p, "points", 0.0)) if starters else None

def _bust_player(lineup):
    starters = [p for p in lineup if _is_starter(p)]
    if not starters:
        return None
    candidates = [p for p in starters if (getattr(p, "projected_points", 0.0) or 0.0) >= 8.0]
    if not candidates:
        candidates = starters
    return min(candidates, key=lambda p: getattr(p, "points", 0.0))

def _find_dst_note(lineup, team_label):
    starters = [p for p in lineup if _is_starter(p)]
    for p in starters:
        pos = (getattr(p, "position", "") or "").upper()
        name = getattr(p, "name", "") or ""
        pts = getattr(p, "points", 0.0) or 0.0
        if ("D/ST" in pos or "D/ST" in name.upper()) and pts >= 8.0:
            return f"{team_label} D/ST chipped in {_fmt_pts(pts)}."
    return ""

def fetch_espn_data(league_id, year, espn_s2, swid, week_number):
    """Fetch data from ESPN Fantasy API with better error handling"""
    print(f"Connecting to ESPN league {league_id} for week {week_number}")

    try:
        from espn_api.football import League

        league = League(
            league_id=league_id,
            year=year,
            espn_s2=espn_s2,
            swid=swid
        )

        print(f"Connected to league: {league.settings.name}")
        print(f"Teams in league: {len(league.teams)}")

        # Log team names
        for i, team in enumerate(league.teams, 1):
            print(f"  {i}. {team.team_name}")

        # Get matchups for the specified week
        matchups = league.scoreboard(week=week_number)
        print(f"Found {len(matchups)} matchups for week {week_number}")

        # Initialize matchup_data FIRST
        matchup_data = {}

        # Process matchups into template format
        for i, matchup in enumerate(matchups[:10], 1):  # Limit to 10 matchups
            try:
                home_team = matchup.home_team
                away_team = matchup.away_team

                home_name = home_team.team_name if home_team else "Unknown"
                away_name = away_team.team_name if away_team else "Unknown"
                home_score = getattr(matchup, 'home_score', 0) or 0
                away_score = getattr(matchup, 'away_score', 0) or 0

                print(f"  Game {i}: {home_name} ({home_score}) vs {away_name} ({away_score})")

                matchup_data.update({
                    f'MATCHUP{i}_HOME': home_name,
                    f'MATCHUP{i}_AWAY': away_name,
                    f'MATCHUP{i}_HS': home_score,
                    f'MATCHUP{i}_AS': away_score,
                })

                # Add logos
                home_logo = get_team_logo_path(home_name)
                away_logo = get_team_logo_path(away_name)

                if home_logo:
                    matchup_data[f'MATCHUP{i}_HOME_LOGO_PATH'] = home_logo
                    print(f"    Found logo for {home_name}: {home_logo}")

                if away_logo:
                    matchup_data[f'MATCHUP{i}_AWAY_LOGO_PATH'] = away_logo
                    print(f"    Found logo for {away_name}: {away_logo}")

            except Exception as e:
                print(f"Error processing matchup {i}: {e}")
                continue

        # Now process box scores (after matchup_data is created)
        try:
            box_scores = league.box_scores(week=week_number)
            bs_index = {}
            for bs in box_scores:
                h = getattr(bs.home_team, "team_name", "Unknown")
                a = getattr(bs.away_team, "team_name", "Unknown")
                bs_index[(h, a)] = bs

            for i in range(1, 10 + 1):
                home = matchup_data.get(f'MATCHUP{i}_HOME')
                away = matchup_data.get(f'MATCHUP{i}_AWAY')
                if not home or not away:
                    continue
                bs = bs_index.get((home, away)) or bs_index.get((away, home))
                if not bs:
                    continue

                home_lineup = getattr(bs, "home_lineup", []) if getattr(bs, "home_team", None) and getattr(bs.home_team, "team_name", None) == home else getattr(bs, "away_lineup", [])
                away_lineup = getattr(bs, "away_lineup", []) if getattr(bs, "away_team", None) and getattr(bs.away_team, "team_name", None) == away else getattr(bs, "home_lineup", [])

                top_h = _best_player(home_lineup)
                top_a = _best_player(away_lineup)
                bust = _bust_player((home_lineup or []) + (away_lineup or []))

                matchup_data[f'MATCHUP{i}_TOP_HOME'] = f"{getattr(top_h, 'name', '—')} ({_fmt_pts(getattr(top_h, 'points', 0))})" if top_h else "—"
                matchup_data[f'MATCHUP{i}_TOP_AWAY'] = f"{getattr(top_a, 'name', '—')} ({_fmt_pts(getattr(top_a, 'points', 0))})" if top_a else "—"
                matchup_data[f'MATCHUP{i}_BUST'] = f"{getattr(bust, 'name', '—')} ({_fmt_pts(getattr(bust, 'points', 0))})" if bust else "—"

                hs = matchup_data.get(f'MATCHUP{i}_HS', 0.0) or 0.0
                as_ = matchup_data.get(f'MATCHUP{i}_AS', 0.0) or 0.0
                winner = home if (float(hs) >= float(as_)) else away
                top_w = top_h if winner == home else top_a
                matchup_data[f'MATCHUP{i}_KEYPLAY'] = (
                    f"{winner} rode {getattr(top_w, 'name', 'their star')}'s {_fmt_pts(getattr(top_w, 'points', 0))} to slam the door."
                    if top_w else "Late surge sealed it."
                )

                dn = _find_dst_note(home_lineup, f"{home}") or _find_dst_note(away_lineup, f"{away}")
                matchup_data[f'MATCHUP{i}_DEF'] = dn or "Defenses traded blows without a true game-swinger."

                matchup_data[f'MATCHUP{i}_HOME_PLAYERS'] = [getattr(p, 'name', '') for p in home_lineup if _is_starter(p)][:18]
                matchup_data[f'MATCHUP{i}_AWAY_PLAYERS'] = [getattr(p, 'name', '') for p in away_lineup if _is_starter(p)][:18]

        except Exception as e:
            print(f"Box score spotlight unavailable: {e}")

        return matchup_data

    except Exception as e:
        print(f"Error fetching ESPN data: {e}")
        traceback.print_exc()
        raise

def calculate_awards(matchup_data):
    """Calculate weekly awards from matchup data"""
    team_scores = []
    matchup_gaps = []

    # Extract all team scores and calculate gaps
    for i in range(1, 10 + 1):
        home = matchup_data.get(f'MATCHUP{i}_HOME')
        away = matchup_data.get(f'MATCHUP{i}_AWAY')
        hs = matchup_data.get(f'MATCHUP{i}_HS')
        as_score = matchup_data.get(f'MATCHUP{i}_AS')

        if not home or not away:
            continue

        # Add team scores
        try:
            if hs and str(hs) != '':
                hs_float = float(hs)
                team_scores.append((home, hs_float))
        except (ValueError, TypeError):
            pass

        try:
            if as_score and str(as_score) != '':
                as_float = float(as_score)
                team_scores.append((away, as_float))
        except (ValueError, TypeError):
            pass

        # Calculate gap for this matchup
        try:
            if hs and as_score and str(hs) != '' and str(as_score) != '':
                hs_float = float(hs)
                as_float = float(as_score)
                gap = abs(hs_float - as_float)
                winner = home if hs_float > as_float else away
                loser = away if hs_float > as_float else home
                matchup_gaps.append((f"{winner} over {loser}", gap))
        except (ValueError, TypeError):
            pass

    # Calculate awards
    awards = {
        'AWARD_TOP_TEAM': '',
        'AWARD_TOP_NOTE': '',
        'AWARD_CUPCAKE_TEAM': '',
        'AWARD_CUPCAKE_NOTE': '',
        'AWARD_KITTY_TEAM': '',
        'AWARD_KITTY_NOTE': ''
    }

    if team_scores:
        # Top score
        top_team, top_score = max(team_scores, key=lambda x: x[1])
        awards['AWARD_TOP_TEAM'] = top_team
        awards['AWARD_TOP_NOTE'] = f"{top_score:.1f} points"

        # Lowest score (Cupcake Award)
        low_team, low_score = min(team_scores, key=lambda x: x[1])
        awards['AWARD_CUPCAKE_TEAM'] = low_team
        awards['AWARD_CUPCAKE_NOTE'] = f"{low_score:.1f} points"

    if matchup_gaps:
        # Largest gap (Kitty Award)
        gap_desc, gap_value = max(matchup_gaps, key=lambda x: x[1])
        awards['AWARD_KITTY_TEAM'] = gap_desc
        awards['AWARD_KITTY_NOTE'] = f"{gap_value:.1f} point gap"

    return awards

# --- Sabre prompt import ---
from gazette_helpers import find_league_logo
from storymaker import SABRE_STORY_PROMPT, SABRE_SIGNATURE

def generate_llm_content(matchup_data, style="sabre", words=300, temperature=0.4):
    """
    Build LLM blurbs for each matchup using the selected style.
    Ensures team names/emojis are passed verbatim.
    """
    llm_content = {}
    client = _make_openai_client()

    # Simple style map: extend here if you have other prompts
    selected_prompt = None
    if style == "sabre":
        selected_prompt = SABRE_STORY_PROMPT

    for i in range(1, 10 + 1):  # Up to 10 matchups
        home = matchup_data.get(f'MATCHUP{i}_HOME')
        away = matchup_data.get(f'MATCHUP{i}_AWAY')
        if not home or not away:
            continue

        home_score = matchup_data.get(f'MATCHUP{i}_HS', 'TBD')
        away_score = matchup_data.get(f'MATCHUP{i}_AS', 'TBD')

        top_home = matchup_data.get(f'MATCHUP{i}_TOP_HOME', '')
        top_away = matchup_data.get(f'MATCHUP{i}_TOP_AWAY', '')
        bust = matchup_data.get(f'MATCHUP{i}_BUST', '')
        defense_note = matchup_data.get(f'MATCHUP{i}_DEF', '')

        # Keep names/emoji EXACT
        base_ctx = f"""Matchup data:
- Home team: {home}
- Home score: {home_score}
- Away team: {away}
- Away score: {away_score}
- Top performer(s): {top_home} | {top_away}
- Biggest bust(s): {bust}
- Defense note: {defense_note}

Constraints:
- Keep team names, emojis, and formatting EXACTLY as provided.
- Target length: {words} words (±10%).
- End with a natural handoff into Stats Spotlight (per prompt).
"""

        if selected_prompt:
            prompt = f"{selected_prompt}\n\n{base_ctx}"
        else:
            # Fallback generic style if no prompt provided
            prompt = (
                f"Write a {words}-word fantasy football recap in '{style}' style.\n\n{base_ctx}"
            )

        try:
            if client is None:
                raise RuntimeError("OpenAI client not available or OPENAI_API_KEY not set.")

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=int(words * 4),  # conservative buffer
                temperature=temperature
            )
            content = response.choices[0].message.content.strip()
            llm_content[f'MATCHUP{i}_BLURB'] = content
            print(f"Generated blurb for {home} vs {away} ({len(content)} chars)")
        except Exception as e:
            print(f"Error generating LLM content for matchup {i}: {e}")
            llm_content[f'MATCHUP{i}_BLURB'] = (
                f"{home} vs {away}: Sabre's still chasing down the story. "
                f"And if you need the receipts, here's the Stats Spotlight."
            )

    print(f"Generated {len(llm_content)} LLM blurbs")
    return llm_content

def create_image_objects(doc, context):
    """Convert image paths to InlineImage objects"""
    image_context = {}

    for key, value in context.items():
        if key.endswith('_LOGO_PATH') and value and Path(value).exists():
            # Convert path to InlineImage object
            logo_key = key.replace('_PATH', '')
            try:
                # Check if it's actually an image file
                if Path(value).suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp', '.gif'}:
                    image_context[logo_key] = InlineImage(doc, value, width=Mm(25))
                    print(f"Loaded image for {logo_key}: {value}")
                else:
                    print(f"Skipping non-image file for {logo_key}: {value}")
            except Exception as e:
                print(f"Error loading image {value}: {e}")

        

        elif key in ['LEAGUE_LOGO', 'SPONSOR_LOGO']:
            # Handle league and sponsor logos
            if isinstance(value, str) and Path(value).exists():
                try:
                    if Path(value).suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp', '.gif'}:
                        width = Mm(20) if key == 'SPONSOR_LOGO' else Mm(30)
                        image_context[key] = InlineImage(doc, value, width=width)
                        print(f"Loaded {key}: {value} (width: {width})")
                    else:
                        print(f"Skipping non-image file for {key}: {value}")
                except Exception as e:
                    print(f"Error loading {key}: {e}")
        else:
            image_context[key] = value

    return image_context

def main():
    parser = argparse.ArgumentParser(description='Build fantasy football gazette')
    parser.add_argument('--template', required=True, help='Path to Word template')
    parser.add_argument('--out-docx', required=True, help='Output docx file path')
    parser.add_argument('--league-id', required=True, help='ESPN League ID')
    parser.add_argument('--year', type=int, required=True, help='League year')
    parser.add_argument('--week', type=int, default=1, help='Week number')
    parser.add_argument('--llm-blurbs', action='store_true', help='Generate LLM blurbs')
    parser.add_argument('--blurb-style', default='sabre', help='LLM blurb style')
    parser.add_argument('--blurb-words', type=int, default=300, help='LLM blurb word count')
    parser.add_argument('--temperature', type=float, default=0.4, help='LLM temperature')
    parser.add_argument('--slots', type=int, default=10, help='Max matchup slots')

    args = parser.parse_args()

    print(f"=== Building Gridiron Gazette ===")
    print(f"Template: {args.template}")
    print(f"Output: {args.out_docx}")
    print(f"League ID: {args.league_id}")
    print(f"Year: {args.year}")
    print(f"Week: {args.week}")
    print(f"LLM Blurbs: {args.llm_blurbs}")
    print()

def main():
    parser = argparse.ArgumentParser(description='Build fantasy football gazette')
    parser.add_argument('--template', required=True, help='Path to Word template')
    parser.add_argument('--out-docx', required=True, help='Output docx file path')
    parser.add_argument('--league-id', required=True, help='ESPN League ID')
    parser.add_argument('--year', type=int, required=True, help='League year')
    parser.add_argument('--week', type=int, default=1, help='Week number')
    parser.add_argument('--llm-blurbs', action='store_true', help='Generate LLM blurbs')
    parser.add_argument('--blurb-style', default='sabre', help='LLM blurb style')
    parser.add_argument('--blurb-words', type=int, default=300, help='LLM blurb word count')
    parser.add_argument('--temperature', type=float, default=0.4, help='LLM temperature')
    parser.add_argument('--slots', type=int, default=10, help='Max matchup slots')

    args = parser.parse_args()

    print(f"=== Building Gridiron Gazette ===")
    print(f"Template: {args.template}")
    print(f"Output: {args.out_docx}")
    print(f"League ID: {args.league_id}")
    print(f"Year: {args.year}")
    print(f"Week: {args.week}")
    print(f"LLM Blurbs: {args.llm_blurbs}")
    print()

    try:
        # Validate template exists
        if not Path(args.template).exists():
            raise FileNotFoundError(f"Template not found: {args.template}")

        # Load league configuration
        league_config = load_league_config()
        print(f"Loaded league config: {league_config.get('name', 'Unknown')}")

        # Get ESPN credentials
        espn_creds = get_espn_credentials()
        if not espn_creds['espn_s2'] or not espn_creds['swid']:
            raise RuntimeError("ESPN_S2 and SWID environment variables are required")

        # Fetch ESPN data
        espn_data = fetch_espn_data(
            league_id=int(args.league_id),
            year=args.year,
            espn_s2=espn_creds['espn_s2'],
            swid=espn_creds['swid'],
            week_number=args.week
        )

        if not espn_data:
            raise RuntimeError(f"No ESPN data found for week {args.week}")

        # Calculate awards
        awards = calculate_awards(espn_data)

        # Generate LLM content if requested
        llm_content = {}
        if args.llm_blurbs:
            llm_content = generate_llm_content(
                espn_data,
                style=args.blurb_style,
                words=args.blurb_words,
                temperature=args.temperature
            )

        # Build template context
        context = {
            'title': league_config.get('name', 'Fantasy Football Gazette'),
            'WEEK_NUMBER': args.week,
            'WEEKLY_INTRO': f"Week {args.week} recap for {league_config.get('name')}",
            'FOOTER_NOTE': league_config.get('sponsor', {}).get('line', 'Fantasy Football Gazette'),
            'SPONSOR_LINE': league_config.get('sponsor', {}).get('line', 'Your weekly fantasy fix.'),
            **espn_data,
            **llm_content,
            **awards
        }

        from images_attach import create_image_objects

        # Load and render template
        print(f"Loading template: {args.template}")
        doc = DocxTemplate(args.template)

        # build your context = {...} as usual, including HOME_TEAM_NAME / AWAY_TEAM_NAME, etc.
        context = create_image_objects(doc, context)  # ← converts to InlineImage objects safely
        doc.render(context)

        from gazette_helpers import find_league_logo
        logo_path = find_league_logo(league_config.get('name'))
        # insert picture using logo_path

        # Add league and sponsor logos if they exist
        if league_config.get('league_logo'):
            league_logo_path = find_or_create_logo(
                league_config['league_logo'],
                league_config.get('name', 'League')
            )
            if league_logo_path:
                context['LEAGUE_LOGO'] = league_logo_path
                print(f"League logo: {league_logo_path}")

        sponsor = league_config.get('sponsor', {})
        if sponsor.get('logo'):
            sponsor_logo_path = find_or_create_logo(
                sponsor['logo'],
                sponsor.get('name', 'Sponsor')
            )
            if sponsor_logo_path:
                context['SPONSOR_LOGO'] = sponsor_logo_path
                print(f"Sponsor logo: {sponsor_logo_path}")

        # Create output directory if it doesn't exist
        output_path = Path(args.out_docx)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        from pathlib import Path
        from scripts.docx_to_pdf import docx_to_pdf
        from scripts.pdf_to_pdfa import pdf_to_pdfa
        # optional, resilient locking (already patched earlier)
        try:
            from scripts.lock_pdf import lock_pdf  # falls back to unlocked if pikepdf missing
        except Exception:
            lock_pdf = None

        # Define docx_path as the output DOCX file path
        output_path = Path(args.out_docx)
        docx_path = output_path
        doc.save(str(docx_path))
        # add_footer_gradient(str(docx_path), "./logos/footer_gradient_diagonal.png", bar_height_mm=12.0)

        # 1) DOCX -> PDF
        pdf_path = docx_to_pdf(str(docx_path))

        # 2) PDF -> PDF/A-2b (write alongside original)
        pdfa_path = Path(pdf_path).with_suffix(".pdf")  # we’ll place it over the original name in a moment
        pdfa_tmp = Path(pdf_path).with_suffix(".pdfa.pdf")
        pdfa_path = pdf_to_pdfa(pdf_path, str(pdfa_tmp))

        # (Optional) 3) Lock the PDF/A; keep unlocked as fallback
        if lock_pdf:
            locked_out = Path(pdf_path).with_suffix(".locked.pdf")  # or use .pdf for final
            try:
                lock_pdf(pdfa_tmp, str(locked_out))
                final_pdf = locked_out
            except Exception as e:
                print(f"[lock_pdf] failed ({e}); keeping UNLOCKED PDF/A: {pdfa_tmp}")
                final_pdf = Path(pdfa_tmp)
        else:
            final_pdf = Path(pdfa_tmp)

        # Rename final output to the canonical name (overwrite prior simple PDF)
        final_name = Path(pdf_path)
        final_name.unlink(missing_ok=True)
        final_pdf.rename(final_name)

        print(f"[build] PDF/A available at: {final_name}")

        from footer_gradient import add_footer_gradient

        add_footer_gradient(docx_path="assets/brand/footer_gradient_diagonal.png", bar_height_mm=12.0, output_path=args.out_docx)

        # Convert image paths to InlineImage objects
        print("Processing images...")
        context = create_image_objects(doc, context)

        # Debug
        print(f"\nContext summary:")
        print(f"  Total keys: {len(context)}")
        print(f"  Matchup keys: {len([k for k in context.keys() if 'MATCHUP' in k])}")
        print(f"  Logo keys: {len([k for k in context.keys() if 'LOGO' in k])}")
        print(f"  Award keys: {len([k for k in context.keys() if 'AWARD' in k])}")

        # Optional: sanity check undeclared variables
        undeclared = doc.get_undeclared_template_variables(context)
        if undeclared:
            print(f"Template has undeclared variables: {sorted(undeclared)[:10]}...")
        else:
            print("All template variables are declared")

        # Render & save
        print("Rendering template...")
        doc.render(context)
        print(f"Saving to: {args.out_docx}")
        doc.save(args.out_docx)

        if Path(args.out_docx).exists():
            file_size = Path(args.out_docx).stat().st_size
            print(f"Gazette saved successfully!  ({file_size:,} bytes)")
        else:
            raise RuntimeError("File was not created!")

    except Exception as e:
        print(f"Error building gazette: {e}")
        traceback.print_exc()
        sys.exit(1)

    # build_gazette.py (excerpt)
from scripts.pdf_export import docx_to_pdf_a
from scripts.lock_pdf import lock_pdf
from scripts.flatten_pdf import flatten_pdf
from pathlib import Path
import os

PDF_MODE = os.environ.get("PDF_MODE", "flatten")  # flatten | lock | none

def finalize_pdf(docx_path: str, league_slug: str, season: str, week: str) -> str:
    # 1) Export to PDF/A (fonts embedded)
    pdf_a = docx_to_pdf_a(docx_path, "out_pdf")

    # 2) Harden
    out_dir = Path(f"out_pdf_final/{season}/week-{week:>02}")
    out_dir.mkdir(parents=True, exist_ok=True)
    final_pdf = out_dir / f"{league_slug}.pdf"

    if PDF_MODE == "flatten":
        flatten_pdf(pdf_a, str(final_pdf), dpi=200)
    elif PDF_MODE == "lock":
        lock_pdf(pdf_a, str(final_pdf))
    else:
        # no hardening, just move the embedded PDF/A
        Path(pdf_a).rename(final_pdf)

    return str(final_pdf)


if __name__ == "__main__":
    main()


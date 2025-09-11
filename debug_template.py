from docxtpl import DocxTemplate
from gazette_data import build_context, fetch_week_from_espn
from gazette_runner import add_enumerated_matchups, add_template_synonyms
import json

tpl = DocxTemplate("recap_template.docx")
cfg = json.load(open("leagues.json"))[0]
games = fetch_week_from_espn(cfg["league_id"], cfg["year"], cfg.get("espn_s2", ""), cfg.get("swid", ""))
ctx = build_context(cfg, games)

# Print out the context structure to check it
print("Context keys:", list(ctx.keys()))

add_enumerated_matchups(ctx, max_slots=12)
add_template_synonyms(ctx, slots=12)

# After we build the context, check the undeclared variables
try:
    print(sorted(tpl.get_undeclared_template_variables(ctx)))
except Exception as e:
    print(f"Error while getting undeclared template variables: {e}")

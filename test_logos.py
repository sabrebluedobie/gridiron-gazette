import logo_resolver
import json

# Load your team_logos.json
with open("team_logos.json") as f:
    data = json.load(f)

print("Keys in team_logos.json:")
for key in data.keys():
    print(f"  '{key}'")

print("\nTesting logo resolution:")
test_teams = [
    "Nana's Hawks",
    "DEM BOY'S!🏆🏆🏆🏆", 
    "🏉THE💀REBELS🏉",
    "Annie1235 slayy"
]

for team in test_teams:
    logo_path = logo_resolver.team_logo(team)
    status = "✅" if logo_path else "❌"
    print(f"{status} '{team}' -> {logo_path}")

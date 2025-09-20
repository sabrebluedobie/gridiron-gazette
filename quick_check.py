# quick_check.py
from gazette_helpers import find_logo_for
for name in ["Nana's Hawks", "THE 💀REBELS💀", "DEM BOY’S! 🏆🏆🏆🏆"]:
    print(name, "->", find_logo_for(name))

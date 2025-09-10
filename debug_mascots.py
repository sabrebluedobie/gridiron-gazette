# debug_mascots.py
from mascots_util import debug_info
import json

for name in ["Wafflers", "Storm"]:
    print(json.dumps(debug_info(name), indent=2))

.PHONY: setup run pdf debug

setup:
\tpython3 -m venv .venv && . .venv/bin/activate && python -m pip install --upgrade pip && pip install -r requirements.txt

run:
\t. .venv/bin/activate && python gazette_runner.py --slots 10

pdf:
\t. .venv/bin/activate && python gazette_runner.py --slots 10 --pdf

debug:
\t. .venv/bin/activate && python debug_mascots.py

.PHONY: gen-logos

gen-logos:
\t. .venv/bin/activate && python generate_logos.py --from-espn


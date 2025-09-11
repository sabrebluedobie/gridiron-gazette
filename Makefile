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

# Makefile snippet
VENVDIR ?= .venv
PY      ?= $(VENVDIR)/bin/python
SLOTS   ?= 10
WEEK    ?=
LLM     ?=
PDF     ?=

define RUN_FLAGS
--slots $(SLOTS) \
$(if $(WEEK),--week $(WEEK),) \
$(if $(LLM),--llm-blurbs,) \
$(if $(PDF),--pdf,)
endef

.PHONY: run
run:
	$(PY) gazette_runner.py $(RUN_FLAGS)

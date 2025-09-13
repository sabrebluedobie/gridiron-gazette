# ===== Gridiron Gazette Makefile =====
# Usage examples:
#   make venv
#   make install
#   make run WEEK=1 PDF=1
#   make run LLM=1 BLURB_STYLE=mascot
#   make branding-test PDF=1 PRINT_LOGO_MAP=1
#
# Tip: For LLM blurbs, first:
source .venv/bin/activate &&
-include .env.local
# export ***REMOVED***
ENVUTF8 := PYTHONIOENCODING=utf-8 LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8

VENV            ?= .venv
PY              := $(VENV)/bin/python3
PIP             := $(VENV)/bin/pip

# Paths / files
LEAGUES         ?= leagues.json
TEMPLATE        ?= recap_template.docx
OUT             ?= recaps

# Run-time knobs
SLOTS           ?= 10
WEEK            ?=
LEAGUE          ?=
LOGO_MM         ?= 25
PDF             ?= 0
PDF_ENGINE      ?= soffice           # auto|soffice|word
PRINT_LOGO_MAP  ?= 0

# LLM blurbs
LLM             ?= 0                 # 1 to enable
BLURB_WORDS     ?= 160
BLURB_STYLE     ?= default           # default|mascot
MODEL           ?= gpt-4o-mini
TEMP            ?= 0.7

# ---- Derived CLI args (built conditionally) ----
ARGS = --leagues $(LEAGUES) --template $(TEMPLATE) --out-dir "$(PWD)/recaps" --slots $(SLOTS) --logo-mm $(LOGO_MM) --pdf-engine $(PDF_ENGINE)

ifeq ($(PDF),1)
ARGS += --pdf
endif
ifneq ($(WEEK),)
ARGS += --week $(WEEK)
endif
ifneq ($(LEAGUE),)
ARGS += --league "$(LEAGUE)"
endif
ifeq ($(PRINT_LOGO_MAP),1)
ARGS += --print-logo-map
endif
ifeq ($(LLM),1)
ARGS += --llm-blurbs --blurb-words $(BLURB_WORDS) --model $(MODEL) --temperature $(TEMP) --blurb-style $(BLURB_STYLE)
endif

run:
	$(ENVUTF8) $(PY) gazette_runner.py $(ARGS)

branding-test:
	$(ENVUTF8) $(PY) gazette_runner.py --branding-test --slots 1 $(ARGS)


# ---- Phony targets ----
.PHONY: help venv install upgrade run branding-test pdf clean

help:
	@echo "Gridiron Gazette — Make targets"
	@echo "  make venv                 # create .venv"
	@echo "  make install              # install requirements into .venv"
	@echo "  make run [WEEK=1] [PDF=1] [LLM=1 BLURB_STYLE=mascot] [LEAGUE='Name']"
	@echo "  make branding-test [PDF=1] [PRINT_LOGO_MAP=1]"
	@echo "  make pdf WEEK=1           # shortcut for PDF export via $(PDF_ENGINE)"
	@echo
	@echo "Vars: SLOTS=$(SLOTS) WEEK=$(WEEK) PDF=$(PDF) PDF_ENGINE=$(PDF_ENGINE) LLM=$(LLM) BLURB_STYLE=$(BLURB_STYLE)"

venv:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip

install: venv
	$(PIP) install -r requirements.txt

upgrade:
	$(PIP) install --upgrade -r requirements.txt

# Full run (honors WEEK, PDF, LLM, etc.)
run:
	$(PY) gazette_runner.py $(ARGS)

# Quick smoke test for logos/template (no ESPN calls)
branding-test:
	$(PY) gazette_runner.py --branding-test --slots 1 $(ARGS)

# Convenience: force PDF using current engine
pdf:
	$(MAKE) run PDF=1

clean:
	rm -rf $(OUT)/* __pycache__ */__pycache__

open-latest:
	@open "$$(ls -t recaps/*/*.{pdf,docx} | head -1)"

serve:
	@python3 -m http.server 8000 --bind 0.0.0.0

share-latest:
	@mkdir -p shared
	@cp "$$(ls -t recaps/*/*.{pdf,docx} | head -1)" shared/
	@echo "Shared -> $$PWD/shared"

.PHONY: doctor espn-check branding-test run

doctor:
	@echo "Repo root: $$(git rev-parse --show-toplevel)"
	@echo "Python: $$(.venv/bin/python3 -V 2>/dev/null || python3 -V)"
	@echo "Venv: $${VIRTUAL_ENV:-'(inactive)'}"
	@echo "Template exists? $$(test -f recap_template.docx && echo yes || echo NO)"
	@echo "LibreOffice: $$(command -v soffice || echo 'not found')"
	@echo "OpenAI key set? $$(test -n "$$OPENAI_API_KEY" && echo yes || echo NO)"
	@echo "ESPN cookies present? $$(python3 - <<'PY'\nimport json;import sys\ntry:\n cfg=json.load(open('leagues.json'))[0]\n print('yes' if (cfg.get('espn_s2') and cfg.get('swid')) else 'NO')\nexcept Exception as e:\n print('error:',e)\nPY)"
	@echo "Latest recaps:" && ls -lht recaps/*/*.{pdf,docx} 2>/dev/null | head -n 6 || true

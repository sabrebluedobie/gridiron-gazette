SHELL := /bin/bash

.PHONY: run blurb-test

# Defaults (override at CLI)
WEEK        ?= 1
SLOTS       ?= 10
PDF         ?= 1
BLURB_WORDS ?= 1000
MODEL       ?= gpt-4o-mini
TEMP        ?= 0.4
BLURB_STYLE ?= rtg
ARGS        ?=

# Template fields (export so Python picks them up)
FOOTER_NOTE  ?= See everyone Thursday!
SPONSOR_LINE ?= Brought to you this week by ______
export FOOTER_NOTE
export SPONSOR_LINE

PY      ?= python3
ENVUTF8 ?= env PYTHONIOENCODING=UTF-8
PDF_FLAG := $(if $(filter 1 yes true on,$(PDF)),--pdf,)

run:
	$(ENVUTF8) $(PY) gazette_runner.py \
	  --week $(WEEK) --slots $(SLOTS) $(PDF_FLAG) \
	  --llm-blurbs --blurb-words $(BLURB_WORDS) \
	  --model $(MODEL) --temperature $(TEMP) $(ARGS)

blurb-test:
	$(ENVUTF8) $(PY) gazette_runner.py \
	  --blurb-test --llm-blurbs \
	  --blurb-words $(BLURB_WORDS) \
	  --model $(MODEL) --temperature $(TEMP) \
	  --blurb-style $(BLURB_STYLE) $(ARGS)

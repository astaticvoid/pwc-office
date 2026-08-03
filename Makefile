-include .env
export

.PHONY: venv test test-unit test-smoke test-seasonal test-full test-tools build check-dist check-integrity check-text serve serve-fg serve-dist stop status restart deploy test-web validate fetch-sources extract mobile-sync mobile-ios mobile-android qa

PORT      ?= 8080
PORT_DIST ?= 8081

# Python interpreter. Prefer the project venv (`make venv`) when present, so no
# shell activation is needed; fall back to the ambient python3 (CI, which gets a
# clean setup-python interpreter). Homebrew's python3 is externally managed
# (PEP 668) and refuses direct installs, so the venv is the supported path.
PYTHON := $(shell [ -x .venv/bin/python3 ] && echo .venv/bin/python3 || echo python3)

# Create the venv and install Python dependencies.
venv:
	python3 -m venv .venv
	.venv/bin/python3 -m pip install --quiet --upgrade pip
	.venv/bin/python3 -m pip install --quiet pymupdf pytest
	@echo "venv ready: $$(.venv/bin/python3 -V) — make will use it automatically"

# Download all source files. Everything is publicly available — no manual steps.
fetch-sources:
	$(PYTHON) tools/fetch_sources.py

# Run the full extraction pipeline after sources are present.
extract:
	$(PYTHON) tools/extract_offices.py
	$(PYTHON) tools/normalize_offices.py
	$(PYTHON) tools/extract_psalter.py
	$(PYTHON) tools/extract_collects.py
	$(PYTHON) tools/extract_fats.py
	$(PYTHON) tools/convert_lectionary.py --window 12
# Corrections run last, after every extractor has produced pristine output.
# convert_lectionary.py rewrites data/lectionary/ wholesale, so it must come
# before apply_corrections.py or it discards the lectionary corrections; and
# validate_corrections.py checks PRE-application state, so it must see freshly
# converted data or it reports every lectionary correction as stale. See #37.
	$(PYTHON) tools/validate_corrections.py
	$(PYTHON) tools/apply_corrections.py
	$(PYTHON) tools/update_extract_manifest.py
	@if [ -z "$$CI" ] && git -C data/ rev-parse --git-dir >/dev/null 2>&1; then \
	  git -C data/ add -A && git -C data/ commit -m "extraction $(shell date +%Y-%m-%d)" || true; \
	fi

# Suppress Node 22 localStorage experimental warning (render.js has polyfill).
NODE_OPTIONS = --localstorage-file=/tmp/pwc-ls.json

# Unit tests — no API key needed, always fast.
test-unit:
	npm test

test: test-unit test-tools qa

# Smoke — 4 cases: structural + reading citation check vs lectionary.anglican.ca.
# Skips citation check if site is unreachable.
test-smoke:
	node tools/test_eval.js --smoke

# Seasonal — 26 cases: one MP+EP per liturgical form + OrdinaryTime weekdays.
# Skips citation check if site is unreachable.
test-seasonal:
	node tools/test_eval.js --seasonal

# Full — structural check of every day in the lectionary year. No API key needed.
test-full:
	node tools/test_full.js

# Assemble dist/ for static deployment (S3, etc.).
# Copies web/ source + dereferences the data/ symlink into one deployable folder.
build:
	rm -rf dist
	cp -rL web/. dist/
	rm -rf dist/data/.git
	$(PYTHON) tools/generate_version_manifest.py --dist-dir dist
	@echo "dist/ ready ($$(find dist -type f | wc -l | tr -d ' ') files)"

# Verify dist/ has everything the app needs before deploying.
check-dist: build test-unit
	@$(PYTHON) tools/check_dist.py

# Local server management (http://localhost:$(PORT)/).
# Override port: make serve PORT=9000
PID_FILE = .server-pid

# Free a TCP port. `fuser -k PORT/tcp` is GNU-only — BSD fuser (macOS) takes
# files, not ports, so it silently frees nothing. lsof works on both.
# Usage: $(call kill_port,8080)
kill_port = kill $$(lsof -ti tcp:$(1)) 2>/dev/null; true

serve:
	@$(MAKE) stop --no-print-directory 2>/dev/null; true
	@nohup $(PYTHON) -m http.server $(PORT) --directory web > /tmp/pwc-server.log 2>&1 & echo $$! > $(PID_FILE)
	@sleep 0.5
	@if kill -0 $$(cat $(PID_FILE)) 2>/dev/null; then \
	  echo "Server started: http://localhost:$(PORT) (pid $$(cat $(PID_FILE)))"; \
	else \
	  echo "Server failed to start — check /tmp/pwc-server.log"; \
	fi

stop:
	@if [ -f $(PID_FILE) ]; then kill $$(cat $(PID_FILE)) 2>/dev/null && rm -f $(PID_FILE) && echo "Server stopped (port $(PORT))" || true; fi
	@$(call kill_port,$(PORT))

status:
	@if [ -f $(PID_FILE) ] && kill -0 $$(cat $(PID_FILE)) 2>/dev/null; then \
	  echo "Server running: http://localhost:$(PORT) (pid $$(cat $(PID_FILE)))"; \
	else \
	  echo "Server not running on port $(PORT)"; \
	  rm -f $(PID_FILE); \
	fi

restart: stop serve

# Serve web/ directly for local development — foreground mode (for debugging).
# Override port: make serve-fg PORT=9000
serve-fg:
	@$(call kill_port,$(PORT))
	@sleep 0.3
	$(PYTHON) -m http.server $(PORT) --directory web

# Build and serve dist/ as it will appear when deployed (http://localhost:$(PORT_DIST)/).
# Required for E2E tests and pre-deploy checks.
# Override port: make serve-dist PORT_DIST=9001
serve-dist: check-dist
	@$(call kill_port,$(PORT_DIST))
	@sleep 0.3
	$(PYTHON) -m http.server $(PORT_DIST) --directory dist

# Unit tests for Python extraction tools (pytest comes from `make venv`).
test-tools:
	$(PYTHON) -m pytest tools/tests/ -v

# Scan extracted JSON files for PDF extraction artifacts (missing spaces, etc.).
check-text:
	$(PYTHON) tools/check_text_quality.py

# Liturgical quality gate — runs validators and coherence scorer.
# Used by 'make test' so every PR checks liturgical coherence.
qa:
	@echo "=== Liturgical validation ==="
	@node tools/validate_office.cjs --json > /tmp/pwc-validate.json
	@node tools/audit_office.cjs --json > /tmp/pwc-audit.json
	@COHERENCE_THRESHOLD=100 node tools/coherence_score.cjs /tmp/pwc-validate.json /tmp/pwc-audit.json
	@rm -f /tmp/pwc-validate.json /tmp/pwc-audit.json
	@echo "=== CSS validity ==="
	@node tools/validate_css.cjs
	@echo "=== Render validation ==="
	@node tools/validate_render.cjs
	@echo "=== Lectionary data ==="
	@node tools/validate_lectionary.cjs
	@echo "=== Cross-form text ==="
	@node tools/audit_text.cjs
	@echo "=== Accessibility ==="
	@node tools/audit_a11y.cjs

# Validate extracted lectionary data against the ACC HTML source.
# Requires network access; run manually before a data re-extraction.
validate: check-text
	$(PYTHON) tools/validate_lectionary.py

# Run E2E tests locally against web/ (default — no bandwidth cost).
test-web:
	npx playwright test

# Verify data/ files match the last extraction — exits 1 if any file was edited directly.
check-integrity:
	$(PYTHON) tools/check_data_integrity.py

# Mobile — build dist/ then sync web assets into iOS and Android native projects.
# After mobile-sync, open the native project in Xcode / Android Studio to build and archive.
mobile-sync: build
	npx cap sync

# Open iOS project in Xcode (requires Xcode + Apple Developer account for device/archive).
mobile-ios: mobile-sync
	npx cap open ios

# Open Android project in Android Studio (requires Android Studio + JDK).
mobile-android: mobile-sync
	npx cap open android

# ── Deploy (versioned directories) ──────────────────────────────────────────
# Requires AWS_PROFILE or ambient credentials, BUCKET, CF_DISTRIBUTION_ID.
#
# Three-stage workflow:
#   1. make deploy-staging      — upload to releases/vTIMESTAMP/ and staging/
#   2. make test-staging        — Playwright smoke against staging
#      (make test-staging-full  — optional: full e2e regression, not just @smoke)
#   3. make promote             — CloudFront origin-path swap to production
#
# Rollback: make rollback    — swaps to previous release

RELEASE = $(shell date -u +%Y-%m-%dT%H%M%SZ)-$(shell git rev-parse --short HEAD)

deploy-staging: check-integrity check-dist
	aws s3 sync dist/ s3://$(BUCKET)/releases/$(RELEASE)/ --delete
	# Everything on staging gets a 1-minute cache. Staging exists to be deployed
	# to and looked at immediately, so production-shaped TTLs are wrong here: the
	# data files were cached for an hour and the images for a day, which meant a
	# re-extraction could be verified as correct on the CDN while the browser
	# kept serving the previous copy. Production caching is unaffected — the
	# releases/ objects below carry no cache-control and promote swaps the
	# CloudFront origin path.
	aws s3 sync dist/ s3://$(BUCKET)/staging/ --delete \
	  --exclude "*" --include "*.html" --include "*.js" --include "*.css" \
	  --include "*.json" --include "*.png" --include "*.svg" --include "*.ico" \
	  --cache-control "max-age=60"
	# sw.js: never cache — kill-switch must always be fresh
	aws s3 sync dist/ s3://$(BUCKET)/staging/ --delete \
	  --exclude "*" --include "sw.js" \
	  --cache-control "max-age=0, no-store"
	@echo "Staging deployed: $(RELEASE)"
	@echo "$(RELEASE)" > .deploy-latest

test-staging:
	BASE_URL=https://$(STAGING_DOMAIN) \
	  npx playwright test --grep "@smoke"

# Full regression against staging — every e2e spec, not just @smoke.
# Slower (~3 min); run before a risky promote or after UI-touching changes.
test-staging-full:
	BASE_URL=https://$(STAGING_DOMAIN) \
	  npx playwright test

promote:
	@test -f .deploy-latest || (echo "Run deploy-staging first"; exit 1)
	@if [ -z "$$PROMOTE_FORCE" ]; then \
	  echo "Checking coherence score..."; \
	  node tools/validate_office.cjs --json > /tmp/pwc-promote-val.json 2>/dev/null; \
	  node tools/audit_office.cjs --json > /tmp/pwc-promote-aud.json 2>/dev/null; \
	  COHERENCE_THRESHOLD=100 node tools/coherence_score.cjs --check-promote /tmp/pwc-promote-val.json /tmp/pwc-promote-aud.json \
	    || (echo "Promotion blocked — score below 100. Fix issues or use PROMOTE_FORCE=1 to bypass."; \
	        rm -f /tmp/pwc-promote-val.json /tmp/pwc-promote-aud.json; exit 1); \
	  rm -f /tmp/pwc-promote-val.json /tmp/pwc-promote-aud.json; \
	fi
	@RELEASE=$$(cat .deploy-latest) && \
	aws cloudfront get-distribution-config --id $(CF_DISTRIBUTION_ID) \
	  > /tmp/cf-config.json && \
	jq '.DistributionConfig.Origins.Items[0].OriginPath = "/releases/'"$$RELEASE"'" | .DistributionConfig' \
	  /tmp/cf-config.json > /tmp/cf-new.json && \
	aws cloudfront update-distribution --id $(CF_DISTRIBUTION_ID) \
	  --distribution-config file:///tmp/cf-new.json \
	  --if-match $$(jq -r '.ETag' /tmp/cf-config.json) && \
	echo "Promoted $$RELEASE to production"

rollback:
	@PREV=$$(aws s3 ls s3://$(BUCKET)/releases/ | sort -r | head -2 | tail -1 | awk '{print $$2}' | sed 's:/$$::') && \
	test -n "$$PREV" || (echo "No previous release found — nothing to roll back to"; exit 1) && \
	echo "Rolling back to $$PREV" && \
	aws cloudfront get-distribution-config --id $(CF_DISTRIBUTION_ID) \
	  > /tmp/cf-config.json && \
	jq '.DistributionConfig.Origins.Items[0].OriginPath = "/releases/'"$$PREV"'" | .DistributionConfig' \
	  /tmp/cf-config.json > /tmp/cf-new.json && \
	aws cloudfront update-distribution --id $(CF_DISTRIBUTION_ID) \
	  --distribution-config file:///tmp/cf-new.json \
	  --if-match $$(jq -r '.ETag' /tmp/cf-config.json) && \
	echo "Rolled back to $$PREV"

# Legacy single-step deploy — kept for compatibility during transition.
# Use deploy-staging + test-staging + promote for production deploys.
deploy: check-integrity check-dist
	@echo "DEPRECATED: use 'make deploy-staging' then 'make promote'"
	@echo "Running legacy deploy..."
	aws s3 sync dist/ s3://$(BUCKET)/ --delete --exclude "sw.js"
	aws s3 cp dist/sw.js s3://$(BUCKET)/sw.js \
	  --cache-control "no-cache, no-store" \
	  --content-type "application/javascript"
	aws cloudfront create-invalidation --distribution-id $(CF_DISTRIBUTION_ID) --paths "/*"

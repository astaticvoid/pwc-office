-include .env
export

.PHONY: test test-unit test-smoke test-seasonal test-full test-tools build check-dist check-integrity check-text check-casing check-book generate-golden serve serve-dist deploy test-web validate fetch-sources extract extract-rcl mobile-sync mobile-ios mobile-android qa

PORT      ?= 8080
PORT_DIST ?= 8081

# Download all source files. Everything is publicly available — no manual steps.
fetch-sources:
	python3 tools/fetch_sources.py

# Run the full extraction pipeline after sources are present.
extract:
	python3 tools/extract_offices.py
	python3 tools/normalize_offices.py
	python3 tools/extract_psalter.py
	python3 tools/extract_collects.py
	python3 tools/extract_fats.py
	python3 tools/validate_corrections.py
	python3 tools/apply_corrections.py
	python3 tools/convert_lectionary.py --window 12
	python3 tools/update_extract_manifest.py
	@if [ -z "$$CI" ] && git -C data/ rev-parse --git-dir >/dev/null 2>&1; then \
	  git -C data/ add -A && git -C data/ commit -m "extraction $(shell date +%Y-%m-%d)" || true; \
	fi

# Unit tests — no API key needed, always fast.
test: test-unit test-tools qa

test-unit:
	npm test

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
	python3 tools/generate_version_manifest.py --dist-dir dist
	@echo "dist/ ready ($$(find dist -type f | wc -l | tr -d ' ') files)"

# Verify dist/ has everything the app needs before deploying.
check-dist: build test-unit
	@python3 tools/check_dist.py

# Serve web/ directly for local development (http://localhost:$(PORT)/).
# No build step — web/data symlink is followed live.
# Override port: make serve PORT=9000
serve:
	-lsof -ti:$(PORT) | xargs kill -9 2>/dev/null; true
	python3 -m http.server $(PORT) --directory web

# Build and serve dist/ as it will appear when deployed (http://localhost:$(PORT_DIST)/).
# Required for E2E tests and pre-deploy checks.
# Override port: make serve-dist PORT_DIST=9001
serve-dist: check-dist
	-lsof -ti:$(PORT_DIST) | xargs kill -9 2>/dev/null; true
	python3 -m http.server $(PORT_DIST) --directory dist

# Unit tests for Python extraction tools (requires pytest: brew install pytest).
test-tools:
	pytest tools/tests/ -v

# Diff book-mode renderer output against golden file. Usage: make check-book FORM=ordinary-sunday-ep [DATE=2026-06-14]
check-book:
	python3 tools/compare_book.py $(FORM) $(DATE)

# Generate golden files for all 31 forms from the source PDF.
# Files are written to tests/fixtures/book/ (gitignored — contain copyrighted content).
generate-golden:
	for form in $$(python3 -c "import sys; sys.path.insert(0,'tools'); from extract_offices import OFFICES; print(' '.join(r[0] for r in OFFICES))"); do \
		python3 tools/extract_form_text.py $$form; \
	done

# Scan extracted JSON files for PDF extraction artifacts (missing spaces, etc.).
check-text:
	python3 tools/check_text_quality.py

# Casing oracle: compare offices.json segment casing against pdftotext ground
# truth (pdfplumber lowercases the small-caps font; pdftotext decodes it right).
check-casing:
	python3 tools/check_casing.py

# Liturgical quality gate — runs validators and coherence scorer.
# Used by 'make test' so every PR checks liturgical coherence.
qa:
	@echo "=== Liturgical validation ==="
	@node tools/validate_office.cjs --json > /tmp/pwc-validate.json
	@node tools/audit_office.cjs --json > /tmp/pwc-audit.json
	@COHERENCE_THRESHOLD=65 node tools/coherence_score.cjs /tmp/pwc-validate.json /tmp/pwc-audit.json
	@rm -f /tmp/pwc-validate.json /tmp/pwc-audit.json

# Validate extracted lectionary data against the ACC HTML source.
# Requires network access; run manually before a data re-extraction.
validate: check-text check-casing
	python3 tools/validate_lectionary.py

# Extract RCL Daily Readings from RTF source → data/rcl-daily/
extract-rcl:
	python3 tools/extract_rcl_daily.py

# Validate RCL Daily extraction output
validate-rcl:
	python3 tools/validate_rcl_daily.py --strict

# Run E2E tests locally against web/ (default — no bandwidth cost).
test-web:
	npx playwright test

# Verify data/ files match the last extraction — exits 1 if any file was edited directly.
check-integrity:
	python3 tools/check_data_integrity.py

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
#   1. make deploy-staging  — upload to releases/vTIMESTAMP/ and staging/
#   2. make test-staging     — Playwright smoke against staging
#   3. make promote          — CloudFront origin-path swap to production
#
# Rollback: make rollback    — swaps to previous release

RELEASE = $(shell date -u +%Y-%m-%dT%H%M%SZ)-$(shell git rev-parse --short HEAD)

deploy-staging: check-integrity check-dist
	aws s3 sync dist/ s3://$(BUCKET)/releases/$(RELEASE)/ --delete
	# App shell: short cache (1 min) — pick up changes quickly during testing
	aws s3 sync dist/ s3://$(BUCKET)/staging/ --delete \
	  --exclude "*" --include "*.html" --include "*.js" --include "*.css" \
	  --cache-control "max-age=60"
	# Data files: medium cache (1 hour) — change only on re-extraction
	aws s3 sync dist/ s3://$(BUCKET)/staging/ --delete \
	  --exclude "*" --include "*.json" \
	  --cache-control "max-age=3600"
	# Static assets: long cache (24 hours) — images, fonts, icons
	aws s3 sync dist/ s3://$(BUCKET)/staging/ --delete \
	  --exclude "*" --include "*.png" --include "*.svg" --include "*.ico" \
	  --cache-control "max-age=86400"
	# sw.js: never cache — kill-switch must always be fresh
	aws s3 sync dist/ s3://$(BUCKET)/staging/ --delete \
	  --exclude "*" --include "sw.js" \
	  --cache-control "max-age=0, no-store"
	@echo "Staging deployed: $(RELEASE)"
	@echo "$(RELEASE)" > .deploy-latest

test-staging:
	STAGING_URL=https://$(STAGING_DOMAIN) \
	  npx playwright test --grep "@smoke"

promote:
	@test -f .deploy-latest || (echo "Run deploy-staging first"; exit 1)
	@if [ -z "$$PROMOTE_FORCE" ]; then \
	  echo "Checking coherence score..."; \
	  node tools/validate_office.cjs --json > /tmp/pwc-promote-val.json 2>/dev/null; \
	  node tools/audit_office.cjs --json > /tmp/pwc-promote-aud.json 2>/dev/null; \
	  node tools/coherence_score.cjs --check-promote /tmp/pwc-promote-val.json /tmp/pwc-promote-aud.json \
	    || (echo "Promotion blocked — score below 85. Fix issues or use PROMOTE_FORCE=1 to bypass."; \
	        rm -f /tmp/pwc-promote-val.json /tmp/pwc-promote-aud.json; exit 1); \
	  rm -f /tmp/pwc-promote-val.json /tmp/pwc-promote-aud.json; \
	fi
	@RELEASE=$$(cat .deploy-latest); \
	aws cloudfront get-distribution-config --id $(CF_DISTRIBUTION_ID) \
	  > /tmp/cf-config.json; \
	jq '.DistributionConfig.Origins.Items[0].OriginPath = "/releases/'"$$RELEASE"'"' \
	  /tmp/cf-config.json > /tmp/cf-new.json; \
	aws cloudfront update-distribution --id $(CF_DISTRIBUTION_ID) \
	  --distribution-config file:///tmp/cf-new.json; \
	echo "Promoted $$RELEASE to production"

rollback:
	@PREV=$$(aws s3 ls s3://$(BUCKET)/releases/ | sort -r | head -2 | tail -1 | awk '{print $$2}'); \
	echo "Rolling back to $$PREV"; \
	aws cloudfront get-distribution-config --id $(CF_DISTRIBUTION_ID) \
	  > /tmp/cf-config.json; \
	jq '.DistributionConfig.Origins.Items[0].OriginPath = "/releases/'"$$PREV"'"' \
	  /tmp/cf-config.json > /tmp/cf-new.json; \
	aws cloudfront update-distribution --id $(CF_DISTRIBUTION_ID) \
	  --distribution-config file:///tmp/cf-new.json; \
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

-include .env
export

.PHONY: test test-unit test-smoke test-seasonal test-full test-tools build check-dist check-integrity check-text check-book generate-golden serve serve-dist deploy test-web validate fetch-sources extract

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
	python3 tools/validate_patches.py
	python3 tools/apply_patches.py
	python3 tools/convert_lectionary.py --accept --window 12
	python3 tools/validate_lectionary.py
	python3 tools/update_extract_manifest.py
	git -C data/ add -A && git -C data/ commit -m "extraction $(shell date +%Y-%m-%d)" || true

# Unit tests — no API key needed, always fast.
test: test-unit test-tools

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

# Validate extracted lectionary data against the ACC HTML source.
# Requires network access; run manually before a data re-extraction.
validate: check-text
	python3 tools/validate_lectionary.py

# Run E2E tests locally against web/ (default — no bandwidth cost).
test-web:
	npx playwright test

# Verify data/ files match the last extraction — exits 1 if any file was edited directly.
check-integrity:
	python3 tools/check_data_integrity.py

# Deploy — sync dist/ to S3 (requires AWS_PROFILE or ambient credentials).
# Set BUCKET in environment or pass: make deploy BUCKET=my-bucket-name
deploy: check-integrity check-dist
	# sw.js uploaded no-cache so existing installs receive the kill-switch promptly.
	aws s3 sync dist/ s3://$(BUCKET)/ --delete --exclude "sw.js"
	aws s3 cp dist/sw.js s3://$(BUCKET)/sw.js \
	  --cache-control "no-cache, no-store" \
	  --content-type "application/javascript"
	aws cloudfront create-invalidation --distribution-id $(CF_DISTRIBUTION_ID) --paths "/*"

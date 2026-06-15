-include .env
export

.PHONY: test test-unit test-smoke test-seasonal test-full test-tools build check-dist check-integrity check-text check-book serve serve-dist deploy test-web validate fetch-sources extract update-golden

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
	go test ./...

test-unit:
	npm test

# Smoke — 4 LLM evaluations run sequentially; stops at first failure.
# Output saved to /tmp/smoke_out.txt; summary printed at end.
test-smoke:
	go test -tags e2e_smoke -v -failfast -timeout 10m ./e2e/... \
	  > /tmp/smoke_out.txt 2>&1; \
	  grep -E "^(=== RUN|--- (PASS|FAIL)|    seasonal_test|    smoke_test)" /tmp/smoke_out.txt || true; \
	  grep "issue:" /tmp/smoke_out.txt || true; \
	  tail -3 /tmp/smoke_out.txt

# Seasonal — one MP+EP per liturgical season, sequential with early exit on first failure.
# Output saved to /tmp/seasonal_out.txt; summary printed at end.
test-seasonal:
	go test -tags e2e_seasonal -v -failfast -timeout 30m ./e2e/... \
	  > /tmp/seasonal_out.txt 2>&1; \
	  grep -E "^(=== RUN|--- (PASS|FAIL))" /tmp/seasonal_out.txt || true; \
	  grep "issue:" /tmp/seasonal_out.txt || true; \
	  tail -3 /tmp/seasonal_out.txt

# Full — structural check of every day in the lectionary year. No API key needed.
test-full:
	node tools/test_full.js

# Regenerate golden snapshot files after an intentional rendering change.
update-golden:
	go test ./e2e/... -tags e2e_full -run TestGolden -update

# Assemble dist/ for static deployment (S3, etc.).
# Copies web/ source + dereferences the data/ symlink into one deployable folder.
# Stamps dist/sw.js with a content hash of the precached shell files so the
# service worker cache is automatically invalidated on every deploy.
build:
	rm -rf dist
	cp -rL web/. dist/
	rm -rf dist/data/.git
	@HASH=$$(python3 -c "import hashlib,sys; h=hashlib.sha256(); \
	  [h.update(open(f,'rb').read()) for f in sys.argv[1:]]; \
	  print(h.hexdigest()[:8])" \
	  dist/index.html dist/app.js dist/render.js dist/office.css dist/manifest.json \
	  dist/data/offices.json dist/data/collects.json dist/data/season_bounds.json); \
	sed -i '' "s/pwc-v1/pwc-$$HASH/" dist/sw.js; \
	echo "dist/ ready (cache: pwc-$$HASH, $$(find dist -type f | wc -l | tr -d ' ') files)"

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
	# sw.js must be no-cache so browsers always revalidate after a deploy.
	# Sync everything except sw.js, then upload sw.js with explicit header.
	aws s3 sync dist/ s3://$(BUCKET)/ --delete --exclude "sw.js"
	aws s3 cp dist/sw.js s3://$(BUCKET)/sw.js \
	  --cache-control "no-cache, no-store" \
	  --content-type "application/javascript"
	aws cloudfront create-invalidation --distribution-id $(CF_DISTRIBUTION_ID) --paths "/*"

-include .env
export

.PHONY: test test-smoke test-seasonal test-full test-tools build check-dist serve serve-dist deploy test-web validate

PORT      ?= 8080
PORT_DIST ?= 8081

# Unit tests — no API key needed, always fast.
test:
	go test ./...

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
	go test -tags e2e_full -timeout 5m ./e2e/...

# Assemble dist/ for static deployment (S3, etc.).
# Copies web/ source + dereferences the data/ symlink into one deployable folder.
# Stamps dist/sw.js with a content hash of the precached shell files so the
# service worker cache is automatically invalidated on every deploy.
build:
	rm -rf dist
	cp -rL web/. dist/
	@HASH=$$(python3 -c "import hashlib,sys; h=hashlib.sha256(); \
	  [h.update(open(f,'rb').read()) for f in sys.argv[1:]]; \
	  print(h.hexdigest()[:8])" \
	  dist/index.html dist/app.js dist/office.css dist/manifest.json \
	  dist/data/offices.json dist/data/collects.json dist/data/season_bounds.json); \
	sed -i '' "s/pwc-v1/pwc-$$HASH/" dist/sw.js; \
	echo "dist/ ready (cache: pwc-$$HASH, $$(find dist -type f | wc -l | tr -d ' ') files)"

# Verify dist/ has everything the app needs before deploying.
check-dist: build
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

# Validate extracted lectionary data against the ACC HTML source.
# Requires network access; run manually before a data re-extraction.
validate:
	python3 tools/validate_lectionary.py

# Run E2E tests locally against web/ (default — no bandwidth cost).
test-web:
	npx playwright test

# Deploy — sync dist/ to S3 (requires AWS_PROFILE or ambient credentials).
# Set BUCKET in environment or pass: make deploy BUCKET=my-bucket-name
deploy: check-dist
	# sw.js must be no-cache so browsers always revalidate after a deploy.
	# Sync everything except sw.js, then upload sw.js with explicit header.
	aws s3 sync dist/ s3://$(BUCKET)/ --delete --exclude "sw.js"
	aws s3 cp dist/sw.js s3://$(BUCKET)/sw.js \
	  --cache-control "no-cache, no-store" \
	  --content-type "application/javascript"
	aws cloudfront create-invalidation --distribution-id $(CF_DISTRIBUTION_ID) --paths "/*"

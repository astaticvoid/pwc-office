-include .env
export

.PHONY: test test-smoke test-seasonal test-full build check-dist serve serve-dist deploy test-web

PORT      ?= 8080
PORT_DIST ?= 8081

# Unit tests — no API key needed, always fast.
test:
	go test ./...

# Smoke — 4 LLM evaluations of representative days. Requires ANTHROPIC_API_KEY.
test-smoke:
	go test -tags e2e_smoke -v -timeout 10m ./e2e/...

# Seasonal — one MP+EP per liturgical season, parallel LLM evaluations.
test-seasonal:
	go test -tags e2e_seasonal -v -timeout 30m ./e2e/...

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

# Run E2E tests locally against web/ (default — no bandwidth cost).
test-web:
	npx playwright test

# Deploy — sync dist/ to S3 (requires AWS_PROFILE or ambient credentials).
# Set BUCKET in environment or pass: make deploy BUCKET=my-bucket-name
deploy: check-dist
	aws s3 sync dist/ s3://$(BUCKET)/ --delete
	aws cloudfront create-invalidation --distribution-id $(CF_DISTRIBUTION_ID) --paths "/*"

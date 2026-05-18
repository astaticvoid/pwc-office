-include .env
export

.PHONY: test test-smoke test-seasonal test-full build check-dist serve serve-dist deploy test-web test-web-local

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

# Assemble dist/ for static deployment (Netlify, S3, etc.).
# Copies web/ source + dereferences the data/ symlink into one deployable folder.
build:
	rm -rf dist
	cp -rL web/. dist/
	@echo "dist/ ready ($$(find dist -type f | wc -l | tr -d ' ') files)"

# Verify dist/ has everything the app needs before deploying.
check-dist: build
	@python3 tools/check_dist.py

# Serve web/ directly for local development (http://localhost:8080/).
# No build step — web/data symlink is followed live.
serve:
	python3 -m http.server 8080 --directory web

# Build and serve dist/ as it will appear when deployed (http://localhost:8081/).
# Required for E2E tests and pre-deploy checks.
serve-dist: check-dist
	python3 -m http.server 8081 --directory dist

# Run E2E tests against the live Netlify deployment.
test-web:
	npx playwright test

# Build dist/ then run E2E tests against a local server.
test-web-local: check-dist
	BASE_URL=http://localhost:8081 npx playwright test

# Build and deploy dist/ to Netlify.
# Icon: place sources/pwc-cover.png (gitignored) before deploying.
deploy: check-dist
	@if [ -f sources/pwc-cover.png ]; then \
	  cp sources/pwc-cover.png dist/apple-touch-icon.png; \
	  cp sources/pwc-cover.png dist/icon.png; \
	  echo "icon: sources/pwc-cover.png injected"; \
	else \
	  echo "⚠ icon: sources/pwc-cover.png not found — deploying without icon"; \
	fi
	netlify deploy --dir=dist --prod

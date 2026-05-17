-include .env
export

.PHONY: test test-smoke test-seasonal test-full build check-dist serve serve-dist deploy

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

# Serve the source tree for local development (http://localhost:8080/web/).
serve:
	python3 -m http.server 8080

# Build and serve dist/ exactly as it will appear when deployed (http://localhost:8081/).
serve-dist: check-dist
	python3 -m http.server 8081 --directory dist

# Build and deploy dist/ to Netlify.
deploy: check-dist
	netlify deploy --dir=dist --prod

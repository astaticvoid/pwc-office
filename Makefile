-include .env
export

.PHONY: test test-smoke test-seasonal test-full

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

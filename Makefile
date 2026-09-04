-include .env
export

.PHONY: lint-css check-conservation venv extract-baseline extract-diff invalidate-production test test-unit test-smoke test-seasonal test-full test-tools build check-dist check-integrity check-text audit-errata intake-year serve serve-fg serve-dist stop status restart deploy test-web validate fetch-sources extract mobile-sync mobile-bump-version mobile-ios mobile-android qa lint lint-js lint-ts lint-py test-mutations hooks slice-readings audit-copyright

PORT      ?= 8080
PORT_DIST ?= 8081

# Python interpreter. Prefer the project venv (`make venv`) when present, so no
# shell activation is needed; fall back to the ambient python3 (CI, which gets a
# clean setup-python interpreter). Homebrew's python3 is externally managed
# (PEP 668) and refuses direct installs, so the venv is the supported path.
PYTHON := $(shell [ -x .venv/bin/python3 ] && echo .venv/bin/python3 || echo python3)

# Ruff binary — same venv-first, ambient-fallback policy as PYTHON. CI installs
# `ruff` into the runner's python3, so it falls back to the ambient ruff.
RUFF := $(shell [ -x .venv/bin/ruff ] && echo .venv/bin/ruff || echo ruff)

# Install the repo's git hooks. commit-msg enforces the no-Co-Authored-By rule.
# Uses core.hooksPath so the hooks live in-tree (githooks/, versioned) rather
# than in a local .git/hooks that no one can see. Idempotent — safe to run at
# any time, and needed once per fresh clone (CI is unaffected).
hooks:
	git config core.hooksPath githooks
	@echo "Git hooks installed: core.hooksPath=githooks (commit-msg, pre-commit)."

# Create the venv and install Python dependencies.
venv:
	python3 -m venv .venv
	.venv/bin/python3 -m pip install --quiet --upgrade pip
	.venv/bin/python3 -m pip install --quiet pymupdf pytest ruff
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
# Corrections run after the extractors because they consume the .build/ stage-1
# artifacts, which is a data dependency rather than a rule anyone has to hold in
# their head. The ordering hazard this comment used to describe is gone (#49):
# convert_lectionary.py writes .build/lectionary/ and so cannot discard published
# corrections, and validate_corrections.py names the pre-correction artifacts and
# so cannot see corrected output whatever order things run in. Verified by running
# validate after apply — the order that used to report every correction as stale.
	$(PYTHON) tools/validate_corrections.py
	$(PYTHON) tools/apply_corrections.py
	$(PYTHON) tools/update_extract_manifest.py
# Auto-commit the extraction, but only when data/ is its OWN repository — the
# separate-data-repo setup this was written for. `rev-parse --git-dir` succeeds
# from anywhere inside any repo, so in a normal checkout it found *this* repo and
# the `git add -A` that followed staged the entire working tree, committing
# unrelated in-progress work under an "extraction" message. Comparing toplevels
# is the question actually being asked: is data/ a repo root?
	@top=$$(git -C data/ rev-parse --show-toplevel 2>/dev/null); \
	 if [ -z "$$CI" ] && [ -n "$$top" ] && \
	    [ "$$top" = "$$(cd data/ && pwd -P)" ]; then \
	   git -C data/ add -A && git -C data/ commit -m "extraction $(shell date +%Y-%m-%d)" || true; \
	 fi

# Suppress Node 22 localStorage experimental warning (render.js has polyfill).
NODE_OPTIONS = --localstorage-file=/tmp/pwc-ls.json

# Unit tests — no API key needed, always fast.
test-unit:
	npm test

# Lint — JS via ESLint (eslint.config.js), type-check via tsc --checkJs over
# web/ (tsconfig.web.json, #147), Python via Ruff (ruff.toml).
# Fast and part of `make test`, so a formatting or dead-code slip cannot land.
# Configs are curated low-noise: advice is to ADD a rule only when it catches
# a real class of mistake and the existing code passes it.
lint-js:
	npx eslint .

lint-ts:
	npx tsc -p tsconfig.web.json

lint-py:
	$(RUFF) check tools/

lint-css:
	npx stylelint "web/*.css"

lint: lint-js lint-ts lint-py lint-css

# check-integrity runs first and fails fast: it catches data/ that no longer
# matches the manifest, which is the state left by editing an extractor and
# forgetting to re-run the pipeline. A commit was once made in exactly that state
# because the check was a separate command nobody ran (#50).
test: lint check-integrity test-unit test-tools qa test-mutations

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
	rm -rf dist/data/translations
	rm -rf dist/data/lectionary
	@if [ -n "$$EVAL_AUTH_TOKEN" ]; then \
		echo "Injecting EVAL_AUTH_TOKEN into scripture-provider.js"; \
		sed -i.bak "s|__EVAL_AUTH_TOKEN__|$$EVAL_AUTH_TOKEN|g" dist/scripture-provider.js && \
		rm dist/scripture-provider.js.bak; \
	fi
	@if [ -n "$$API_ORIGIN" ]; then \
		echo "Injecting API_ORIGIN into scripture-provider.js"; \
		sed -i.bak "s|__API_ORIGIN__|$$API_ORIGIN|g" dist/scripture-provider.js && \
		rm dist/scripture-provider.js.bak; \
	fi
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
	@nohup $(PYTHON) tools/local_server.py $(PORT) --directory web > /tmp/pwc-server.log 2>&1 & echo $$! > $(PID_FILE)
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
	$(PYTHON) tools/local_server.py $(PORT) --directory web

# Build and serve dist/ as it will appear when deployed (http://localhost:$(PORT_DIST)/).
# Required for E2E tests and pre-deploy checks.
# Override port: make serve-dist PORT_DIST=9001
serve-dist: check-dist
	@$(call kill_port,$(PORT_DIST))
	@sleep 0.3
	$(PYTHON) tools/local_server.py $(PORT_DIST) --directory dist

# Unit tests for Python extraction tools (pytest comes from `make venv`).
test-tools:
	$(PYTHON) -m pytest tools/tests/ -v

# Check data/offices.json against the errata: every line break it asks for
# present, every wording divergence declared. Reports; does not gate. Run it
# whenever docs/errata/ or the office_text corrections change.
audit-errata:
	$(PYTHON) tools/audit_errata.py

# Worklist for a new lectionary year: every decision the converter cannot
# derive from the CSV. Reports; `make extract` is what gates. First thing to
# run after dropping a new bas_short_YYYY.csv into sources/.
# See docs/runbooks/lectionary-year-intake.md.
intake-year:
	$(PYTHON) tools/intake_year.py

# Scan extracted JSON files for PDF extraction artifacts (missing spaces, etc.).
check-text:
	$(PYTHON) tools/check_text_quality.py

# Account for every printed line against the shipped data, and every shipped
# line against the page (#94). The only check that compares the data to the
# source rather than to itself or to a hardcoded expectation, so it is the only
# one that can see text leaving the pipeline or being invented in it.
#
# Needs sources/ and .build/ as well as data/, unlike the rest of qa: it reads
# the pre-correction artifact to tell an extraction defect from an authorised
# correction. Both are gitignored, so `make fetch-sources && make extract` has
# to have run — which is what CI does before `make test`, and what
# `make check-integrity` already assumes for data/.
check-conservation:
	$(PYTHON) tools/check_conservation.py --chain offices
	$(PYTHON) tools/check_conservation.py --chain psalter
	$(PYTHON) tools/check_conservation.py --chain fats

# Liturgical quality gate — runs validators and coherence scorer.
# Used by 'make test' so every PR checks liturgical coherence.
qa:
	@echo "=== Source conservation (offices) ==="
	@$(PYTHON) tools/check_conservation.py --chain offices
	@echo "=== Source conservation (psalter) ==="
	@$(PYTHON) tools/check_conservation.py --chain psalter
	@echo "=== Source conservation (fats) ==="
	@$(PYTHON) tools/check_conservation.py --chain fats
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
	@echo "=== Rubric repeats and cue consistency ==="
	@node tools/audit_rubric_repeats.cjs
	@echo "=== Accessibility ==="
	@node tools/audit_a11y.cjs

# Mutation tests for the qa rules themselves: apply a targeted violation to a
# temp copy of the data and assert the rule actually fires. Catches a rule
# quietly losing the ability to fail — the failure mode in #70 and #71 — at
# the commit that breaks it instead of at the next manual audit.
test-mutations:
	@echo "=== Rule mutation tests ==="
	@node tools/test_rule_mutations.cjs

# Validate extracted lectionary data against the ACC HTML source.
# Requires network access; run manually before a data re-extraction.
validate: check-text
	$(PYTHON) tools/validate_lectionary.py

# Run E2E tests locally against web/ (default — no bandwidth cost).
test-web:
	npx playwright test

# ── Verifying an extractor change ────────────────────────────────────────────
# The safety net for touching tools/extract_*.py. Capture a baseline, make the
# change, then diff — and say what the expected node count is:
#
#   make extract-baseline
#   ...edit tools/extract_offices.py...
#   make extract-diff EXPECT=0        # a refactor must change nothing
#   make extract-diff                 # or just look at what moved
#
# The baseline comes from a FULL pipeline run, which this target guarantees by
# depending on `extract`. Before #48 a standalone extract_offices.py wrote a
# complete-looking data/offices.json whose _shared was missing three blocks, and
# diffing against it produced confident nonsense; the stages now write separate
# artifacts, so an intermediate can no longer be mistaken for the finished file.
BASELINE = .build/baseline

extract-baseline: extract
	@mkdir -p $(BASELINE)
	@cp data/offices.json $(BASELINE)/offices.json
	@echo "Baseline captured in $(BASELINE)/ — now make your change, then 'make extract-diff'"

extract-diff:
	@test -f $(BASELINE)/offices.json || \
	  (echo "No baseline. Run 'make extract-baseline' before changing the extractor."; exit 1)
	@$(MAKE) extract --no-print-directory CI=1 >/dev/null
	@$(PYTHON) tools/diff_extraction.py $(BASELINE)/offices.json data/offices.json \
	  $(if $(EXPECT),--expect $(EXPECT),)

# Verify data/ files match the last extraction — exits 1 if any file was edited directly.
check-integrity:
	$(PYTHON) tools/check_data_integrity.py

# Mobile — build dist/ then sync web assets into iOS and Android native projects.
# After mobile-sync, open the native project in Xcode / Android Studio to build and archive.
# The synced native web dirs are gitignored, so staleness is invisible to git:
# check_mobile_sync.py is the guard that keeps an archive from bundling an old dist/
# (runbook: docs/runbooks/ios-testflight-ship.md).
mobile-sync: check-dist
	npx cap sync
	$(PYTHON) tools/check_mobile_sync.py

# Bump the iOS build number (CFBundleVersion). TestFlight rejects a build number
# already uploaded, so each ship needs a fresh one — committed in the pbxproj.
mobile-bump-version:
	$(PYTHON) tools/bump_ios_version.py

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
# The steps are enforced, not merely recommended: promote refuses a release that
# does not name the current HEAD or has not passed test-staging, and aborts if
# the release is not actually in S3. PROMOTE_FORCE=1 bypasses the first two.
#
# Rollback: make rollback    — swaps to previous release

# A release name is what promote and rollback reason about later, so it has to be
# honest about what went into it. An uncommitted tree gets a -dirty suffix rather
# than a hard block: staging is exactly where uncommitted work belongs, and the
# tree is dirty by default right after `make extract` (the manifest timestamp).
# promote refuses a -dirty release unless forced, which is where it matters (#53).
GIT_DIRTY := $(shell git status --porcelain 2>/dev/null | head -1)
RELEASE = $(shell date -u +%Y-%m-%dT%H%M%SZ)-$(shell git rev-parse --short HEAD)$(if $(GIT_DIRTY),-dirty,)

slice-readings:
	node tools/slice_lectionary_readings.js
	node tools/slice_daily_payload.js

audit-copyright:
	$(PYTHON) tools/audit_copyright_leak.py --dist-dir dist

deploy-staging: check-integrity check-dist audit-copyright slice-readings
	aws s3 sync dist/ s3://$(BUCKET)/releases/$(RELEASE)/ --delete
	# Sync private sliced calendar and lectionary readings (protected by CloudFront gate function)
	aws s3 sync .build/private/ s3://$(BUCKET)/private/ \
	  --cache-control "max-age=86400"
	# Everything on staging gets a 1-minute cache. Staging exists to be deployed
	# to and looked at immediately, so production-shaped TTLs are wrong here: the
	# data files were cached for an hour and the images for a day, which meant a
	# re-extraction could be verified as correct on the CDN while the browser
	# kept serving the previous copy. Production caching is unaffected — the
	# releases/ objects below carry no cache-control and promote swaps the
	# CloudFront origin path.
	#
	# Wiped first because `aws s3 sync` skips files whose content is unchanged,
	# and cache-control is only written on upload — so an object keeps whatever
	# TTL it was first uploaded with, forever. Changing the header above without
	# this would leave every unchanged file on its old TTL. Staging is ~11MB, so
	# re-uploading it wholesale each deploy is cheaper than reasoning about which
	# objects carry stale metadata.
	aws s3 rm s3://$(BUCKET)/staging/ --recursive --only-show-errors
	aws s3 sync dist/ s3://$(BUCKET)/staging/ --delete \
	  --exclude "*" \
	  --include "*.html" --include "*.js" --include "*.css" \
	  --include "*.json" --include "*.png" --include "*.svg" --include "*.ico" \
	  --include "*.woff2" \
	  --exclude "sw.js" \
	  --cache-control "max-age=60"
	# sw.js: never cache — kill-switch must always be fresh. The exclude above
	# must come after --include "*.js", since s3 filters apply in order and the
	# last match wins; ahead of it, the *.js include would claim sw.js and this
	# sync would then skip it as unchanged, leaving the kill-switch cacheable.
	aws s3 sync dist/ s3://$(BUCKET)/staging/ \
	  --exclude "*" --include "sw.js" \
	  --cache-control "max-age=0, no-store"
	@echo "Staging deployed: $(RELEASE)"
	@echo "$(RELEASE)" > .deploy-latest

# On success, record which release was verified. promote requires this to name
# the release it is about to ship, so a deploy that was never smoke-tested — or
# one superseded by a later deploy-staging — cannot reach production (#52).
test-staging:
	@test -f .deploy-latest || (echo "Nothing deployed. Run 'make deploy-staging' first."; exit 1)
	BASE_URL=https://$(STAGING_DOMAIN) \
	  npx playwright test --grep "@smoke"
	$(PYTHON) tools/audit_copyright_leak.py --url https://$(STAGING_DOMAIN)
	@cp .deploy-latest .staging-tested
	@echo "Staging verified: $$(cat .staging-tested)"

# Full regression against staging — every e2e spec, not just @smoke.
# Slower (~3 min); run before a risky promote or after UI-touching changes.
test-staging-full:
	BASE_URL=https://$(STAGING_DOMAIN) \
	  npx playwright test

# Gates, all bypassable with PROMOTE_FORCE=1:
#   - the release names the current HEAD, so a deploy from days ago cannot ship
#     silently after the code moved on
#   - test-staging passed for that exact release
#   - coherence is at threshold
# The S3 existence check below is not a policy gate and always runs.
promote:
	@test -f .deploy-latest || (echo "Run deploy-staging first"; exit 1)
	@if [ -z "$$PROMOTE_FORCE" ]; then \
	  RELEASE=$$(cat .deploy-latest); HEAD_SHA=$$(git rev-parse --short HEAD); \
	  case "$$RELEASE" in \
	    *-$$HEAD_SHA) ;; \
	    *-$$HEAD_SHA-dirty) \
	       echo "Promotion blocked — $$RELEASE was built from an uncommitted tree."; \
	       echo "Its name records $$HEAD_SHA but its contents do not match that commit."; \
	       echo "Commit, re-deploy, or PROMOTE_FORCE=1 to ship it anyway."; exit 1;; \
	    *) echo "Promotion blocked — .deploy-latest is $$RELEASE but HEAD is $$HEAD_SHA."; \
	       echo "That release was built from different code. Re-run 'make deploy-staging',"; \
	       echo "or PROMOTE_FORCE=1 to ship it anyway."; exit 1;; \
	  esac; \
	  if [ ! -f .staging-tested ] || [ "$$(cat .staging-tested)" != "$$RELEASE" ]; then \
	    echo "Promotion blocked — $$RELEASE has not passed 'make test-staging'."; \
	    echo "Run it, or PROMOTE_FORCE=1 to skip."; exit 1; \
	  fi; \
	  echo "Checking coherence score..."; \
	  node tools/validate_office.cjs --json > /tmp/pwc-promote-val.json 2>/dev/null; \
	  node tools/audit_office.cjs --json > /tmp/pwc-promote-aud.json 2>/dev/null; \
	  COHERENCE_THRESHOLD=100 node tools/coherence_score.cjs --check-promote /tmp/pwc-promote-val.json /tmp/pwc-promote-aud.json \
	    || (echo "Promotion blocked — score below 100. Fix issues or use PROMOTE_FORCE=1 to bypass."; \
	        rm -f /tmp/pwc-promote-val.json /tmp/pwc-promote-aud.json; exit 1); \
	  rm -f /tmp/pwc-promote-val.json /tmp/pwc-promote-aud.json; \
	fi
	@RELEASE=$$(cat .deploy-latest) && \
	(aws s3 ls s3://$(BUCKET)/releases/$$RELEASE/index.html >/dev/null 2>&1 || \
	  (echo "Promotion aborted — s3://$(BUCKET)/releases/$$RELEASE/ has no index.html."; \
	   echo "The release is missing or incomplete; swapping to it would break production."; \
	   exit 1)) && \
	aws cloudfront get-distribution-config --id $(CF_DISTRIBUTION_ID) \
	  > /tmp/cf-config.json && \
	jq '(.DistributionConfig.Origins.Items[] | select(.Id != "S3-Private")).OriginPath = "/releases/'"$$RELEASE"'" | .DistributionConfig' \
	  /tmp/cf-config.json > /tmp/cf-new.json && \
	aws cloudfront update-distribution --id $(CF_DISTRIBUTION_ID) \
	  --distribution-config file:///tmp/cf-new.json \
	  --if-match $$(jq -r '.ETag' /tmp/cf-config.json) > /dev/null && \
	echo "Promoted $$RELEASE to production" && \
	$(MAKE) invalidate-production --no-print-directory

# CloudFront caches by URL path, not by origin path, so swapping the origin in
# promote does not on its own change what anyone is served. Objects under
# releases/ carry no cache-control and the distribution uses Managed-
# CachingOptimized (24h default), so without this a promotion stays invisible
# for up to a day. Split out so a rollback can reuse it.
invalidate-production:
	@echo "Invalidating production cache..."
	@ID=$$(aws cloudfront create-invalidation --distribution-id $(CF_DISTRIBUTION_ID) \
	  --paths "/*" --query 'Invalidation.Id' --output text) && \
	echo "Invalidation $$ID created (typically completes in 1-3 min)."
	@echo "Note: pwc-deploy cannot read invalidation status (cloudfront:GetInvalidation"
	@echo "is denied), so this cannot be waited on — check the site in a minute or two."

# Rolls back to the newest release strictly older than the one currently live,
# rather than "second newest in the bucket" — those differ as soon as a deploy
# happens after the bad promote, which is a normal way to discover the problem.
# The target is checked for an index.html first: rollback runs when something is
# already wrong, so swapping to an incomplete prefix is the worst possible
# outcome. See #53.
rollback:
	@CURRENT=$$(aws cloudfront get-distribution-config --id $(CF_DISTRIBUTION_ID) \
	  --query 'DistributionConfig.Origins.Items[?Id!=`S3-Private`].OriginPath | [0]' --output text \
	  | sed 's:^/releases/::') && \
	echo "Currently live: $$CURRENT" && \
	PREV=$$(aws s3 ls s3://$(BUCKET)/releases/ | awk '{print $$2}' | sed 's:/$$::' \
	  | grep -v '^$$' | sort | awk -v cur="$$CURRENT" '$$0 < cur' | tail -1) && \
	test -n "$$PREV" || (echo "No release older than $$CURRENT — nothing to roll back to"; exit 1) && \
	(aws s3 ls s3://$(BUCKET)/releases/$$PREV/index.html >/dev/null 2>&1 || \
	  (echo "Rollback aborted — releases/$$PREV/ has no index.html and is incomplete."; \
	   exit 1)) && \
	echo "Rolling back to $$PREV" && \
	aws cloudfront get-distribution-config --id $(CF_DISTRIBUTION_ID) \
	  > /tmp/cf-config.json && \
	jq '(.DistributionConfig.Origins.Items[] | select(.Id != "S3-Private")).OriginPath = "/releases/'"$$PREV"'" | .DistributionConfig' \
	  /tmp/cf-config.json > /tmp/cf-new.json && \
	aws cloudfront update-distribution --id $(CF_DISTRIBUTION_ID) \
	  --distribution-config file:///tmp/cf-new.json \
	  --if-match $$(jq -r '.ETag' /tmp/cf-config.json) > /dev/null && \
	echo "Rolled back to $$PREV"
	@$(MAKE) invalidate-production --no-print-directory

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

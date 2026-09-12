# ADR 0028: Diocese Infrastructure Cutover and API v3 Data Pipeline

## Status
Accepted

## Context
Historically, the application deployed to Amazon Web Services (AWS) using S3 buckets for static hosting and private readings storage, CloudFront for CDN distribution, and CloudFront Functions for basic auth and temporal gating (ADR 0006, ADR 0024).

As the project reached diocesan adoption and prepared for authorized synod evaluation under the *Pray Without Ceasing* domain (`praywithoutceasing.ca`), several architectural requirements emerged:
1. **Official Ownership & Governance:** Hosting and data storage needed to cut over from personal developer infrastructure to official diocesan infrastructure.
2. **Modern Edge Stack:** Cloudflare Pages (with edge Functions for evaluation access gating), Cloudflare Workers (for API v3 backend-for-frontend requests), and Cloudflare R2 (for zero-egress, S3-compatible private storage).
3. **API v3 Slicing Efficiency:** ADR 0025 introduced the unified calendar + scripture BFF payload model (`/api/v3/calendar`). The legacy v1 readings slicer (`tools/slice_lectionary_readings.js`) generated hundreds of redundant files that bloated build artifacts and R2 storage.
4. **Clean Environmental Separation:** Personal AWS infrastructure and personal Cloudflare development domains must remain isolated to service existing legacy mobile evaluation clients until imminent teardown, and must never be touched or updated by diocesan builds.

## Decision

### 1. Default Deployment Target: `diocese`
`Makefile` establishes `DEPLOY_TARGET ?= diocese` as the default target.
- Standard targets (`make deploy-staging`, `make test-staging`, `make promote`, `make test-prod`) operate unconditionally against the diocese Cloudflare environment:
  - Web SPA: Cloudflare Pages (`praywithoutceasing.ca`, `staging.praywithoutceasing.ca`).
  - API BFF: Cloudflare Workers (`api.praywithoutceasing.ca`, `api-staging.praywithoutceasing.ca`).
  - Private Scripture Storage: Cloudflare R2 (`pwc-private-data`).
- The personal developer environment is isolated behind `DEPLOY_TARGET=personal` and is preserved only for maintenance and eventual teardown.

### 2. Streamlined API v3 Slicing Pipeline
- `make slice-readings` executes solely `tools/slice_daily_payload.js` (API v3).
- The legacy `tools/slice_lectionary_readings.js` (v1 readings) is retired from the active pipeline.
- Sliced calendar payloads are generated deterministically into `.build/private/calendar/v3/{nrsvue,kjv}/`: volatile build timestamps (`fetchedAt`) and build commit hashes are omitted from the static JSON, and `writeIfChanged` avoids modifying untouched files.
- `make sync-r2` syncs directly to `s3://pwc-private-data/calendar/v3/` on Cloudflare R2 using `--size-only --delete`.
- Unchanged deployments perform 0 writes to R2 in ~1 second. Total stored footprint is ~109 MB across 1,588 files, eliminating legacy v1/v2 duplication and staying well within Cloudflare R2's free tier thresholds (10 GB storage, 1,000,000 Class A writes/month, 10,000,000 Class B reads/month, zero egress fees).

### 3. Complete Legacy Isolation
- AWS S3 syncs (`deploy-aws-staging`, `deploy-aws-prod`), CloudFront cache invalidations (`invalidate-production`), and legacy origin-swap rollbacks (`rollback`, `deploy`) are guarded with strict checks:
  ```makefile
  @if [ "$(DEPLOY_TARGET)" != "personal" ]; then ... exit 1; fi
  ```
- Diocesan deployments make zero network calls to AWS.

### 4. Gated Evaluation Access
- In accordance with copyright and evaluation requirements, both Pages (`infra/cloudflare/pages-functions/_middleware.js`) and Workers (`infra/cloudflare/worker.js`) enforce fail-closed HTTP Basic Authentication and secure evaluation session cookies (`pwc-auth=1`).
- Unauthenticated requests to Pages receive an HTTP 401 response with an authorized takedown notice and an interactive Evaluation Sign-In modal (ADR 0027).

## Consequences

### Positive
- **Zero Accidental AWS Footprint:** Diocesan developers cannot inadvertently trigger AWS billing or modify personal dev infrastructure.
- **Fast Deployments:** Eliminating legacy file uploads reduces R2 sync duration from minutes to seconds.
- **Storage Hygiene:** Storing only active v3 payloads keeps R2 utilization minimal and clean.
- **High Coherence & Quality Assurance:** Test gates (`test_staging.cjs` and `test_prod.cjs`) continuously verify isolation, authentication, and correct liturgical DOM rendering.

### Negative
- **Manual Teardown Required:** The legacy personal AWS stack (S3 bucket, CloudFront distribution) remains deployed until the remaining evaluation clients update, requiring a deliberate teardown step once all clients migrate.

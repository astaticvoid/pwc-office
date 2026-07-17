# ADR 0006: Versioned directory deploys with staged promotion

## Status
Proposed

## Context
The project deploys as a static site to S3 + CloudFront. The deploy mechanism
must ensure that users see a **consistent** set of assets — an old `index.html`
with new `offices.json` can produce broken pages. It must be **verifiable** —
the deployed content must pass a smoke test before serving traffic. It must be
**rollback-able** — reverting to a previous deploy must be a single operation.

CloudFront does not provide atomic origin switching. An origin-path change takes
5–15 minutes to propagate to all edge locations. During propagation, different
edge nodes may serve different origin paths. The deploy strategy must tolerate
this window — the system must work correctly regardless of which version any
individual request hits.

## Decision
Deploy each build to a **versioned, immutable release directory** on S3, then
promote via a **CloudFront origin-path change**. Immutable assets with consistent
versioning guarantee that any combination of old-path + new-path assets is still
internally consistent.

### Directory structure
```
s3://bucket/
  releases/
    v2026-07-16T120000Z-abc1234/    # Build artifacts (immutable)
    v2026-07-15T110000Z-def5678/    # Previous deploy (retained for rollback)
  staging/                           # Latest build, overwritten per deploy
```

Release directories use ISO-8601 timestamps (`vYYYY-MM-DDTHHmmssZ-shorthash`)
so that lexicographic sort == chronological sort, making "previous release" a
deterministic `ls | sort | tail -2 | head -1`.

### Deploy workflow

1. **`make build`** — assembles `dist/` as today.
2. **`make deploy-staging`** — uploads `dist/` to
   `s3://bucket/releases/vTIMESTAMP-HASH/`. Then copies (not re-uploads) that
   S3 prefix to `s3://bucket/staging/` via `aws s3 sync` with `--delete` on
   the staging prefix only.
3. **`make test-staging`** — runs Playwright smoke tests against the staging
   CloudFront distribution (a separate distribution or a separate origin path
   pointing at `/staging/`).
4. **`make promote`** — updates the production CloudFront distribution's
   `OriginPath` from `/releases/vOLD` to `/releases/vNEW`.

### Propagation window (5–15 minutes)
During the origin-path propagation:
- Users hitting an old edge node receive all assets from `vOLD`.
- Users hitting a new edge node receive all assets from `vNEW`.
- Each release directory is a complete, self-consistent build — every asset
  within it references files in the same directory. An `index.html` from `vNEW`
  will never load `offices.json` from `vOLD` because all asset references are
  relative or version-prefixed.
- The service worker (ADR 0007) uses version-manifest hashing: `version.json`
  within each release directory carries the hashes for that directory's data
  files. Even if a user hits edge nodes serving different origin paths for
  different requests (extremely unlikely within a single page-load session),
  the hashes will be internally consistent because each release directory is
  self-contained.

This is **eventually consistent deployment with internal consistency at every
edge node** — not atomic, but safe.

### Rollback
```bash
make rollback
```
Reads the penultimate release directory from S3 (lexicographic sort by timestamp
prefix) and sets the CloudFront `OriginPath` to it. The same 5–15 minute
propagation applies.

### Lifecycle
An S3 lifecycle policy deletes release directories older than 10 builds. Tagged
releases (version tags from git) are exempt from expiry. Staging is always
overwritten — no lifecycle needed.

### Interaction with existing `make deploy`
The existing single-command `make deploy BUCKET=... CF_DISTRIBUTION_ID=...` is
replaced by the three-stage workflow. The old target is removed during
implementation; `make deploy` becomes an alias for `make deploy-staging` with a
prominent notice that `make promote` is the second required step.

### In-flight SPA sessions
A user with the app open during a deploy will, on their next data fetch
(`version.json` per ADR 0007), detect that the stored data hash differs from the
manifest. The app can prompt a reload. If the user does not reload, they
continue using their cached data until their next visit — the old shell + old
data is internally consistent because it came from a single release directory.

## Consequences

### Positive
- Every release directory is a complete, self-consistent build. No cross-version
  asset mixing, even during CloudFront propagation.
- Staging smoke tests exercise the exact artifacts that will serve production
  traffic (byte-identical via S3 copy, not re-upload).
- Rollback is one command; any previous release is immediately available.
- No `--delete` on production content. Releases accumulate until lifecycle
  policy removes them.

### Negative
- CloudFront origin-path updates are not instantaneous. The 5–15 minute
  propagation window means deploys are not real-time.
- A second CloudFront distribution (or a separate origin path) is needed for
  staging smoke tests, adding minor operational setup.
- The ISO-8601 timestamp naming convention must be followed exactly for
  rollback sort correctness.

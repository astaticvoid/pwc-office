# ADR 0024: CloudFront edge temporal gating and private S3 distribution for copyrighted scripture

## Status
Proposed

## Context
ADR 0023 established the vendor-neutral `IScriptureProvider` architecture and the legal requirement for a server-side gate that:
1. Only returns scripture readings for an appointed lectionary date.
2. Enforces a strict temporal window of $\pm 30$ days from the current date.
3. Completely prevents client-side retrieval of whole books or unappointed passages.

PWC's production infrastructure is deployed on AWS (S3 and CloudFront) via a versioned directory and origin-path promotion workflow (ADR 0006) driven by `Makefile` targets (`deploy-staging`, `promote`, `rollback`). Introducing an external compute platform (such as Cloudflare Workers) creates multi-vendor split-brain deployments, cross-origin CORS overhead, and fragmented rollback procedures.

However, implementing this inside CloudFront requires solving three operational challenges:
1. **OriginPath Collision**: ADR 0006 dynamically points CloudFront's `OriginPath` to `/releases/${RELEASE}`. If private scripture readings are placed at `s3://${BUCKET}/private/readings/`, CloudFront would prepend `OriginPath`, looking for `/releases/${RELEASE}/private/...` and returning 404.
2. **Direct S3 Bypass & Path Traversal**: If CloudFront can access the S3 bucket via Origin Access Control (OAC), direct viewer requests to `/private/*` or malicious `translation=../../` query parameters could bypass the temporal gate or traverse directories.
3. **Timezone Skew Near Midnight**: The Earth spans 26 timezones (UTC-12 to UTC+14). A user in New Zealand (UTC+13) or Hawaii (UTC-10) requesting a reading 30 days away could be 31 days away in UTC time, causing false-positive 403 rejections under a rigid 30-day UTC comparison.

## Decision
Implement the scripture service using a **CloudFront Function** viewer-request gate backed by **pre-sliced daily lectionary JSON files** served from a dedicated private S3 origin.

### 1. Build Pipeline Pre-Slicing (`tools/slice_lectionary_readings.js`)
Rather than running a heavy Bible parsing engine dynamically at edge runtime, the pipeline pre-slices the readings during `make extract` / build:
- Iterates over all dates in `data/lectionary/*.json`.
- Traverses both `morning` and `evening` offices, including all `alternate` offices (31 dates across the year).
- Handles multi-lesson days (`lessons_pick: 2`) and internal alternative choices (`" or "` citations), extracting all potential readings so choices remain choices (ADR 0016).
- Formats verses into structured JSON with paragraph break markup (from `data/paragraphs.json`).
- Writes `.build/private/readings/v1/nrsvue/YYYY-MM-DD.json`.
- Slices are uploaded to `s3://${BUCKET}/private/readings/v1/nrsvue/`.

### 2. S3 & Distribution Packaging Safeguards
To prevent accidental distribution of full copyrighted Bible texts:
1. **Build Exclusion**: In `Makefile`, `make build` explicitly removes any `dist/data/translations/nrsvue/` directory after copying `web/` assets.
2. **Distribution Verification**: `tools/check_dist.py` asserts that `dist/data/translations/` contains only authorized public domain translations (KJV). If an `nrsvue` folder is found in `dist/`, the build fails immediately.
3. **Private Sync**: Pre-sliced lectionary files are synced from `.build/private/readings/` directly to `s3://${BUCKET}/private/readings/` and are never placed in the public release bundle.

### 3. Dual-Origin CloudFront Architecture
To avoid the `OriginPath` collision with ADR 0006's versioned releases, the CloudFront distribution is configured with two distinct origins:
- **`S3-Releases` Origin**:
  - `OriginPath`: `/releases/${RELEASE}` (updated dynamically by `make promote`).
  - Target of default cache behavior (`*`).
- **`S3-Private` Origin**:
  - `OriginPath`: `""` (fixed root path).
  - Target of cache behavior `/api/*` (routing to Viewer Request gate).
  - Accessible only via Origin Access Control (OAC).

`Makefile` targets (`promote`, `rollback`) are updated to modify `Origins.Items` specifically where `Id == "S3-Releases"`, ensuring the private origin configuration is untouched during releases.

### 4. Direct `/private/*` Access Prohibition
A dedicated CloudFront Cache Behavior is created for path pattern `/private/*`:
- Immediately returns HTTP `403 Forbidden`.
- Directly accessing `/private/readings/v1/nrsvue/YYYY-MM-DD.json` via CloudFront is unconditionally blocked. The only entry point is `/api/v1/readings`.

### 5. CloudFront Function: Viewer Request Gate (`infra/cloudfront-functions/gate-readings.js`)
Associated with the `/api/*` behavior on Viewer Request:

```javascript
function handler(event) {
  var request = event.request;
  var params = request.querystring;

  // 1. Validate date parameter
  if (!params.date || !params.date.value || !/^\d{4}-\d{2}-\d{2}$/.test(params.date.value)) {
    return {
      statusCode: 400,
      statusDescription: 'Bad Request',
      headers: { 'content-type': { value: 'application/json' } },
      body: JSON.stringify({ error: 'Missing or invalid date parameter (YYYY-MM-DD)' })
    };
  }

  // 2. Strict translation parameter allowlist (prevents path traversal)
  var translation = (params.translation && params.translation.value) || 'nrsvue';
  if (translation !== 'nrsvue') {
    return {
      statusCode: 400,
      statusDescription: 'Bad Request',
      headers: { 'content-type': { value: 'application/json' } },
      body: JSON.stringify({ error: 'Unsupported translation. Only nrsvue is served via this endpoint.' })
    };
  }

  // 3. Temporal Gating with 31-day timezone grace buffer
  var dateStr = params.date.value;
  var now = new Date();
  var todayUtc = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  var parts = dateStr.split('-');
  var targetUtc = Date.UTC(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));
  var diffDays = Math.round(Math.abs(targetUtc - todayUtc) / 86400000);

  // 31 days accommodates the 26-hour global timezone offset near midnight
  if (diffDays > 31) {
    return {
      statusCode: 403,
      statusDescription: 'Forbidden',
      headers: {
        'content-type': { value: 'application/json' },
        'cache-control': { value: 'no-store' }
      },
      body: JSON.stringify({
        error: 'Temporal restriction: Readings only available within ±30 days of current date.',
        requestedDate: dateStr,
        daysDifference: diffDays
      })
    };
  }

  // 4. Rewrite URI to fetch the private pre-sliced S3 object
  request.uri = '/private/readings/v1/' + translation + '/' + dateStr + '.json';
  request.querystring = {};
  return request;
}
```

### 6. Cache Policy
- CloudFront edge caches 200 OK responses with `Cache-Control: public, max-age=86400, s-maxage=86400`.
- Out-of-window requests (403 Forbidden) carry `Cache-Control: no-store` to prevent caching temporal rejections once a date enters the active window.
- Custom Error Responses configure `ErrorCachingMinTTL = 0` for 403 and 404 to avoid caching transient S3 misses.

## Consequences

### Positive
- **Zero Additional Hosting Cost**: CloudFront Functions provides 2,000,000 invocations/month permanently free; S3 storage for pre-sliced readings is $< 50\text{ MB}$ ($< \$0.01/\text{month}$).
- **Single Provider & Single Pipeline**: All assets, functions, and data stay within AWS and are managed via PWC's existing `Makefile`.
- **No CORS Overhead**: The API is served on the same origin (`https://pwc.app/api/v1/readings`), eliminating preflight OPTIONS requests and webview CORS restrictions.
- **Ultra-Low Latency**: CloudFront Function executes in $< 1\text{ms}$ with zero cold starts, followed by CDN edge cache delivery.
- **Bulletproof Isolation**: Dedicated S3-Private origin avoids `OriginPath` collisions; `/private/*` public requests are blocked; `dist/` is audited against containing whole copyrighted books.

### Negative
- **Requires Pre-Extraction**: When the lectionary year is intake-processed or updated, sliced readings must be regenerated alongside `data/lectionary/*.json`.
- **CloudFront Dual Origin Setup**: The distribution configuration must declare the second origin (`S3-Private`) and associate the `/api/*` and `/private/*` cache behaviors.

### Neutral / Notes
- Reconciles with ADR 0006: promotion scripts selectively update `S3-Releases` origin path while leaving `S3-Private` origin path fixed.
- The client-side `RemoteScriptureProvider` targets `/api/v1/readings?date=YYYY-MM-DD`.

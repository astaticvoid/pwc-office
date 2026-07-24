# CloudFront Functions

Source of truth for the two CloudFront Functions attached to both the
production (`E75O4QVPI7OH0`) and staging (`E3UNB7ER9KWV8U`) distributions'
`DefaultCacheBehavior`. Before 2026-07-24 these existed only as
console-edited state in AWS with no copy in version control — that's how a
broken cookie check shipped silently for two months.

| Function | Event | Purpose |
|---|---|---|
| `pwc-basic-auth.js` | `viewer-request` | Gate: valid `pwc-auth=1` cookie or valid `Authorization: Basic` header passes through; otherwise 401 + `WWW-Authenticate` challenge. |
| `pwc-set-auth-cookie.js` | `viewer-response` | After `pwc-basic-auth` passes a request authenticated via the `Authorization` header (not yet via cookie), sets `Set-Cookie: pwc-auth=1` (30 days) so subsequent requests/refreshes don't re-prompt. |

CloudFront Functions have no build step — these files are deployed as-is.
There's no Makefile target for this yet (functions change far less often
than the app itself); to push a change:

```bash
export AWS_PROFILE=pwc-office
NAME=pwc-basic-auth   # or pwc-set-auth-cookie
ETAG=$(aws cloudfront describe-function --name "$NAME" --query ETag --output text)
aws cloudfront update-function --name "$NAME" --if-match "$ETAG" \
  --function-config Comment="<keep existing comment>",Runtime=cloudfront-js-2.0 \
  --function-code "fileb://infra/cloudfront-functions/$NAME.js"

# Test before publishing — see `aws cloudfront test-function help` for the
# event-object shape. cloudfront-js-2.0 requires cookies under
# request.cookies / response.cookies, never request/response.headers.cookie
# (that's the exact bug this pair had for two months).
NEWETAG=$(aws cloudfront describe-function --name "$NAME" --query ETag --output text)
aws cloudfront publish-function --name "$NAME" --if-match "$NEWETAG"
```

Publishing to `LIVE` applies immediately to both distributions — there's no
separate staging/production function version, only one shared `LIVE` stage
per function.

// CloudFront Function: Viewer Request handler for /api/readings (ADR 0024).
// Enforces date validation, translation allowlisting, and ±31-day temporal gating.

function handler(event) {
    var request = event.request;
    var method = request.method;

    // 1. Handle CORS preflight requests
    if (method === "OPTIONS") {
        return {
            statusCode: 204,
            statusDescription: "No Content",
            headers: {
                "access-control-allow-origin": { value: "*" },
                "access-control-allow-methods": { value: "GET, OPTIONS" },
                "access-control-allow-headers": { value: "content-type" },
                "access-control-max-age": { value: "86400" }
            }
        };
    }

    // 2. Reject non-GET requests
    if (method !== "GET") {
        return {
            statusCode: 405,
            statusDescription: "Method Not Allowed",
            headers: {
                "content-type": { value: "application/json" },
                "allow": { value: "GET, OPTIONS" },
                "access-control-allow-origin": { value: "*" }
            },
            body: JSON.stringify({ error: "Method not allowed. Use GET." })
        };
    }

    var params = request.querystring;

    // 3. Validate date parameter
    if (!params.date || !params.date.value || !/^\d{4}-\d{2}-\d{2}$/.test(params.date.value)) {
        return {
            statusCode: 400,
            statusDescription: "Bad Request",
            headers: {
                "content-type": { value: "application/json" },
                "access-control-allow-origin": { value: "*" }
            },
            body: JSON.stringify({ error: "Missing or invalid date parameter (YYYY-MM-DD)" })
        };
    }

    // 4. Strict translation parameter allowlist (prevents path traversal)
    var translation = (params.translation && params.translation.value) || "nrsvue";
    if (translation !== "nrsvue") {
        return {
            statusCode: 400,
            statusDescription: "Bad Request",
            headers: {
                "content-type": { value: "application/json" },
                "access-control-allow-origin": { value: "*" }
            },
            body: JSON.stringify({ error: "Unsupported translation. Only nrsvue is served via this endpoint." })
        };
    }

    // 5. Temporal Gating with 31-day timezone grace buffer
    var dateStr = params.date.value;
    var now = new Date();
    var todayUtc = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
    var parts = dateStr.split("-");
    var targetUtc = Date.UTC(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));
    var diffDays = Math.round(Math.abs(targetUtc - todayUtc) / 86400000);

    // 31 days accommodates the 26-hour global timezone offset near midnight
    if (diffDays > 31) {
        return {
            statusCode: 403,
            statusDescription: "Forbidden",
            headers: {
                "content-type": { value: "application/json" },
                "cache-control": { value: "no-store" },
                "access-control-allow-origin": { value: "*" }
            },
            body: JSON.stringify({
                error: "Temporal restriction: Readings only available within ±30 days of current date.",
                requestedDate: dateStr,
                daysDifference: diffDays
            })
        };
    }

    // 6. Rewrite URI to fetch the private pre-sliced S3 object
    request.uri = "/private/readings/" + translation + "/" + dateStr + ".json";
    request.querystring = {};
    return request;
}

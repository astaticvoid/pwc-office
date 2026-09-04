// CloudFront Function: Viewer Request handler for /api/v1/readings and /api/v2/calendar (ADR 0023, 0024, 0025).
// Enforces date validation, translation allowlisting, API versioning, temporal gating, and KJV fallbacks.

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

    // 3. Validate path and extract API version and resource
    var uri = request.uri || "";
    var match = uri.match(/^\/api\/(?:([^/]+)\/)?(readings|calendar)\/?$/);
    if (!match) {
        return {
            statusCode: 404,
            statusDescription: "Not Found",
            headers: {
                "content-type": { value: "application/json" },
                "access-control-allow-origin": { value: "*" }
            },
            body: JSON.stringify({ error: "Invalid endpoint path." })
        };
    }

    var version = match[1];
    var resource = match[2];

    if (!version) {
        return {
            statusCode: 400,
            statusDescription: "Bad Request",
            headers: {
                "content-type": { value: "application/json" },
                "access-control-allow-origin": { value: "*" }
            },
            body: JSON.stringify({ error: "Missing API version in path. Expected /api/v1/" + resource })
        };
    }

    if (resource === "readings") {
        if (version !== "v1") {
            return {
                statusCode: 404,
                statusDescription: "Not Found",
                headers: {
                    "content-type": { value: "application/json" },
                    "access-control-allow-origin": { value: "*" }
                },
                body: JSON.stringify({ error: "Unsupported API version: " + version })
            };
        }

        var params = request.querystring || {};

        // Validate date parameter
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

        // Strict translation parameter allowlist (prevents path traversal)
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

        // Temporal Gating with 31-day timezone grace buffer
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

        // Rewrite URI to fetch the private pre-sliced S3 object
        request.uri = "/private/readings/" + version + "/" + translation + "/" + dateStr + ".json";
        request.querystring = {};
        return request;
    }

    if (resource === "calendar") {
        if (version !== "v2") {
            return {
                statusCode: 404,
                statusDescription: "Not Found",
                headers: {
                    "content-type": { value: "application/json" },
                    "access-control-allow-origin": { value: "*" }
                },
                body: JSON.stringify({ error: "Unsupported API version: " + version })
            };
        }

        params = request.querystring || {};
        var reqTranslation = (params.translation && params.translation.value) || "nrsvue";
        if (reqTranslation !== "nrsvue" && reqTranslation !== "kjv") {
            return {
                statusCode: 400,
                statusDescription: "Bad Request",
                headers: {
                    "content-type": { value: "application/json" },
                    "access-control-allow-origin": { value: "*" }
                },
                body: JSON.stringify({ error: "Unsupported translation. Supported: nrsvue, kjv" })
            };
        }

        now = new Date();
        todayUtc = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());

        function calcDiff(dStr) {
            var pts = dStr.split("-");
            var target = Date.UTC(parseInt(pts[0], 10), parseInt(pts[1], 10) - 1, parseInt(pts[2], 10));
            return Math.round(Math.abs(target - todayUtc) / 86400000);
        }

        var useTranslation;

        // Batch querying: ?start=YYYY-MM-DD&end=YYYY-MM-DD
        if (params.start || params.end) {
            if (!params.start || !params.start.value || !/^\d{4}-\d{2}-\d{2}$/.test(params.start.value) ||
                !params.end || !params.end.value || !/^\d{4}-\d{2}-\d{2}$/.test(params.end.value)) {
                return {
                    statusCode: 400,
                    statusDescription: "Bad Request",
                    headers: {
                        "content-type": { value: "application/json" },
                        "access-control-allow-origin": { value: "*" }
                    },
                    body: JSON.stringify({ error: "Both start and end date parameters (YYYY-MM-DD) are required for batch queries." })
                };
            }

            var startStr = params.start.value;
            var endStr = params.end.value;
            if (startStr > endStr) {
                return {
                    statusCode: 400,
                    statusDescription: "Bad Request",
                    headers: {
                        "content-type": { value: "application/json" },
                        "access-control-allow-origin": { value: "*" }
                    },
                    body: JSON.stringify({ error: "Invalid date range: start date must be <= end date." })
                };
            }

            var startDiff = calcDiff(startStr);
            var endDiff = calcDiff(endStr);
            useTranslation = reqTranslation;
            if (useTranslation === "nrsvue" && (startDiff > 31 || endDiff > 31)) {
                useTranslation = "kjv"; // Temporal fallback to KJV outside ±30 days (ADR 0025)
            }

            request.uri = "/private/calendar/v2/" + useTranslation + "/batch/" + startStr + "_" + endStr + ".json";
            request.querystring = {};
            return request;
        }

        // Single date query: ?date=YYYY-MM-DD
        if (!params.date || !params.date.value || !/^\d{4}-\d{2}-\d{2}$/.test(params.date.value)) {
            return {
                statusCode: 400,
                statusDescription: "Bad Request",
                headers: {
                    "content-type": { value: "application/json" },
                    "access-control-allow-origin": { value: "*" }
                },
                body: JSON.stringify({ error: "Missing or invalid date parameter (YYYY-MM-DD) or date range (start & end)." })
            };
        }

        dateStr = params.date.value;
        diffDays = calcDiff(dateStr);
        useTranslation = reqTranslation;
        if (useTranslation === "nrsvue" && diffDays > 31) {
            useTranslation = "kjv"; // Temporal fallback to KJV outside ±30 days (ADR 0025)
        }

        request.uri = "/private/calendar/v2/" + useTranslation + "/" + dateStr + ".json";
        request.querystring = {};
        return request;
    }

    return {
        statusCode: 404,
        statusDescription: "Not Found",
        headers: {
            "content-type": { value: "application/json" },
            "access-control-allow-origin": { value: "*" }
        },
        body: JSON.stringify({ error: "Invalid endpoint path." })
    };
}

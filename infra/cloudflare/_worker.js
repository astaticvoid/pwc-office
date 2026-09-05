/* global URL, Response, Headers */

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const method = request.method;

    // 1. CORS Preflight - must happen before Auth!
    if (method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "GET, OPTIONS",
          "Access-Control-Allow-Headers": "Content-Type, Authorization",
          "Access-Control-Max-Age": "86400",
        },
      });
    }

    // 2. STAGING BASIC AUTHENTICATION
    // If we are in the staging environment, require Basic Auth or a valid cookie.
    if (env.ENVIRONMENT === "staging") {
      const authHeader = request.headers.get("Authorization");
      const cookieHeader = request.headers.get("Cookie") || "";
      const hasValidCookie = cookieHeader.includes("pwc-auth=1");
      const expectedAuth = env.BASIC_AUTH; // E.g., "Basic b2ZmaWNlOmRhaWx5"

      if (!hasValidCookie && authHeader !== expectedAuth) {
        return new Response("Unauthorized", {
          status: 401,
          headers: {
            "WWW-Authenticate": 'Basic realm="PWC Staging"',
          },
        });
      }
    }

    // 3. API EDGE GATEWAY (/api/v1/readings and /api/v2/calendar)
    if (url.pathname.startsWith("/api/")) {
      const pathParts = url.pathname.split("/").filter(Boolean);
      // Expected: ["api", "v1", "readings"] or ["api", "v2", "calendar"]
      if (pathParts.length < 3) {
        return createError(400, "Missing API version or resource in path.");
      }

      const version = pathParts[1];
      const resource = pathParts[2];
      const now = new Date();
      const todayUtc = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());

      function calcDiff(dStr) {
        const pts = dStr.split("-");
        const target = Date.UTC(parseInt(pts[0], 10), parseInt(pts[1], 10) - 1, parseInt(pts[2], 10));
        return Math.round(Math.abs(target - todayUtc) / 86400000);
      }

      let r2Key = null;

      if (resource === "readings") {
        if (version !== "v1") return createError(404, "Unsupported API version: " + version);

        const dateStr = url.searchParams.get("date");
        if (!dateStr || !/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
          return createError(400, "Missing or invalid date parameter (YYYY-MM-DD)");
        }

        const translation = url.searchParams.get("translation") || "nrsvue";
        if (translation !== "nrsvue") {
          return createError(400, "Unsupported translation. Only nrsvue is served via this endpoint.");
        }

        const diffDays = calcDiff(dateStr);
        if (diffDays > 31) {
          return new Response(
            JSON.stringify({
              error: "Temporal restriction: Readings only available within ±30 days of current date.",
              requestedDate: dateStr,
              daysDifference: diffDays,
            }),
            {
              status: 403,
              headers: { "Content-Type": "application/json", "Cache-Control": "no-store", "Access-Control-Allow-Origin": "*" },
            }
          );
        }

        r2Key = `readings/${version}/${translation}/${dateStr}.json`;
      } else if (resource === "calendar") {
        if (version !== "v2") return createError(404, "Unsupported API version: " + version);

        const reqTranslation = url.searchParams.get("translation") || "nrsvue";
        if (reqTranslation !== "nrsvue" && reqTranslation !== "kjv") {
          return createError(400, "Unsupported translation. Supported: nrsvue, kjv");
        }

        const startStr = url.searchParams.get("start");
        const endStr = url.searchParams.get("end");
        const dateStr = url.searchParams.get("date");

        if (startStr || endStr) {
          if (!startStr || !/^\d{4}-\d{2}-\d{2}$/.test(startStr) || !endStr || !/^\d{4}-\d{2}-\d{2}$/.test(endStr)) {
            return createError(400, "Both start and end date parameters are required for batch queries.");
          }
          if (startStr > endStr) return createError(400, "start date must be <= end date.");

          let useTranslation = reqTranslation;
          if (useTranslation === "nrsvue" && (calcDiff(startStr) > 31 || calcDiff(endStr) > 31)) {
            useTranslation = "kjv";
          }
          r2Key = `calendar/v2/${useTranslation}/batch/${startStr}_${endStr}.json`;
        } else if (dateStr) {
          if (!/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) return createError(400, "Invalid date parameter.");
          let useTranslation = reqTranslation;
          if (useTranslation === "nrsvue" && calcDiff(dateStr) > 31) {
            useTranslation = "kjv";
          }
          r2Key = `calendar/v2/${useTranslation}/${dateStr}.json`;
        } else {
          return createError(400, "Missing date or start/end parameters.");
        }
      } else {
        return createError(404, "Invalid endpoint path.");
      }

      // Fetch from R2 bucket
      if (!env.PRIVATE_DATA) {
        return createError(500, "R2 bucket binding (PRIVATE_DATA) not configured.");
      }

      const object = await env.PRIVATE_DATA.get(r2Key);
      if (object === null) {
        return createError(404, "Data not found for requested date/translation.");
      }

      const headers = new Headers();
      object.writeHttpMetadata(headers);
      headers.set("etag", object.httpEtag);
      headers.set("Access-Control-Allow-Origin", "*");
      headers.set("Content-Type", "application/json");

      // Allow browser to cache API responses slightly, unless otherwise specified
      headers.set("Cache-Control", "public, max-age=3600");

      return new Response(object.body, { headers });
    }

    // 3. FALLBACK: SERVE STATIC SPA ASSETS
    // This allows Cloudflare Pages to serve your static dist/ folder normally.
    let response = await env.ASSETS.fetch(request);

    // 4. SET COOKIE AFTER SUCCESSFUL AUTH
    if (env.ENVIRONMENT === "staging" && response.status < 400) {
      const authHeader = request.headers.get("Authorization");
      const cookieHeader = request.headers.get("Cookie") || "";
      if (authHeader === env.BASIC_AUTH && !cookieHeader.includes("pwc-auth=1")) {
        // We clone the response to mutate headers
        response = new Response(response.body, response);
        // Set cookie for 30 days
        response.headers.append("Set-Cookie", "pwc-auth=1; Path=/; Max-Age=2592000; HttpOnly; Secure; SameSite=Lax");
      }
    }

    return response;
  },
};

function createError(status, message) {
  return new Response(JSON.stringify({ error: message }), {
    status,
    headers: {
      "Content-Type": "application/json",
      "Access-Control-Allow-Origin": "*",
    },
  });
}

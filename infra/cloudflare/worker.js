/* global URL, Response, Headers, console */

export default {
  async fetch(request, env) {
    try {
      const url = new URL(request.url);
      const method = request.method;

      // 1. CORS Preflight - must happen before Auth!
      if (method === "OPTIONS") {
        return new Response(null, {
          status: 204,
          headers: {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Client-Version, X-Client-Platform",
            "Access-Control-Expose-Headers": "X-API-Version, X-Git-Commit, X-Environment",
            "Access-Control-Max-Age": "86400",
          },
        });
      }

      // 2. STAGING BASIC AUTHENTICATION (fail-closed in staging environment)
      if (env.ENVIRONMENT === "staging") {
        const expectedAuth = env.STAGING_AUTH || env.BASIC_AUTH;
        if (!expectedAuth) {
          return new Response("Staging authentication is misconfigured", {
            status: 500,
            headers: {
              "Content-Type": "text/plain; charset=utf-8",
              "Access-Control-Allow-Origin": "*",
            },
          });
        }

        const authHeader = request.headers.get("Authorization");

        if (authHeader !== expectedAuth) {
          const isV3 = url.pathname.includes("/v3/") || url.pathname.endsWith("/version");
          return new Response("Unauthorized", {
            status: 401,
            headers: {
              "WWW-Authenticate": 'Basic realm="PWC Staging API"',
              "Cache-Control": "no-store",
              "Access-Control-Allow-Origin": "*",
              "Access-Control-Expose-Headers": "X-API-Version, X-Git-Commit, X-Environment",
              "X-API-Version": isV3 ? "3.0.0" : "2.0.0",
              "X-Environment": env.ENVIRONMENT || "unknown",
              "X-Git-Commit": env.GIT_COMMIT || "unknown",
            },
          });
        }
      }

    // 3. API ROUTING — only /api/* is valid
    if (!url.pathname.startsWith("/api/")) {
      return createError(404, "Not found. This is an API endpoint.", {}, env);
    }

    const pathParts = url.pathname.split("/").filter(Boolean);
    // Support /api/version, /api/v2/version, or /api/v3/version as dedicated health/version endpoint
    if ((pathParts.length === 2 && pathParts[1] === "version") || (pathParts.length === 3 && pathParts[2] === "version")) {
      const respApiVer = (pathParts.length === 3 && pathParts[1] === "v2") ? "2.0.0" : "3.0.0";
      return new Response(
        JSON.stringify({
          status: "ok",
          apiVersion: respApiVer,
          commit: env.GIT_COMMIT || "unknown",
          environment: env.ENVIRONMENT || "unknown",
        }),
        {
          status: 200,
          headers: {
            "Content-Type": "application/json",
            "Cache-Control": "no-store",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Expose-Headers": "X-API-Version, X-Git-Commit, X-Environment",
            "X-API-Version": respApiVer,
            "X-Git-Commit": env.GIT_COMMIT || "unknown",
            "X-Environment": env.ENVIRONMENT || "unknown",
          },
        }
      );
    }

    // Expected: ["api", "v1", "readings"] or ["api", "v2", "calendar"]
    if (pathParts.length < 3) {
      return createError(400, "Missing API version or resource in path.", {}, env);
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

    const reqApiVer = version === "v3" ? "3.0.0" : (version === "v2" ? "2.0.0" : "1.0.0");

    if (resource === "readings") {
      if (version !== "v1") return createError(404, "Unsupported API version: " + version, {}, env, reqApiVer);

      const dateStr = url.searchParams.get("date");
      if (!dateStr || !/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
        return createError(400, "Missing or invalid date parameter (YYYY-MM-DD)", {}, env, reqApiVer);
      }

      const translation = url.searchParams.get("translation") || "nrsvue";
      if (translation !== "nrsvue") {
        return createError(400, "Unsupported translation. Only nrsvue is served via this endpoint.", {}, env, reqApiVer);
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
            headers: {
              "Content-Type": "application/json",
              "Cache-Control": "no-store",
              "Access-Control-Allow-Origin": "*",
              "Access-Control-Expose-Headers": "X-API-Version, X-Git-Commit, X-Environment",
              "X-API-Version": reqApiVer,
              "X-Environment": env.ENVIRONMENT || "unknown",
              "X-Git-Commit": env.GIT_COMMIT || "unknown",
            },
          }
        );
      }

      r2Key = `readings/${version}/${translation}/${dateStr}.json`;
    } else if (resource === "calendar") {
      if (version !== "v2" && version !== "v3") return createError(404, "Unsupported API version: " + version, {}, env, reqApiVer);

      const reqTranslation = url.searchParams.get("translation") || "nrsvue";
      if (reqTranslation !== "nrsvue" && reqTranslation !== "kjv") {
        return createError(400, "Unsupported translation. Supported: nrsvue, kjv", {}, env, reqApiVer);
      }

      const startStr = url.searchParams.get("start");
      const endStr = url.searchParams.get("end");
      const dateStr = url.searchParams.get("date");

      if (startStr || endStr) {
        if (!startStr || !/^\d{4}-\d{2}-\d{2}$/.test(startStr) || !endStr || !/^\d{4}-\d{2}-\d{2}$/.test(endStr)) {
          return createError(400, "Both start and end date parameters are required for batch queries.", {}, env, reqApiVer);
        }
        if (startStr > endStr) return createError(400, "start date must be <= end date.", {}, env, reqApiVer);

        let useTranslation = reqTranslation;
        if (useTranslation === "nrsvue" && (calcDiff(startStr) > 31 || calcDiff(endStr) > 31)) {
          useTranslation = "kjv";
        }
        r2Key = `calendar/${version}/${useTranslation}/batch/${startStr}_${endStr}.json`;
      } else if (dateStr) {
        if (!/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) return createError(400, "Invalid date parameter.", {}, env, reqApiVer);
        let useTranslation = reqTranslation;
        if (useTranslation === "nrsvue" && calcDiff(dateStr) > 31) {
          useTranslation = "kjv";
        }
        r2Key = `calendar/${version}/${useTranslation}/${dateStr}.json`;
      } else {
        return createError(400, "Missing date or start/end parameters.", {}, env, reqApiVer);
      }
    } else {
      return createError(404, "Invalid endpoint path.", {}, env, reqApiVer);
    }

    // Fetch from R2 bucket
    if (!env.PRIVATE_DATA) {
      return createError(500, "R2 bucket binding (PRIVATE_DATA) not configured.", {}, env, reqApiVer);
    }

    const object = await env.PRIVATE_DATA.get(r2Key);
    if (object === null) {
      return createError(404, "Data not found for requested date/translation.", {}, env, reqApiVer);
    }

    const apiVerHeader = version === "v3" ? "3.0.0" : (version === "v2" ? "2.0.0" : "1.0.0");
    const headers = new Headers();
    object.writeHttpMetadata(headers);
    headers.set("etag", object.httpEtag);
    headers.set("Access-Control-Allow-Origin", "*");
    headers.set("Access-Control-Expose-Headers", "X-API-Version, X-Git-Commit, X-Environment");
    headers.set("Content-Type", "application/json");
    headers.set("Cache-Control", "public, max-age=3600");
    headers.set("X-API-Version", apiVerHeader);
    headers.set("X-Environment", env.ENVIRONMENT || "unknown");
    headers.set("X-Git-Commit", env.GIT_COMMIT || "unknown");

      return new Response(object.body, { headers });
    } catch (err) {
      const clientVer = request.headers.get("X-Client-Version") || "unknown";
      const clientPlatform = request.headers.get("X-Client-Platform") || "unknown";
      console.error(`Internal server error [client=${clientPlatform}@${clientVer}]:`, err);
      return createError(500, "Internal Server Error", { clientVersion: clientVer, clientPlatform }, env);
    }
  },
};

function createError(status, message, extra = {}, env = {}, apiVersion = "3.0.0") {
  const apiVer = extra.apiVersion || apiVersion || "3.0.0";
  return new Response(JSON.stringify({ error: message, ...extra }), {
    status,
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": "no-store",
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Expose-Headers": "X-API-Version, X-Git-Commit, X-Environment",
      "X-API-Version": apiVer,
      "X-Environment": env?.ENVIRONMENT || "unknown",
      "X-Git-Commit": env?.GIT_COMMIT || "unknown",
    },
  });
}

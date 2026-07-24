function handler(event) {
    var request = event.request;
    var headers = request.headers;
    var cookies = request.cookies;
    var expected = "Basic b2ZmaWNlOmRhaWx5";

    // Check for existing auth cookie (cookies live in request.cookies under
    // the cloudfront-js-2.0 runtime, never in request.headers.cookie)
    if (cookies && cookies["pwc-auth"] && cookies["pwc-auth"].value === "1") {
        return request;
    }

    // Check Authorization header
    if (headers.authorization && headers.authorization.value === expected) {
        // Pass through — cookie is set by the pwc-set-auth-cookie viewer-response trigger
        return request;
    }

    return {
        statusCode: 401,
        statusDescription: "Unauthorized",
        headers: {
            "www-authenticate": { value: 'Basic realm="Daily Office", charset="UTF-8"' }
        }
    };
}

function handler(event) {
    var request = event.request;
    var response = event.response;
    var headers = request.headers;
    var expected = "Basic b2ZmaWNlOmRhaWx5";

    // Only fires when pwc-basic-auth (viewer-request) already let this
    // request through — either it had the cookie already, or it just
    // presented valid Basic Auth credentials. Only the latter case needs
    // a cookie written; re-setting it every time is harmless.
    if (headers.authorization && headers.authorization.value === expected) {
        response.cookies["pwc-auth"] = {
            value: "1",
            attributes: "Path=/; Max-Age=2592000; Secure; HttpOnly; SameSite=Lax"
        };
    }

    return response;
}

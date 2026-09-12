/* global Response, btoa */

export async function onRequest(context) {
  const { request, next, env } = context;

  // Check for existing auth cookie
  const cookieHeader = request.headers.get("Cookie") || "";
  if (cookieHeader.includes("pwc-auth=1")) {
    return next();
  }

  // Staging authentication
  const expectedUser = env.AUTH_USER || "__AUTH_USER__";
  const expectedPass = env.AUTH_PASSWORD || "__AUTH_PASSWORD__";
  const expectedAuth = "Basic " + btoa(expectedUser + ":" + expectedPass);

  const authHeader = request.headers.get("Authorization");
  if (authHeader !== expectedAuth) {
    return new Response("Unauthorized", {
      status: 401,
      headers: {
        "WWW-Authenticate": 'Basic realm="Pray Without Ceasing Staging"',
        "Content-Type": "text/plain; charset=utf-8",
        "Cache-Control": "no-store",
      },
    });
  }

  const response = await next();
  const newResponse = new Response(response.body, response);
  newResponse.headers.append("Set-Cookie", "pwc-auth=1; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=86400");
  return newResponse;
}

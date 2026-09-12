/* global Response, btoa */

const TAKEDOWN_HTML = `<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta
      name="description"
      content="Pray Without Ceasing is temporarily unavailable for reasons of copyright."
    />
    <title>Pray Without Ceasing</title>
    <style>
      :root {
        color-scheme: light;
        --page: #f6f1e8;
        --paper: #fffaf1;
        --ink: #26231e;
        --muted: #665f55;
        --line: #d9cdbc;
        --accent: #315f67;
        --accent-strong: #23494f;
        --shadow: 0 24px 60px rgb(74 59 38 / 14%);
        font-family: Georgia, 'Times New Roman', serif;
      }

      * {
        box-sizing: border-box;
      }

      body {
        margin: 0;
        min-width: 320px;
        min-height: 100vh;
        display: grid;
        place-items: center;
        padding: 32px 16px;
        background: var(--page);
        color: var(--ink);
      }

      main {
        width: min(100%, 680px);
        padding: clamp(24px, 6vw, 48px);
        border: 1px solid var(--line);
        border-radius: 8px;
        background: var(--paper);
        box-shadow: var(--shadow);
      }

      h1 {
        margin: 0 0 18px;
        font-size: clamp(2rem, 7vw, 3.5rem);
        font-weight: 500;
        line-height: 1;
        letter-spacing: 0;
      }

      p {
        margin: 0 0 16px;
        color: var(--muted);
        font-size: clamp(1.08rem, 2.5vw, 1.28rem);
        line-height: 1.55;
      }

      a {
        color: var(--accent-strong);
      }

      a:hover {
        color: var(--accent);
      }

      .footer-note {
        margin-top: 32px;
        padding-top: 16px;
        border-top: 1px solid var(--line);
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 0.85rem;
        color: #8c8274;
        font-family: system-ui, -apple-system, sans-serif;
      }

      .eval-btn {
        background: none;
        border: 1px solid var(--line);
        border-radius: 4px;
        color: var(--muted);
        padding: 4px 10px;
        font-size: 0.8rem;
        cursor: pointer;
        font-family: inherit;
      }

      .eval-btn:hover {
        background: var(--line);
        color: var(--ink);
      }

      dialog {
        border: 1px solid var(--line);
        border-radius: 8px;
        background: var(--paper);
        color: var(--ink);
        padding: 24px;
        box-shadow: var(--shadow);
        max-width: 360px;
        width: 90vw;
        font-family: system-ui, -apple-system, sans-serif;
      }

      dialog::backdrop {
        background: rgba(0, 0, 0, 0.4);
        backdrop-filter: blur(2px);
      }

      dialog h2 {
        margin: 0 0 12px;
        font-size: 1.2rem;
      }

      dialog label {
        display: block;
        font-size: 0.85rem;
        margin-bottom: 4px;
        color: var(--muted);
      }

      dialog input {
        width: 100%;
        padding: 8px 10px;
        margin-bottom: 12px;
        border: 1px solid var(--line);
        border-radius: 4px;
        font-size: 0.95rem;
      }

      dialog .actions {
        display: flex;
        justify-content: flex-end;
        gap: 8px;
        margin-top: 8px;
      }

      dialog button {
        padding: 6px 14px;
        border-radius: 4px;
        font-size: 0.9rem;
        cursor: pointer;
      }

      dialog .submit-btn {
        background: var(--accent);
        color: #fff;
        border: none;
      }
      dialog .submit-btn:hover {
        background: var(--accent-strong);
      }

      dialog .cancel-btn {
        background: transparent;
        border: 1px solid var(--line);
      }

      .error-alert {
        color: #b3261e;
        font-size: 0.85rem;
        margin-bottom: 12px;
        display: none;
      }
    </style>
  </head>
  <body>
    <main aria-labelledby="notice-title">
      <h1 id="notice-title">Pray Without Ceasing</h1>
      <p>
        For reasons of copyright, this website is no longer available. Please go to
        <a href="https://www.anglican.ca/resources/pray-without-ceasing/">https://www.anglican.ca/resources/pray-without-ceasing/</a>
        for more resources related to the Pray Without Ceasing book and possible online and app versions.
      </p>
      <div class="footer-note">
        <span>Anglican Church of Canada Daily Office</span>
        <button class="eval-btn" onclick="document.getElementById('eval-dialog').showModal()">Evaluation Sign In</button>
      </div>
    </main>

    <dialog id="eval-dialog">
      <h2>Evaluation Access</h2>
      <p style="font-size: 0.85rem; color: var(--muted); margin-bottom: 16px;">Authorized Synod evaluators may sign in below.</p>
      <div id="error-msg" class="error-alert">Invalid username or password.</div>
      <form method="dialog" id="eval-form">
        <label for="u">Username</label>
        <input type="text" id="u" required autocomplete="username" />
        <label for="p">Password</label>
        <input type="password" id="p" required autocomplete="current-password" />
        <div class="actions">
          <button type="button" class="cancel-btn" onclick="document.getElementById('eval-dialog').close()">Cancel</button>
          <button type="submit" class="submit-btn">Sign In</button>
        </div>
      </form>
    </dialog>

    <script>
      document.getElementById('eval-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const u = document.getElementById('u').value.trim();
        const p = document.getElementById('p').value;
        const errEl = document.getElementById('error-msg');
        errEl.style.display = 'none';

        const token = btoa(u + ':' + p);
        try {
          const res = await fetch(window.location.href, {
            headers: { 'Authorization': 'Basic ' + token }
          });
          if (res.ok) {
            window.location.reload();
          } else {
            errEl.style.display = 'block';
          }
        } catch (err) {
          errEl.textContent = 'Connection error. Please try again.';
          errEl.style.display = 'block';
        }
      });
    </script>
  </body>
</html>`;

export async function onRequest(context) {
  const { request, next, env } = context;

  // 1. Check for existing auth cookie
  const cookieHeader = request.headers.get("Cookie") || "";
  if (cookieHeader.includes("pwc-auth=1")) {
    return next();
  }

  // 2. Evaluate Basic Authentication
  const expectedUser = env.AUTH_USER || "__AUTH_USER__";
  const expectedPass = env.AUTH_PASSWORD || "__AUTH_PASSWORD__";
  const expectedAuth = "Basic " + btoa(expectedUser + ":" + expectedPass);

  const authHeader = request.headers.get("Authorization");
  if (authHeader === expectedAuth) {
    const response = await next();
    const newResponse = new Response(response.body, response);
    newResponse.headers.append("Set-Cookie", "pwc-auth=1; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=86400");
    return newResponse;
  }

  // 3. Unauthenticated response: Return 401 with takedown notice HTML
  return new Response(TAKEDOWN_HTML, {
    status: 401,
    headers: {
      "WWW-Authenticate": 'Basic realm="Pray Without Ceasing Staging"',
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "no-store",
    },
  });
}


import { describe, it, expect } from 'vitest';
import worker from '../../infra/cloudflare/worker.js';
import { onRequest } from '../../infra/cloudflare/pages-functions/_middleware.js';

describe('Cloudflare Worker Authentication Gate', () => {
  const stagingEnv = {
    ENVIRONMENT: 'staging',
    STAGING_AUTH: 'Basic b2ZmaWNlOmRhaWx5',
    GIT_COMMIT: 'test-commit',
  };

  const prodEnv = {
    ENVIRONMENT: 'production',
    GIT_COMMIT: 'test-commit',
  };

  it('allows OPTIONS CORS preflight without authorization on staging', async () => {
    const req = new Request('https://api-staging.praywithoutceasing.ca/api/v3/version', {
      method: 'OPTIONS',
    });
    const res = await worker.fetch(req, stagingEnv);
    expect(res.status).toBe(204);
    expect(res.headers.get('Access-Control-Allow-Origin')).toBe('*');
  });

  it('rejects unauthenticated requests on staging with 401 Unauthorized', async () => {
    const req = new Request('https://api-staging.praywithoutceasing.ca/api/v3/version', {
      method: 'GET',
    });
    const res = await worker.fetch(req, stagingEnv);
    expect(res.status).toBe(401);
    expect(res.headers.get('WWW-Authenticate')).toContain('Basic');
    expect(res.headers.get('Access-Control-Allow-Origin')).toBe('*');
  });

  it('rejects requests with invalid credentials on staging with 401 Unauthorized', async () => {
    const req = new Request('https://api-staging.praywithoutceasing.ca/api/v3/version', {
      method: 'GET',
      headers: { Authorization: 'Basic wrongtoken' },
    });
    const res = await worker.fetch(req, stagingEnv);
    expect(res.status).toBe(401);
  });

  it('fails closed with 500 when staging environment has no auth credentials configured', async () => {
    const req = new Request('https://api-staging.praywithoutceasing.ca/api/v3/version', {
      method: 'GET',
    });
    const res = await worker.fetch(req, { ENVIRONMENT: 'staging', GIT_COMMIT: 'test' });
    expect(res.status).toBe(500);
    const text = await res.text();
    expect(text).toContain('misconfigured');
  });

  it('allows requests with valid credentials on staging', async () => {
    const req = new Request('https://api-staging.praywithoutceasing.ca/api/v3/version', {
      method: 'GET',
      headers: { Authorization: 'Basic b2ZmaWNlOmRhaWx5' },
    });
    const res = await worker.fetch(req, stagingEnv);
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data.status).toBe('ok');
    expect(data.apiVersion).toBe('3.0.0');
    expect(data.environment).toBe('staging');
  });

  it('fails closed with 500 when production environment has no auth credentials configured', async () => {
    const req = new Request('https://api.praywithoutceasing.ca/api/v3/version', {
      method: 'GET',
    });
    const res = await worker.fetch(req, prodEnv);
    expect(res.status).toBe(500);
    const text = await res.text();
    expect(text).toContain('misconfigured');
  });

  it('rejects unauthenticated requests in production when BASIC_AUTH is configured', async () => {
    const req = new Request('https://api.praywithoutceasing.ca/api/v3/version', {
      method: 'GET',
    });
    const authedProdEnv = { ...prodEnv, BASIC_AUTH: 'Basic b2ZmaWNlOmRhaWx5' };
    const res = await worker.fetch(req, authedProdEnv);
    expect(res.status).toBe(401);
    expect(res.headers.get('WWW-Authenticate')).toContain('PWC API');
  });

  it('allows authenticated requests in production when BASIC_AUTH is configured', async () => {
    const req = new Request('https://api.praywithoutceasing.ca/api/v3/version', {
      method: 'GET',
      headers: { Authorization: 'Basic b2ZmaWNlOmRhaWx5' },
    });
    const authedProdEnv = { ...prodEnv, BASIC_AUTH: 'Basic b2ZmaWNlOmRhaWx5' };
    const res = await worker.fetch(req, authedProdEnv);
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data.environment).toBe('production');
  });
});

describe('Cloudflare Pages Functions Middleware Gate', () => {
  const env = {
    AUTH_USER: 'office',
    AUTH_PASSWORD: 'daily',
  };

  it('whitelists /sw.js to allow service worker unregistration without authentication', async () => {
    const req = new Request('https://staging.praywithoutceasing.ca/sw.js', {
      method: 'GET',
    });
    let reached = false;
    const next = () => {
      reached = true;
      return new Response('self.registration.unregister();', { status: 200 });
    };

    const res = await onRequest({ request: req, next, env });
    expect(reached).toBe(true);
    expect(res.status).toBe(200);
  });

  it('rejects unauthenticated requests with 401 and serves takedown notice HTML', async () => {
    const req = new Request('https://staging.praywithoutceasing.ca/', {
      method: 'GET',
    });
    const next = () => new Response('should not reach here');

    const res = await onRequest({ request: req, next, env });
    expect(res.status).toBe(401);
    expect(res.headers.get('WWW-Authenticate')).toBeNull();
    expect(res.headers.get('Content-Type')).toContain('text/html');
    const html = await res.text();
    expect(html).toContain('For reasons of copyright, this website is no longer available');
    expect(html).toContain('Evaluation Sign In');
    expect(html).toContain('eval-dialog');
  });

  it('fails closed and serves takedown notice when env credentials are missing', async () => {
    const req = new Request('https://staging.praywithoutceasing.ca/', {
      method: 'GET',
      headers: { Authorization: 'Basic X19BVVRIX1VTRVJfXzpfX0FVVEhfUEFTU1dPUkRfXw==' },
    });
    const next = () => new Response('should not reach here');

    const res = await onRequest({ request: req, next, env: {} });
    expect(res.status).toBe(401);
    const html = await res.text();
    expect(html).toContain('For reasons of copyright');
  });

  it('fails closed and blocks access even with valid cookie when credentials are not configured', async () => {
    const req = new Request('https://staging.praywithoutceasing.ca/', {
      method: 'GET',
      headers: { Cookie: 'pwc-auth=1' },
    });
    const next = () => new Response('should not reach here');

    const res = await onRequest({ request: req, next, env: {} });
    expect(res.status).toBe(401);
    const html = await res.text();
    expect(html).toContain('For reasons of copyright');
  });

  it('passes through when valid pwc-auth cookie is present and credentials are configured', async () => {
    const req = new Request('https://staging.praywithoutceasing.ca/', {
      method: 'GET',
      headers: { Cookie: 'some-cookie=abc; pwc-auth=1; other=def' },
    });
    let reached = false;
    const next = () => {
      reached = true;
      return new Response('<html>OK</html>', { status: 200 });
    };

    const res = await onRequest({ request: req, next, env });
    expect(reached).toBe(true);
    expect(res.status).toBe(200);
    expect(res.headers.get('Cache-Control')).toBe('private, no-cache');
    expect(res.headers.get('Vary')).toContain('Cookie');
  });

  it('rejects forged cookie that merely contains pwc-auth=1 as a substring', async () => {
    const req = new Request('https://staging.praywithoutceasing.ca/', {
      method: 'GET',
      headers: { Cookie: 'tracking=xyz_pwc-auth=1_abc' },
    });
    const next = () => new Response('should not reach here');

    const res = await onRequest({ request: req, next, env });
    expect(res.status).toBe(401);
  });

  it('sets secure cookie and redirects (303) to clean URL on valid eval_token', async () => {
    const credentials = btoa(env.AUTH_USER + ':' + env.AUTH_PASSWORD);
    const req = new Request(`https://staging.praywithoutceasing.ca/?eval_token=${credentials}`, {
      method: 'GET',
    });
    const next = () => new Response('should not reach here');

    const res = await onRequest({ request: req, next, env });
    expect(res.status).toBe(303);
    expect(res.headers.get('Location')).toBe('/');
    const setCookie = res.headers.get('Set-Cookie');
    expect(setCookie).toBeDefined();
    expect(setCookie).toContain('pwc-auth=1');
    expect(setCookie).toContain('HttpOnly');
    expect(setCookie).toContain('Secure');
  });

  it('sets secure cookie and passes through on valid Basic Auth header', async () => {
    const credentials = btoa(env.AUTH_USER + ':' + env.AUTH_PASSWORD);
    const req = new Request('https://staging.praywithoutceasing.ca/', {
      method: 'GET',
      headers: { Authorization: `Basic ${credentials}` },
    });
    let reached = false;
    const next = () => {
      reached = true;
      return new Response('<html>OK</html>', { status: 200 });
    };

    const res = await onRequest({ request: req, next, env });
    expect(reached).toBe(true);
    expect(res.status).toBe(200);
    const setCookie = res.headers.get('Set-Cookie');
    expect(setCookie).toBeDefined();
    expect(setCookie).toContain('pwc-auth=1');
    expect(setCookie).toContain('HttpOnly');
    expect(setCookie).toContain('Secure');
  });
});

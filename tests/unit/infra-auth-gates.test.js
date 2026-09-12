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

  it('allows unauthenticated requests in production environment', async () => {
    const req = new Request('https://api.praywithoutceasing.ca/api/v3/version', {
      method: 'GET',
    });
    const res = await worker.fetch(req, prodEnv);
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data.status).toBe('ok');
    expect(data.apiVersion).toBe('3.0.0');
    expect(data.environment).toBe('production');
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

  it('rejects unauthenticated requests with 401 and serves takedown notice HTML', async () => {
    const req = new Request('https://staging.praywithoutceasing.ca/', {
      method: 'GET',
    });
    const next = () => new Response('should not reach here');

    const res = await onRequest({ request: req, next, env });
    expect(res.status).toBe(401);
    expect(res.headers.get('WWW-Authenticate')).toContain('Basic realm="Pray Without Ceasing Staging"');
    expect(res.headers.get('Content-Type')).toContain('text/html');
    const html = await res.text();
    expect(html).toContain('For reasons of copyright, this website is no longer available');
    expect(html).toContain('Evaluation Sign In');
    expect(html).toContain('eval-dialog');
  });

  it('passes through when valid pwc-auth cookie is present', async () => {
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

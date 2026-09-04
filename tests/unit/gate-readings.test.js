import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import vm from 'vm';

const __dirname = dirname(fileURLToPath(import.meta.url));
const code = readFileSync(join(__dirname, '../../infra/cloudfront-functions/gate-readings.js'), 'utf8');

function executeGateHandler(event) {
  const context = {
    event,
    Date,
    Math,
    parseInt,
    JSON,
  };
  vm.createContext(context);
  vm.runInContext(code + '\nresult = handler(event);', context);
  return context.result;
}

function createEvent({
  method = 'GET',
  uri = '/api/v1/readings',
  querystring = {},
} = {}) {
  return {
    request: {
      method,
      uri,
      querystring,
      headers: {},
    },
  };
}

function getTodayString(offsetDays = 0) {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

describe('gate-readings CloudFront Function', () => {
  it('handles CORS OPTIONS preflight with 204 No Content', () => {
    const event = createEvent({ method: 'OPTIONS' });
    const response = executeGateHandler(event);
    expect(response.statusCode).toBe(204);
    expect(response.headers['access-control-allow-origin'].value).toBe('*');
    expect(response.headers['access-control-allow-methods'].value).toContain('GET');
  });

  it('rejects non-GET methods with 405 Method Not Allowed', () => {
    const event = createEvent({ method: 'POST' });
    const response = executeGateHandler(event);
    expect(response.statusCode).toBe(405);
    expect(JSON.parse(response.body).error).toContain('Method not allowed');
  });

  it('rejects invalid endpoint paths with 404', () => {
    const event = createEvent({ uri: '/api/other' });
    const response = executeGateHandler(event);
    expect(response.statusCode).toBe(404);
    expect(JSON.parse(response.body).error).toBe('Invalid endpoint path.');
  });

  it('rejects unversioned /api/readings with 400 Bad Request', () => {
    const event = createEvent({
      uri: '/api/readings',
      querystring: { date: { value: getTodayString() } },
    });
    const response = executeGateHandler(event);
    expect(response.statusCode).toBe(400);
    expect(JSON.parse(response.body).error).toContain('Missing API version in path');
  });

  it('rejects unsupported API versions with 404 Not Found', () => {
    const event = createEvent({
      uri: '/api/v2/readings',
      querystring: { date: { value: getTodayString() } },
    });
    const response = executeGateHandler(event);
    expect(response.statusCode).toBe(404);
    expect(JSON.parse(response.body).error).toContain('Unsupported API version: v2');
  });

  it('rejects missing or invalid date parameters with 400', () => {
    const noDate = createEvent({ uri: '/api/v1/readings', querystring: {} });
    expect(executeGateHandler(noDate).statusCode).toBe(400);

    const badDate = createEvent({
      uri: '/api/v1/readings',
      querystring: { date: { value: '2026/09/02' } },
    });
    expect(executeGateHandler(badDate).statusCode).toBe(400);
  });

  it('rejects unauthorized or path-traversing translations with 400', () => {
    const event = createEvent({
      uri: '/api/v1/readings',
      querystring: {
        date: { value: getTodayString() },
        translation: { value: '../../secret' },
      },
    });
    const response = executeGateHandler(event);
    expect(response.statusCode).toBe(400);
    expect(JSON.parse(response.body).error).toContain('Unsupported translation');
  });

  it('blocks out-of-window requests beyond ±31 days with 403 Forbidden', () => {
    const futureDate = getTodayString(45);
    const event = createEvent({
      uri: '/api/v1/readings',
      querystring: {
        date: { value: futureDate },
      },
    });
    const response = executeGateHandler(event);
    expect(response.statusCode).toBe(403);
    expect(response.headers['cache-control'].value).toBe('no-store');
    expect(JSON.parse(response.body).error).toContain('Temporal restriction');
  });

  it('rewrites valid in-window /api/v1/readings requests to private S3 path', () => {
    const today = getTodayString(0);
    const event = createEvent({
      uri: '/api/v1/readings',
      querystring: {
        date: { value: today },
        translation: { value: 'nrsvue' },
      },
    });

    const result = executeGateHandler(event);
    expect(result.uri).toBe(`/private/readings/v1/nrsvue/${today}.json`);
    expect(result.querystring).toEqual({});
  });
});

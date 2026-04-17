// ScannerRouter + NetworkTransport unit tests (Slice 7).
//
// Covers the 4-step resolution pipeline (prefix → alias → numeric → unknown),
// input validation for control chars / empty / oversize payloads, and the
// idempotency-key + X-Client-Created-At header contract on
// NetworkTransport.executeAction (M1 non-negotiable).
//
// Transport is mocked with vi.fn() so we never hit the network here.
// NetworkTransport tests mock the apiClient module.

import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
  type MockInstance,
} from 'vitest';
import { ScannerRouter } from '../lib/scan-router';
import { NetworkAliasResolver } from '../lib/network-alias-resolver';
import type {
  ActionResult,
  AliasResolver,
  ResolveResponse,
  ResolvedEntity,
  ScanContext,
  Transport,
} from '../types/scanner';

// --- Shared fixtures -------------------------------------------------------

const CTX: ScanContext = {
  running_timer_id: null,
  current_order_id: null,
  current_location: null,
  device_type: 'desktop',
  input_source: 'manual',
};

function stubResponse(path: ResolveResponse['resolution_path']): ResolveResponse {
  return {
    resolved: path !== 'unknown',
    resolution_path: path,
    entity_type: path === 'unknown' ? null : 'order',
    entity_id: path === 'unknown' ? null : 1,
    entity: null,
    actions: [],
    status_hint: null,
  };
}

function makeMockTransport(
  response: ResolveResponse = stubResponse('prefix'),
): Transport & {
  resolve: ReturnType<typeof vi.fn>;
  logScan: ReturnType<typeof vi.fn>;
  executeAction: ReturnType<typeof vi.fn>;
} {
  return {
    resolve: vi.fn().mockResolvedValue(response),
    logScan: vi.fn().mockResolvedValue(undefined),
    executeAction: vi.fn().mockResolvedValue({ success: true } as ActionResult),
  };
}

function makeMockResolver(
  result: ResolvedEntity | null = null,
): AliasResolver & { lookup: ReturnType<typeof vi.fn> } {
  return {
    lookup: vi.fn().mockResolvedValue(result),
  };
}

// ---------------------------------------------------------------------------
// ScannerRouter.resolve — pipeline routing
// ---------------------------------------------------------------------------

describe('ScannerRouter.resolve — prefix match', () => {
  it('calls transport with canonical "ORDER:42" for "ORDER:42"', async () => {
    const resolver = makeMockResolver();
    const transport = makeMockTransport();
    const router = new ScannerRouter(resolver, transport);

    await router.resolve('ORDER:42', CTX);

    expect(transport.resolve).toHaveBeenCalledTimes(1);
    expect(transport.resolve).toHaveBeenCalledWith('ORDER:42', CTX);
    expect(resolver.lookup).not.toHaveBeenCalled();
  });

  it('passes "REPAIR:17" through unchanged to transport', async () => {
    const resolver = makeMockResolver();
    const transport = makeMockTransport();
    const router = new ScannerRouter(resolver, transport);

    await router.resolve('REPAIR:17', CTX);

    expect(transport.resolve).toHaveBeenCalledWith('REPAIR:17', CTX);
    expect(resolver.lookup).not.toHaveBeenCalled();
  });

  it('accepts all V1.1 prefixes: ORDER, REPAIR, METAL, MATERIAL, ACTIVITY, INTERRUPT', async () => {
    const resolver = makeMockResolver();
    const transport = makeMockTransport();
    const router = new ScannerRouter(resolver, transport);

    const payloads = [
      'ORDER:1',
      'REPAIR:2',
      'METAL:3',
      'MATERIAL:4',
      'ACTIVITY:hartloeten',
      'INTERRUPT:phone',
    ];
    for (const p of payloads) {
      await router.resolve(p, CTX);
    }

    expect(transport.resolve).toHaveBeenCalledTimes(payloads.length);
    payloads.forEach((p, idx) => {
      expect(transport.resolve).toHaveBeenNthCalledWith(idx + 1, p, CTX);
    });
    expect(resolver.lookup).not.toHaveBeenCalled();
  });
});

describe('ScannerRouter.resolve — numeric fallback', () => {
  it('canonicalises bare "42" to "ORDER:42"', async () => {
    const resolver = makeMockResolver();
    const transport = makeMockTransport(stubResponse('numeric_fallback'));
    const router = new ScannerRouter(resolver, transport);

    const res = await router.resolve('42', CTX);

    expect(transport.resolve).toHaveBeenCalledWith('ORDER:42', CTX);
    expect(resolver.lookup).not.toHaveBeenCalled();
    expect(res.resolution_path).toBe('numeric_fallback');
  });

  it('canonicalises "0" to "ORDER:0" (transport decides if entity exists)', async () => {
    const resolver = makeMockResolver();
    const transport = makeMockTransport();
    const router = new ScannerRouter(resolver, transport);

    await router.resolve('0', CTX);

    expect(transport.resolve).toHaveBeenCalledWith('ORDER:0', CTX);
  });

  it('trims whitespace before numeric check', async () => {
    const resolver = makeMockResolver();
    const transport = makeMockTransport();
    const router = new ScannerRouter(resolver, transport);

    await router.resolve('  42  ', CTX);

    expect(transport.resolve).toHaveBeenCalledWith('ORDER:42', CTX);
  });
});

describe('ScannerRouter.resolve — alias lookup fallthrough', () => {
  it('on unknown prefix "FOO:bar" queries alias resolver first, then transport', async () => {
    const resolver = makeMockResolver(null); // alias lookup miss
    const transport = makeMockTransport(stubResponse('unknown'));
    const router = new ScannerRouter(resolver, transport);

    await router.resolve('FOO:bar', CTX);

    expect(resolver.lookup).toHaveBeenCalledTimes(1);
    expect(resolver.lookup).toHaveBeenCalledWith('FOO:bar');
    expect(transport.resolve).toHaveBeenCalledTimes(1);
    expect(transport.resolve).toHaveBeenCalledWith('FOO:bar', CTX);
  });

  it('on alias hit, canonicalises hit to "<TYPE>:<id>" before calling transport', async () => {
    const hit: ResolvedEntity = {
      entity_type: 'metal',
      entity_id: 85,
      data: {},
    };
    const resolver = makeMockResolver(hit);
    const transport = makeMockTransport();
    const router = new ScannerRouter(resolver, transport);

    await router.resolve('supplier-barcode-abc', CTX);

    expect(resolver.lookup).toHaveBeenCalledWith('supplier-barcode-abc');
    expect(transport.resolve).toHaveBeenCalledWith('METAL:85', CTX);
  });

  it('non-numeric "42a" falls through to alias lookup', async () => {
    const resolver = makeMockResolver(null);
    const transport = makeMockTransport(stubResponse('unknown'));
    const router = new ScannerRouter(resolver, transport);

    await router.resolve('42a', CTX);

    expect(resolver.lookup).toHaveBeenCalledTimes(1);
    expect(resolver.lookup).toHaveBeenCalledWith('42a');
    expect(transport.resolve).toHaveBeenCalledWith('42a', CTX);
  });
});

describe('ScannerRouter.resolve — input validation', () => {
  it('payload with nul byte (\\x00) falls through to alias (canonical=null)', async () => {
    const resolver = makeMockResolver(null);
    const transport = makeMockTransport(stubResponse('unknown'));
    const router = new ScannerRouter(resolver, transport);

    const payload = '\x00ORDER:1';
    await router.resolve(payload, CTX);

    // Canonicalize rejects due to control char → falls through to alias path.
    // Alias returns null → transport called with raw payload for server logging.
    expect(resolver.lookup).toHaveBeenCalledWith(payload);
    expect(transport.resolve).toHaveBeenCalledWith(payload, CTX);
  });

  it('empty string falls through (alias called, then transport for logging)', async () => {
    const resolver = makeMockResolver(null);
    const transport = makeMockTransport(stubResponse('unknown'));
    const router = new ScannerRouter(resolver, transport);

    await router.resolve('', CTX);

    expect(resolver.lookup).toHaveBeenCalledWith('');
    expect(transport.resolve).toHaveBeenCalledWith('', CTX);
  });

  it('oversize payload (>500 chars) falls through to alias, not canonicalised', async () => {
    const resolver = makeMockResolver(null);
    const transport = makeMockTransport(stubResponse('unknown'));
    const router = new ScannerRouter(resolver, transport);

    const big = 'X'.repeat(501);
    await router.resolve(big, CTX);

    expect(resolver.lookup).toHaveBeenCalledWith(big);
    expect(transport.resolve).toHaveBeenCalledWith(big, CTX);
  });

  it('lowercase prefix "order:42" is NOT canonicalised (uppercase grammar)', async () => {
    // Decision: we route only uppercase canonical forms. Lowercase gets treated
    // as an alias candidate so the server can log it as an unknown or the
    // alias table can eventually resolve it.
    const resolver = makeMockResolver(null);
    const transport = makeMockTransport(stubResponse('unknown'));
    const router = new ScannerRouter(resolver, transport);

    await router.resolve('order:42', CTX);

    expect(resolver.lookup).toHaveBeenCalledWith('order:42');
    expect(transport.resolve).toHaveBeenCalledWith('order:42', CTX);
  });
});

// ---------------------------------------------------------------------------
// NetworkAliasResolver — V1.1 stub always returns null
// ---------------------------------------------------------------------------

describe('NetworkAliasResolver (V1.1 stub)', () => {
  it('returns null for any externalCode', async () => {
    const resolver = new NetworkAliasResolver();
    expect(await resolver.lookup('anything')).toBeNull();
    expect(await resolver.lookup('')).toBeNull();
    expect(await resolver.lookup('ORDER:42')).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// NetworkTransport — idempotency-key + X-Client-Created-At contract
// ---------------------------------------------------------------------------

// Mock apiClient at the module boundary. Every post() call returns an object
// with data={success:true} unless the test overrides per-call.
vi.mock('../api/client', () => ({
  default: {
    post: vi.fn(),
    get: vi.fn(),
  },
}));

// Helpers imported AFTER the mock is registered.
import apiClient from '../api/client';
import { NetworkTransport } from '../lib/network-transport';

// Narrow the mocked post to the vi.fn surface.
const mockedPost = apiClient.post as unknown as MockInstance<
  (url: string, data?: unknown, config?: unknown) => Promise<{ data: unknown }>
>;

describe('NetworkTransport', () => {
  beforeEach(() => {
    mockedPost.mockReset();
    mockedPost.mockResolvedValue({ data: { success: true } });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('executeAction', () => {
    it('auto-generates a v4 UUID Idempotency-Key when none is provided', async () => {
      const transport = new NetworkTransport();

      await transport.executeAction({
        action_id: 'start_timer',
        entity_type: 'order',
        entity_id: 42,
        payload: { activity_id: 3 },
        idempotency_key: '', // falsy → auto-generate
      });

      expect(mockedPost).toHaveBeenCalledTimes(1);
      const [url, body, config] = mockedPost.mock.calls[0];

      expect(url).toBe('/scan/action/start_timer');
      expect(body).toEqual({
        entity_type: 'order',
        entity_id: 42,
        payload: { activity_id: 3 },
      });

      const cfg = config as { headers: Record<string, string> };
      expect(cfg.headers['Idempotency-Key']).toBeDefined();
      // v4 UUID: 8-4-4-4-12 hex, variant '1' in the third-group leading hex,
      // version '4' in the second-group leading hex.
      expect(cfg.headers['Idempotency-Key']).toMatch(
        /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
      );
    });

    it('uses the caller-provided idempotency_key verbatim when present', async () => {
      const transport = new NetworkTransport();
      const providedKey = 'deadbeef-1234-4abc-8def-1234567890ab';

      await transport.executeAction({
        action_id: 'switch_timer',
        entity_type: 'order',
        entity_id: 99,
        payload: {},
        idempotency_key: providedKey,
      });

      const [, , config] = mockedPost.mock.calls[0];
      const cfg = config as { headers: Record<string, string> };
      expect(cfg.headers['Idempotency-Key']).toBe(providedKey);
    });

    it('attaches an ISO 8601 X-Client-Created-At header on every call', async () => {
      const transport = new NetworkTransport();

      await transport.executeAction({
        action_id: 'stop_timer',
        entity_type: 'order',
        entity_id: 1,
        payload: {},
        idempotency_key: '',
      });

      const [, , config] = mockedPost.mock.calls[0];
      const cfg = config as { headers: Record<string, string> };
      const createdAt = cfg.headers['X-Client-Created-At'];

      expect(createdAt).toBeDefined();
      // ISO 8601 w/ millis + Z suffix, e.g. 2026-04-16T12:34:56.789Z.
      expect(createdAt).toMatch(
        /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/,
      );
      // Round-trips through Date without NaN.
      expect(Number.isNaN(new Date(createdAt).getTime())).toBe(false);
    });

    it('generates a distinct idempotency key per call', async () => {
      const transport = new NetworkTransport();

      await transport.executeAction({
        action_id: 'start_timer',
        entity_type: 'order',
        entity_id: 1,
        payload: {},
        idempotency_key: '',
      });
      await transport.executeAction({
        action_id: 'start_timer',
        entity_type: 'order',
        entity_id: 2,
        payload: {},
        idempotency_key: '',
      });

      const headers0 = (mockedPost.mock.calls[0][2] as {
        headers: Record<string, string>;
      }).headers;
      const headers1 = (mockedPost.mock.calls[1][2] as {
        headers: Record<string, string>;
      }).headers;

      expect(headers0['Idempotency-Key']).not.toBe(headers1['Idempotency-Key']);
    });

    it('returns the ActionResult from the server', async () => {
      mockedPost.mockResolvedValueOnce({
        data: { success: true, data: { new_timer_id: 'abc' } },
      });
      const transport = new NetworkTransport();

      const result = await transport.executeAction({
        action_id: 'start_timer',
        entity_type: 'order',
        entity_id: 1,
        payload: {},
        idempotency_key: '',
      });

      expect(result).toEqual({
        success: true,
        data: { new_timer_id: 'abc' },
      });
    });
  });

  describe('resolve', () => {
    it('POSTs to /scan/resolve with raw_payload + context', async () => {
      const response: ResolveResponse = stubResponse('prefix');
      mockedPost.mockResolvedValueOnce({ data: response });
      const transport = new NetworkTransport();

      const out = await transport.resolve('ORDER:42', CTX);

      expect(mockedPost).toHaveBeenCalledWith('/scan/resolve', {
        raw_payload: 'ORDER:42',
        context: CTX,
      });
      expect(out).toBe(response);
    });
  });

  describe('logScan', () => {
    it('POSTs to /scan/log with the event payload', async () => {
      const transport = new NetworkTransport();
      const event = {
        raw_payload: 'ORDER:1',
        resolution_path: 'prefix',
        client_tap_at: new Date().toISOString(),
      };

      await transport.logScan(event);

      expect(mockedPost).toHaveBeenCalledWith('/scan/log', event);
    });
  });
});

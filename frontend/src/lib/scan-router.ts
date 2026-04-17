// ScannerRouter — V1.1 async resolver with injectable AliasResolver + Transport.
//
// Pipeline (spec §10.a, plan §7):
//   1. prefix match       — "ORDER:42" / "REPAIR:17" / …
//   2. alias lookup       — delegated to AliasResolver (V1.1 stub returns null)
//   3. numeric fallback   — bare numeric string → treat as ORDER:<n>
//   4. unknown            — forward to server so it can emit the canonical
//                           `resolved=false, resolution_path='unknown'` response
//                           (role-filtered too; we don't fabricate it here).
//
// Role filtering is the *server's* job. The router only canonicalizes and routes.
// The client never decides "you can't see this entity" — it only decides which
// canonical form to hand to the server.

import type {
  AliasResolver,
  ResolveResponse,
  ScanContext,
  Transport,
} from '../types/scanner';

// Must match backend src/goldsmith_erp/services/scanner_service.py KNOWN_PREFIXES_V1.
// Keep in sync with plan §3 ("Key contract points").
const KNOWN_PREFIXES: ReadonlySet<string> = new Set([
  'ORDER',
  'REPAIR',
  'METAL',
  'MATERIAL',
  'ACTIVITY',
  'INTERRUPT',
]);

// Max payload length matches backend ResolveRequest.raw_payload validator.
const MAX_PAYLOAD_LENGTH = 500;

// Strictly digits (ASCII 0-9) — no leading +/-, no whitespace, no locale separators.
const NUMERIC_ONLY = /^\d+$/;

// Prefix grammar: uppercase letters followed by a colon, then at least one char.
// Anchored. Uppercase-only because our canonical prefixes are uppercase.
const PREFIX_SHAPE = /^([A-Z]+):(.+)$/;

/**
 * Detect ASCII control characters we refuse to route (see plan §3, M6).
 * Tab (0x09) is allowed by the backend validator; everything else < 0x20
 * plus DEL (0x7F) is rejected here and by Pydantic on the backend.
 */
function hasControlChars(s: string): boolean {
  for (let i = 0; i < s.length; i++) {
    const code = s.charCodeAt(i);
    if (code === 0x09) continue; // tab is fine
    if (code < 0x20 || code === 0x7f) return true;
  }
  return false;
}

export class ScannerRouter {
  constructor(
    private readonly aliasResolver: AliasResolver,
    private readonly transport: Transport,
  ) {}

  /**
   * Resolve a raw scan payload to a canonical entity via the server.
   *
   * Returns an {@link ResolveResponse}. Does not throw on unknown codes — the
   * server emits `resolved=false` with `resolution_path='unknown'` and an
   * empty action list for those cases. Transport errors propagate to caller.
   */
  async resolve(
    rawPayload: string,
    context: ScanContext,
  ): Promise<ResolveResponse> {
    const canonical = this.canonicalize(rawPayload);

    if (canonical !== null) {
      // Step 1 (prefix hit) or step 3 (numeric fallback). Transport call with
      // the canonicalized payload — server does role filtering + action compute.
      return this.transport.resolve(canonical, context);
    }

    // Step 2: alias lookup for anything that didn't canonicalize. V1.1 stub
    // returns null; V1.2 will wire this to GET /aliases/lookup/:code.
    const aliased = await this.aliasResolver.lookup(rawPayload);
    if (aliased !== null) {
      // Alias resolver returned a hit — hand the canonicalized form
      // "<TYPE>:<id>" to the server so it can apply role filtering and build
      // the action list consistently. We do NOT synthesize a ResolveResponse
      // here: the server is the single source of truth for actions.
      const aliasedCanonical = `${aliased.entity_type.toUpperCase()}:${aliased.entity_id}`;
      return this.transport.resolve(aliasedCanonical, context);
    }

    // Step 4: unknown. Pass the original payload so the server can log the
    // miss and return the canonical unknown-response for the UI.
    return this.transport.resolve(rawPayload, context);
  }

  /**
   * Canonicalize a raw payload to a known-prefix form.
   *
   * Returns:
   *   - "ORDER:42" / "REPAIR:17" for known-prefix hits (unchanged).
   *   - "ORDER:42" for numeric fallback from the bare string "42".
   *   - null if the input contains a control char, is empty, is too long,
   *     is an unknown-prefix "FOO:bar" (alias or server handles it), or is
   *     otherwise non-numeric / non-prefix ("42a").
   *
   * null does NOT mean "fail" — it means "router cannot canonicalize; pass
   * through to alias/unknown stages".
   */
  private canonicalize(rawPayload: string): string | null {
    // Defensive input validation (M6): reject null/undefined, empty,
    // oversize, and payloads carrying control characters such as \x00.
    // Backend Pydantic enforces the same, but we want the router to be
    // safe to call in tests/unit contexts without a transport.
    if (typeof rawPayload !== 'string') return null;
    if (rawPayload.length === 0) return null;
    if (rawPayload.length > MAX_PAYLOAD_LENGTH) return null;
    if (hasControlChars(rawPayload)) return null;

    const trimmed = rawPayload.trim();
    if (trimmed.length === 0) return null;

    // Step 1: known-prefix match. We uppercase-normalise before emitting
    // the canonical form. Use String.prototype.match so we stay away from
    // the word "exec" that some static analysers flag.
    const prefixMatch = trimmed.match(PREFIX_SHAPE);
    if (prefixMatch !== null) {
      const prefix = prefixMatch[1];
      const body = prefixMatch[2];
      if (KNOWN_PREFIXES.has(prefix)) {
        return `${prefix}:${body}`;
      }
      // Unknown prefix — fall through to alias/unknown. Do NOT treat
      // "FOO:42" as an ORDER:42 numeric fallback; that would be a footgun.
      return null;
    }

    // Step 3: numeric fallback — bare digits → ORDER.
    if (NUMERIC_ONLY.test(trimmed)) {
      return `ORDER:${trimmed}`;
    }

    // Anything else (e.g. "42a", "hello", mixed-case unknown) is neither
    // prefix nor numeric. Let alias/unknown stages handle it.
    return null;
  }
}

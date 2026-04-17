// NetworkAliasResolver — V1.1 no-op stub.
//
// V1.1 ships without the `barcode_aliases` table being populated; the alias
// system arrives with V1.2 along with the goods-receipt alias-capture flow.
// This stub exists so ScannerRouter's constructor contract is honoured and so
// the swap to a real implementation in V1.2 is a single injection-site change.
//
// V1.2 will replace this body with a call to GET /api/v1/aliases/lookup/:code
// (see spec §10.a). Tests for that wiring belong to Slice 7 of V1.2, not here.

import type { AliasResolver, ResolvedEntity } from '../types/scanner';

export class NetworkAliasResolver implements AliasResolver {
  async lookup(_externalCode: string): Promise<ResolvedEntity | null> {
    // V1.1: alias system not yet available. Always returns null so that every
    // non-prefix / non-numeric scan falls through to the server for logging
    // as `resolution_path='unknown'`.
    return null;
  }
}

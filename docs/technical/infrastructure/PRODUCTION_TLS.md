# Production TLS (Caddy reverse proxy)

The production stack terminates HTTPS at a **Caddy** reverse proxy. Every request
from a workshop device is encrypted between the browser and Caddy; Caddy then
forwards it over the internal container network to the frontend nginx, which
serves the SPA and proxies `/api`, `/ws` and `/uploads` to the backend.

```
browser ──HTTPS(443)──▶ caddy ──HTTP──▶ frontend nginx ──HTTP──▶ backend
                                            (SPA + /api /ws /uploads proxy)
```

The `caddy` service is the **only** one that publishes ports to the LAN (443 and
80). The `backend` and `frontend` containers are `expose`-only — reachable inside
the compose network but never on the host — so no plaintext HTTP endpoint is
exposed to the workshop network. See `podman-compose.prod.yml` and
`deploy/Caddyfile`.

## Why Caddy

- **TLS with zero config for a LAN.** There is no public domain and no way to
  run public ACME/Let's Encrypt validation. Caddy ships a built-in CA
  (`tls internal`) that signs a locally-trusted certificate, and with
  `on_demand` it mints one for whatever LAN IP or hostname a browser requests
  (`https://192.168.1.50`, `https://goldsmith.local`, …). The Caddyfile needs no
  edit when the machine's IP changes.
- **Single moving part.** One small container, one config file. It slots in
  front of the existing frontend nginx without changing the SPA or the backend.
- **Rootless-friendly.** Runs with `no-new-privileges` like every other service
  and persists only two small volumes.

> **Security note:** `on_demand` issuance is safe here **only** because Caddy is
> reachable on the workshop LAN alone. Never publish `:443` to the public
> internet with `on_demand` enabled — it would let anyone trigger unbounded
> certificate issuance.

## COOKIE_SECURE is enforced in production

The login endpoint sets the HttpOnly session cookie with
`secure=settings.COOKIE_SECURE`. In production (`DEBUG=false`) the backend
**refuses to boot** unless `COOKIE_SECURE=true` — a `model_validator` in
`core/config.py` raises with an actionable message. Without TLS + a Secure
cookie, credentials and the session cookie would cross the LAN in cleartext.

`setup.sh` writes `COOKIE_SECURE=true` into the generated `.env.production`, so a
standard install is correct by default. The Secure flag governs the
browser↔Caddy hop (which is HTTPS); the internal Caddy→nginx→backend hops are
plain HTTP but never leave the container network.

## One-time step: trust the Caddy root CA on each device

Because the certificate is signed by Caddy's **own** CA (not a public one),
every device that opens the app must trust that CA once. Until then, browsers
show a certificate warning.

### 1. Export the root CA from the Caddy data volume

The CA lives inside the persisted `caddy_data` volume at
`/data/caddy/pki/authorities/local/root.crt`. Copy it out of the running
container:

```bash
podman cp goldsmith-caddy-prod:/data/caddy/pki/authorities/local/root.crt ./caddy-root.crt
# (Docker: docker cp goldsmith-caddy-prod:/data/caddy/pki/authorities/local/root.crt ./caddy-root.crt)
```

`caddy-root.crt` is the file you install on each workshop device. The
`caddy_data` volume is persisted, so the CA stays stable across restarts and
redeploys — you only distribute it once (re-export only if the volume is wiped).

### 2. Install `caddy-root.crt` per device

- **macOS:** double-click the file → Keychain Access → add to the **System**
  keychain → open the cert → *Trust* → *When using this certificate: Always
  Trust*. (CLI: `sudo security add-trusted-cert -d -r trustRoot -k
  /Library/Keychains/System.keychain caddy-root.crt`.)
- **iOS/iPadOS:** AirDrop/email the file to the device → install the profile in
  *Settings → General → VPN & Device Management* → then enable full trust in
  *Settings → General → About → Certificate Trust Settings*.
- **Android:** *Settings → Security → Encryption & credentials → Install a
  certificate → CA certificate* and pick the file. (Chrome on newer Android also
  honours user CAs for LAN sites; some apps need the system store.)
- **Windows:** `certutil -addstore -f Root caddy-root.crt` in an elevated prompt,
  or *Manage user certificates → Trusted Root Certification Authorities → Import*.
- **Firefox** (any OS) keeps its own trust store — import under *Settings →
  Privacy & Security → Certificates → View Certificates → Authorities → Import*
  and tick "Trust this CA to identify websites".

After trusting the CA, reload `https://<workshop-ip>` (or the mDNS name) — the
padlock should be clean with no warning.

## Troubleshooting

- **Certificate warning persists:** the device has not trusted `caddy-root.crt`,
  or you are hitting the box by a name/IP the browser did not request a cert for
  yet — reload once so `on_demand` provisions it, then retry.
- **`ERR_CONNECTION_REFUSED` on :443:** the `caddy` service is not up; check
  `podman-compose -f podman-compose.prod.yml ps` and Caddy's logs.
- **New root CA after redeploy:** the `caddy_data` volume was removed. Re-export
  the CA (step 1) and re-trust it. Keep the volume to avoid this.

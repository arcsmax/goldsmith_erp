# Security fixes, audit 2026-09-25 (wave 1: config, proxy, logging, headers)

Source: `docs/review/2026-09-25/02-security.md`. Each item has a regression test.

| ID | Change | Test |
|---|---|---|
| SEC-02 | `Settings` rejects the public `.env.example` placeholder for `SECRET_KEY` and `ANONYMIZATION_SALT` when `DEBUG=False` (error names the variable). With `DEBUG=True` it warns and boots. | `tests/unit/test_config.py::TestPlaceholderSecretsRejectedInProduction` |
| SEC-03 / F-1 | `setup.sh` generates `SECRET_KEY`, `ENCRYPTION_KEY` (stdlib, no `cryptography` needed on the host) and `ANONYMIZATION_SALT`, and no longer writes `ACCESS_TOKEN_EXPIRE_MINUTES` (the config default of 30 min applies). Re-running on an existing `.env.production` appends a missing salt (never rotates one) and warns about a token-lifetime override. `.env.example` no longer sets 11520. Non-interactive modes: `setup.sh --render-env <file>`, `setup.sh --upgrade-env <file>`. | `tests/scripts/test_setup_env.py` |
| SEC-04 | `core/client_ip.get_client_ip` resolves the real client behind Caddy/nginx: forwarded headers count only when the TCP peer is in `TRUSTED_PROXIES`, and the chain is walked right-to-left so client-prepended entries never win. Login, portal limiters, rate-limit middleware, audit log and request log use it. | `tests/unit/test_client_ip.py`, `tests/integration/test_rate_limit_real_client_ip.py` |
| SEC-05 | Request logs record `request.url.path` only, never the query string. The nginx access log uses a format with `$uri` and no referer. | `tests/unit/test_request_logging_no_query.py`, `tests/scripts/test_nginx_security_headers.py` |
| SEC-06 | nginx sends CSP (inline theme script allowed by sha256 hash), `X-Frame-Options`, `nosniff`, `Referrer-Policy`, `Permissions-Policy` and HSTS on the SPA document and assets, from `frontend/nginx-security-headers.conf`. Proxied `/api`, `/uploads`, `/ws` keep the backend's headers. | `tests/scripts/test_nginx_security_headers.py` |
| SEC-07 | `LabelService` HTML-escapes every interpolated value. | `tests/unit/test_label_service_escaping.py` |
| SEC-11 | `PUT /users/me` requires `current_password` to change email or password (400 if missing, 403 if wrong, logged without PII). | `tests/integration/test_users_me_reauth.py` |

## Operator notes

- `TRUSTED_PROXIES` (JSON array or comma-separated CIDRs) defaults to loopback,
  `10.0.0.0/8`, `172.16.0.0/12` and `fc00::/7`, which covers podman and docker
  networks but not `192.168.0.0/16`. If the workshop LAN itself is in `10.x` or
  `172.16-31.x`, narrow it to the compose subnet (`podman network inspect`).
- If the inline script in `frontend/index.html` changes, update its hash in
  `frontend/nginx-security-headers.conf`; the test above fails until you do.
- Existing installs: run `./setup.sh --upgrade-env .env.production` (or re-run
  `setup.sh`) to add the missing `ANONYMIZATION_SALT`, then remove any
  `ACCESS_TOKEN_EXPIRE_MINUTES=10080` line.

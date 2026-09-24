# Review 07: GDPR / Data Protection (2026-09-24, HEAD 73fff19, branch main)

**Reviewer:** Anna Becker (DPO persona), read-only review
**Scope:** Every rule in the CLAUDE.md "Data Privacy Rules (CRITICAL)" section checked against the code. Open GDPR findings from `docs/review/2026-04-23/04-gdpr-privacy.md` and `docs/review/2026-07-26/production-readiness.md` (rows 1.2-1.5, 2.2, 2.3, 2.5, 2.11, 2.12, 2.15) re-checked. Assessment of what a customer-feedback channel (status emails with photos, PDF reports, token status page) requires.
**Method:** Static reading of the schema, routers, services, middleware, jobs, scripts, systemd units, templates and docs. Nothing was executed against a live stack. All `path:line` references are relative to the repo root unless stated otherwise. Legal points marked "verify" should be confirmed with the Steuerberater or an external lawyer. They are not legal advice.

**Files examined (main ones):**
`src/goldsmith_erp/db/models.py`, `db/types.py`, `core/encryption.py`, `core/config.py`, `core/permissions.py`, `main.py`, `middleware/audit_logging.py`, `middleware/auth_required.py`, `middleware/logging.py`, `api/routers/{customers,customer_portal,customer_updates,orders,photos,repairs,quotes,valuations,scrap_gold,analytics,invoices,metal_inventory,materials,users,admin_email}.py`, `services/{customer_service,customer_update_service,notification_service,email_service,file_erasure_service,user_service,valuation_service,quote_service,image_validation,label_service,import_service,accounting_export_service,metal_price_service}.py`, `jobs/{gdpr_cleanup,retention_sweep}.py`, `db/repositories/customer.py`, `models/{customer,order,repair,material,comparison}.py`, `templates/email/*.html`, `scripts/{backup,backup-sync,gdpr-cleanup,rotate-secrets}.sh`, `deploy/systemd/*.service`, `podman-compose.prod.yml`, `frontend/src/pages/CustomerPortalPage.tsx`, `frontend/src/components/SignatureCanvas.tsx`, `docs/superpowers/plans/qr-barcode-workflow/VERZEICHNIS-VERARBEITUNGSTAETIGKEITEN.md`, `docs/technical/GDPR_ERASURE_RETENTION.md`, `docs/GDPR_COMPLIANCE.md`.

**Verdict in one paragraph:** The engineering has improved a lot since April. Customer contact PII and valuations are encrypted, the audit middleware is registered, the Art. 17 loop is closed in code, and employee erasure exists. Two things are still wrong. (1) The erasure path over-deletes. It scrubs and anonymises records that German tax and anti-money-laundering law require the workshop to keep unchanged (invoices, Altgold receipts and signatures). Invoices are rendered on the fly from the live customer row, so no immutable copy exists. (2) Role-based access has gaps: VIEWER can still read repair costs and insurance values, customer revenue, material prices, design descriptions and photos. Also missing: consent storage, Art. 9 handling of allergies, a customer privacy notice (Art. 13), and the pre-V1.1 entries of the Art. 30 record. The customer-feedback channel should not go live until the items in section E are done.

---

## A. Status of prior GDPR findings

| Source + id | Topic | Status | Evidence |
|---|---|---|---|
| Apr F (P0) | Customer names/email plaintext | **fixed** | `src/goldsmith_erp/db/models.py:245-262` (EncryptedString), `:255` email_hash blind index |
| Apr F (P0) | `appraised_value` plaintext | **fixed** | `db/models.py:2414-2423` (`_appraised_value_cipher` + HMAC) |
| Apr F (P0) | Encryption best-effort, exceptions swallowed | **partial** | Encrypt now raises (`db/types.py:99-104`). Decrypt still falls back to returning plaintext because `tolerate_plaintext=True` is the default for every column (`db/types.py:75,130`) |
| Apr F (P0) | VIEWER sees order financial fields | **partial** | Top-level fields stripped (`api/routers/orders.py:44-66`). Nested `OrderRead.materials[].unit_price` (`models/order.py:397`, `models/material.py:21`) is not in `_FINANCIAL_FIELDS` |
| Apr F (P0) | Financial reads not audited | **partial** | Middleware covers invoices, valuations, scrap-gold, consultations, updates, estimates (`middleware/audit_logging.py:120-172`). Quotes and analytics write structured logs only (`services/quote_service.py:53-61`, `api/routers/analytics.py:27-51`). Repairs and metal-inventory have no audit (grep count 0) |
| Apr F (P0) | AuditLoggingMiddleware not registered | **fixed** | `main.py:148-150` |
| Apr F (P0) | Consent columns referenced but missing | **open** | `db/repositories/customer.py:463` `update_consent` is dead code. `Customer` has no consent columns (`db/models.py:241-305`). No consent storage exists anywhere |
| Apr F (P0) | Cleanup cron: no file re-erasure, no audit | **fixed** | `services/customer_service.py:1768` (file sweep), `:1798-1811` (GDPRRequest row) |
| Apr F (P1) | Retention engine missing | **partial** | `jobs/retention_sweep.py` exists but covers only scan_logs, time_entries and material_usage, and ships in dry-run (`deploy/systemd/goldsmith-retention-sweep.service:44`) |
| Apr F (P1) | Export includes `order.description` | **fixed** | `api/routers/customers.py:333-352` |
| Apr F (P1) | VIEWER can read order photos | **open** | `api/routers/photos.py:114,137,180` gated by `ORDER_VIEW`. VIEWER holds it (`core/permissions.py:241`) |
| Apr F (P1) | Scrap gold readable by VIEWER | **fixed** | `api/routers/scrap_gold.py:65,243,314,333` `SCRAP_GOLD_VIEW` |
| Apr F (P1) | Signatures plaintext | **open** | `db/models.py:1157` (`scrap_gold.signature_data`), `:1494` (`quotes.customer_signature_data`) |
| Apr F (P1) | No startup check for ENCRYPTION_KEY | **fixed** | `core/config.py:210-224` |
| Apr F (P1) | Birthday without consent | **open** | `db/models.py:287` ("For marketing/gift vouchers"). CSV import still accepts it (`services/import_service.py:221-233`) |
| Apr F (P1) | No breach infrastructure (Art. 33/34) | **open** | No model, endpoint or runbook. grep for `DataBreach` in `src` finds nothing |
| Apr F (P1) | No customer self-service Art. 17 request | **open** | `api/routers/customer_portal.py` is read-only |
| Apr F (P2) | Export requires CUSTOMER_DELETE | **open** | `api/routers/customers.py:261` |
| Apr F (P2) | GDPRRequest has no artefact columns | **open** | `db/models.py:2890-2910` |
| Apr F (P2) | Labels print full customer name | **open** | `services/label_service.py:232,282` |
| Apr F (P2) | CustomerAuditLog has no retention | **open** | `db/models.py:2860-2887`. Not covered by the retention sweep |
| Apr F (P2) | `user_email` survives anonymisation | **fixed** | `services/user_service.py:484-487` |
| Apr F (P2) | GDPR_COMPLIANCE.md stale | **open** | `docs/GDPR_COMPLIANCE.md:4,14` still dated 2025-11-06 and still says "NOT GDPR compliant" |
| Jul 1.2 | GDPRRequest FK blocks PENDING row | **fixed** | `db/models.py:2894-2901` (FK dropped, migration `20260610_e1_gdpr_audit_nofk`) |
| Jul 1.3 | Hard-delete never runs | **partial** | Job and timer exist (`deploy/systemd/goldsmith-gdpr-cleanup.{service,timer}`). Install is manual and not part of `setup.sh`. The unit defaults to `COMPOSE_FILE=podman-compose.yml` while production uses `podman-compose.prod.yml` (`goldsmith-gdpr-cleanup.service:36`). The disposition also destroys tax records (GDPR-01) |
| Jul 1.4 | No employee erasure path | **fixed** | `api/routers/users.py:272-317` calls `anonymize_user` |
| Jul 1.5 | VIEWER reads Altgold | **fixed** | see above |
| Jul 2.2 | Financial reads unaudited | **partial** | materials, time-tracking, users, photos and measurements registered (`audit_logging.py:186-217`). Quotes, repairs, metal-inventory, analytics and `/customers/top` revenue are still not DB-audited |
| Jul 2.3 | Retention enforcement | **partial** | Dry-run only, three tables (see above) |
| Jul 2.5 | Backup vs erasure | **partial** | Policy documented (`docs/technical/GDPR_ERASURE_RETENTION.md:183-240`), but the policy has a logic hole (GDPR-07) |
| Jul 2.11 | Export emits order.description | **fixed** | `api/routers/customers.py:333-352` |
| Jul 2.12 | Plaintext financial/PII columns | **open** | `db/models.py:268` (notes), `:287` (birthday), `:1152-1157` (scrap-gold value/signature), `:1872` (repair insurance value). No documented exemption found |
| Jul 2.15 | Art. 30 record stale | **partial** | Refreshed to v1.1 (2026-07-26), but the V1.0 entries (customer master data, orders, photos, invoices, valuations) are still missing (`VERZEICHNIS...md` Anhang B, deadline 2026-05-31 missed). `DPIA-LIGHT-TEMPLATE.md`, which the record cites for TOMs, does not exist in the repo. V1.1-010 still describes the VIEWER orders leak as open |

---

## B. CLAUDE.md privacy-rule compliance matrix

| # | Rule | Compliant | Evidence | Gap |
|---|---|---|---|---|
| 1 | Customer names, addresses, phone, email encrypted at rest (EncryptedString) | **yes** (for the listed fields) | `db/models.py:245-262` | `country` plaintext (low). Adjacent PII (notes, birthday, measurements, preferences, style_profile) plaintext, see table C. Employee PII plaintext (`db/models.py:187-190`) |
| 2 | Never log customer PII | **partial** | Email recipients anonymised (`services/email_service.py:315`). Portal logs a reference hash (`customer_portal.py:381-388`) | `middleware/logging.py:46,68,83` logs `str(request.url)` including the query string, so `GET /customers/search?q=<name>` and `/customers/?search=<email>` put names and emails into app logs (GDPR-10) |
| 3 | Customer data exportable (Art. 15) | **partial** | `api/routers/customers.py:257-448` | Omits invoices, quotes, valuations, Altgold, repairs, customer_updates, cost-change approvals and photos. No Art. 15(1)(a)-(h) meta information. ADMIN only (GDPR-05) |
| 4 | Customer data deletable (Art. 17) | **partial** | `customers.py:551-800`, `customer_service.py:1681-1830` | Over-deletes statutory records (GDPR-01). Backup replay hole (GDPR-07). Timer not installed by default |
| 5 | Design IP (designs, CAD refs) GOLDSMITH/ADMIN only | **no** | VIEWER holds ORDER_VIEW and REPAIR_VIEW (`core/permissions.py:241,254`) | VIEWER reads `order.description` / `special_instructions` (`models/order.py:39,412`), order photos (`photos.py:114-180`), repair photos and item descriptions (`repairs.py:456-508`) (GDPR-04) |
| 6 | Design files not in exports without consent | **yes** | `customers.py:274-287,443-447` (`design_data_excluded`) | Legal tension: Art. 15 covers the customer's own statements. See GDPR-05 |
| 7 | Design descriptions business-confidential | **partial** | Export excludes them | Public portal returns `order.title` and `repair.item_description[:60]` (`customer_portal.py:222,267`). The REPAIR_RECEIVED email sends the internal `notification.message` to the customer (`notification_service.py:687`) |
| 8 | Financial data visible only to ADMIN/GOLDSMITH | **no** | Orders top level OK (`orders.py:44-66`) | VIEWER sees repair `estimated_value/estimated_cost/actual_cost` (`models/repair.py:241-245,275`; `repairs.py:62-104`), customer `total_spent` and the revenue ranking (`customers.py:108-190`; `customer_service.py:758,843`), material `unit_price` (`models/material.py:21`), metal purchase `price_total` (`models/metal_inventory.py:54`; `metal_inventory.py:106,157`), order Soll/Ist cost comparison via REPORTS_VIEW (`analytics.py:70`; `permissions.py:246`) (GDPR-03) |
| 9 | All financial data access audit-logged | **partial** | Middleware table `audit_logging.py:120-217` | Quotes and analytics are log-only. Repairs, metal-inventory, `/orders/{id}/photos`, `/orders/{id}` nested materials and `/customers/top` are not recorded in the DB with a financial action |
| 10 | Altgold = financial, same protection | **yes** (reads) / **partial** (at rest) | `scrap_gold.py:65` | `total_value_eur`, `gold_price_per_g` and `signature_data` plaintext (`db/models.py:1152-1157`) |
| 11 | Valuations encrypted at rest | **partial** | `db/models.py:2414` | `repair_jobs.estimated_value` ("Versicherungswert", `db/models.py:1872`) is plaintext. Valuation PDFs written via `record_pdf_path` (`services/valuation_service.py:260-274`) are plaintext files |
| 12 | Valuation access logged | **yes** | `audit_logging.py:123` | The repair insurance value is not logged |
| 13 | Valuations exportable only by ADMIN | **no** | `api/routers/valuations.py:297` uses `VALUATION_VIEW` (GOLDSMITH holds it). `VALUATION_EXPORT` is defined (`permissions.py:117`) but never used (`valuations.py:12-15` admits it) | GDPR-09 |
| 14 | Minimum data | **partial** | | Birthday kept "for marketing" without consent. Allergies are health data (GDPR-02). Free-text `customers.notes` has no guidance |
| 15 | Every PII field has a retention policy | **no** | `retention_class` only on orders, time_entries, material_usage, scan_logs (`db/models.py:553,750,1053,3060`) | customers (inactive), consultations, photos, customer_updates, quotes, repairs, audit logs, notifications, Redis portal tokens: no rule (GDPR-08) |
| 16 | Soft-delete, 30-day grace, then hard delete | **partial** | `customers.py:681-689`, `customer_service.py:1741-1747` | Plain `DELETE /customers/{id}` only sets `is_active=False` (`customer_service.py:732`) and is never purged. Timer install is manual |
| 17 | Anonymise audit logs on erasure (`deleted_user_{hash}`) | **partial** | Users: `user_service.py:484-487`. Customers: `customer_audit_logs.customer_id` SET NULL (`db/models.py:2866-2870`) | Employee `ip_address` / `user_agent` kept indefinitely (`db/models.py:2883-2885`). No retention |

---

## C. Encryption coverage (db/models.py)

Legend: ENC = EncryptedString / cipher column. PLAIN = stored in clear. Class: P = PII, H = health (Art. 9), F = financial, V = valuation, D = design IP, S = signature.

| Table.column | Line | Class | Storage | Note |
|---|---|---|---|---|
| customers.first_name / last_name / company_name | 245-247 | P | ENC | |
| customers.email | 254 | P | ENC | + `email_hash` HMAC blind index (255), key derived from ENCRYPTION_KEY (`core/encryption.py:98-113`) |
| customers.phone / mobile | 256-257 | P | ENC | |
| customers.street / city / postal_code | 260-262 | P | ENC | `country` PLAIN (263) |
| customers.allergies | 280 | **H** | ENC | Art. 9 data. Encrypted, but no explicit consent is stored and VIEWER can read it (`models/customer.py:43`, CustomerRead) |
| customers.notes | 268 | P | **PLAIN** | Free text, typically the richest PII field |
| customers.birthday | 287 | P | **PLAIN** | Marketing purpose, no consent |
| customers.ring_size / chain / bracelet | 272-274 | P | PLAIN | Low sensitivity, acceptable if documented |
| customers.preferences / style_profile / tags | 281-286, 269 | P | PLAIN | |
| customer_measurements.value / notes | 397, 405 | P | PLAIN | |
| customer_no_gos.value / note | 2150, 2157 | P/H | ENC | + value_hash (2156) |
| users.email / first_name / last_name | 187-190 | P (employee) | **PLAIN** | Outside the CLAUDE.md rule (it says "Customer PII"). Document the choice |
| orders.description / special_instructions / title | 459, 526, 458 | D (+P by accident) | PLAIN | Scrubbed on erasure |
| orders.price / cost / margin fields | 460-503 | F | PLAIN | Rule requires access control + audit, not encryption |
| scrap_gold.total_value_eur / gold_price_per_g | 1152-1153 | F | **PLAIN** | Jul 2.12 open |
| scrap_gold.signature_data | 1157 | S | **PLAIN** | Base64 PNG. Static image, not biometric under Art. 4(14) (no pressure/timing captured: `frontend/src/components/SignatureCanvas.tsx:148`) |
| scrap_gold.receipt_pdf_path file | 1159 | F/S/P | PLAIN file on disk | |
| quotes.customer_signature_data | 1494 | S | **PLAIN** | |
| repair_jobs.estimated_value | 1872 | **V** | **PLAIN** | "Versicherungswert des Stuecks". Violates rule 11 |
| repair_jobs.estimated_cost / actual_cost | 1886-1887 | F | PLAIN | VIEWER-visible |
| consultations.budget_min / max | 2046-2047 | F | PLAIN | Access-controlled (CONSULTATION_VIEW) |
| consultations.wishes / notes / source_material | 2049, 2065, 2051 | D/P | PLAIN | |
| valuation_certificates.appraised_value | 2414 | V | ENC | `appraised_value_hmac` (2423) reveals equal values across rows. Low risk |
| valuation_certificates PDF (pdf_path) | 2438 | V/P | PLAIN file | |
| customer_updates.body / subject | 2703-2704 | P/D | PLAIN | Scrubbed on erasure |
| cost_change_requests.* amounts / reason / evidence | 2791-2806 | F/P | PLAIN | |
| customer_audit_logs.old_value / new_value / ip / user_agent | 2879-2885 | P | PLAIN | Active code paths do not write customer PII into old/new values (only the dead repository does) |
| order_photos / repair_photos / consultation_photos files | 866, 1954, 2105 | D/P | PLAIN files | Originals keep EXIF. Only email variants are stripped (`services/image_validation.py:185-196`) |

**Key management:**
- ENCRYPTION_KEY: required in production and validated (`core/config.py:210-224`, `core/encryption.py:44-70`). Good.
- Rotation: no procedure. `scripts/rotate-secrets.sh:5-8,35-38` explicitly excludes it. There is no key-version column. The blind index is derived from the same key (`core/encryption.py:98-113`), so a rotation also invalidates `email_hash`, `value_hash` and `appraised_value_hmac`.
- Key escrow: no documented off-host copy of `.env.production`. If the host is lost, backups cannot be decrypted (Art. 32(1)(c) availability). `docs/DEPLOYMENT.md:427` says only "Restore correct encryption key from backup".
- `tolerate_plaintext=True` default (`db/types.py:75`): a row written while the key was missing would be served silently. There is no check that all rows are ciphertext.

**Backups:** `scripts/backup.sh:68-72` writes an **unencrypted** `pg_dump | gzip`. Encrypted columns stay ciphertext inside the dump, but every PLAIN row in the table above is in clear. `scripts/backup-sync.sh:58-65` PUTs the dump unencrypted to `BACKUP_CLOUD_URL` with no auth header (the URL is the credential) (GDPR-06). Uploaded files (`./uploads`) are not part of the DB dump at all.

---

## D. Findings

### GDPR-01 (CRITICAL): Erasure destroys records that tax and anti-money-laundering law require the workshop to keep; invoices have no immutable copy
- **Evidence:** Erasure scrubs `invoices.notes`, `invoice_line_items.description`, `quote_line_items.description`, `scrap_gold.signature_data`, `scrap_gold_items.description` and `quotes.customer_signature_data` (`services/customer_service.py:204,224,229,242`). It also deletes receipt PDFs and photos immediately (`customers.py` step 3, `file_erasure_service.py`). After 30 days, `anonymize_customer` overwrites name and address (`customer_service.py:1627-1648`). The invoice PDF is rendered on demand from the **live** customer row (`api/routers/invoices.py:397-438`) and no issued invoice is stored.
- **Legal basis:** §147 Abs. 1 Nr. 4, Abs. 3 AO and §14b UStG (keep invoices, including the recipient's name and address under §14 Abs. 4 Nr. 1 UStG and a description of the goods under Nr. 5. Retention for Buchungsbelege is 8 years since BEG IV 2025, verify with the Steuerberater). §146 Abs. 4 AO / GoBD Rz. 58 ff. (records must not be changed). GwG §8 Abs. 4 (5-year retention of identification records for Altgold cash purchases). GDPR Art. 17(3)(b) explicitly exempts these records, so the code goes further than the law requires, and in doing so breaks other laws.
- **Impact:** A tax audit (Betriebsprüfung) finds invoices without recipient or goods description. That can lead to rejection of the bookkeeping, a tax estimate (§162 AO) and loss of input-tax deduction for business customers. Any change to a customer's address also silently rewrites historic invoices. The workshop's own record `VERZEICHNIS...md` V1.1-009 says signatures are deleted only "nach Ablauf der GwG-Frist", which the code contradicts.
- **Fix:** (a) Store an immutable snapshot of every issued invoice: the PDF plus recipient name, address, line items and a hash, write-once, 8-10 years. (b) Exclude invoice, line-item, quote-accepted and Altgold columns from `SCRUBBABLE_FIELDS` while retention runs. Instead mark them "restricted" (Art. 18: access ADMIN-only, blocked from all other processing). Schedule deletion at the end of the retention period. (c) Do not delete Altgold receipt PDFs or signatures on request; retain for 5 years. (d) Document this in the Art. 30 record and in the answer letter to the customer (Art. 17(3)(b) reason).
- **Effort:** M-L. **Confidence:** high (code). Medium on the exact retention durations.

### GDPR-02 (CRITICAL): Allergy data (health data under Art. 9) processed without explicit consent and readable by all roles
- **Evidence:** `customers.allergies` (`db/models.py:280`) and no-gos (`db/models.py:2140-2157`) hold "Nickel", "Kupfer" and similar. `CustomerRead` returns allergies (`models/customer.py:43` via CustomerBase) to anyone with CUSTOMER_VIEW, VIEWER included (`core/permissions.py:245`). No consent columns exist anywhere (section A).
- **Legal basis:** Art. 9(1) GDPR (health data). Art. 9(2)(a) requires explicit consent. Performance of a contract (Art. 6(1)(b)) is not an Art. 9(2) exception. Art. 7(1): the controller must be able to prove consent.
- **Impact:** Unlawful processing of special-category data, which carries the highest fine tier. It is realistic: the allergy is exactly what a goldsmith writes down.
- **Fix:** Add a consent record (see GDPR-11) with purpose `health_allergy`, the wording shown, a timestamp, and how it was given (paper or tablet). Block writing `allergies` / health no-gos without it. Restrict reads to GOLDSMITH/ADMIN. Alternative: store only a material restriction ("kein Nickel verwenden") without the health reason. Confirm with a lawyer whether that wording escapes Art. 9.
- **Effort:** M. **Confidence:** high.

### GDPR-03 (HIGH): VIEWER role reads financial data and repair insurance values
- **Evidence:**
  - Repairs: `api/routers/repairs.py:62-104` return `RepairJobRead` / `RepairJobListItem` with `estimated_value`, `estimated_cost` and `actual_cost` (`models/repair.py:241-245,275`) under `REPAIR_VIEW`, which VIEWER holds (`permissions.py:254`). The schema docstring claims "enforced at the router level" (`models/repair.py:5-6`). It is not.
  - Customer revenue: `/customers/top?by=revenue` and `/customers/{id}/stats` (`customers.py:108-190`, `customer_service.py:758,843`) under CUSTOMER_VIEW.
  - Materials: `unit_price` (`models/material.py:21`) via MATERIAL_VIEW, including nested inside `OrderRead.materials` (`models/order.py:397`), which bypasses `_FINANCIAL_FIELDS`.
  - Metal purchases: `price_total` / `price_per_gram` (`models/metal_inventory.py:54,116`; `metal_inventory.py:106,157,387`).
  - Analytics: `/orders/{id}/comparison` and `/analytics/workshop-stats` under REPORTS_VIEW. VIEWER holds it (`permissions.py:246`), although the docstrings say "ADMIN und GOLDSMITH" (`analytics.py:77-79`).
- **Legal basis:** CLAUDE.md financial rule. Art. 5(1)(f), Art. 25(2) and Art. 32 GDPR (need-to-know). The insurance value doubles as a security risk: which customer owns what, and where they live.
- **Fix:** Reuse the C5 projection pattern (`orders.py:57-80`) for RepairJobRead and ListItem, material and metal-purchase schemas, customer stats and top, and nested `OrderRead.materials`. Remove REPORTS_VIEW from VIEWER, or split it into a non-financial scope. Add a test that walks every response model for a VIEWER token and asserts none of the financial keys appear.
- **Effort:** M. **Confidence:** high.

### GDPR-04 (HIGH): Design IP and photos readable by VIEWER
- **Evidence:** `photos.py:114,137,180` (ORDER_VIEW). `repairs.py:456-508` repair photos (REPAIR_VIEW). `OrderRead.description` and `special_instructions` are not stripped (`models/order.py:39,412`; `orders.py:44-54`).
- **Legal basis:** CLAUDE.md design-IP rule. Trade-secret protection under §2 Nr. 1 b GeschGehG requires "angemessene Geheimhaltungsmaßnahmen". Role-based access is exactly such a measure, and missing it weakens the workshop's legal protection of its designs.
- **Fix:** Add a `DESIGN_VIEW` permission (GOLDSMITH/ADMIN). Gate order, repair and consultation photo routes with it and strip `description` / `special_instructions` for other roles.
- **Effort:** S-M. **Confidence:** high.

### GDPR-05 (HIGH): Art. 15 export is incomplete and ADMIN-only
- **Evidence:** `customers.py:300-448` exports the customer, orders (id, status, price, dates), measurements, no-gos, style profile and consultation metadata. It omits invoices, quotes (including the stored signature), valuations (the customer's own appraisal), Altgold purchases, repairs, customer_updates sent to them, §649 cost-change approvals, and photos of their items. It also lacks the Art. 15(1)(a)-(h) information: purposes, recipients (Steuerberater, SMTP provider), storage periods, source, and the right to complain. It is gated by `CUSTOMER_DELETE` (`:261`). There is no `gdpr_requests` row of type export. Only a log line is written (`:338-347`); the middleware adds a generic "accessed" row.
- **Legal basis:** Art. 15(1), (3); Art. 12(3) (one month). CJEU C-307/22 and C-579/21 (copy of the data; log data about consultations). Excluding design IP: Art. 15(4) and Recital 63 allow withholding trade secrets, but not a blanket refusal. The customer's own wishes and the description of their heirloom (`source_material`) are their personal data. Give the customer-supplied facts and withhold only the goldsmith's design work.
- **Fix:** Extend the export to every customer-linked table. Add a static `meta` block (purposes, recipients, retention, rights). Write a `gdpr_requests(request_type='export')` row. Add a `GDPR_EXPORT` permission. Produce a PDF or JSON bundle suitable for handing to a customer. Revisit the design-IP exclusion with a lawyer: include `wishes` and `source_material` as told by the customer.
- **Effort:** M. **Confidence:** high (code). Medium on the Recital 63 balance.

### GDPR-06 (HIGH): Backups unencrypted; off-site sync is plaintext with URL-only auth; no key escrow
- **Evidence:** `scripts/backup.sh:68-72`, `scripts/backup-sync.sh:58-65`. No `gpg`/`age`/`openssl` step in either script. No documented off-host copy of ENCRYPTION_KEY.
- **Legal basis:** Art. 32(1)(a),(c). Art. 28 (the cloud provider is a processor and needs an AVV). Art. 44 ff. if the provider is outside the EU.
- **Impact:** A leaked dump exposes customer notes, birthdays, design briefs, repair insurance values, signatures, employee names and IP logs. Losing the host without a key copy makes every backup useless.
- **Fix:** Encrypt dumps with `age` (public key on the host, private key offline with Anne). Require an EU provider with an AVV and a signed or authenticated upload. Back up `./uploads` too (also encrypted). Document key escrow: a printed ENCRYPTION_KEY and ANONYMIZATION_SALT in Anne's safe, plus a restore test every quarter.
- **Effort:** S-M. **Confidence:** high.

### GDPR-07 (HIGH): The "re-run cleanup after restore" policy does not re-erase customers whose erasure postdates the backup
- **Evidence:** The cleanup selects only rows with `deletion_scheduled_at <= now` (`customer_service.py:1741-1747`). A dump taken before the erasure request contains the customer without that flag, and also lacks the `gdpr_requests` row. After a restore, the re-run finds nothing. `GDPR_ERASURE_RETENTION.md:203-206,236-239` claims the re-run "guarantees that an erasure is re-applied". That claim is false for this case.
- **Legal basis:** Art. 17(1), Art. 5(2) (accountability).
- **Fix:** Keep an append-only erasure ledger outside the DB and outside the dump rotation: customer_id, email_hash, request date, disposition. `restore.sh` replays it before the stack goes live (re-flag and run cleanup). Correct the policy doc.
- **Effort:** S. **Confidence:** high.

### GDPR-08 (HIGH): No storage limitation for most personal data
- **Evidence:** The sweep covers 3 tables, dry-run only (`jobs/retention_sweep.py:43-52`; `deploy/systemd/goldsmith-retention-sweep.service:44`). `orders.retention_class = indefinite_business` is excluded by design. Nothing expires inactive customers, consultations that never converted, quotes that were never accepted, customer_updates, photos, notifications or audit logs. Plain customer "delete" is never purged (`customer_service.py:712-732`).
- **Legal basis:** Art. 5(1)(e), Art. 5(2), Art. 30(1)(f).
- **Fix:** Write a retention schedule per table in the Art. 30 record. Suggested starting points, to be confirmed:
  - Invoices and Buchungsbelege: 8 years.
  - Accepted quotes and business letters: 6 years (§257 HGB).
  - Warranty-relevant order data: 2 years after delivery plus the 3-year limitation period to year end.
  - Non-converted consultations: 12-24 months.
  - Inactive customers without financial records: 3 years after last contact, then ask or erase.
  - Audit logs: 3 years.
  - Portal tokens: 1 h (already).

  Then extend the sweep and switch `RETENTION_EXECUTE=1` after sign-off.
- **Effort:** M. **Confidence:** high.

### GDPR-09 (MEDIUM): Valuation PDF export not limited to ADMIN; repair insurance value neither encrypted nor audited
- **Evidence:** `api/routers/valuations.py:297` uses `VALUATION_VIEW`. `VALUATION_EXPORT` is unused (`valuations.py:12-15`). `repair_jobs.estimated_value` is PLAIN (`db/models.py:1872`). Repairs are missing from `_RESOURCE_ROUTES`.
- **Fix:** Gate the PDF with VALUATION_EXPORT. Move `estimated_value` to the cipher pattern (`db/models.py:2414-2423`) and register `repairs` in the audit table.
- **Effort:** S. **Confidence:** high.

### GDPR-10 (MEDIUM): Customer names and emails in request logs via query strings
- **Evidence:** `middleware/logging.py:46,68,83` log `str(request.url)`. The customer search endpoints take names and emails as query params (`customers.py:51,85`). Logs go to `./logs` (`podman-compose.prod.yml:86`) with no rotation or retention found. Portal tokens are path parameters (`customer_portal.py:428`) and are logged the same way.
- **Legal basis:** CLAUDE.md "NEVER log customer PII". Art. 5(1)(c),(e). Art. 32.
- **Fix:** Log `request.url.path` only, or redact the query string. Mask `/portal/status/{token}`. Add logrotate with 30-90 day retention.
- **Effort:** S. **Confidence:** high.

### GDPR-11 (MEDIUM): No consent or objection management at all
- **Evidence:** No consent columns or table (section A). The repository `update_consent` targets non-existent attributes (`db/repositories/customer.py:463`). Email templates carry no privacy or opt-out footer (`templates/email/base.html:120-127`). Birthday is stored "for marketing" (`db/models.py:287`).
- **Legal basis:** Art. 6(1)(a), Art. 7, Art. 9(2)(a), Art. 21(2)-(4). §7 Abs. 2 Nr. 2 / Abs. 3 UWG. §25 TDDDG does not apply (no cookies or trackers found).
- **Fix:** Add a `customer_consents` table: customer_id, purpose (`email_status`, `email_marketing`, `birthday_greetings`, `photo_portfolio`, `health_allergy`), granted_at, withdrawn_at, method, wording version, evidence. Gate every non-transactional send on it. Add an opt-out link to every marketing email.
- **Effort:** M. **Confidence:** high.

### GDPR-12 (MEDIUM): Public portal leaks design details, is weak against a determined enumerator, and its rate limit is broken behind the proxy
- **Evidence:**
  - Order IDs are sequential integers (`customer_portal.py:342`). The only secret is the customer's email, which relatives and ex-partners know.
  - The response returns `order.title` and `repair.item_description[:60]` (`:222,267`), contradicting the docstring "no design details" (`:6`).
  - The limiter keys on `get_remote_address` (`:40,374`). Production runs uvicorn behind Caddy without `--forwarded-allow-ips` (`podman-compose.prod.yml:79-82`), so all customers most likely share the proxy's IP bucket. The in-memory limiter is also per worker (2 workers).
  - `/status/{token}` has no rate limit (`:428`).
  - The token is reusable for 1 h. The docstring calls it "one-time".
  - Lookups are not recorded in the DB audit.
  - Soft-deleted customers inside the grace window can still be looked up.
  - The portal page has no privacy-notice or Impressum link and still shows placeholder contact data (`frontend/src/pages/CustomerPortalPage.tsx:168-170`).
- **Legal basis:** Art. 25, Art. 32, Art. 13. §5 DDG (Impressum) once reachable from the internet.
- **Fix:** Replace ID+email with random per-order public references, or with signed links only (see E). Return a generic item label. Configure trusted-proxy headers. Add rate limits per reference and per IP. Record lookups in the audit. Add Datenschutz and Impressum links.
- **Effort:** M. **Confidence:** high on code. Medium on the proxy IP behaviour (not run live).

### GDPR-13 (MEDIUM): Internal staff text sent to customers in automatic emails
- **Evidence:** The REPAIR_RECEIVED path passes `notification.message[:120]` as the description and the order ID as the "bag number" (`services/notification_service.py:684-689`). The fitting reminder also passes `notification.message[:80]` (`:678-681`). These are internal notification texts written for staff.
- **Fix:** Build customer emails from explicit customer-facing fields only. Never reuse internal notification text.
- **Effort:** S. **Confidence:** high.

### GDPR-14 (MEDIUM): Per-employee performance analytics not covered by the Art. 30 record or the employee notice
- **Evidence:** `/analytics/goldsmith-accuracy/{user_id}` (`analytics.py:169-230`) gives ADMIN a personal accuracy score, best and worst order types, and a trend for each goldsmith. The Art. 30 record says "KEINE Leistungskontrolle einzelner Mitarbeiter" (V1.1-001/002) and has no entry for this.
- **Legal basis:** §26 BDSG / Art. 88 GDPR. Art. 13 (employee information). If a works council ever exists, §87(1) Nr. 6 BetrVG.
- **Fix:** Either aggregate it (minimum group of 3) or document it as its own processing activity with purpose and legal basis, and update `MITARBEITER-INFORMATION-BDSG26.md`.
- **Effort:** S. **Confidence:** high.

### GDPR-15 (MEDIUM): SMTP provider, cloud backup and accounting export are processors or recipients the documents don't cover
- **Evidence:** The Art. 30 record says "lokal konfigurierter SMTP; kein Cloud-Dienst" (V1.2-001). In reality `SMTP_HOST` can be set at runtime by ADMIN (`admin_email.py:130-151`), and a small workshop will almost certainly use a hosted mailbox (IONOS, Strato, Google). Backup cloud sync: GDPR-06. DATEV / lexoffice CSV export goes to the Steuerberater (`services/accounting_export_service.py:100,202`). The metal price API gets no PII (`metal_price_service.py:234`), so no AVV is needed.
- **Legal basis:** Art. 28 (AVV with the mail host and the backup host). Art. 30(1)(d) recipients. The Steuerberater is his own controller under §57 StBerG, so no AVV, but he must be listed as a recipient.
- **Fix:** Sign AVVs and list the recipients in the record and the privacy notice. Enforce TLS (`email_service.py:300-301` falls back to plaintext on any port other than 465/587).
- **Effort:** S. **Confidence:** medium (depends on the actual deployment).

### GDPR-16 (MEDIUM): Cleanup and retention timers are not wired by default and point at the dev compose file
- **Evidence:** `deploy/systemd/goldsmith-gdpr-cleanup.service:36` and `goldsmith-retention-sweep.service:41` set `COMPOSE_FILE=podman-compose.yml`. Production is `podman-compose.prod.yml`. `setup.sh` does not install the units (grep found nothing). The wrapper exits 1 if the backend service isn't found (`scripts/gdpr-cleanup.sh:36-40`), so a misconfiguration alerts rather than failing silently. Good, but only if the alert unit is also installed.
- **Fix:** Default to the prod compose file. Install and enable both timers from `setup.sh`. Add a health check that reports the last successful cleanup run.
- **Effort:** S. **Confidence:** high on the config. Medium on the runtime effect.

### GDPR-17 (MEDIUM): No breach-response capability (Art. 33/34)
- **Evidence:** No model, endpoint or runbook. `docs/GDPR_COMPLIANCE.md` §6.4 describes one that was never built.
- **Fix:** For a 3-person shop, a one-page runbook is enough: who decides, the Berlin/Land DPA contact, a 72-hour template, and how to pull `customer_audit_logs` for scoping. Add a breach register (a spreadsheet is fine) and an entry in the TOMs document.
- **Effort:** S. **Confidence:** high.

### GDPR-18 (LOW): Encryption hardening
- `tolerate_plaintext=True` default (`db/types.py:75`). Flip it to False for all customer columns once a one-off "all rows are ciphertext" check passes.
- No key version or rotation path (`scripts/rotate-secrets.sh:5-8`). Document a rotation procedure (decrypt/re-encrypt migration plus blind-index rebuild) even if it is never used.
- `appraised_value_hmac` (`db/models.py:2423`) shows which certificates share a value. Drop it if no equality search is needed.
- **Effort:** S-M. **Confidence:** high.

### GDPR-19 (LOW): Photo originals keep EXIF; labels print full names
- `services/photo_service.py:135` writes raw bytes. Only email variants are stripped (`image_validation.py:185-196`).
- `services/label_service.py:232,282` prints the customer's full name and ring size on bag labels.
- **Fix:** Strip EXIF on upload. Print initials only, or make the name a setting.
- **Effort:** S. **Confidence:** high.

### GDPR-20 (LOW): No customer self-service rights requests; audit rows keep employee IP and user agent indefinitely
- `customer_portal.py` is read-only. `db/models.py:2883-2885` has no retention.
- **Fix:** Add a portal "Anfrage zu meinen Daten" form that creates a PENDING `gdpr_requests` row and notifies ADMIN. Add an audit-log retention period (GDPR-08).
- **Effort:** S-M. **Confidence:** high.

---

## E. Customer-feedback channel: what must exist before launch

**Channel variants:** (1) status emails or digests with photos, (2) PDF progress reports, (3) a token-based status page, possibly with a comment or feedback box.

**Legal basis per purpose:**

| Purpose | Basis | Notes |
|---|---|---|
| Order status, ready-for-pickup, §649 cost notice | Art. 6(1)(b) | No consent needed. Mention it in the Art. 13 notice |
| Progress photos of the customer's piece | Art. 6(1)(b) if the customer asked for updates | If a person is visible (hands at a fitting), you also need consent under Art. 6(1)(a) / §22 KUG |
| Reuse of photos for the portfolio, Instagram or website | Art. 6(1)(a) consent, separate and revocable | Never bundle it with the order |
| Asking for satisfaction feedback or reviews after pickup | Treated as advertising (BGH VI ZR 225/17). Needs §7(3) UWG existing-customer exception plus an opt-out in every mail, or consent | Many shops get this wrong |
| Birthday or anniversary mails | Consent (Art. 6(1)(a) + §7(2) UWG) | `occasion_date` and `birthday` exist today with no consent |
| Customer comments or feedback text stored | Art. 6(1)(b) (order-related) / (f) (quality) | Needs a retention period and must be included in Art. 15 and Art. 17 |

**Checklist (present = verified in code):**

| # | Requirement | Present? | Evidence / gap |
|---|---|---|---|
| E1 | Consent store per purpose with proof (wording version, time, method), revocation | **no** | GDPR-11 |
| E2 | Art. 13 privacy notice for customers (paper at intake, link in every email and on the status page) | **no** | Nothing in `docs`, `templates` or `CustomerPortalPage.tsx` |
| E3 | Impressum and Datenschutz link on any internet-facing page | **no** | `CustomerPortalPage.tsx:168-170` placeholders |
| E4 | Email footer: sender identity, contact, opt-out link for any non-transactional mail | **partial** | `templates/email/base.html:120-127` has name and contact, but no opt-out and no privacy link |
| E5 | Only explicitly selected, EXIF-stripped, downsized photos in emails | **yes** | `customer_update_service.py:726-734`, `image_validation.py:185-196` |
| E6 | Data minimisation in status mails: no prices unless it is the §649 notice, no insurance value, no address, no internal notes | **partial** | Customer updates OK. Automatic REPAIR_RECEIVED leaks internal text (GDPR-13) |
| E7 | Recipient verification before the first photo or PDF mail (double-check or confirmation step) | **no** | Wrong-address risk for photos of valuables |
| E8 | TLS-enforced SMTP and an AVV with the mail provider | **partial** | STARTTLS only on 587, SSL only on 465 (`email_service.py:300-301`). No AVV (GDPR-15) |
| E9 | Status-page links: ≥128-bit random token, stored hashed, expiry (e.g. until pickup + 30 days), revocable, one per order, never containing the email | **partial** | `CustomerUpdate.token` uuid4 (122 bit), stored in plaintext, no expiry or revocation (`db/models.py:2717-2723`). Portal token: 256 bit, 1 h TTL, Redis, email in the payload (`customer_portal.py:403-411`) |
| E10 | Status page shows only: generic item label, pipeline step, date; no name, price, design text or photos unless opted in | **partial** | Leaks `order.title` / `item_description` (GDPR-12) |
| E11 | Token not logged, `Referrer-Policy: no-referrer`, `noindex`, no third-party assets | **partial** | Token logged via URL (GDPR-10). `middleware/security_headers.py:28` sets `strict-origin-when-cross-origin` (path stripped cross-origin; `no-referrer` preferred on the status page). No `noindex` found |
| E12 | Trusted-proxy config so rate limits work per client | **no** | GDPR-12 |
| E13 | Public TLS certificate and hardened exposure (reverse proxy exposing only `/portal` routes) | **no** | Current TLS guide uses an internal root CA for the LAN (commit `2499e52`). Customers' phones won't trust it. The whole API would be exposed unless Caddy restricts paths |
| E14 | Feedback and comment storage with a retention rule and inclusion in Art. 15 export and Art. 17 scrub | **no** | No such table yet. Add it to `SCRUBBABLE_FIELDS` and the export on creation |
| E15 | Right to object and unsubscribe honoured automatically (suppression list keyed on email_hash) | **no** | |
| E16 | Audit of every outbound customer email: what, to whom (customer_id), which photos, not the body | **partial** | `_log_financial_access` log line (`customer_update_service.py:750-756`). Automatic notification mails are not recorded |
| E17 | Art. 30 entry "Kundenkommunikation / Status-Seite" including the SMTP processor and the internet-facing exposure; short DSFA screening (Art. 35: new technology plus exposure to the internet) | **no** | V1.2-001 assumes "kein Live-Portal" |
| E18 | Separate consent before using any customer photo publicly | **no** | GDPR-11 |

**Minimum viable path:** Start with email plus PDF (no internet-exposed page). That needs E1, E2, E4, E6, E7, E8, E15 and E17. Leave the token status page (E9-E13) for a later phase. It changes the threat model from "LAN only" to "internet-facing", and should come after GDPR-12 is fixed.

---

## F. Documentation gaps

1. **Art. 30 record (`VERZEICHNIS...md`):**
   - Controller listed as "Max Kull (Einzelunternehmer)". The controller is Anne's workshop, the business that deals with customers. The developer is not the controller, and at most a processor if he operates the system for her.
   - The same person is named as controller and DPO (Art. 38(6) conflict). With fewer than 20 people processing, no DPO is required (§38 BDSG). Better to name none than a conflicted one.
   - Address and contact fields are still `[AUSFUELLEN]`.
   - V1.0 entries (customer master data, orders, photos, invoices, valuations) are still missing (Anhang B).
   - V1.1-010 still says the VIEWER leak is open. It was fixed for top-level order fields, but new leaks exist (GDPR-03).
2. **Processing activities in code but not in the record:**
   - Consultations (budget, wishes, allergies and no-gos, style profile, sketches)
   - Repair intake (insurance value, photos, checklist)
   - Customer portal (public lookup, Redis tokens)
   - Automatic customer notification emails
   - CSV customer import
   - Calendar and follow-up reminders
   - Label printing
   - Per-employee accuracy analytics (GDPR-14)
   - ML duration prediction
   - Request and audit logging (IP and user agent of staff)
   - Backups and cloud sync
   - DATEV / lexoffice export
3. **TOMs (Art. 32):** The record cites `DPIA-LIGHT-TEMPLATE.md` §4-§5 for TOMs, but that file does not exist in `docs/superpowers/plans/qr-barcode-workflow/` (listing: EIDAS, MITARBEITER, PII-SCRUB-AUDIT, USER-FK-AUDIT, V1.1-POST-WAVE5, VERZEICHNIS). As a result, no TOM document exists.
4. **Art. 13 customer privacy notice:** missing. Needed at intake (paper), on the portal and in emails.
5. **Employee information:** `MITARBEITER-INFORMATION-BDSG26.md` exists. It needs updating for per-user analytics and request logging.
6. **AVV / processor list:** missing (SMTP host, backup host, hosting if it ever moves off-prem).
7. **Retention schedule:** `GDPR_ERASURE_RETENTION.md` covers erasure and 3 tables. There is no per-table schedule (GDPR-08). It also needs correcting for GDPR-01 (what is not erased and why) and GDPR-07.
8. **Breach runbook and register:** missing (GDPR-17).
9. **Key-management runbook:** escrow, rotation, restore test (GDPR-06/18).
10. **`docs/GDPR_COMPLIANCE.md`:** stale since 2025-11-06 and still says "NOT GDPR compliant". Replace it with a pointer to the current documents.
11. **`PII-SCRUB-AUDIT.md`** (2026-04-17) is the "single source of truth" for field classification. It predates V1.2/V1.3 columns (customer_updates, cost_change_requests, estimate_accuracy).

---

## G. Prioritized fix order

| Order | Item | Why first | Effort |
|---|---|---|---|
| 1 | GDPR-01: stop scrubbing invoices, quotes and Altgold. Add an immutable invoice snapshot | Current code destroys legally mandated records on every erasure, and every address edit rewrites old invoices. Highest legal exposure (tax plus GwG) | M-L |
| 2 | GDPR-02 + GDPR-11: consent table, then allergies behind explicit consent, plus GOLDSMITH/ADMIN-only reads | Special-category data without a legal basis. The consent table is also the foundation for the feedback channel | M |
| 3 | GDPR-03 + GDPR-04 + GDPR-09: role projection sweep (repairs, customer stats and top, materials, metal purchases, analytics, photos, design text, valuation PDF) plus a single VIEWER-response test | Several leaks with one shared fix pattern | M |
| 4 | GDPR-06 + GDPR-07: encrypted backups, key escrow, erasure ledger replayed on restore | A breach or a restore undoes everything else | S-M |
| 5 | GDPR-16 + GDPR-08: install timers with the prod compose file, write the retention schedule, enable the sweep | Storage limitation. Makes the documented policy actually run | M |
| 6 | Documentation: Art. 30 controller correction plus V1.0 entries, TOMs, Art. 13 notice, AVVs, breach runbook (section F) | Cheap. First thing a supervisory authority asks for | S-M |
| 7 | GDPR-05: complete the Art. 15 export | One-month response deadline once a customer asks | M |
| 8 | GDPR-10, GDPR-13, GDPR-14, GDPR-15 | Logging hygiene, customer-email content, employee analytics, processors | S each |
| 9 | Feedback channel phase 1 (email/PDF): E1, E2, E4, E6, E7, E8, E15, E17 | After 2 and 6 | M |
| 10 | GDPR-12 + E9-E13: token status page, only after the portal is hardened | Internet exposure | M-L |
| 11 | GDPR-17-20 | Hardening | S |

---

## H. Things the user might have missed

1. **The controller is Anne, not Max.** Every legal document (Art. 30 record, privacy notice, AVVs, breach notification) must name Anne's business. If Max operates or hosts the system for her, he is her processor and needs an AVV with her. Self-appointing the controller as DPO is a conflict of interest.
2. **Retention periods changed in 2025.** BEG IV shortened retention of Buchungsbelege, including invoices, from 10 to 8 years (§147 Abs. 3 AO, §14b UStG). The code and docs say "financial_10y" everywhere. Keeping data too long is itself an Art. 5(1)(e) problem. Verify with the Steuerberater which documents stay at 10 years (books, annual accounts) versus 8 (receipts) versus 6 (business letters, accepted quotes).
3. **GwG identification for Altgold cash purchases.** Precious-metal traders must identify the seller for cash transactions from 2,000 EUR (§10 Abs. 6a Nr. 1 b GwG, verify). That means name, date and place of birth, nationality, address, and ID document type, number and authority. `scrap_gold` has none of these fields, and `customer_id` is nullable, so walk-in purchases are possible with no identity at all (`db/models.py:1137-1142`). This is a legal gap regardless of GDPR. It also means the Art. 30 record's GwG legal basis (V1.1-009) currently has no data behind it.
4. **No APPRENTICE role exists** (`db/models.py:66-71`: ADMIN, GOLDSMITH, VIEWER). An apprentice must be given either GOLDSMITH (full financial, valuation and design access) or VIEWER (which still leaks, GDPR-03). If apprentices are planned, the role model has to change before they get accounts.
5. **"Scrub" is not "erasure" for data other people hold.** Photos and PDFs sent by email stay in the SMTP provider's sent folder and the customer's mailbox. Art. 17(2) asks the controller to take reasonable steps, and the sent-mail folder is in the workshop's control. Include the mailbox in the erasure runbook.
6. **Invoices re-rendered from live data are also a correctness bug.** Beyond erasure, a customer who moves has all old invoice PDFs regenerated with the new address, and a VAT-rate or line-item change would do the same. An immutable issued-invoice snapshot fixes GoBD, erasure and reproducibility at once.
7. **Signatures are not biometric data in this implementation.** The canvas exports a static PNG with no pressure or timing data (`SignatureCanvas.tsx:148`). Art. 9 does not apply, so don't over-engineer. Encrypting them at rest (Jul 2.12) is still sensible, since the image can be forged from. Under eIDAS a simple electronic signature is legally sufficient for a formfree Kaufvertrag. A qualified signature is not required by GwG.
8. **Internet exposure changes the whole assessment.** Everything so far assumed a LAN. The moment `/portal` is reachable by customers from the internet, the entire API behind Caddy is reachable too, unless Caddy only forwards `/api/v1/portal/*`. At that point login rate limiting and brute-force protection become internet-facing, and a short DSFA screening (Art. 35) should be written down.
9. **Asking for a review counts as advertising.** A "Wie zufrieden waren Sie?" email after pickup needs consent or the §7(3) UWG existing-customer route with an opt-out in each mail. Design this into the feedback channel from the start.
10. **The design-IP export exclusion may be over-broad.** CLAUDE.md's blanket rule protects the workshop, but a customer who asks "what did I tell you about my grandmother's ring?" is entitled to that (their own statements, `consultations.source_material`). Separate customer-supplied facts, which you must disclose, from the goldsmith's design work, which you may withhold under Art. 15(4).

---

## Verification (2026-09-25)

Verifier: `.orchestrated-fable/ux-erp-audit-2026-09/verify-security-gdpr.md` (adversarial, read-only, HEAD `73fff19`). All eight CRITICAL/HIGH findings confirmed; none dropped or downgraded.

| ID | Title (short) | Claimed | Verdict | Corrected severity | Verifier note |
|---|---|---|---|---|---|
| GDPR-01 | Erasure destroys tax/AML records; no invoice snapshot | CRITICAL | CONFIRMED | CRITICAL | Understated if anything: signatures and invoice text are scrubbed at request time, not after the 30-day grace; file erasure also runs immediately. Legal durations remain "verify" |
| GDPR-02 | Allergy data without consent, VIEWER-readable | CRITICAL | CONFIRMED | CRITICAL | No consent columns anywhere; `update_consent()` targets non-existent attributes. Art. 9 classification is a legal judgment |
| GDPR-03 | VIEWER reads repair costs/insurance value, revenue, prices | HIGH | CONFIRMED | HIGH | Same code and root cause as SEC-01 |
| GDPR-04 | Design IP and photos readable by VIEWER | HIGH | CONFIRMED | HIGH | Exact line matches; no `DESIGN_VIEW` exists |
| GDPR-05 | Art. 15 export incomplete, ADMIN-only | HIGH | CONFIRMED | HIGH | Gated by `CUSTOMER_DELETE`; only orders, measurements, no-gos, consultations loaded |
| GDPR-06 | Backups unencrypted; cloud sync URL-only auth | HIGH | CONFIRMED | HIGH | No gpg/age/openssl; no auth header on the PUT |
| GDPR-07 | Re-run cleanup after restore misses earlier backups | HIGH | CONFIRMED | HIGH | The doc's "guarantees" claim is contradicted by the WHERE clause |
| GDPR-08 | No storage limitation (3 tables, dry-run) | HIGH | CONFIRMED | HIGH | Exact matches on all three citations |

MEDIUM and LOW findings (GDPR-09 to GDPR-20) were outside the verifier's scope. No new CRITICAL/HIGH issue was found.

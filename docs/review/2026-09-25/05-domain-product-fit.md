# Review 05: Domain and Product Fit (Goldsmith Workshop)

- **Reviewer:** Meister Thomas Brenner (domain persona: Goldschmiedemeister, 25 years at the bench, ERP consultant for the craft trades)
- **Date:** 2026-09-24, repo `main` @ 73fff19
- **Scope:** Does the built product make it "easier and faster for a goldsmith to keep track of their work and clients, and enable the clients to get better feedback on their jewelry"? Covers features and workflows from the bench and the customer's point of view. Code quality, security and architecture are out of scope (other reviewers cover them).
- **Method:** Read-only. I read the vision, requirements and user-guide docs first, then checked every claim against routers, services, models and React pages. "Exists" means reachable from the UI unless I say "backend only". Where I trace behaviour I cite `path:line`. I also ran one schema check: `ScrapGoldItemCreate(alloy=925)` raises `Input should be a valid string`, which confirms DOM-19.
- **Docs read:** `docs/planning/VISION_AND_ROADMAP_2026-07.md`, `docs/feedback/Ideensammlung.md`, `docs/technical/specs/GOLDSMITH_WORKSHOP_REQUIREMENTS.md` (outline), `docs/user-guide/DAILY_WORKFLOWS.md`, `docs/user-guide/features/*` (list), `CLAUDE.md`.
- **Code examined (main):** `src/goldsmith_erp/api/routers/{orders,customers,customer_portal,customer_updates,photos,quotes,repairs,consultations,notifications,handoffs,calendar,time_tracking,scanner,scrap_gold,invoices,valuations,hallmarks,measurements,metal_prices,ml,analytics}.py`; `services/{order,quote,consultation,customer_update,notification,repair,scrap_gold,invoice,pdf,email,metal_price}_service.py`, `services/system_monitor.py`; `db/models.py`; `models/{order,scrap_gold,customer}.py`; `frontend/src/App.tsx`, `layouts/MainLayout.tsx`, `pages/*` (OrderDetail, Dashboard, CustomerDetail, Quotes, Consultation wizard, Portal), `components/{orders,scrap-gold,qc,scanner,dashboard}/*`, `api/*.ts`.

---

## A. Product goal and the jobs it implies

The goal has two halves. The first is **workshop throughput and memory**: fewer paper bags and sticky notes, less searching, nothing forgotten. The second is **customer confidence**: the customer sees how their piece is progressing and gets a say before costs or designs change.

| # | Who | Job to be done | What "done well" looks like at the bench |
|---|---|---|---|
| J1 | Goldsmith | **Take in a piece or a wish once, completely.** | One flow at the counter: customer, piece, photos, measurements, metal, stones, deadline and signature. Nothing gets typed twice later. |
| J2 | Goldsmith | **Know at a glance what to work on next and what is burning.** | One screen with overdue and due-soon work, pieces waiting on stones or on the customer, and today's pickups. One tap from each item to the action. |
| J3 | Goldsmith | **Price honestly and stay legally safe.** | Quote from real metal price plus historic labour. §649 BGB overrun notice. §14 UStG invoice, correct Altgold credit. Hallmark only where applicable. |
| J4 | Customer | **Know where my piece is, see it, and be asked before things change.** | Push updates with photos, a durable link, one-click approve/decline for design or cost changes, a pickup notice that arrives once. |
| J5 | Customer + goldsmith | **Keep the relationship after pickup.** | Care instructions, warranty, insurance valuation, the piece's history with photos, and a reminder for re-polish, resizing or an anniversary. |

---

## B. Capability inventory

Quality is scored from a user's view: 1 = unusable/absent, 3 = works with friction, 5 = would use daily without complaint.

| Feature | Exists | Where | Job | Quality | Note |
|---|---|---|---|---|---|
| Customer master data (encrypted, GDPR) | yes | `routers/customers.py`, `pages/CustomersPage.tsx`, `CustomerDetailPage.tsx:16` | J1,J5 | 3 | Email is mandatory (`models/customer.py:16`), which blocks walk-ins with no email |
| Measurement library | yes | `routers/measurements.py`, `components/measurements/MeasurementPanel.tsx` | J1 | 3 | Also duplicated in `Customer.ring_size` (`db/models.py:~245`). Not used to prefill the order |
| No-gos / style profile | yes | `customers.py:906-1037`, `consultation/NoGoWarning.tsx` | J1 | 4 | Good. Warns on order form (`OrderFormModal.tsx:300-320`) |
| Consultation wizard (7 steps) | yes | `pages/ConsultationWizardPage.tsx`, `components/consultation/*` | J1 | 3 | Rich capture, but conversion drops most of it (DOM-03) |
| Order intake form with Pflichtfelder | yes | `components/orders/OrderFormModal.tsx:216-236` | J1 | 3 | Metal+alloy duplicated; ring detection by substring; no stones |
| Gemstones (4C, Fassung) | backend model only | `db/models.py:879-915`; no router creates `Gemstone` | J1,J3 | 1 | No API, no UI |
| Order photos | backend only | `routers/photos.py:55` upload; `frontend/src/api/photos.ts:4-7` has only `getForOrder` | J1,J4 | 1 | **No upload anywhere in order UI** (DOM-01) |
| Repair pipeline + intake photos | yes | `routers/repairs.py`, `pages/RepairDetailPage.tsx:388`, `repairs/IntakeChecklist.tsx` | J1 | 4 | Solid. No customer-facing messaging (DOM-12) |
| Quotes (KVA) + PDF + signature | yes | `routers/quotes.py`, `pages/QuotesPage.tsx:230-305` | J3 | 3 | "Send" only flips status (`quote_service.py:762-790`) |
| Labour estimator | yes | `routers/estimator.py`, `components/estimator/EstimatorPanel.tsx` | J3 | 3 | Only as good as the corpus. Order type is often missing (DOM-03) |
| Metal price sync | partial | `services/metal_price_service.py:146-148`, `system_monitor.py:312` | J3 | 2 | Falls back silently to hardcoded defaults. Source not shown in UI |
| Cost watch + §649 change request | yes | `routers/customer_updates.py:230-385`, `orders/CostAlertBanner.tsx`, `CostChangeSection.tsx` | J3,J4 | 4 | Well thought out. Approval is recorded manually |
| Customer progress updates (email/PDF) | yes | `customer_updates.py:75-228`, `orders/KundeninfoTab.tsx` | J4 | 3 | Manual only. Photos only from order photos, which cannot be uploaded (DOM-01) |
| Customer portal (status lookup) | yes | `routers/customer_portal.py:363-453`, `pages/CustomerPortalPage.tsx` | J4 | 2 | Pull only, status text, 1 h tokens, no photos. LAN-only in practice |
| Automated customer emails | yes (implicit) | `notification_service.py:49-57,103-113` | J4 | 1 | Sends one email per staff user, daily or more (DOM-10) |
| Order status lifecycle | yes | `db/models.py:47-63`, `OrderDetailPage.tsx:453-490` | J2 | 2 | No cancelled, no on-hold. Free jumping between statuses |
| Status history | backend only | `db/models.py:2938` `OrderStatusHistory` | J2 | 1 | UI "Verlauf" shows only created/updated (`OrderDetailPage.tsx:492-521`) |
| QR labels + scanner + quick actions | yes | `routers/scanner.py`, `pages/ScannerPage.tsx`, `components/scanner/*` | J2 | 4 | Best bench-oriented feature in the app |
| Time tracking + interruptions | yes | `routers/time_tracking.py`, `TimerWidget.tsx`, `ActionHandlers.ts:300-314` | J2,J3 | 4 | Good. Seed activities lack Giessen/Wachs/Montage/Rhodinieren (`seed_data.py:41-97`) |
| Handoffs between staff | yes | `routers/handoffs.py`, `orders/HandoffTab.tsx`, dashboard accept/decline `DashboardPage.tsx:223-234` | J2 | 4 | Matches Anne's "Stabuebergabe" |
| Order comments (digital post-it) | yes | `routers/comments.py`, `CommentsTab.tsx` | J2 | 3 | Only reachable per order. No "unread for me" list |
| Calendar with traffic light | yes | `pages/CalendarPage.tsx:1-70`, `routers/calendar.py` | J2 | 4 | Matches Anne's Ampel idea |
| In-app notifications + reminder scans | yes | `notification_service.py:226-600`, `system_monitor.py:316-322`, `NotificationBell.tsx` | J2 | 3 | Scans run every cycle. Customer-email side effect is broken (DOM-10) |
| Dashboard (role-based) | yes | `pages/DashboardPage.tsx:193-630`, `components/dashboard/*` | J2 | 2 | Overdue ranked lowest. No repairs, quotes or customer items (DOM-14/15) |
| Materials + purchase list by supplier + low stock | yes | `routers/materials.py:112`, `MaterialsPage.tsx:33` | J2 | 4 | Matches Anne's Einkaufsliste |
| Metal inventory (FIFO/LIFO/avg) | yes | `routers/metal_inventory.py`, `MetalInventoryPage.tsx` | J3 | 3 | Parallel to Materials. Two stock worlds (DOM-33) |
| Altgold with signature + receipt PDF | yes | `routers/scrap_gold.py`, `scrap-gold/ScrapGoldTab.tsx` | J3 | 1 | UI add-item contract broken. Silver priced as gold (DOM-19/20) |
| Invoices + DATEV/lexoffice export + Altgold credit | yes | `routers/invoices.py:57-457`, `InvoicesPage.tsx`, `SollIstTab.tsx:195` | J3 | 3 | PDF lacks §14 UStG seller data (DOM-24) |
| Soll/Ist + Arbeitszettel | yes | `orders/SollIstTab.tsx`, `orders/ArbeitszettelTab.tsx` | J3 | 4 | Matches Anne module 2 |
| Punzierung check | yes (scanner only) | `qc/PunzierungsCheckModal.tsx`, `ActionHandlers.ts:399-410`, `order_service.py:36-90` | J3 | 2 | Too few marks. Mandatory gate. Not in order page (DOM-22/23) |
| Hallmark register (assay workflow) | backend only | `routers/hallmarks.py`, `db/models.py:2230-2340`; `api/hallmarks.ts` unused | J3 | 1 | UK-style assay-office states. Second hallmark system |
| Insurance valuation certificate | backend only | `routers/valuations.py`, `db/models.py:2340`; `api/valuations.ts` has no consumer | J5 | 1 | Strong aftercare value with no UI |
| Care instructions / warranty / anniversary reminders | no | grep for `Pflege|warranty|Garantie|anniversary` in `src/` finds nothing | J5 | 1 | |
| Deposit (Anzahlung) / dunning | no | grep for `Anzahlung|deposit|Mahnung` finds nothing | J3 | 1 | |
| Customer rating / feedback | no | none | J4 | 1 | |
| ML (duration, anomaly, forecast) | backend only | `routers/ml.py` (914 lines); no frontend call | none | n/a | Bloat (section E) |
| Analytics | backend only | `routers/analytics.py`; no frontend call | J2 | n/a | Bloat |
| Offline queue | no (deferred) | `lib/network-transport.ts:1-7` ("V1.1.5 offline-queue swap") | J2 | 1 | Idempotency is ready. The queue does not exist |

**Coverage of Anne's own Ideensammlung:** module 1 (Pflichtfelder) partial; 2 (Kalkulation, Soll/Ist, invoice by click) yes; 3 (Lager, pictures, supplier list) yes; 4 (Altgold) exists but broken; 5 (deadlines, Ampel, reminders) yes, with the email bug; 6 (360° profile, visual history) partial, because order photos cannot be added; 7 (role dashboard, post-its, handoff) mostly yes. Anne's ideas are mostly **built**. What is missing is the **connective tissue**: data carried from one step to the next, photos, and messages that reach the customer.

---

## C. Workflow assessments

### C1. Intake (custom piece or repair)

**Narrative.** A customer comes in with a wish. Anne can run the consultation wizard (`ConsultationWizardPage.tsx`, 7 steps: customer, occasion/budget, wish, style/no-gos, measurements, sketches/photos, summary). That is a good counter experience, and the no-go capture is better than anything I have seen in DACH tools. Then she converts. Converting to an **order** creates a shell with only `customer_id`, a title "Beratung #n: ring" and the wish text (`consultation_service.py:297-305`). The occasion date does not become the deadline. `piece_type` does not become `order_type`. `materials_discussed` does not become metal/alloy. The consultation photos do not become order photos. She now has to open the order form and re-enter metal, alloy, deadline and ring size, because those are Pflichtfelder (`OrderFormModal.tsx:216-223`). Counting screens: 7 wizard steps, convert, open the order, edit modal with 2 tabs. That is roughly 10 screens, with part of the data typed twice.

A repair is better. `RepairsPage` plus `IntakeChecklist.tsx` gives phase photos, bag number and a label. But there is no customer signature or receipt ("Reparaturannahmeschein") and no stated liability terms for stones.

What is not captured anywhere: **stones** (no Gemstone API: `db/models.py:879` model only), **Fassungsart** (free text on an unused model), **customer consent** (photo use, marketing, AGB), **deposit**, and **customer-supplied material** other than Altgold (e.g. a family stone, which `Consultation.source_material` holds as free text).

| ID | Gap | Evidence | Impact | Proposal | Effort |
|---|---|---|---|---|---|
| DOM-01 | No way to upload order photos in the UI. Scanner "take photo" goes nowhere | `frontend/src/api/photos.ts:4-7` (read only); `ActionHandlers.ts:316-321` navigates to `?action=take-photo`, but `OrderDetailPage.tsx` never reads search params; user guide promises a "Foto hochladen" button (`DAILY_WORKFLOWS.md:196-201`) | **H** | Add camera/upload to the Fotos tab and honour `?action=take-photo` (open the camera directly). Reuse the repair upload component | S |
| DOM-02 | Walk-in customers without email cannot be created | `models/customer.py:16` `email: EmailStr = Field(...)`; `db/models.py` `email ... nullable=False`, unique `email_hash` | **H** | Make email optional (phone-only customers are common among older repair clients). Keep uniqueness only when present | M |
| DOM-03 | Consultation→order/quote conversion drops deadline, piece type, metal, measurements, photos | `consultation_service.py:297-305` (OrderCreate with 3 fields); quote path `:306-340` only adds a budget line | **H** | Map `occasion_date`→`deadline`, `piece_type`→`order_type`, first `materials_discussed`→`metal_type/alloy`, ring measurement→`ring_size_mm`; link consultation photos to the order | M |
| DOM-04 | No gemstone capture (4C, certificate, Fassungsart, customer's own stone) | `Gemstone` at `db/models.py:879-915`; no router or service creates it; order form comment admits "no separate gemstone field" `OrderFormModal.tsx:305` | **H** | Small "Steine" section on the order: type, count, ct, colour/clarity, shape, Fassungsart dropdown (Zargen, Krappen, Kanal, Pavee, Spann, Unsichtbar), "Kundenstein ja/nein" | M |
| DOM-05 | Ring-size requirement triggered by substring "ring", so "Ohrring" demands a ring size | `OrderFormModal.tsx:228-230` | M | Drive it from `order_type == ring` (the field exists: `db/models.py` `order_type`) and add `order_type` to the form | S |
| DOM-06 | Metal and alloy entered twice and can contradict each other; no 333 in MetalType, no Palladium alloy | `MetalType` `db/models.py:74-93` vs `ALLOY_OPTIONS` `OrderFormModal.tsx:38-48`; scanner needs `AlloyMismatchModal.tsx` to catch the conflict | M | One picker "Legierung & Farbe" (e.g. "585 Gelbgold", "750 Weissgold", "Pd 950") from which both fields derive | M |
| DOM-07 | No consent capture (photo use for updates/portfolio, marketing birthday mails, AGB) | vision backlog item "Consent tracking" (`VISION_AND_ROADMAP_2026-07.md` backlog); `Customer` has `birthday` but no consent fields (`db/models.py:218-356`) | M | Three checkboxes at intake plus a timestamp. Gate birthday or anniversary mails on marketing consent | S |
| DOM-08 | Repair intake has no signed receipt or conditions | `RepairJob` fields `db/models.py:1828-1933` (no signature); `SignatureCanvas` exists for quotes/Altgold only | M | Reuse SignatureCanvas and render an "Annahmeschein" PDF with bag no., condition photos, estimated price and stone liability clause | S |
| DOM-09 | Order-type field exists but the form never sets it, so the estimator's exact-tier match starves | `Order.order_type` in `db/models.py`; not among form inputs (`OrderFormModal.tsx` name list); `quote_service.py:~925` also omits it | M | Add it to the form and carry it through conversions | S |

### C2. Quote and approval

**Narrative.** QuotesPage is capable. It has line-item editing, the estimator panel for DRAFT quotes, PDF, signature on approval (`QuotesPage.tsx:230-305`) and reject with reason. Three things hurt in practice. (1) **"Versenden" does not send.** It only sets status SENT (`quote_service.py:762-790`). Anne still downloads the PDF and emails it herself, although `EmailService.send_quote` and `quote_sent.html` exist (`email_service.py:407`). (2) **Converting an approved quote creates a thin order.** The title becomes "Auftrag aus KV-…", the description is the quote notes, and the price is the gross total. Line items, metal, weight and deadline are not carried over (`quote_service.py:884-935`). The chain consultation→quote→order therefore loses data twice. (3) Approval evidence covers in-person signature only. There is no "customer replied by email" link like the one V1.2 built for cost changes.

§649 BGB is handled well on the **cost-change** side: projected-cost watcher, change request with reason, response logged with method (`db/models.py:2627-2651, 2760`). The quote PDF text calls the KVA "unverbindlich" and says metal price changes are reserved (`pdf_service.py:854-858`). That is reasonable. But nobody tells the goldsmith *what* counts as a significant overrun. The default threshold of 15% (vision doc) is fine; it needs to be visible and adjustable in settings.

| ID | Gap | Evidence | Impact | Proposal | Effort |
|---|---|---|---|---|---|
| DOM-11 | Quote "send" is status only, no email | `quote_service.py:762-790`; `email_service.py:407 send_quote` unused by the router `quotes.py:228-247` | **H** | Send the PDF by email when SMTP is set; otherwise mark it PDF-manual like CustomerUpdate does. Add an approve/decline link (section D) | S |
| DOM-11b | Quote→order conversion drops line items, metal, weight, deadline, order type | `quote_service.py:913-925` | **H** | Copy quote lines into the order's Soll (labour hours, metal weight, stones) so Soll/Ist works without retyping | M |
| DOM-11c | Metal price source (live, DB, hardcoded default) not shown when quoting | `metal_price_service.py:146-148`; no source display in `EstimatorPanel.tsx` | M | Show "Kurs vom <date>, Quelle" next to the metal line. Warn in red when on hardcoded defaults | S |
| DOM-11d | Quote may be approved directly from DRAFT with no record of how the customer agreed | `quote_service.py:813` allows DRAFT→APPROVED | L | Require a response method (in person/signature, email, phone) as in `CostChangeResponseMethod` | S |

### C3. Production tracking

**Narrative.** This is the strongest area. QR labels, the scanner with quick actions, the timer with interruptions, handoffs with accept/decline, the calendar with Ampel, Soll/Ist and Arbeitszettel together follow a real workshop day. The weak points are in the **order state model** and the **order page**:

- The status list has no **Storniert** and no **Pausiert / wartet auf Stein / wartet auf Kunde** (`db/models.py:47-63`). A job waiting three weeks for a sapphire either sits "in Bearbeitung", which is a lie and triggers deadline alarms, or gets misfiled. Anne listed "Warten auf Anprobe" herself; waiting on material is just as common. Time tracking has "Warten auf Material" as an *activity* (`seed_data.py:85`), but that does not stop the clock on deadlines.
- The status tab offers all 9 statuses as free buttons (`OrderDetailPage.tsx:453-490`). There is no guided "next step" and nothing prompts "tell the customer?" on key transitions.
- The **order page has 13 tabs** (`OrderDetailPage.tsx:173-265`). With gloves and a tablet that is too many. Kosten, Metall, Materialien, Arbeitszettel and Soll-Ist are all money/material views.
- The **history tab** shows only "created" and "updated" (`OrderDetailPage.tsx:492-521`), although `OrderStatusHistory` is recorded (`db/models.py:2938`). The goldsmith cannot answer "when did this go to setting?"
- The **Punzierung gate** blocks COMPLETED for any order with an alloy until marks are recorded (`order_service.py:36-90`). The status tab does not handle the 409; it shows a generic toast (`OrderDetailPage.tsx:84-94`). The only way to record marks is the scanner flow (`ActionHandlers.ts:399-410`). The allowed marks are 585/750/925/Pt950 only (`models/order.py:290-305`), so a 333, 375, 900, 999, Ag800 or palladium piece can only be completed by recording a **wrong** Feingehalt mark. Under the German Feingehaltsgesetz stamping is voluntary. What the law requires is that a stamp, if applied, is correct. A hard gate is the wrong model.
- **Who is doing what:** no assignee on orders (`UserRole` has only admin/goldsmith/viewer, `db/models.py:66-71`; no `assigned_to` column). "Mein Arbeitsvorrat" is every open order (`DashboardPage.tsx:100-145`), not *mine*. No apprentice role (e.g. may track time but not see prices).
- **Several pieces in one order** (a set of earrings plus a pendant, or two wedding rings of different sizes): `OrderItem` exists (`db/models.py:2918`) but nothing uses it outside GDPR export. Wedding rings, the single most common custom job, need **two ring sizes and two engravings** in one order.

| ID | Gap | Evidence | Impact | Proposal | Effort |
|---|---|---|---|---|---|
| DOM-13 | No Storniert / Pausiert (waiting for stone, customer, casting service) statuses | `db/models.py:47-63` | **H** | Add `on_hold` with a reason and an expected resume date (deadline alarms suppressed, shown in its own lane) and `cancelled` with a §649 note | M |
| DOM-16 | Order history does not show status history | `OrderDetailPage.tsx:492-521` vs `OrderStatusHistory` `db/models.py:2938` | M | Render status history, handoffs, customer updates and photos as one timeline | S |
| DOM-17 | 13 tabs on the order page | `OrderDetailPage.tsx:173-265` | M | Collapse to 5: Überblick (details+status+next step), Arbeit (time, Arbeitszettel, materials/metal), Fotos, Kunde (Kundeninfo, comments, handoff), Geld (costs, Altgold, Soll/Ist) | M |
| DOM-18 | Status change is 9 free buttons with no next-step guidance | `OrderDetailPage.tsx:453-490` | M | One big "Weiter: <next status>" button plus a "more" menu; on "fertig" offer "Kunde benachrichtigen" prefilled | S |
| DOM-22 | Hallmark vocabulary misses 333/375/900/999/Ag800/Ag935/Pd, which forces false records | `models/order.py:290-305`; alloys offered `OrderFormModal.tsx:38-48` | **H** | Derive the allowed Feingehalt mark from the order's alloy. Add "nicht punziert (Grund)" | S |
| DOM-23 | Punzierung is a hard gate, only reachable via the scanner; the order page shows a raw error | `order_service.py:36-90`; `OrderDetailPage.tsx:84-94`; modal only in `ActionHandlers.ts:399` | M | Make it a QC checklist item (warn, allow with reason). Open the modal from the order page on 409 | S |
| DOM-25 | No assignee / "mine" view; no apprentice role | `db/models.py:66-71`; `DashboardPage.tsx:100-145` | M | `assigned_to` on order (set by handoff accept), "Meine Stücke" filter, optional APPRENTICE role without price visibility | M |
| DOM-26 | No multi-piece orders (e.g. wedding ring pair with 2 sizes/engravings) | `OrderItem` `db/models.py:2918` unused | M | Use `OrderItem` for positions with per-item size, engraving text, metal | M |
| DOM-27 | Endkontrolle has no checklist (stones tight, clasp, polish, weight, hallmark, engraving spelling) | status only `QUALITY_CHECK`; repair has `/quality-check` endpoint `repairs.py:281` but orders have none | M | 6-item tap checklist on QC, stored with the order; engraving text shown for proof-reading | S |
| DOM-28 | Seed activities miss core techniques (Giessen/Wachsmodell, Montage, Schmieden, Walzen/Ziehen, Rhodinieren) | `seed_data.py:41-97` | L | Extend the seed list, since the estimator corpus is keyed by activity | S |

### C4. Customer feedback and communication

**Narrative.** Today the customer can receive: (a) V1.2 **manual** updates (progress / ready for pickup / custom), sent by SMTP or as a PDF that Anne passes on herself (`KundeninfoTab.tsx`, `customer_updates.py:75-228`); (b) §649 **cost-change** mails whose answer Anne records by hand (`customer_updates.py:279-333`); (c) **automatic** mails from the notification layer; (d) a **portal** lookup by reference plus email (`customer_portal.py:363-415`).

Problems, in order of harm:

1. **Automatic mails fire once per staff user and repeat.** `create_notification` sends a customer email for PICKUP_READY/FITTING_REMINDER/ORDER_STATUS whenever a customer id is attached (`notification_service.py:49-57, 103-113`). `check_pickup_reminders` creates one notification **per ADMIN/GOLDSMITH user** (`:492-517`). It de-duplicates only on unread notifications from the same day (`:494-503`), and it runs every monitor cycle (`system_monitor.py:316-322`). With three staff users, a customer gets three "ready for pickup" mails per day. They get more if staff mark the bell notifications as read, which lets the next cycle create fresh ones. Fitting reminders use the same loop (`:532-600`). The moment Anne turns SMTP on for V1.2, this reaches her customers.
2. **Photos cannot reach the customer**, because order photos cannot be uploaded (DOM-01). The V1.2 PhotoPicker only chooses from order photos. The feature built for "better feedback on their jewelry" is effectively dead.
3. **Repairs get nothing.** Repair "ready" notifies staff only, yet sets `customer_notified_at = now` (`repair_service.py:520-541`), a false record. No `/repairs/{id}/updates` route exists (`customer_update_service.py:48-55`).
4. **The customer cannot answer in the system.** Approval is "reply to the email, Anne records it". `CustomerUpdate.token` exists (`db/models.py:2653+`), but no endpoint resolves it. Portal tokens live 1 h (`customer_portal.py:44-46`), and `portal_url` is never passed to the pickup template (`email_service.py:428-440` vs `templates/email/ready_for_pickup.html:17`).
5. **Portal is pull-only status text.** No photos, no messages, and the order reference is the raw numeric id (`customer_portal.py:340-352`). It is also reachable only if the self-hosted box is exposed, which the vision explicitly defers.
6. Nothing after pickup: no rating, no care card, no "how is the ring wearing?" follow-up.

| ID | Gap | Evidence | Impact | Proposal | Effort |
|---|---|---|---|---|---|
| DOM-10 | Customer emails sent per staff user and repeated; pickup/fitting spam | `notification_service.py:49-57,103-113,492-517,532-600`; `system_monitor.py:316-322` | **H** | Decouple customer mail from staff notifications. One customer message per event, recorded as a `CustomerUpdate` row (visible in Kundeninfo), with an opt-out per order. Reminders at most once, then staff-only | M |
| DOM-12 | Repairs: no customer updates, false `customer_notified_at` | `repair_service.py:520-541`; `customer_update_service.py:48-55` | **H** | Add `/repairs/{id}/updates` (the service already supports it). On READY, create a ready_for_pickup draft and send it on one tap. Set `customer_notified_at` only on real send | S |
| DOM-29 | Customer can't approve or decline in one click | `CostChangeResponseMethod` only EMAIL_REPLY/IN_PERSON/PHONE (`db/models.py:2641-2651`); token unused | **H** | Signed, expiring link per update or cost change → small public page "Zustimmen / Ablehnen / Frage stellen", logged as evidence (section D) | M |
| DOM-30 | Updates are purely manual; no prompt at meaningful milestones | no hook from status change to `CustomerUpdateService`; `OrderDetailPage.tsx:84-94` | M | On transitions (Guss fertig, bereit zur Anprobe, fertig) offer a prefilled update with the last 1-3 photos pre-ticked (still explicit consent per send) | S |
| DOM-31 | Portal link in emails never rendered; tokens expire in 1 h | `email_service.py:428-440`; `customer_portal.py:44-46` | M | Long-lived per-order token (revocable) and pass `portal_url` to templates, once the portal is reachable | S |
| DOM-32 | No post-pickup feedback / rating | none found | L | Optional "Wie gefällt Ihnen Ihr Stück?" mail 2 weeks after pickup with 1-5 and a comment, stored on the order (feeds testimonials only with consent) | S |

### C5. Handover and aftercare

**Narrative.** Pickup exists for repairs (`repairs.py:331`) and as the DELIVERED status for orders. The invoice is generated from Soll/Ist in one click (`SollIstTab.tsx:195`), with the Altgold credit applied automatically (`invoice_service.py:359-418`). That matches Anne's wish exactly. Mark-paid and cancel exist. Missing are the things customers remember a goldsmith for: a **care card** (Pflegehinweise per metal and stone; opal and pearls need very different care from diamonds), **warranty terms**, the **insurance valuation** (fully built in the backend, `routers/valuations.py`, with encrypted value, but `api/valuations.ts` has no UI consumer), and **reminders**: re-polish or prong check after 12 months, rhodium refresh for white gold, anniversaries (the birthday is stored, `db/models.py` `Customer.birthday`, but nothing uses it). The customer history tab shows orders and first photos (`CustomerDetailPage.tsx:210-262`). It does not show repairs, consultations, quotes or sent updates. Its invoice tab fetches the latest 200 invoices and filters them client-side (`CustomerDetailPage.tsx:363-367`), so older invoices silently disappear. There is no deposit (Anzahlung) handling, although custom pieces with expensive stones almost always take one.

| ID | Gap | Evidence | Impact | Proposal | Effort |
|---|---|---|---|---|---|
| DOM-34 | Insurance valuation has no UI | `routers/valuations.py`; `frontend/src/api/valuations.ts` unused (no importer) | M | "Wertgutachten erstellen" button on delivered orders, prefilled from order/stones, PDF | S |
| DOM-35 | No care instructions / warranty on handover | grep finds nothing | M | Pickup handover sheet PDF: photo, metal, stones, care text by metal/stone, warranty. Optional email | S |
| DOM-36 | No aftercare reminders (service check, rhodium, anniversary) | `birthday` stored, unused; no scheduler rule | M | Rule "12 months after delivery: Service-Check" and "anniversary of wedding-ring pickup" (with consent, DOM-07) | M |
| DOM-37 | No deposit / partial payment | grep `Anzahlung|deposit` in `src/` empty; `Invoice` single total `db/models.py:1309-1382` | M | Record deposits against order; deduct on final invoice (Anzahlungsrechnung per §14 UStG) | M |
| DOM-38 | Customer 360° misses repairs, consultations, quotes, updates; invoices truncated at 200 | `CustomerDetailPage.tsx:16,222,363` | M | One "Verlauf" tab listing all entity types by date; server-side filter by `customer_id` | S |

### C6. Daily overview for Anne

**Narrative.** Three role dashboards exist. The goldsmith view "Mein Arbeitsvorrat" sorts open orders into due-today, due-in-3-days, fitting and in-progress (`DashboardPage.tsx:100-190`) and shows pending handoffs with accept/decline. The admin view has KPI cards that deep-link to filtered lists (`DashboardKPIs.tsx:79-83`; `OrdersPage.tsx:43-62` honours `?status=`), plus alerts and deadlines. This is glanceable and mostly actionable, which is to the team's credit. But:

- **Overdue orders fall to the lowest priority.** Only `dl == today` is urgent and only `today < dl <= +3d` is high (`DashboardPage.tsx:112-145`). A job whose deadline passed yesterday is shown as "low / in progress". The one thing Anne must see first is ranked last.
- All widgets load `limit: 100` orders (`DashboardPage.tsx:204`, `DeadlinesWidget.tsx:24`, `AlertsWidget.tsx:67`, `DashboardKPIs.tsx:31`). A workshop doing 300+ jobs a year will quietly lose items from the counts.
- **Repairs are absent** from the to-do list, although they are often more than half of the daily count.
- Missing "needs a customer action" items: cost changes awaiting an answer, updates that failed to send, quotes sent and near `valid_until`, pieces ready and not collected (collection exists only as a notification), unpaid invoices past due.
- Revenue: KPIs show value and hours, but not "invoiced this month / open receivables".

| ID | Gap | Evidence | Impact | Proposal | Effort |
|---|---|---|---|---|---|
| DOM-14 | Overdue orders ranked lowest | `DashboardPage.tsx:112-145` | **H** | Add an `overdue` bucket at the top (red, days overdue) | S |
| DOM-15 | Dashboard ignores repairs and all customer-side pending items | `DashboardPage.tsx:204-205` (orders + handoffs only) | **H** | "Wartet auf Kunde" and "Wartet auf mich" lanes: repairs, cost changes SENT, updates SEND_FAILED, quotes expiring, ready-not-collected, overdue invoices, each with a one-tap action | M |
| DOM-15b | Widgets truncated at 100 orders | `DashboardPage.tsx:204`, `DeadlinesWidget.tsx:24`, `AlertsWidget.tsx:67`, `DashboardKPIs.tsx:31` | M | Server-side summary endpoint (counts + top N per bucket) | M |
| DOM-15c | No receivables / monthly revenue glance | `DashboardKPIs.tsx:31-40` sources | L | One card "Offen: n Rechnungen, x EUR, davon überfällig y" linking to filtered invoices | S |

### C7. Workshop realities and German legal needs

**Narrative.** The bench side has had real attention: a scanner FAB, a HID-burst nudge for barcode guns, large quick-action tiles, a PWA, and idempotency keys ready for offline use (`lib/network-transport.ts:1-12`). But the offline queue is not built, so a Wi-Fi drop in the back room loses a scan action. The order page's 13 tabs and free status buttons work against glove use (DOM-17/18). Long pauses have no status (DOM-13). Apprentices and multi-piece orders are not modelled (DOM-25/26).

Legal and accounting:
- **§14 Abs. 4 UStG:** the invoice PDF prints the workshop name and "Goldschmiede & Atelier" only. There is no seller address, no Steuernummer/USt-IdNr, and no Leistungsdatum (`pdf_service.py:215-285`; config offers only `WORKSHOP_NAME`/`WORKSHOP_CONTACT`, `core/config.py:150-156`). Such an invoice is not valid for the recipient's input tax deduction and will be questioned in an audit. Also missing: a Kleinunternehmer (§19) switch, and §25a Differenzbesteuerung for resold used pieces.
- **GoBD:** the invoice can still be edited after issue (status, notes, due date: `invoices.py:297-321`). A paid invoice cannot be cancelled, and the error message tells the user to "contact the administrator for a Storno-Gutschrift" (`invoice_service.py:646-662`), but no credit-note flow exists. A correction chain (Stornorechnung plus a new invoice) is mandatory practice.
- **Altgold:** the Feingold total sums gold, silver and platinum into `total_fine_gold_g` and values it all at the gold price per gram (`scrap_gold_service.py:160-171`). 10 g of Ag925 would be credited at roughly 90 EUR/g instead of about 1 EUR/g. In addition, the UI sends `alloy` as a number (`scrap-gold/ScrapGoldTab.tsx:80`, `api/scrap-gold.ts:40-44`) to an API that requires a string (`models/scrap_gold.py:25`). My schema check confirms a 422, so adding items from the tab should fail outright. Even as a string, "925" is not a key of `ALLOY_RATIOS` ("ag925" is), and an unknown alloy silently yields 0.0 g (`scrap_gold_service.py:27-30`). There is no Ankaufsabschlag / Scheidekosten field (buyback is typically 80-95% of fine value). There is no ID capture for the buyer's due diligence. The GwG identification duty for cash precious-metal trades from 2,000 EUR, and the police practice of an Ankaufsbuch, are not supported.
- **§147 AO retention:** `retention_class` exists on the order (`db/models.py:~590`). I did not audit the interplay with GDPR erase; the compliance reviewer should.
- **Hallmarking:** see DOM-22/23. There are two unconnected systems: order-level marks (`punzierung_verified_*`) and an unused `OrderHallmark` register with UK-style assay states (`db/models.py:2245-2260`).

| ID | Gap | Evidence | Impact | Proposal | Effort |
|---|---|---|---|---|---|
| DOM-19 | Altgold add-item from UI sends number, API wants string: items can't be added; "925" maps to 0.0 | `ScrapGoldTab.tsx:80`, `api/scrap-gold.ts:40-44`, `models/scrap_gold.py:9-25`, `scrap_gold_service.py:27-30`; schema check reproduced 422 | **H** | Unify alloy codes (one enum shared by order, scrap, hallmark). Reject unknown alloys with 422 instead of 0.0. Add an e2e test "15 g 585 + 8 g 750 = 14.775 g" | S |
| DOM-20 | Mixed-metal Altgold valued entirely at gold price | `scrap_gold_service.py:160-171` | **H** | Totals per metal (Au/Ag/Pt/Pd fine grams), each × its own price, minus a configurable Ankaufsabschlag %. Receipt PDF lists per metal | M |
| DOM-21 | No ID capture / Ankaufsbuch for Altgold buy-ins | `ScrapGold` model `db/models.py:1128-1200` (no ID fields) | M | Optional ID type + last 4 digits + checked-by, required above a configurable cash threshold; exportable Ankaufsbuch | M |
| DOM-24 | Invoice PDF lacks §14 UStG seller address, tax number, Leistungsdatum | `pdf_service.py:215-285`; `core/config.py:150-156` | **H** | Workshop settings (address, St-Nr/USt-IdNr, bank, Kleinunternehmer flag) and `service_date` on the invoice; print all mandatory fields | S |
| DOM-24b | No Storno / credit-note flow; issued invoices editable | `invoice_service.py:646-662`; `invoices.py:297-321` | M | Lock issued invoices; "Stornieren" creates a negative Stornorechnung with its own number and a link | M |
| DOM-39 | No offline queue for bench actions | `lib/network-transport.ts:1-7` | M | Ship the V1.1.5 queue for scan actions and timer start/stop (idempotency is already in place) | M |

### C8. Feature bloat check

Summary here; details in section E. A single workshop with 2-4 people does not need three analytics layers or two stock systems. Out of 35 routers, about 8 are either unreachable from the UI or aimed at a scale Anne does not have: `ml`, `analytics`, `admin_scan_metrics` (scan adoption gate), `theme`, `valuations` (unreached but valuable), `hallmarks` (unreached and wrong model), `imports`, and the duplicated `metal_inventory`/`materials`/`metal_types` split. Their cost is not runtime. The cost is **attention**: 13 tabs, 14 nav items (`MainLayout.tsx:83-258`), and features promised in docs that users then cannot find.

---

## D. The customer-feedback question

**Constraint from the vision (`VISION_AND_ROADMAP_2026-07.md`, decisions table):** no live portal for now; email/PDF first; data stays portal-ready (tokens). The system is self-hosted in the workshop, so any customer-clickable link needs *some* public endpoint. That is the crux.

**Precondition for every option:** fix DOM-01 (photos can be taken), DOM-10 (no spam) and DOM-12 (repairs included). Without those, no channel gives better feedback.

### Option 1: Email digest with photos plus a reply-based approval (the current path, finished)
The goldsmith taps "Kunde informieren" at a milestone. A mail goes out with 1-3 selected photos, a short text and, for decisions, the explicit question "Bitte antworten Sie mit JA oder NEIN". Anne logs the reply with one tap ("Antwort: Zustimmung per E-Mail") on the cost change or design step.
- **Pros:** no public exposure, works today with SMTP and the existing V1.2 code, legally adequate (a written reply is good §649 evidence), zero new infrastructure.
- **Cons:** approval depends on Anne reading mail and logging it. No status "at a glance" for the customer between mails. Customers who don't use email get nothing (use the PDF-to-WhatsApp path that already exists, `UpdateDeliveryMethod.PDF_MANUAL`).
- **Effort:** S (milestone prompts DOM-30, repair route DOM-12, "Antwort erfassen" shortcut).

### Option 2: PDF progress report ("Werkstattbericht")
One PDF per milestone or at pickup: photos of the stages (wax, casting, setting, finished), metal and stones used, hallmark, care instructions. It is handed over or sent by WhatsApp.
- **Pros:** tangible and premium. It doubles as the aftercare/valuation document the customer keeps (J5), works fully offline, and suits a craft brand.
- **Cons:** no interaction; it is a report, not a conversation. It needs the photo discipline first.
- **Effort:** S-M (the PDF service and photo variants already exist, `pdf_service.py`, `customer_update_service.py:391-450`).

### Option 3: Lightweight token status page with one-click approve
A per-order signed token (long-lived, revocable) renders a read-only page with the status timeline, the photos the goldsmith explicitly shared, and buttons for pending decisions (approve/decline cost change, "design passt / bitte ändern", free-text question). It is served either through a small tunnel (Cloudflare Tunnel or Tailscale Funnel exposing only `/portal/*`) or as a static snapshot pushed to a tiny host on each update.
- **Pros:** the best customer experience, and click evidence is stronger and faster than reading emails. It reuses `CustomerUpdate.token` and the existing portal page.
- **Cons:** it breaks the "data never leaves the workshop" promise unless it is done as a snapshot. It adds an attack surface (rate limits already exist, `customer_portal.py:376`). Someone must operate the tunnel.
- **Effort:** M-L.

### Recommendation
Do **Option 1 now**, add the **Option 2 handover report** at pickup (it also closes J5 gaps DOM-34/35), and design Option 3's approve page **without building the public exposure yet**. Concretely: generate the signed token link in every update mail, but have it point to a "reply by email" fallback until the tunnel exists. Then turning on Option 3 later is a config change, not a rebuild, which is exactly what the vision asked for. For a single workshop, a photo-rich mail at three milestones (design approved, casting/raw piece, finished) plus a handover PDF gives more "better feedback" than any portal.

---

## E. Feature bloat and simplification

| Item | Evidence | Verdict | Action |
|---|---|---|---|
| ML router (duration prediction, anomaly, forecast) | `routers/ml.py` (914 lines); no frontend caller | Premature. The statistical estimator (V1.3) replaced it for pricing | Hide behind a feature flag; stop maintaining; keep `find_similar_orders` only if the estimator uses it |
| Analytics router | `routers/analytics.py`; no frontend caller | Unused | Remove, or fold 2-3 numbers into the admin dashboard |
| Scan adoption gate / metrics dashboard | `routers/admin_scan_metrics.py`, `pages/admin/ScanAdoptionDashboard.tsx`, `App.tsx` `admin/scan-gate` | Rollout tool, not a workshop need | Keep for the dogfood period, then hide |
| Theme router (server-side theme) | `routers/theme.py`, `hooks/useTheme.ts` | Over-engineered; a local toggle is enough | Keep toggle, drop server persistence if unused |
| Materials vs Metal inventory vs Metal types vs Gemstone | `routers/materials.py`, `metal_inventory.py`, `metal_types.py`; `Gemstone` model; `Order.materials` M2M `db/models.py:175-180` plus `MaterialUsage` | Two stock worlds and an unused third | One "Lager" page with tabs Metall / Steine / Verbrauch. Order consumption through one path |
| Two hallmark systems | `Order.punzierung_verified_*` vs `OrderHallmark` register | Confusing; the register models a UK assay office | Drop `OrderHallmark` from UI plans; keep order-level marks with correct vocabulary |
| `Customer.ring_size` etc. vs `CustomerMeasurement` | `db/models.py:~245` vs `:358` | Duplicate truth | Keep only the measurement library; show the latest ring size in the header |
| `OrderItem` model | `db/models.py:2918` | Unused but needed (DOM-26) | Use it rather than delete it |
| Order `metal_type` and `alloy` | `db/models.py` Order; `OrderFormModal.tsx:216-223` | Double entry, conflicts | Single picker (DOM-06) |
| Order detail 13 tabs; 14 nav items | `OrderDetailPage.tsx:173-265`; `MainLayout.tsx:83-258` | Too much for a tablet | 5 tabs; nav grouped into Werkstatt / Kunden / Geld / Lager / Admin |
| `NEW` legacy status | `db/models.py:63` | Dead value still in labels | Migrate to CONFIRMED and remove |

---

## F. Top 15 prioritized recommendations

Ordered by value to the goal ÷ effort. Items 1-5 are prerequisites for "better feedback on their jewelry".

| # | Recommendation | IDs | Value | Effort | Definition of done |
|---|---|---|---|---|---|
| 1 | Stop customer-email spam from the notification layer | DOM-10 | H | M | With 3 staff users and SMTP on, a completed order produces exactly one customer mail, visible as a CustomerUpdate row; an integration test asserts this |
| 2 | Photo capture on orders (tab and scanner deep link) | DOM-01 | H | S | From a tablet, scanner "Foto" opens the camera, the photo appears in the Fotos tab and can be ticked in Kundeninfo within 3 taps |
| 3 | Fix Altgold: alloy contract, per-metal valuation, no silent 0.0 | DOM-19, DOM-20 | H | S-M | UI adds 15 g 585 + 8 g 750 → 14.775 g Au; adding 10 g Ag925 yields 9.25 g Ag valued at the silver price; unknown alloy returns 422 |
| 4 | Repairs get customer updates; `customer_notified_at` only on real send | DOM-12 | H | S | Repair READY creates a pickup draft; one tap sends it; notified timestamp equals send time |
| 5 | Overdue bucket and customer-pending lane on the dashboard, repairs included | DOM-14, DOM-15 | H | M | An order 1 day past its deadline appears first in red; the lane lists SENT cost changes, failed updates, repairs ready but not collected, each with one tap to the action |
| 6 | §14 UStG-complete invoice PDF plus workshop settings | DOM-24 | H | S | PDF shows seller address, St-Nr/USt-IdNr, Leistungsdatum, sequential number; checked against the §14 Abs. 4 list |
| 7 | Carry data through consultation → quote → order | DOM-03, DOM-11b, DOM-09 | H | M | Converting a consultation with occasion date, ring size and "585 Gelbgold" yields an order with deadline, ring size, alloy, order type and photos, no retyping |
| 8 | Quote "Versenden" actually sends (email or PDF-manual) | DOM-11 | H | S | Clicking Versenden with SMTP set delivers the PDF; without SMTP it downloads and records PDF_MANUAL |
| 9 | Add on-hold (with reason and resume date) and cancelled statuses | DOM-13 | H | M | A piece "wartet auf Stein" leaves the deadline alarm list and shows in its own lane; cancelled orders drop out of all active counts |
| 10 | Hallmark: vocabulary from alloy, soft gate, reachable from the order page | DOM-22, DOM-23 | H | S | A 333 order can be completed with "Feingehalt 333" or "nicht punziert: <reason>"; the 409 opens the modal instead of a toast |
| 11 | Gemstones on orders with Fassungsart dropdown | DOM-04 | H | M | Order shows stones (type, ct, 4C, Fassung, customer stone flag); they print on quote, invoice and valuation |
| 12 | Milestone prompts plus handover report PDF | DOM-30, DOM-35, section D | M | S-M | Moving to "fertig" offers a prefilled update with the latest photos; pickup produces a PDF with photos, materials and care text |
| 13 | Email optional for customers | DOM-02 | H | M | A phone-only customer can be created and gets PDF-manual updates |
| 14 | Order page reduced to 5 tabs with a "Weiter" button, and a real timeline | DOM-16, DOM-17, DOM-18 | M | M | A tester with gloves on a 10" tablet advances an order and finds its history in under 10 s |
| 15 | Surface the insurance valuation | DOM-34 | M | S | "Wertgutachten" button on delivered orders produces the PDF from existing backend data |

---

## G. Things the user might have missed

1. **The feedback feature is blocked by photo capture, not by the channel.** V1.2 built careful consent-by-selection photo sharing, but no screen lets anyone add an order photo (DOM-01). Fixing the upload does more for "better feedback" than any portal work.
2. **Turning on SMTP is risky today.** It activates the per-user duplicate customer mails (DOM-10). Treat DOM-10 as a release blocker for V1.2 going live.
3. **Altgold money errors are real money.** The UI path appears broken, and the backend math values silver as gold (DOM-19/20). If anyone has been using the API directly, their past receipts should be re-checked.
4. **Hallmarking in Germany is voluntary, but it must be correct if applied.** The current gate plus the narrow vocabulary pushes staff toward recording a wrong Feingehalt. That is worse for compliance than recording nothing.
5. **Deadline semantics.** "Deadline" is used both as the promised customer date and as internal planning. Workshops need both: *Liefertermin* (promise) and *intern fertig bis* (buffer for polishing/QC, typically 2-3 days earlier). The overdue bug (DOM-14) is sharper because of this.
6. **Wedding rings are the bread-and-butter job and do not fit the model**: one order holding two rings, two sizes and two engravings, with engraving text needing customer proof-reading. `OrderItem` exists for this (DOM-26).
7. **Customer-supplied stones and heirlooms** carry liability. You need intake photos, a weight and a condition note, and an explicit clause ("Fassen auf Risiko des Kunden bei Steinen mit Einschlüssen"). The repair intake has photos. Custom orders have none.
8. **GwG and the Ankaufsbuch for gold buying.** Buying Altgold for cash above thresholds requires ID checks, and police do ask for purchase records when stolen jewellery surfaces. A simple optional log protects the workshop (DOM-21).
9. **Widerrufsrecht for remote approvals.** Custom pieces are exempt (§312g Abs. 2 Nr. 1 BGB). Repairs or stock sales agreed purely by email may not be, and the approval mail should carry the correct notice. Have the legal wording checked together with the §649 template the vision already flags.
10. **Documentation promises features that don't exist** ("Foto hochladen", "Kunde kann Fortschritt sehen": `DAILY_WORKFLOWS.md:190-210`). Anne or staff reading the guide will lose trust quickly. Align the docs or the UI before handing over.
11. **Scale cliff at around 100 open or recent orders.** Dashboard widgets and the customer invoice tab fetch fixed pages and filter on the client (DOM-15b, DOM-38). A workshop crosses that within a year.
12. **Metal price fallback is silent.** If the price API is unset or down, quotes use hardcoded default prices with only a server log line (`metal_price_service.py:146-148`). With gold moving a few percent per month, a stale default can cost more than a whole labour line.

---

## Verification (2026-09-25)

Verifier: `.orchestrated-fable/ux-erp-audit-2026-09/verify-frontend-domain-design.md` (every impact-H gap; the ScrapGold alloy check was re-run). All confirmed.

| ID | Title (short) | Claimed impact | Verdict | Corrected severity | Verifier note |
|---|---|---|---|---|---|
| DOM-01 | No order-photo upload | H | CONFIRMED | HIGH | Identical to FE-13 (upgraded to HIGH there) |
| DOM-02 | Customer email mandatory | H | CONFIRMED | HIGH | `models/customer.py:16` required |
| DOM-03 | Consultation to order drops data | H | CONFIRMED | HIGH | `OrderCreate` with exactly 3 fields |
| DOM-04 | No gemstone capture | H | CONFIRMED | HIGH | Nothing instantiates `Gemstone`; no create endpoint |
| DOM-10 | Customer email spam per staff user | H | CONFIRMED | HIGH (effectively release-blocking) | No dedup inside `_try_send_customer_email`; per-user dedup cannot stop N staff giving N emails |
| DOM-11 | "Versenden" does not send | H | CONFIRMED | HIGH | `EmailService.send_quote` never invoked |
| DOM-11b | Quote to order drops data | H | CONFIRMED | HIGH | No lines, metal, weight, deadline or order_type copied |
| DOM-12 | Repairs get no customer messages; false `customer_notified_at` | H | CONFIRMED | HIGH | `_notify_admins_repair_ready` bypasses `create_notification`; timestamp written regardless |
| DOM-13 | No on-hold/cancelled statuses | H | CONFIRMED | HIGH | Enum has exactly the 10 listed values |
| DOM-14 | Overdue ranked lowest | H | CONFIRMED | HIGH | Same code path as FE-05 |
| DOM-15 | Dashboard ignores repairs | H | CONFIRMED | HIGH | No repair API call in `DashboardPage.tsx` |
| DOM-19 | Altgold alloy int vs str, 422 | H | CONFIRMED | HIGH | `ValidationError` reproduced; `"925"` is not an `ALLOY_RATIOS` key either, so 0.0 |
| DOM-20 | Mixed-metal Altgold at gold price | H | CONFIRMED | HIGH | One `total_fine` over all metals |
| DOM-22 | Hallmark vocabulary too narrow | H | CONFIRMED | HIGH | Allowed set has no 333/375/900/999/Ag800/Ag935/Pd |
| DOM-24 | Invoice PDF lacks §14 UStG data | H | CONFIRMED | HIGH | Settings hold only `WORKSHOP_NAME`, `WORKSHOP_CONTACT` |
| DOM-29 | No one-click approve/decline | H | CONFIRMED | HIGH | `CostChangeResponseMethod` has no token option (PHONE not individually re-verified) |

**New while verifying:** (1) repair-ready notifications go to every active user with no role filter, including VIEWER, and carry the customer's name and bag number (register VER-01, HIGH); (2) the same path skips the WebSocket publish, so repair notifications arrive only on the bell's poll (VER-02, MEDIUM); (3) `customer_notified_at` is a provably false audit field on repairs (tracked under DOM-12).

Register note: this report's section E rows carry no IDs; the register assigns DOM-33 (the row this report already calls DOM-33) and DOM-40 to DOM-46. See [FINDINGS-REGISTER.md](FINDINGS-REGISTER.md).

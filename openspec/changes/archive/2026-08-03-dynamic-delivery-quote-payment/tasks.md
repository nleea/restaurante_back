> Estado resincronizado con el código el 2026-08-03. Sección 4 implementada: el cliente ya recibe
> por WhatsApp su total con domicilio y el enlace de pago. Lo que falta para cerrar el flujo es la
> nada: el flujo completo quedó verificado a mano el 2026-08-03.

## 1. Persisted quote and tariff model

- [x] 1.1 Add branch-scoped delivery tariff-plan and distance-band domain/ORM models, repository ports, migration, validation and RBAC-protected API.
- [x] 1.2 Add quote state, adjusted distance, selected band, frozen fee, timestamps and actionable failure reason to the delivery record, with a migration safe for existing rows.
- [x] 1.3 Add `delivery_fee` to orders and update authoritative total recomputation to calculate `subtotal − discount + delivery_fee` without affecting non-delivery orders.
- [x] 1.4 Add a scoped, expiring, hashed-token payment-request model/repository (migration 0039).
- [x] 1.5 Invalidate a pending payment request when its quote changes (address edit and re-quote both kill prior links).
- [x] 1.6 Add backend tests for tariff continuity/validation, band selection (inclusive upper bound, ordered by position), frozen totals and the zero-fee invariant for non-delivery orders.

## 2. Asynchronous quote calculation

Cotizar es aritmética local (Haversine): no hay proveedor ni límite de tasa, así que lo único que
un presupuesto esperaba era que EXISTIERAN coordenadas. Por eso hay ahora dos caminos rápidos —
`quote_delivery` para un pedido con GPS, y una cotización en caliente dentro del propio trabajo de
geocoding— con el barrido de cada minuto como garantía.

- [x] 2.1 Define a swappable distance-estimator port; implement the deterministic Haversine + 0.7 km adapter and persist its method/buffer with each quote.
- [x] 2.2 Build an idempotent quote worker that waits for delivery coordinates, calculates adjusted distance from the branch pin, selects the tariff band, and commits quote plus order fee atomically.
- [x] 2.3 Integrate geocoding completion, explicit pins and manual pin updates with quote enqueueing via the `sweep_pending_quotes` cron pass; preserve the geocoding worker's retry and rate-limit guarantees.
- [x] 2.4 Invalidate quote and frozen fee on address or coordinate edits, then schedule recalculation where possible.
- [x] 2.5 Handle outside-coverage, no-plan, missing-branch-pin and unresolvable-address states without inventing a price: writes `quote_failure_reason` instead of skipping the row, with logs.
- [x] 2.6 Fix `PendingQuoter`: `events` is now guarded, and the returned count reports priced deliveries only.
- [x] 2.7 Add unit/integration tests for GPS and geocoded intake, invalidation, outside coverage and the immediate-quote fast path.

## 3. Deferred payment workflow

- [x] 3.1 Change public storefront order intake so delivery orders are created without `payment_method` (pickup still requires one) and skip the misleading intake acknowledgement.
- [x] 3.2 Implement the token-authenticated payment-request API/read model with narrow authority: view quoted total, choose payment method and submit a proof/claim only.
- [x] 3.3 Connect payment-method selection and proof declarations to the existing order payment-claim and verification flow without registering money prematurely.
- [x] 3.4 Gate prepaid delivery payment verification and kitchen release on a finalized quote via the `DeliveryQuoteGate` port; the verified amount is the order total, so it includes the frozen delivery fee.
- [x] 3.5 Add tests for the payment-request view, refused pre-quote payment/kitchen actions, unquotable reasons and verified totals.

## 4. WhatsApp payment-request delivery — COMPLETA

El token en claro sólo vive dentro de `create_payment_request`, así que la emisión ocurre en la
misma pasada de cotización y un "reintento" es en realidad una re-emisión con token nuevo, nunca
un reenvío del viejo. El enlace se construye con `shared/links.delivery_payment_url`.

A diferencia de los avisos de estado, esta emisión **reabre** un hilo cerrado. `CLOSING_STATES`
cierra en `delivered`, así que todo cliente que repite llega con el hilo cerrado; rendirse ante eso
dejaba sin poder pagar justo al cliente habitual. Reabrir no viola "nunca iniciamos": eso lo
sostiene `is_reachable` en el gateway. Un contacto sin NINGÚN hilo en la sede sí se rechaza.

- [x] 4.1 Add an emission-state migration to `delivery_payment_requests` (`emission_status`, `emitted_at`, `emission_failure_reason`) plus its ORM/domain fields — migration 0041.
- [x] 4.2 Create an idempotent payment-request emission use case that sends order label, final total and payment URL only to a reachable linked WhatsApp contact, called from `PendingQuoter` where the raw token is still readable.
- [x] 4.3 Persist emission status and failure reason, and ensure an emission failure never changes quote/payment/kitchen state.
- [x] 4.4 Implement authorized recovery as **re-issue** via `POST /delivery/deliveries/{id}/payment-request` (gated by `delivery.assign`): a new single-use request for the same unchanged quote that invalidates the previous one.
- [x] 4.5 Add messaging and integration tests for successful emission, missing/unreachable contact, re-issue behavior and duplicate suppression (19 new tests).

## 5. Frontend flows

- [x] 5.1 Remove the storefront's fixed delivery fee and up-front payment-method requirement; the payment step is skipped for delivery and the ticket says "Domicilio: por confirmar".
- [x] 5.2 Build the public payment-request page at `/payment/delivery/:token`: full order breakdown (lines, subtotal, delivery fee, amount due), payment-method picker with QR, proof upload and a WhatsApp fallback, themed like the carta. Declares the ORDER BALANCE, never the delivery fee.
- [x] 5.3 Add delivery administration controls for kilometer tariff bands (`TariffPanel` on /delivery): explicit save, mirrored validation, coverage edge and buffer explained, read-only without `delivery.manage`.
- [x] 5.4 Surface quote status, adjusted distance, frozen fee and payment-request emission state on dispatch, with an authorized re-issue button; emission joined into the deliveries list in one batched read.
- [x] 5.5 Add frontend unit/component tests for deferred totals, valid/invalid payment links, tariff editing and dispatch quote states (41 new).

## 6. End-to-end verification and rollout

- [x] 6.1 End-to-end verificado a mano el 2026-08-03: intake sin método de pago → cotización → WhatsApp con total y enlace → comprobante → verificación → cocina.
- [x] 6.2 Add a per-branch configuration guard: the public checkout refuses a delivery from a branch with no pin or no tariff bands, telling the customer to order for pickup instead of stranding them.
- [x] 6.3 Document branch pin/tariff configuration, operational recovery and the no-WhatsApp fallback — `docs/delivery/quote-and-payment.md`.
- [x] 6.4 Suites green (1195 backend / 924 frontend), delivery module clean on ruff+mypy, and every one of the 117 stored orders satisfies `total = subtotal − discount + delivery_fee`.

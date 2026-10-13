# النظام الذكي (Smart System) — Cloned App

## Original Problem Statement
Clone the mobile app from https://github.com/abufuadeid419-glitch/apk-ios-code.git and wire it to the owner's existing Convex deployment.

## Architecture
- **Frontend**: Expo Router (React Native), Arabic RTL (forced), Cairo font family. ~30 screens across 4 role areas: `owner/`, `acct/` (accountant), `dist` (distributor/field agent), `dev/` (developer). Uses `@tanstack/react-query`, offline sync queue, Bluetooth receipt printing, maps/GPS tracking, QR scan.
- **Backend**: Convex (external BaaS). All REST logic in `frontend/convex/*.ts`, served from the deployment's HTTP `.site` domain under `/api/...`. The FastAPI `backend/server.py` is a health-check stub only (no MongoDB).
- **Convex deployment**: `fearless-ostrich-878` (eu-west-1).
  - `EXPO_PUBLIC_CONVEX_URL=https://fearless-ostrich-878.eu-west-1.convex.cloud`
  - `EXPO_PUBLIC_CONVEX_SITE_URL=https://fearless-ostrich-878.eu-west-1.convex.site`
- **Auth**: Phone + SMS OTP via SMS Gateway (sms-gate.app). Credentials (`SMS_GATE_USERNAME`, `SMS_GATE_PASSWORD`, `OTP_PEPPER`, `DEVELOPER_PHONES_HASH`) live server-side in Convex deployment env — not in app code. No WhatsApp fallback; clear error on SMS failure.

## User Personas
- **Owner (OWNER)**: dashboard, customers, products, sales, reports, employees, Pro plan.
- **Distributor / Field Agent (EMPLOYEE/FIELD_AGENT)**: route, deliveries, new sale, collections, map tracking.
- **Accountant (EMPLOYEE/ACCOUNTANT)**: sales, customers, debts, collections.
- **Developer (DEVELOPER)**: orgs, licenses, billing (super-admin).

## Core Requirements (static)
- Arabic RTL interface preserved exactly.
- All 4 roles functional against live Convex data.
- Offline-first sync with reconnect queue drain.
- Pro subscription tiers (trial → free fallback → paid lock).

## Implemented (dates)
- 2026-06: Cloned full repo into workspace; wired frontend to owner's live Convex deployment via env vars; preserved platform-protected env vars. Verified: app boots to Arabic login screen, Convex `/api` reachable, `/api/auth/me` returns 401 unauthenticated (auth routing OK), FastAPI stub healthy.
- 2026-06: Phone country-code validation (`src/phone.ts`) — rejects unassigned codes before OTP is sent (no wasted SMS).
- 2026-06: Real-time theme store (`src/theme.ts` via `useSyncExternalStore`) + coherent dark palette; `app.json` userInterfaceStyle=automatic.
- 2026-06: **Advanced inventory + dual-currency (deployed to live Convex).**
  - Products: `price_currency` (SYP/USD), `pieces_per_package`, `package_unit`; bidirectional piece↔package pricing in the product form; stock shown as cartons + pieces (`stockLabel`).
  - Sales invoices: per-line unit picker (PIECE/PACKAGE); server converts USD→SYP at the CURRENT org rate, deducts stock in pieces, and **stamps `exchange_rate` + `currency` onto the invoice** (immutable — past invoices never change when the rate updates). Each line stores unit, pieces, pieces_per_package, price_currency, orig_unit_price (product currency), unit_price (SYP).
  - Receipt vouchers (سند قبض / collections) & payment vouchers (سند صرف): optional USD entry → converted to SYP base at current rate; stamp `exchange_rate`, `currency`, `amount_input`, `input_currency`. Ledger/balances stay in SYP.
  - Currency management: Owner sets base/alt/USD→SYP rate in Management → العملات (pre-existing `PUT /org/currency`, now fully applied across documents).
  - Backend files: `convex/{schema,lib,products,sales,collections,vouchers,deliveries}.ts`. Frontend: `screens/{Products,NewSale,DistributorOps,Sales}.tsx`, `components/{CollectSheet,VoucherSheet}.tsx`, `offlineActions.ts`, `pricing.ts`.

## How to test (requires owner login via SMS OTP)
1. Management → العملات: set USD→SYP rate (e.g. 15000) and save.
2. المخزون → add a product priced in USD, pieces-per-package = 12; confirm piece/package prices auto-link and stock shows cartons+pieces.
3. As a field agent: فاتورة جديدة → add that product, toggle القطعة/الكرتونة; price shows converted SYP; save → invoice total in SYP with the stamped rate visible in the invoice detail.
4. Change the rate in settings, reopen the old invoice → its total & rate are unchanged (immutable).
5. سند قبض / سند صرف: enter an amount in $ → see the SYP conversion; saved voucher shows the original $ amount + stamped rate.

## Notes / Backlog (P1/P2)
- Customer-type price lists (`customer_types.prices`) are interpreted in the product's `price_currency` before conversion.
- Native-only features (Bluetooth printing, camera QR scan, background GPS, haptics) require a real device build — not testable in Expo Go / web preview.
- Full E2E testing agent intentionally skipped: all screens are behind phone+SMS OTP, and testing would send real SMS / mutate live production data.
- 80mm/PDF receipt templates (`receipts.ts`) still print the SYP total; per-line unit labels on the printed copy are a possible polish item.

## 2026-06 (this workspace)
- Re-cloned from https://github.com/abufuadeid419-glitch/dis-error.git into a new workspace; kept this project's bundle id/package `com.emergent.errordisdemo.r67q61`.
- Env: EXPO_PUBLIC_CONVEX_URL / EXPO_PUBLIC_CONVEX_SITE_URL / CONVEX_DEPLOY_KEY in frontend/.env.
- Re-deployed `frontend/convex/*` to fearless-ostrich-878 (`npx convex deploy`) so live functions match the repo.
- Smoke test passed (iteration_1): login screen, validation, legal screen, Convex /api reachable.
- 2026-06: FIX distributor "page not found": recreated `app/dist/*` routes (source repo's .gitignore `dist/` had dropped them); added gitignore negations so they're tracked.
- 2026-06: FIX `convex/products.ts` missing `round2` import (product create/update crashed) — redeployed.
- 2026-06: Printed receipts show unit label per line (e.g. "2 كرتونة × price") + carton→pieces line; WhatsApp invoice text too.
- 2026-06: Login screen free 14-day Pro trial offer card; intent stored → activation screen leads with the trial form.
- 2026-06: Owner supplier statements (المخزون → storefront icon): grouped from purchases/purchase-returns, one-tap PDF share + full DocActions.
- 2026-06: Distributor one-tap customer statement PDF icon on each customer row.
- Testing: iteration_2 all green (all 4 roles, all tabs). Test accounts in memory/test_credentials.md.
## Backlog
- Supplier payments (سند صرف لمورد) so supplier balances reflect payments, not just purchases/returns.
- 2026-06: Supplier payments (سند صرف لمورد): new Convex table `supplier_payments`, `GET/POST /api/supplier-payments` (owner creates, staff lists; blocks overpayment; USD→SYP at current rate). Supplier statements now subtract payments; record payment form + per-payment voucher PDF in the supplier sheet.
- 2026-06 (batch 3):
  - Distributor crash: Convex `useQuery` (throws in render on any server error, e.g. revoked session) replaced by REST `useApi` polling in NotificationBell + SalesTargets (MyTargetCard on distributor home). app/dist routes present.
  - Name re-prompt: auth now persists the latest profile to cache on every change (was caching the nameless OTP user → offline/slow boots re-asked the name); saveName keeps the name even if /auth/me refresh fails.
  - Pricing policy on cost change: org.pricing_method FIFO | WAVG (PUT /api/org/pricing-method). Purchases with a different cost and stock on hand return PRICING_METHOD_REQUIRED → owner sheet asks once. WAVG = weighted cost, sale price keeps markup. FIFO = product.cost_layers; sales/purchase returns consume oldest layer; price moves to next layer when exhausted. Settings in الإدارة ← ملف المؤسسة.
  - Units (piece/package) across purchases, purchase returns, deliveries, customer returns, warehouse returns, stock requests (backend `unitQty`, stock always pieces); void + profit use pieces.
  - Keyboard: Sheet uses Reanimated keyboard lift (no KeyboardAvoidingView in Modal) + navigationBarTranslucent.
  - RBAC delete: developer can't delete accounts (self or approving org deletions); owner deletes own account+org directly; employees delete own.
  - Dev license create fixed (dynamic import unsupported in Convex → static import).
- 2026-06: FIX Android crash 'FontSize should be a positive value' on role headers (AccountButton hidden <T fontSize:0> test markers → empty Views). iteration_5 passed.
- 2026-06 (batch 4):
  - Price change alerts: every sale-price change from purchases/FIFO (lib.logPrice) notifies all org FIELD_AGENTs (type price_change).
  - Stock requests by unit: distributor per-item request sheet (stock-request-sheet) with piece/package.
  - Supplier contacts: `suppliers` table, GET/PUT /api/suppliers (owner upsert by name); phone used for supplier statement WhatsApp/SMS.
  - Android PDF: printDoc tries sized PDF then default size, copies to "<title>.pdf" (expo-file-system) before share, falls back to print dialog if sharing unavailable.
  - WhatsApp text option replaced by "إرسال رسالة نصية SMS إلى العميل" (expo-sms on device, sms: link fallback) in DocActions.
  - Org profile save fix: endpoint tolerates read-only fields; frontend sends only editable keys.
  - New pricing policy LATEST "اعتماد السعر الجديد على كل البضاعة".
  - printDoc: File.copySync (copy() is async in expo-file-system 57) — iteration_6 bug fixed.

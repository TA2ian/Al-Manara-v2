# Migration Gates

The migration is considered successful only when all gates below are satisfied on the integration branch.

1. **Persistence gate** — schema rebuild, lint, contract tests, atomic order creation/transition, receipt reservation/finalization, idempotency and concurrency tests all pass.
2. **Domain gate** — network/wallet, money/currency, order-state and receipt policies match the approved behavior and explicit exclusions.
3. **Application gate** — quote/order creation and receipt orchestration preserve snapshots, expiry, bounded retries and replay behavior.
4. **Runtime gate** — Telegram-facing handlers are implemented against v2 application ports; legacy database/runtime modules are not imported as compatibility shortcuts.
5. **Regression gate** — every verified current-Al-Manara behavior that materially affects users, payments, receipts, wallets, administration or order lifecycle has a corresponding v2 contract/unit/integration test.
6. **CI gate** — unit and database workflows are green for the final integration commit before promotion to v2 main.

A failure in a gate is a repair target, not a reason to abandon the migration. Fix the underlying defect, add or correct regression coverage, and rerun the affected gate.

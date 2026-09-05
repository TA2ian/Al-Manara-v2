# Al-Manara-v2

## Telegram runtime

The integration branch contains the V2 Telegram polling runtime. It is not active merely because the repository is updated; a long-running deployment must execute `python main.py`.

Required runtime environment variables:

- `TELEGRAM_BOT_TOKEN`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

The runtime uses Telegram polling, clears any webhook before polling, and uses a shared Supabase lease to prevent multiple customer pollers from consuming the same update stream. The local process also uses an OS-level lock to prevent duplicate pollers on one host.

`/start` opens the customer dashboard. `/verify` and `/orders` remain direct command fallbacks. `/admin` opens the administrative dashboard only after the existing database-backed primary-admin authorization succeeds.

For container deployment, use the repository `Dockerfile` and provide the three required environment variables through the hosting platform's secret manager. Do not commit credentials to the repository.

This branch is an integration branch. It must not be treated as a production deployment until the migration and runtime acceptance checks are complete.

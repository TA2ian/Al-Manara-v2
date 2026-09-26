# Al-Manara-v2

## Telegram runtime

The integration branch contains the V2 Telegram polling runtime. It is not active merely because the repository is updated; a long-running deployment must execute `python main.py`.

Required runtime environment variables:

- `TELEGRAM_BOT_TOKEN`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `AL_MANARA_EMERGENCY_MODE` (optional; defaults to `false`; set to `true`/`1`/`on` only through the deployment secret manager to enable backup-admin emergency access)

The runtime uses Telegram polling, clears any webhook before polling, and uses a shared Supabase lease to prevent multiple customer pollers from consuming the same update stream. The local process also uses an OS-level lock to prevent duplicate pollers on one host.

`/start` opens the customer dashboard. `/verify` and `/orders` remain direct command fallbacks. `/admin` opens the administrative dashboard only after the existing database-backed primary-admin authorization succeeds.

For container deployment, use the repository `Dockerfile` and provide the three required environment variables through the hosting platform's secret manager. Do not commit credentials to the repository.

This branch is an integration branch. It must not be treated as a production deployment until the migration and runtime acceptance checks are complete.


### Emergency Mode

Backup-admin access is fail-closed and disabled by default. Emergency Mode is controlled only by the deployment environment; there is no Telegram control for enabling it.

Set `AL_MANARA_EMERGENCY_MODE=true` (or `1`/`on`) in the trusted deployment environment and restart/redeploy the bot. The runtime reads the value at startup. When disabled, backup administrators cannot create or use an administrative session through the Telegram runtime. Primary-admin access is unaffected.

Do not commit this setting or credentials to the repository. Treat enabling Emergency Mode as a security-sensitive deployment action and keep the deployment audit trail.

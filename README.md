# JRF Motorcycle Parts

Inventory, point-of-sale, and reporting system for a motorcycle parts shop.
Flask 3 + PostgreSQL, with a server-rendered UI and a JSON API over the same
service layer.

---

## Quick start

### 1. Requirements

- Python 3.11+
- PostgreSQL 14+ (or a Supabase project)
- Redis — optional; needed only for background tasks and shared rate limiting

### 2. Install

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt        # runtime only
pip install -r requirements-dev.txt    # + tests, linters
```

### 3. Configure

```bash
cp .env.example .env              # deployment settings
cp .env.local.example .env.local  # your machine — point at a throwaway DB
```

| Variable       | Notes                                     |
| -------------- | ----------------------------------------- |
| `DATABASE_URL` | PostgreSQL connection string              |
| `SECRET_KEY`   | Required in production, ≥32 chars         |
| `FLASK_ENV`    | `development`, `production`, or `testing` |

Generate a secret key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

**Which database am I talking to?** Precedence is:

```
exported shell variables  >  .env.local  >  .env
```

`.env` describes the deployment. `.env.local` is git-ignored and exists so
local work never touches it — spin up a disposable database with
`docker compose up -d postgres` and point `.env.local` at
`postgresql://jrf_user:…@127.0.0.1:5432/jrf_motoshop`.

Every startup prints the database it resolved, and development mode warns
when that database is remote:

```
INFO  JRF Motoshop starting (env=development, debug=True, database=127.0.0.1:5432/jrf_motoshop)
```

Two implementation notes, both learned the hard way:

- **Config is resolved in `create_app()`, never in a class body.** Class-level
  `os.environ.get(...)` freezes at import, so later changes are ignored. To
  override settings, pass `create_app(overrides={...})` — do not mutate
  `os.environ` and hope.
- **Flask's CLI loads `.env` before importing the app**, so "the variable is
  already set" does not mean a human set it. `load_environment()` compares
  against `.env`'s own contents to decide whether `.env.local` may override.

### 4. Create the schema

```bash
flask --app wsgi db upgrade      # apply migrations
flask --app wsgi init-db         # default settings + bootstrap admin
flask --app wsgi seed-data       # optional sample catalogue
```

`init-db` prints a randomly generated administrator password once. Save it,
then change it after first login. Pass `--admin-password` to choose your own.

### 5. Run

```bash
flask --app wsgi run --debug          # development
gunicorn --bind 0.0.0.0:5000 wsgi:app # production
```

Visit <http://localhost:5000>.

---

## Docker

```bash
cp .env.example .env      # set SECRET_KEY and POSTGRES_PASSWORD
docker compose up -d
```

This starts PostgreSQL, Redis, a one-shot migration container, and the app on
port 5000. The app waits for migrations to complete before serving traffic.

```bash
docker compose --profile workers up -d      # + celery worker and beat
docker compose --profile production up -d   # + nginx reverse proxy
```

For TLS: put `fullchain.pem` and `privkey.pem` in `./ssl` and uncomment the
HTTPS server block in `nginx.conf`.

---

## Architecture

```
wsgi.py                 entry point - create_app()
app/
  core/
    config.py           per-environment config; validated at startup
    factory.py          application factory, blueprint registration
    extensions.py       db, login_manager, migrate, csrf
    security.py         headers, rate limiting, error handlers
  models/               SQLAlchemy models
  schemas/              marshmallow validation + serialisation
  services/             business logic (no HTTP concerns)
  api/                  JSON API blueprints
  web/                  server-rendered page blueprints
  tasks/                Celery background jobs
  cli/                  flask CLI commands
templates/              Jinja2 templates
static/                 CSS, JS, images
migrations/             Alembic migrations
tests/                  pytest suite
```

**The service layer is the single source of truth.** The API blueprints and
the web blueprints are both thin adapters over `app/services/`. A business
rule — who may edit a user, how a sale total is computed, when stock is
deducted — lives in exactly one place so the two front doors cannot disagree.

Two conventions matter when working on this codebase:

1. **`schema.load()` always returns a plain `dict`.** Services construct models
   themselves (`Part(**data)`), so schemas never use `load_instance`.
2. **Money is `Decimal` end to end.** Totals are computed server-side from line
   items; `total_amount`, `receipt_number` and friends are `dump_only`, so a
   client cannot choose what it pays.

---

## Roles and permissions

| Capability              | Admin | Manager | Staff |
| ----------------------- | :---: | :-----: | :---: |
| Point of sale           |   ✓   |    ✓    |   ✓   |
| View inventory          |   ✓   |    ✓    |   ✓   |
| Customers               |   ✓   |    ✓    |   ✓   |
| Edit inventory          |   ✓   |    ✓    |       |
| Manage suppliers        |   ✓   |    ✓    |       |
| Purchase orders         |   ✓   |    ✓    |       |
| Maintenance log         |   ✓   |    ✓    |       |
| Expenses                |   ✓   |    ✓    |       |
| Void sales              |   ✓   |    ✓    |       |
| Reports                 |   ✓   |    ✓    |       |
| Settings                |   ✓   |    ✓    |       |
| Reveal secret settings  |   ✓   |         |       |
| Manage staff            |   ✓   |         |       |
| Backups, logs           |   ✓   |         |       |

The sidebar only shows what the signed-in role can reach.

The last active administrator cannot be demoted, disabled, or deleted.

---

## API

Session-cookie authenticated. Log in at `POST /api/auth/login`.

```
POST   /api/auth/login              GET  /api/auth/me
POST   /api/auth/logout             POST /api/auth/change-password

GET    /api/parts/                  POST /api/parts/
GET    /api/parts/<id>              PUT  /api/parts/<id>
POST   /api/parts/<id>/stock        GET  /api/parts/<id>/stock-history
GET    /api/parts/<id>/sales-metrics
GET    /api/parts/low-stock

GET    /api/suppliers               POST /api/suppliers
GET    /api/customers               POST /api/customers

GET    /api/sales/                  POST /api/sales/
GET    /api/sales/<id>              POST /api/sales/<id>/void
GET    /api/sales/<id>/payments     POST /api/sales/<id>/payments
GET    /api/sales/summary           GET  /api/sales/top-parts

GET    /api/expenses                POST /api/expenses
GET    /api/expenses/<id>           PUT  /api/expenses/<id>

GET    /api/purchase-orders         POST /api/purchase-orders
GET    /api/purchase-orders/<id>
POST   /api/purchase-orders/<id>/receive     (books stock in)
POST   /api/purchase-orders/<id>/status

GET    /api/maintenance             POST /api/maintenance
GET    /api/maintenance/<id>        PUT  /api/maintenance/<id>

GET    /api/reports/dashboard       GET  /api/reports/sales
GET    /api/reports/inventory       GET  /api/reports/profitability
GET    /api/reports/expenses

GET    /api/dashboard/stats         GET  /api/dashboard/today
GET    /api/dashboard/overview      GET  /api/dashboard/sales-chart

GET    /api/staff/                  GET  /api/settings/
GET    /api/notifications/          GET  /api/system/health
POST   /api/system/backups          GET  /api/system/logs
```

`/api/customers` and `/api/suppliers` are the canonical paths; the older
`/api/sales/customers` and `/api/parts/suppliers` still resolve to the same
handlers.

Creating a sale:

```bash
curl -X POST http://localhost:5000/api/sales/ \
  -H 'Content-Type: application/json' -b cookies.txt \
  -d '{
        "payment_method": "cash",
        "customer_id": 3,
        "details": [
          {"part_id": 1, "quantity": 2, "discount_percent": 10, "tax_percent": 12}
        ]
      }'
```

Errors are consistent JSON:

```json
{ "error": "Validation failed", "details": { "price": ["Not a valid number."] } }
```

Every response carries an `X-Request-ID` header, echoed in 500 payloads.

---

## CLI

```bash
flask --app wsgi init-db          # tables, default settings, bootstrap admin
flask --app wsgi create-admin     # add an administrator interactively
flask --app wsgi seed-data        # sample suppliers, parts, customers
flask --app wsgi backup-db        # pg_dump to ./backups
flask --app wsgi cleanup --days 90 [--dry-run]
flask --app wsgi reindex          # REINDEX (PostgreSQL only)
flask --app wsgi db upgrade       # apply migrations
flask --app wsgi db migrate -m "..."   # generate a migration
```

---

## Testing

```bash
pytest --ignore=tests/browser -q         # server-side suite (fast, no browser)
pytest tests/unit -q                     # services only
pytest --cov=app --cov-report=term-missing

# Browser tests - one-off setup, then run
python -m playwright install chromium
pytest tests/browser -q
```

The server-side tests run against in-memory SQLite and need no external
services. They include smoke tests that render every page, which catches
template errors that only surface at render time.

The browser tests (`tests/browser/`) start the real app on a socket and drive
it with Chromium. Every one of them also asserts the page produced **no**
JavaScript errors — that is what catches the class of bug a 200 response
hides: a payload the API rejects, a modal that never opens, a dropdown that
stays empty, a CDN blocked by our own CSP. External requests are blocked so
the tests stay hermetic; whether the CSP actually permits each CDN is asserted
separately (and much faster) in `tests/integration/test_security.py`.

CI runs lint, both suites, and a migration check against a real PostgreSQL
service — see `.github/workflows/ci.yml`.

## Front-end conventions

`static/js/api.js` defines `JRF`, loaded on every page before anything else:

| Helper | Use |
| ------ | --- |
| `JRF.api(url, opts)` | Always resolves to `{ok, status, data}`; never throws. Redirects to login on 401. |
| `JRF.errorMessage(data, fallback)` | Flattens `{details: {field: [msg]}}` into one readable line. |
| `JRF.notify(msg, type)` | Toast instead of `alert()`. Escapes its own message. |
| `JRF.escapeHtml(value)` | **Required** around any user text going into `innerHTML`. |
| `JRF.safeUrl(value)` | Vets a URL for an `href`; rejects `javascript:` and off-site. |

Two rules the tests enforce:

1. **Branch on `response.ok` / `result.ok`, not on a `success` field.** The
   flag exists for older call sites, but the status code is the truth.
2. **Never interpolate user text into `innerHTML` unescaped.** A test greps
   for this and fails the build.

---

## Operational notes

**Rate limiting.** Counters default to in-process memory, which is per-worker.
Set `RATELIMIT_STORAGE_URI` to a Redis URL whenever you run more than one
gunicorn worker, or the effective limit is multiplied by the worker count.

**Proxy headers.** `TRUST_PROXY_HEADERS` is on by default, so the app takes the
client IP from `X-Forwarded-For`. That is correct behind nginx or a platform
load balancer. If the app is exposed directly, set it to `false` — otherwise a
client can spoof the header and evade per-IP limits.

**Backups.** `POST /api/system/backups` and the nightly task shell out to
`pg_dump`, which must be on `PATH` (it is in the Docker image). Downloads are
restricted to files inside the configured backup directory.

**Email.** Optional. Set `MAIL_SERVER` and install `Flask-Mail`; without both,
email tasks return `skipped` rather than failing.

**Restocking goes through purchase orders.** Raise an order at
`/purchase-orders/`, mark it *ordered*, then receive against it. Receiving
increases `stock_quantity`, writes a `StockEntry`, and updates the part's
`cost_price` to what was actually paid (last-cost valuation) — which is what
keeps the profitability report honest. Orders follow a state machine
(`pending → ordered → partial → received`, with `cancelled` available until
receipt); invalid transitions are rejected, and receipts are atomic.

**API response contract.** Every JSON response under `/api/` carries a
`success` boolean, stamped centrally in the factory. Errors additionally
repeat their text under both `error` and `message`, and validation failures
include a `details` object keyed by field.

**Migrations on an existing database.** The pre-2.0 schema differs
substantially from the current models — `parts` lacked `sku`, `is_active` and
`min_stock_level`, and `sale_details` used `price_at_sale`. Alembic's baseline
migration builds the current schema from scratch; it is not a converter for
the old one. Stand up a fresh database and migrate the data across rather than
pointing the app at a pre-2.0 schema.

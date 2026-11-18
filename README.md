# ECHOUTRA ONE

The internal company platform of **ECHOUTRA IT SOLUTIONS**. It covers people, attendance, work, clients and finance, in one installable web app.

| Area | Modules |
|---|---|
| People | Employees · Face-verified attendance · Leave & holidays · Recruitment · Offer letters |
| Work | Projects & milestones · Tasks (list + board) · Clients · Email (Gmail / Outlook) |
| Finance | Payroll & payslips · Expenses & reimbursements |
| Company | Role dashboards · Announcements, meetings & calendar · Reports (PDF / Excel) · AI assistant |
| Administration | Users, roles & permissions · Organization · Settings · Audit log · Backups |

The stack is React 18 (Vite, Tailwind), FastAPI (Python 3.13, SQLAlchemy 2, Alembic) and MySQL 8. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## 1. Prerequisites

- **Python 3.13**. The 3.14 builds of OpenCV and other libraries are not yet available.
- **Node.js 20+** (tested with 24)
- **MySQL 8.0**
- Optional: Redis (shared rate limits), `mysqldump` (backups; ships with MySQL)

## 2. Database setup

Create the database and a dedicated application user. Don't run the app as `root` in production.

```sql
CREATE DATABASE IF NOT EXISTS echo_attend CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'echo_app'@'localhost' IDENTIFIED BY '<strong password>';
GRANT ALL PRIVILEGES ON echo_attend.* TO 'echo_app'@'localhost';
FLUSH PRIVILEGES;
```

Alembic migrations create every table. Never create tables by hand.

## 3. Backend

```powershell
cd backend
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env          # then fill in DB_* and generate the three secrets (see comments in the file)
.venv\Scripts\alembic upgrade head
.venv\Scripts\python -m scripts.download_models      # face detection / recognition models (~38 MB)
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Interactive API documentation: <http://localhost:8000/api/docs>.

## 4. Create the first Super Admin

```powershell
cd backend
.venv\Scripts\python -m scripts.create_superadmin --email ceo@your-domain.com --first-name First --last-name Last
```

The script prompts for the password, which is never passed on the command line. It needs at least 8 characters, with upper- and lower-case letters and a digit. It also creates the matching employee profile (ID `ECH0001`, …) and seeds the reference data: roles, permissions, leave types, expense categories, a salary-component example and the default offer template.

After that, everyone else is onboarded from the app:

1. Go to **Employees → Add employee**.
2. A login is created with a one-time temporary password, which you share securely.
3. The employee must change the password at first sign-in.

## 5. Frontend

```powershell
cd frontend
npm install
npm run dev          # http://localhost:5173  (proxies /api to :8000)
npm run build        # production build in dist/ incl. PWA service worker
```

To install the app as a PWA, open the site in Chrome or Edge and choose **Install**, or use "Add to Home Screen" on iOS/Android. HTTPS is required in production; `localhost` works without it.

## 6. Tests

```powershell
cd backend;  .venv\Scripts\python -m pytest -q      # 52 API/integration tests on a throw-away echo_attend_test DB
cd frontend; npm test                                # 15 component/unit tests (Vitest)
cd frontend; npm run lint                            # ESLint
# Browser workflow test against a TEST deployment (creates records):
#   set E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD, then: npm run e2e
```

The backend suite drops and re-creates `<DB_NAME>_test` from the migrations on every run, and refuses to run against any database whose name doesn't end in `_test`.

## 7. Configuration and integrations

All configuration lives in `backend/.env`; see `backend/.env.example`. Optional integrations:

| Feature | What to set | Details |
|---|---|---|
| AI assistant | `GEMINI_API_KEY` | [docs/INTEGRATIONS.md](docs/INTEGRATIONS.md#gemini) |
| Gmail sync / send | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | [docs/INTEGRATIONS.md](docs/INTEGRATIONS.md#gmail) |
| Outlook sync / send | `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET` | [docs/INTEGRATIONS.md](docs/INTEGRATIONS.md#outlook) |
| S3 document storage | `STORAGE_BACKEND=s3`, `AWS_*` | [docs/INTEGRATIONS.md](docs/INTEGRATIONS.md#s3) |
| Shared rate limiting | `REDIS_URL` | [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) |

Without these keys, the related screens explain what is missing. Nothing is simulated.

## 8. Documentation

- [Architecture & database schema](docs/ARCHITECTURE.md)
- [API reference](docs/API.md) (live OpenAPI at `/api/docs`)
- [Deployment, HTTPS, backups & recovery](docs/DEPLOYMENT.md)
- [Security & privacy](docs/SECURITY.md)
- [External integrations](docs/INTEGRATIONS.md)

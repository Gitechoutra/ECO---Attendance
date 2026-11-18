# ECHOUTRA ONE — Architecture

ECHOUTRA ONE is the internal ERP for **ECHOUTRA IT SOLUTIONS**.

## Stack

| Layer | Technology |
|---|---|
| Frontend | React 18 (JavaScript) + Vite, Tailwind CSS 3, React Router 6, Axios, Recharts, lucide-react, vite-plugin-pwa |
| Backend | Python 3.13, FastAPI, SQLAlchemy 2 ORM, Alembic, Pydantic 2, PyJWT, Argon2 |
| Database | **MySQL 8.0** — database `echo_attend` (utf8mb4). The original spec named PostgreSQL; the owner chose the existing MySQL 8 server instead. The ORM layer is database-agnostic. |
| Face verification | OpenCV YuNet (detector) + SFace (128-d embeddings), challenge–response liveness |
| AI | Google Gemini (`google-genai`), permission-scoped context |
| Email | Gmail API and Microsoft Graph via OAuth 2.0 |
| Files | Storage abstraction: local disk (default) or AWS S3 (when configured) |
| Jobs | APScheduler (in-process). Redis is optional, used for shared rate limits. |
| Documents | ReportLab (PDF), openpyxl (Excel) |

## Layout

```
backend/
  app/
    core/        config, security (hashing/JWT/encryption), permissions, rate limiting
    db/          engine/session, declarative base
    models/      SQLAlchemy models, one file per domain
    schemas/     Pydantic request/response models
    services/    business logic (attendance, payroll, face, email, ai, pdf, storage, audit...)
    api/         FastAPI routers, one per module + deps.py (auth & permission dependencies)
    jobs/        scheduled background jobs
    main.py      app factory
  alembic/       migrations
  scripts/       create_superadmin.py, download_models.py, backup.py
  tests/         pytest suite (runs against echo_attend_test)
frontend/
  src/
    api/         axios client with token refresh, per-module API helpers
    components/  design-system primitives (ui/) and layout
    features/    one folder per module (pages + module components)
    context/     auth & toast providers
    hooks/, lib/
docs/            architecture, API, deployment, security
```

## Authorization model

- Four system roles: `super_admin` (CEO), `hr_admin`, `project_manager`, `employee`.
- Permissions are fine-grained codes (`employees.manage`, `payroll.view`, ...). Roles get default permission sets, which admins can edit. Admins can also grant or revoke individual permissions per user.
- Every API endpoint checks permissions on the server. Row-level scoping applies on top: employees see only their own records, and project managers see only projects they manage or belong to, plus those projects' clients.
- The AI assistant builds its context only from data that the same scoped services return for the calling user.

## Authentication

- Short-lived access JWT (15 min) plus an opaque refresh token (7 days), stored hashed in `refresh_tokens`.
- Refresh tokens rotate on every use. Reusing a revoked token revokes the whole token family, which signals theft.
- Login lockout after repeated failures, plus rate limiting on auth endpoints.

## Database schema (main tables)

| Domain | Tables |
|---|---|
| Identity | `roles`, `permissions`, `role_permissions`, `user_permission_overrides`, `users`, `refresh_tokens`, `audit_logs`, `company_settings`, `notifications`, `files` |
| People | `departments`, `designations`, `employees`, `employee_history` |
| Attendance | `biometric_consents`, `face_profiles`, `liveness_challenges`, `attendance_records`, `attendance_breaks`, `attendance_corrections` |
| Leave | `leave_types`, `leave_balances`, `leave_requests`, `holidays` |
| Clients | `clients`, `client_contacts`, `client_requirements`, `client_meetings`, `client_communications`, `client_feedback`, `client_contracts` |
| Projects | `projects`, `project_members`, `milestones`, `tasks`, `task_comments`, `task_updates`, `task_history` |
| Email | `email_accounts`, `email_messages`, `email_followups` |
| Recruitment | `job_openings`, `candidates`, `interviews` |
| Offers | `offer_templates`, `offer_letters`, `offer_letter_versions` |
| Payroll | `salary_components`, `salary_structures`, `salary_structure_items`, `payroll_adjustments`, `payroll_runs`, `payslips`, `salary_payments` |
| Expenses | `expense_categories`, `expenses` |
| Communication | `announcements`, `meetings`, `meeting_attendees` |
| AI | `ai_conversations`, `ai_messages` |

**Key relationships**

- `employees` is the single person record. `users.employee_id` links a login to it. Attendance, leave, tasks, payroll and expenses all reference `employees.id`.
- `projects.client_id` links to `clients`, so a client's project history is a query, not a copy.
- `candidates.employee_id` is set when a hired candidate is converted. The offer letter's PDF versions are then attached to the employee's documents.
- Uploaded files live in the `files` table (`entity_type`, `entity_id`, `category`) and are served only through authorized download endpoints.

## Biometrics and privacy

- Face embeddings (never raw photos) are encrypted with Fernet (`BIOMETRIC_ENCRYPTION_KEY`).
- Enrollment requires recorded employee consent (`biometric_consents`). Revoking consent deletes the template.
- Templates of deactivated employees are purged after `biometric_retention_days`.
- Liveness works by challenge–response: the server issues a random head-pose sequence with a single-use nonce. The browser captures a burst of live camera frames (gallery uploads are not offered). The server verifies that there is one face per frame, the same identity across frames, the requested pose changes in order, real inter-frame motion, and timing.
- If the camera or verification fails, the employee can use a manual check-in request, which needs approval.

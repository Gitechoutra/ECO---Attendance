# API reference

- Base path: `/api/v1`
- Live, always-current OpenAPI docs: **`/api/docs`** (Swagger) and `/api/redoc`
- Machine-readable schema: `/api/openapi.json`

## Conventions

- **Authentication:** send `Authorization: Bearer <access_token>`. Get tokens from `POST /auth/login`, renew them with `POST /auth/refresh`, which rotates the refresh token.
- **Errors:** responses look like `{"detail": "Human readable message"}`. Validation errors (422) also include `errors: [{field, message}]`.
  - 401: not signed in, or session expired
  - 403: missing permission
  - 404: not found
  - 409: conflict or duplicate
  - 413/415: upload rejected
  - 423: account locked
  - 429: rate limited
  - 503: database or integration unavailable
- **Pagination:** list endpoints accept `page` and `page_size` (maximum 200) and return `{items, total, page, page_size, pages}`.
- **Dates and times:** dates are `YYYY-MM-DD`. Datetimes are UTC, ISO-8601, without a zone suffix unless noted. Attendance and leave dates follow the company time zone (Settings).
- **Uploads:** multipart, `file` field, maximum `MAX_UPLOAD_MB`.

## Endpoint groups

| Group | Main endpoints |
|---|---|
| Auth | `POST /auth/login` · `/auth/refresh` · `/auth/logout` · `/auth/logout-all` · `GET /auth/me` · `POST /auth/change-password` |
| Dashboard | `GET /dashboard` (role-aware sections) · `GET /search?q=` |
| Employees | `GET/POST /employees` · `GET/PUT /employees/{id}` · `/employees/me` · `/employees/directory` · `/{id}/deactivate` · `/reactivate` · `/account` · `/reset-password` · `/photo` · `/documents` · `/history` · `GET/POST/PUT/DELETE /departments`, `/designations` |
| Attendance | `GET /attendance/today` · `POST /attendance/challenge` · `/check-in/face` · `/check-out/face` · `/check-in` · `/check-out` · `/break` · `GET /attendance/my` · `/records` · `/live` · `/summary` · `POST /attendance/manual` · `GET/POST /attendance/corrections` · `/corrections/{id}/review` · `/face/status/{emp}` · `POST /face/enroll` · `DELETE /face/{emp}` |
| Leave | `GET/POST /leave/types` · `GET /leave/balances[/me]` · `PUT /leave/balances` · `GET/POST /leave/requests` (`scope=mine,approvals,all`) · `/requests/{id}/review` · `/cancel` · `GET /leave/calendar` · `GET/POST/PUT/DELETE /holidays` |
| Projects & tasks | `GET/POST /projects` · `GET/PUT/DELETE /projects/{id}` · `/members` · `/milestones` · `/files` · `/report` · `GET/POST /tasks` (`scope=mine,created,all`) · `GET/PUT/DELETE /tasks/{id}` · `PATCH /tasks/{id}/status` · `/comments` · `/updates` |
| Clients | `GET/POST /clients` · `GET/PUT/DELETE /clients/{id}` · `/projects` · `/{contacts,requirements,meetings,communications,feedback,contracts}` (CRUD) · `/contracts/{id}/file` · `/documents/*` · `/emails/list` |
| Email | `GET /email/status` · `/accounts` · `POST /email/connect` · OAuth callbacks · `/accounts/{id}/sync` · `DELETE /accounts/{id}` · `GET /email/messages[/{id}]` · `/messages/{id}/link` · `/followups` · `POST /email/send` |
| Recruitment | `GET/POST/PUT/DELETE /recruitment/jobs` · `/candidates` · `PATCH /candidates/{id}/status` · `/resume` · `/convert` · `/interviews` · `/interviews/{id}/feedback` |
| Offer letters | `GET/POST /offers` · `/offers/templates` · `GET/PUT /offers/{id}` · `/submit` · `/decision` · `/send` · `/withdraw` · public: `GET /public/offers/{token}`, `/pdf`, `POST /respond` |
| Payroll | `GET/POST/PUT /payroll/components` · `/structures` · `/adjustments` · `GET/POST /payroll/runs` · `/runs/{id}/finalize` · `/pay` · `GET /payroll/my-payslips` · `/payslips/{id}/pdf` · `/summary` · `/preview/{emp}` |
| Expenses | `GET/POST /expenses` (multipart with `receipt`) · `/{id}/review` · `/{id}/reimburse` · `/categories` · `/stats` |
| Communication | `GET/POST/PUT/DELETE /announcements` · `GET/POST/PUT /meetings` · `/meetings/{id}/rsvp` · `/cancel` · `GET /calendar/events` · `/celebrations` |
| Reports | `GET /reports` · `GET /reports/{attendance,employees,leave,recruitment,projects,tasks,clients,payroll,expenses}?date_from&date_to&format=json\|xlsx\|pdf` |
| AI | `GET /ai/status` · `POST /ai/chat` · `GET/DELETE /ai/conversations[/{id}]` |
| Admin | `GET/PUT /admin/users` · `/users/{id}/permissions` · `GET/POST/PUT /admin/roles` · `/permissions` · `GET/PUT /admin/settings` · `/audit` · `GET/POST /admin/backups` |
| Files & notifications | `GET /files/{id}` (authorized download) · `GET /notifications` · `/{id}/read` · `/read-all` |
| Health | `GET /api/health` (no auth) |

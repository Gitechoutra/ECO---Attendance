# Security and privacy

## Authentication

- Passwords are hashed with **Argon2id**. The minimum is 8 characters, with mixed case and a digit.
- A dummy hash check on unknown emails prevents user enumeration through timing.
- Accounts lock after `MAX_LOGIN_ATTEMPTS` failed attempts, for `LOCKOUT_MINUTES`. Auth endpoints are rate limited (login: 10 requests per minute per IP).
- **Access tokens** are HS256 JWTs valid for 15 minutes. They are held only in memory in the browser.
- **Refresh tokens** are opaque, 7-day tokens stored in the database as SHA-256 hashes.
  - They are **rotated on every use**.
  - If a rotated token is reused, the whole token family is revoked. This detects theft.
  - Password changes, role changes and deactivation bump `token_version`, which invalidates every live session immediately.
- Trade-off: the browser keeps the refresh token in `localStorage` so the installed PWA stays signed in. Rotation and reuse detection limit the impact of theft. Strict CSP headers (see `frontend/nginx.conf`) reduce XSS exposure, and the app never renders HTML from users or AI.
- New accounts get a one-time temporary password, and a password change is forced at first login.

## Authorization

- 38 permission codes are grouped into four system roles, plus optional custom roles and per-user grant/revoke overrides.
- **Every endpoint checks permissions on the server.** The frontend only hides navigation.
- Row-level scoping:
  - Employees see only their own attendance, leave, payslips and expenses.
  - Project managers see projects they manage or are members of, and only those projects' clients.
  - Email is visible only to the mailbox owner, or for shared mailboxes, to users with `email.view_shared`.
- Self-approval is blocked for leave, attendance corrections, expenses and offer letters. The exception is a Super Admin approving their own offer.
- There must always be at least one active Super Admin. Users cannot change their own role or deactivate themselves.

## Data protection

- Bank account numbers, PAN and national ID are **encrypted at rest** with Fernet (`DATA_ENCRYPTION_KEY`), and are masked for anyone without `employees.view_sensitive`.
- OAuth mailbox tokens are encrypted with the same key.
- Files are stored under random keys and served only through `/api/v1/files/{id}`, which checks the file's owning record.
  - Uploads are size-limited and checked against an allow-list of types.
  - The file's content signature (magic bytes) is verified against its declared type.
- The audit log records sign-ins, every create, update and approval, exports, payslip downloads, biometric events and settings changes, with the user and IP address.
- API responses are never cached by the service worker (`NetworkOnly`).

## Biometric data (face verification)

- **Consent first.** HR records explicit employee consent (version, time, recording administrator) before enrollment. The notice is shown in the app.
- **Templates, not photos.** Only a 128-dimension SFace embedding is stored, encrypted with a separate key (`BIOMETRIC_ENCRYPTION_KEY`). Enrollment and check-in frames are processed in memory and discarded.
- **Revocation.** Employees can revoke consent from *My profile → Biometric privacy*. The template is deleted immediately.
- **Retention.** Templates of former employees are purged automatically after `biometric_retention_days` (Settings).
- **Liveness (presentation-attack resistance).** The server issues a random head-pose sequence and a single-use nonce valid for 90 seconds. The browser captures a burst of frames from the **live camera stream only**; there is no file upload path. The server requires all of the following:
  - exactly one face per frame;
  - the same identity across frames;
  - the requested movements, in order;
  - real motion between frames;
  - plausible capture timing;
  - a match above the configured threshold.
- **Fallback.** If the camera or verification fails, employees submit a *manual attendance request* that HR approves. Every attendance record stores its method (`face`, `web`, `manual` or `correction`).

**Limitation:** this liveness check defeats printed photos, screen replays of still images and pre-recorded videos that cannot follow a random sequence. It is **not** a certified ISO/IEC 30107-3 PAD system and can be defeated by a sophisticated real-time deepfake or a 3D mask. For high-assurance needs, add a certified liveness SDK or kiosk hardware with depth sensing.

Privacy laws such as India's DPDP Act 2023 may impose further obligations, including notice, purpose limitation, grievance contact and retention. Review the consent text with your legal counsel.

## Transport and headers

- Run behind HTTPS in production (see DEPLOYMENT.md). The browser camera API also requires HTTPS.
- The API sends `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy` and `Permissions-Policy` (camera limited to self). It adds HSTS in production.
- CORS is restricted to `CORS_ORIGINS`.
- In production, the backend refuses to start if `SECRET_KEY` or either encryption key is missing or weak.

## Key management

- Keep `SECRET_KEY`, `DATA_ENCRYPTION_KEY` and `BIOMETRIC_ENCRYPTION_KEY` in a secrets manager and back them up separately from database backups.
- **Losing an encryption key makes the data it protects unreadable.** Without the data key, bank details and tokens can't be decrypted; without the biometric key, every employee must re-enroll.
- Rotating `SECRET_KEY` signs everyone out.

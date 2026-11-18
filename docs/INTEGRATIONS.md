# External integrations

Every integration is optional. Credentials go in `backend/.env`, and the API must be restarted after changing them. **Settings → Integrations** in the app shows which integrations are configured.

## Gemini

Gemini powers the AI assistant.

1. Create an API key in Google AI Studio.
2. Set `GEMINI_API_KEY=...`. Optionally set `GEMINI_MODEL` (default `gemini-2.5-flash`).

How data access works:

- The model never receives a bulk export of company data.
- It can only call tool functions (`app/services/ai.py`). Each tool applies the signed-in user's permissions exactly as the REST API does.
- An employee asking about payroll gets "not authorized" from the tool, and the model is instructed to relay that refusal.
- Conversations are stored per user (`ai_conversations`) and logged in the audit log.

## Gmail

Gmail uses Google Workspace OAuth 2.0.

1. In Google Cloud Console, create a project and enable the **Gmail API**.
2. Create an OAuth consent screen. Choose *Internal* for a Workspace domain.
3. Add these scopes: `gmail.readonly`, `gmail.send`, `openid`, `email`.
4. Create an OAuth client of type *Web application* with this authorized redirect URI:
   `{BACKEND_URL}/api/v1/email/oauth/gmail/callback`
   (for example `https://one.echoutra.com/api/v1/email/oauth/gmail/callback`).
5. Set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `BACKEND_URL` and `FRONTEND_URL`.

## Outlook

Outlook uses Microsoft 365 / Graph.

1. In the Azure portal, go to App registrations and create a new registration.
2. Add a *Web* redirect URI: `{BACKEND_URL}/api/v1/email/oauth/outlook/callback`.
3. Add these delegated API permissions: `Mail.Read`, `Mail.Send`, `User.Read`, `offline_access`.
4. Create a client secret.
5. Set `MICROSOFT_CLIENT_ID` and `MICROSOFT_CLIENT_SECRET`. Set `MICROSOFT_TENANT` to your tenant ID to restrict sign-in to your organisation (default `common`).

**How mailbox sync works**

- Only mailboxes a user explicitly connects through the provider's consent screen are synced. Nothing is read without OAuth consent.
- Tokens are encrypted with `DATA_ENCRYPTION_KEY`.
- Sync runs every 10 minutes and covers the last 30 days on first connect.
- Messages are linked to clients automatically by email address or domain. Users can re-link them manually.
- Shared company mailboxes (e.g. `sales@`) are visible only to users with the `email.view_shared` permission.
- Disconnecting a mailbox deletes its tokens.

## S3

S3 is used for document storage.

1. Create a private bucket with *Block all public access* enabled and default encryption turned on.
2. Create an IAM user limited to `s3:PutObject`, `s3:GetObject` and `s3:DeleteObject` on that bucket.
3. Set `STORAGE_BACKEND=s3`, `AWS_S3_BUCKET`, `AWS_REGION`, `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`.

Files are always downloaded through the API, which checks permissions, and never through public URLs. Existing local files in `backend/storage/` are not migrated automatically. Copy them to the bucket with the same keys before switching (`aws s3 sync backend/storage s3://bucket/`).

## Face recognition models

`scripts/download_models.py` fetches two models from the official OpenCV Zoo repository:

- **YuNet** (detector, MIT licence)
- **SFace** (recognizer, Apache-2.0)

They run locally, so no face data leaves your server.

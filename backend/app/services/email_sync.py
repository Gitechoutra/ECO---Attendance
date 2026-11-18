"""Official OAuth-based mailbox integrations (Gmail API, Microsoft Graph).

Only mailboxes that a user explicitly connects through the provider's consent screen are synced.
Nothing is simulated: if OAuth credentials are not configured, the endpoints say so.
"""
import base64
import re
import secrets
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from email.utils import getaddresses, parseaddr, parsedate_to_datetime
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import HTTPException
from sqlalchemy import false, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import ALGORITHM, decrypt_bytes, encrypt_bytes
from app.db.base import utcnow
from app.models import Client, ClientCommunication, ClientContact, EmailAccount, EmailMessage, Project

GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"
GOOGLE_SCOPES = "openid email https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send"

MS_AUTH = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"
MS_TOKEN = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
GRAPH = "https://graph.microsoft.com/v1.0/me"
MS_SCOPES = "offline_access openid email User.Read Mail.Read Mail.Send"

SYNC_DAYS = 30
MAX_PER_SYNC = 200


def provider_configured(provider: str) -> bool:
    if provider == "gmail":
        return bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET)
    if provider == "outlook":
        return bool(settings.MICROSOFT_CLIENT_ID and settings.MICROSOFT_CLIENT_SECRET)
    return False


def redirect_uri(provider: str) -> str:
    return f"{settings.BACKEND_URL}{settings.API_PREFIX}/email/oauth/{provider}/callback"


def build_auth_url(provider: str, user_id: int, shared: bool) -> str:
    if not provider_configured(provider):
        raise HTTPException(503, f"{'Google' if provider == 'gmail' else 'Microsoft'} OAuth is not configured. "
                                 "Add the client ID and secret to backend/.env (see docs/INTEGRATIONS.md).")
    state = jwt.encode({"uid": user_id, "p": provider, "shared": shared, "n": secrets.token_hex(8),
                        "exp": datetime.now(timezone.utc) + timedelta(minutes=10)}, settings.SECRET_KEY, ALGORITHM)
    if provider == "gmail":
        return GOOGLE_AUTH + "?" + urlencode({
            "client_id": settings.GOOGLE_CLIENT_ID, "redirect_uri": redirect_uri("gmail"), "response_type": "code",
            "scope": GOOGLE_SCOPES, "access_type": "offline", "prompt": "consent", "state": state,
            "include_granted_scopes": "true"})
    return MS_AUTH.format(tenant=settings.MICROSOFT_TENANT) + "?" + urlencode({
        "client_id": settings.MICROSOFT_CLIENT_ID, "redirect_uri": redirect_uri("outlook"), "response_type": "code",
        "scope": MS_SCOPES, "response_mode": "query", "state": state, "prompt": "select_account"})


def decode_state(state: str) -> dict:
    try:
        return jwt.decode(state, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.InvalidTokenError:
        raise HTTPException(400, "Invalid or expired authorization state")


def _token_request(provider: str, data: dict) -> dict:
    if provider == "gmail":
        url = GOOGLE_TOKEN
        data |= {"client_id": settings.GOOGLE_CLIENT_ID, "client_secret": settings.GOOGLE_CLIENT_SECRET}
    else:
        url = MS_TOKEN.format(tenant=settings.MICROSOFT_TENANT)
        data |= {"client_id": settings.MICROSOFT_CLIENT_ID, "client_secret": settings.MICROSOFT_CLIENT_SECRET,
                 "scope": MS_SCOPES}
    r = httpx.post(url, data=data, timeout=30)
    if r.status_code != 200:
        raise HTTPException(400, f"Token exchange failed: {r.json().get('error_description', r.text)[:200]}")
    return r.json()


def exchange_code(db: Session, provider: str, code: str, user_id: int, shared: bool) -> EmailAccount:
    tok = _token_request(provider, {"code": code, "grant_type": "authorization_code",
                                    "redirect_uri": redirect_uri(provider)})
    access = tok["access_token"]
    if provider == "gmail":
        profile = httpx.get(f"{GMAIL_API}/profile", headers={"Authorization": f"Bearer {access}"}, timeout=30).json()
        address = profile.get("emailAddress")
    else:
        me = httpx.get(GRAPH, headers={"Authorization": f"Bearer {access}"}, timeout=30).json()
        address = me.get("mail") or me.get("userPrincipalName")
    if not address:
        raise HTTPException(400, "Could not determine the mailbox address")
    acc = db.scalar(select(EmailAccount).where(EmailAccount.provider == provider,
                                               func.lower(EmailAccount.email_address) == address.lower()))
    if acc and acc.owner_user_id != user_id:
        raise HTTPException(409, "This mailbox is already connected by another user")
    if not acc:
        acc = EmailAccount(provider=provider, email_address=address.lower(), owner_user_id=user_id)
        db.add(acc)
    acc.is_shared = shared
    acc.access_token_enc = encrypt_bytes(access.encode())
    if tok.get("refresh_token"):
        acc.refresh_token_enc = encrypt_bytes(tok["refresh_token"].encode())
    acc.token_expires_at = utcnow() + timedelta(seconds=int(tok.get("expires_in", 3600)) - 60)
    acc.sync_status, acc.sync_error = "connected", None
    db.flush()
    return acc


def access_token(db: Session, acc: EmailAccount) -> str:
    if acc.token_expires_at and acc.token_expires_at > utcnow() and acc.access_token_enc:
        return decrypt_bytes(acc.access_token_enc).decode()
    if not acc.refresh_token_enc:
        acc.sync_status = "error"
        raise HTTPException(401, "Mailbox authorization expired. Reconnect the account.")
    tok = _token_request(acc.provider, {"grant_type": "refresh_token",
                                        "refresh_token": decrypt_bytes(acc.refresh_token_enc).decode()})
    acc.access_token_enc = encrypt_bytes(tok["access_token"].encode())
    if tok.get("refresh_token"):
        acc.refresh_token_enc = encrypt_bytes(tok["refresh_token"].encode())
    acc.token_expires_at = utcnow() + timedelta(seconds=int(tok.get("expires_in", 3600)) - 60)
    db.flush()
    return tok["access_token"]


# ------------------------------------------------------------------ linking

def _addresses(*fields: str | None) -> set[str]:
    out = set()
    for f in fields:
        for _, a in getaddresses([f or ""]):
            if a:
                out.add(a.lower())
    return out


def auto_link(db: Session, msg: EmailMessage) -> None:
    addrs = _addresses(msg.from_address, msg.to_addresses, msg.cc_addresses)
    addrs.discard(msg.account.email_address.lower())
    if not addrs:
        return
    client_id = db.scalar(select(Client.id).where(func.lower(Client.email).in_(addrs)).limit(1))
    if not client_id:
        client_id = db.scalar(select(ClientContact.client_id).where(func.lower(ClientContact.email).in_(addrs)).limit(1))
    if not client_id:
        domains = {a.split("@")[1] for a in addrs if "@" in a}
        public = {"gmail.com", "outlook.com", "hotmail.com", "yahoo.com", "icloud.com", "live.com"}
        for d in domains - public:
            client_id = db.scalar(select(Client.id).where(or_(Client.email.ilike(f"%@{d}"), Client.website.ilike(f"%{d}%"))).limit(1))
            if client_id:
                break
    if client_id:
        msg.client_id = client_id
        if msg.subject:
            projects = db.execute(select(Project.id, Project.code, Project.name).where(Project.client_id == client_id)).all()
            subj = msg.subject.lower()
            for pid, code, name in projects:
                if code.lower() in subj or (len(name) > 4 and name.lower() in subj):
                    msg.project_id = pid
                    break


def _log_client_comm(db: Session, msg: EmailMessage) -> None:
    if msg.client_id and not db.scalar(select(ClientCommunication.id).where(ClientCommunication.email_message_id == msg.id)):
        db.add(ClientCommunication(client_id=msg.client_id, channel="email",
                                   subject=(msg.subject or "(no subject)")[:255], summary=msg.snippet,
                                   occurred_at=msg.sent_at, email_message_id=msg.id, user_id=msg.account.owner_user_id))


# ------------------------------------------------------------------ sync

def _strip_html(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?</\1>", "", html)
    text = re.sub(r"(?i)<br\s*/?>|</p>|</div>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"&nbsp;", " ", text)).strip()


def _gmail_body(payload: dict) -> str:
    def walk(part):
        mime = part.get("mimeType", "")
        data = part.get("body", {}).get("data")
        if mime == "text/plain" and data:
            return base64.urlsafe_b64decode(data + "==").decode("utf-8", "replace")
        for p in part.get("parts", []) or []:
            r = walk(p)
            if r:
                return r
        if mime == "text/html" and data:
            return _strip_html(base64.urlsafe_b64decode(data + "==").decode("utf-8", "replace"))
        return None
    return (walk(payload) or "")[:200000]


def _sync_gmail(db: Session, acc: EmailAccount, token: str) -> int:
    headers = {"Authorization": f"Bearer {token}"}
    after = acc.last_synced_at - timedelta(hours=1) if acc.last_synced_at else utcnow() - timedelta(days=SYNC_DAYS)
    q = f"after:{int(after.replace(tzinfo=timezone.utc).timestamp())} -in:chats"
    ids, page = [], None
    with httpx.Client(timeout=30, headers=headers) as http:
        while len(ids) < MAX_PER_SYNC:
            params = {"q": q, "maxResults": 100}
            if page:
                params["pageToken"] = page
            r = http.get(f"{GMAIL_API}/messages", params=params)
            r.raise_for_status()
            data = r.json()
            ids += [m["id"] for m in data.get("messages", [])]
            page = data.get("nextPageToken")
            if not page:
                break
        existing = set(db.scalars(select(EmailMessage.provider_message_id).where(
            EmailMessage.account_id == acc.id, EmailMessage.provider_message_id.in_(ids or [""]))))
        n = 0
        for mid in ids[:MAX_PER_SYNC]:
            if mid in existing:
                continue
            m = http.get(f"{GMAIL_API}/messages/{mid}", params={"format": "full"}).json()
            h = {x["name"].lower(): x["value"] for x in m.get("payload", {}).get("headers", [])}
            frm = h.get("from", "")
            sent = datetime.fromtimestamp(int(m.get("internalDate", "0")) / 1000, timezone.utc).replace(tzinfo=None)
            out = parseaddr(frm)[1].lower() == acc.email_address.lower() or "SENT" in m.get("labelIds", [])
            msg = EmailMessage(account_id=acc.id, provider_message_id=mid, thread_id=m.get("threadId"),
                               direction="out" if out else "in", subject=(h.get("subject") or "")[:500],
                               from_address=frm[:255], to_addresses=h.get("to"), cc_addresses=h.get("cc"),
                               snippet=(m.get("snippet") or "")[:500], body_text=_gmail_body(m.get("payload", {})),
                               sent_at=sent, is_read="UNREAD" not in m.get("labelIds", []))
            msg.account = acc
            db.add(msg)
            db.flush()
            auto_link(db, msg)
            _log_client_comm(db, msg)
            n += 1
    return n


def _sync_outlook(db: Session, acc: EmailAccount, token: str) -> int:
    headers = {"Authorization": f"Bearer {token}", "Prefer": 'outlook.body-content-type="text"'}
    after = acc.last_synced_at - timedelta(hours=1) if acc.last_synced_at else utcnow() - timedelta(days=SYNC_DAYS)
    url = f"{GRAPH}/messages"
    params = {"$filter": f"receivedDateTime ge {after.strftime('%Y-%m-%dT%H:%M:%SZ')}", "$top": 50,
              "$orderby": "receivedDateTime desc",
              "$select": "id,conversationId,subject,from,toRecipients,ccRecipients,bodyPreview,body,receivedDateTime,isRead"}
    n = 0
    with httpx.Client(timeout=30, headers=headers) as http:
        while url and n < MAX_PER_SYNC:
            r = http.get(url, params=params)
            r.raise_for_status()
            data = r.json()
            params = None
            for m in data.get("value", []):
                if db.scalar(select(EmailMessage.id).where(EmailMessage.account_id == acc.id,
                                                           EmailMessage.provider_message_id == m["id"][:190])):
                    continue
                frm = (m.get("from") or {}).get("emailAddress", {})
                fmt = lambda lst: ", ".join(f"{x['emailAddress'].get('name', '')} <{x['emailAddress'].get('address', '')}>" for x in lst or [])  # noqa: E731
                sent = datetime.fromisoformat(m["receivedDateTime"].replace("Z", "+00:00")).replace(tzinfo=None)
                out = (frm.get("address") or "").lower() == acc.email_address.lower()
                msg = EmailMessage(account_id=acc.id, provider_message_id=m["id"][:190],
                                   thread_id=(m.get("conversationId") or "")[:190], direction="out" if out else "in",
                                   subject=(m.get("subject") or "")[:500],
                                   from_address=f"{frm.get('name', '')} <{frm.get('address', '')}>"[:255],
                                   to_addresses=fmt(m.get("toRecipients")), cc_addresses=fmt(m.get("ccRecipients")),
                                   snippet=(m.get("bodyPreview") or "")[:500],
                                   body_text=((m.get("body") or {}).get("content") or "")[:200000], sent_at=sent,
                                   is_read=bool(m.get("isRead")))
                msg.account = acc
                db.add(msg)
                db.flush()
                auto_link(db, msg)
                _log_client_comm(db, msg)
                n += 1
            url = data.get("@odata.nextLink")
    return n


def sync_account(db: Session, acc: EmailAccount) -> int:
    token = access_token(db, acc)
    started = utcnow()
    try:
        n = _sync_gmail(db, acc, token) if acc.provider == "gmail" else _sync_outlook(db, acc, token)
    except httpx.HTTPStatusError as e:
        acc.sync_status = "error"
        acc.sync_error = f"Provider returned {e.response.status_code}"
        db.commit()
        raise HTTPException(502, f"Mailbox sync failed: provider returned {e.response.status_code}")
    acc.last_synced_at, acc.sync_status, acc.sync_error = started, "connected", None
    db.commit()
    return n


def send_email(db: Session, acc: EmailAccount, to: list[str], subject: str, body: str, cc: list[str] | None = None,
               reply_thread_id: str | None = None) -> None:
    token = access_token(db, acc)
    if acc.provider == "gmail":
        mime = MIMEText(body, "plain", "utf-8")
        mime["To"], mime["Subject"], mime["From"] = ", ".join(to), subject, acc.email_address
        if cc:
            mime["Cc"] = ", ".join(cc)
        payload = {"raw": base64.urlsafe_b64encode(mime.as_bytes()).decode()}
        if reply_thread_id:
            payload["threadId"] = reply_thread_id
        r = httpx.post(f"{GMAIL_API}/messages/send", json=payload, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    else:
        payload = {"message": {"subject": subject, "body": {"contentType": "Text", "content": body},
                               "toRecipients": [{"emailAddress": {"address": a}} for a in to],
                               "ccRecipients": [{"emailAddress": {"address": a}} for a in cc or []]},
                   "saveToSentItems": True}
        r = httpx.post(f"{GRAPH}/sendMail", json=payload, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    if r.status_code >= 300:
        raise HTTPException(502, f"Email provider rejected the message ({r.status_code})")


def visible_accounts_filter(db: Session, current):
    ids = list(db.scalars(select(EmailAccount.id).where(or_(
        EmailAccount.owner_user_id == current.id,
        (EmailAccount.is_shared.is_(True)) & (current.has("email.view_shared"))))))
    if not ids:
        return false()
    return EmailMessage.account_id.in_(ids)


_ = parsedate_to_datetime

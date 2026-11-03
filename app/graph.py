"""Microsoft Graph: device-code OAuth2 auth + sending mail for a Hotmail account.

Why Graph (not SMTP): Microsoft is retiring basic auth for personal accounts.
Why device-code: no redirect server or client secret — the user approves once at
microsoft.com/devicelogin and we keep a refresh token in a local cache file.

Sending uses create-draft-then-send (POST /me/messages, then .../send) rather
than /me/sendMail, because the draft response gives us the conversationId and
internetMessageId we need to thread replies in M4.

Graph REST calls use stdlib urllib (msal already pulls its own HTTP stack; we
keep our calls dependency-explicit).
"""

from __future__ import annotations

import base64
import json
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import quote, urlencode

import msal

from app.config import DATA_DIR

AUTHORITY = "https://login.microsoftonline.com/consumers"  # personal MS accounts
SCOPES = ["Mail.Send", "Mail.Read"]
GRAPH = "https://graph.microsoft.com/v1.0"
CACHE_PATH = DATA_DIR / "graph_token_cache.json"
MAX_ATTACHMENT_BYTES = 3 * 1024 * 1024  # inline attachment limit

# Single-user device-flow state, shared across requests while login is pending.
_flow_lock = threading.Lock()
_flow_state: dict = {"status": "idle", "flow": None, "error": None}


# --- token cache + app -----------------------------------------------------

def _load_cache() -> msal.SerializableTokenCache:
    cache = msal.SerializableTokenCache()
    if CACHE_PATH.exists():
        cache.deserialize(CACHE_PATH.read_text())
    return cache


def _save_cache(cache: msal.SerializableTokenCache) -> None:
    if cache.has_state_changed:
        CACHE_PATH.write_text(cache.serialize())


def _build_app(client_id: str, cache: msal.SerializableTokenCache):
    # instance_discovery=False: we only ever target the public cloud, so skip the
    # network call to the discovery endpoint (keeps cache-only checks offline).
    return msal.PublicClientApplication(
        client_id,
        authority=AUTHORITY,
        token_cache=cache,
        instance_discovery=False,
    )


# --- account / token -------------------------------------------------------

def account_username(client_id: str) -> str | None:
    if not client_id:
        return None
    app = _build_app(client_id, _load_cache())
    accounts = app.get_accounts()
    return accounts[0].get("username") if accounts else None


def is_authenticated(client_id: str) -> bool:
    return account_username(client_id) is not None


def acquire_token(client_id: str) -> str | None:
    if not client_id:
        return None
    cache = _load_cache()
    app = _build_app(client_id, cache)
    accounts = app.get_accounts()
    if not accounts:
        return None
    result = app.acquire_token_silent(SCOPES, account=accounts[0])
    _save_cache(cache)
    return result.get("access_token") if result else None


# --- device-code login -----------------------------------------------------

def start_device_flow(client_id: str) -> dict | None:
    with _flow_lock:
        if _flow_state["status"] == "pending":
            return _flow_state["flow"]
    app = _build_app(client_id, _load_cache())
    flow = app.initiate_device_flow(scopes=SCOPES)
    if "user_code" not in flow:
        with _flow_lock:
            _flow_state.update(
                status="error",
                flow=None,
                error=flow.get("error_description", "Could not start device login."),
            )
        return None
    with _flow_lock:
        _flow_state.update(status="pending", flow=flow, error=None)
    threading.Thread(
        target=_poll_device_flow, args=(client_id, flow), daemon=True
    ).start()
    return flow


def _poll_device_flow(client_id: str, flow: dict) -> None:
    cache = _load_cache()
    app = _build_app(client_id, cache)
    result = app.acquire_token_by_device_flow(flow)  # blocks until done/expired
    with _flow_lock:
        if "access_token" in result:
            _save_cache(cache)
            _flow_state.update(status="done", flow=None, error=None)
        else:
            _flow_state.update(
                status="error",
                flow=None,
                error=result.get("error_description", "Login failed or timed out."),
            )


def device_flow_status() -> dict:
    with _flow_lock:
        return dict(_flow_state)


def logout(client_id: str) -> None:
    if client_id:
        cache = _load_cache()
        app = _build_app(client_id, cache)
        for account in app.get_accounts():
            app.remove_account(account)
        _save_cache(cache)
    with _flow_lock:
        _flow_state.update(status="idle", flow=None, error=None)


# --- sending ---------------------------------------------------------------

@dataclass
class SendResult:
    ok: bool
    conversation_id: str | None = None
    message_id: str | None = None
    internet_message_id: str | None = None
    error: str = ""


def _http_error(exc: urllib.error.HTTPError) -> str:
    try:
        payload = json.loads(exc.read().decode("utf-8"))
        msg = payload.get("error", {}).get("message") or str(payload)
    except Exception:
        msg = str(exc)
    return f"Graph error {exc.code}: {msg}"[:300]


def _graph_request(token: str, method: str, path: str, body: dict | None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        GRAPH + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()
        return resp.status, (json.loads(raw) if raw else {})


def send_email(client_id: str, to: str, subject: str, body: str, attachments):
    """attachments: iterable of (filename, mime_type, raw_bytes)."""
    token = acquire_token(client_id)
    if not token:
        return SendResult(False, error="Not signed in to Microsoft. Connect your account first.")

    graph_attachments = []
    for name, mime, raw in attachments:
        if len(raw) > MAX_ATTACHMENT_BYTES:
            return SendResult(
                False, error=f"Attachment '{name}' is larger than 3 MB; use a smaller file."
            )
        graph_attachments.append(
            {
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": name,
                "contentType": mime,
                "contentBytes": base64.b64encode(raw).decode("ascii"),
            }
        )

    message: dict = {
        "subject": subject,
        "body": {"contentType": "Text", "content": body},
        "toRecipients": [{"emailAddress": {"address": to}}],
    }
    if graph_attachments:
        message["attachments"] = graph_attachments

    try:
        _, created = _graph_request(token, "POST", "/me/messages", message)
    except urllib.error.HTTPError as exc:
        return SendResult(False, error=_http_error(exc))
    except Exception as exc:
        return SendResult(False, error=f"Network error reaching Graph ({type(exc).__name__}).")

    msg_id = created.get("id")
    if not msg_id:
        return SendResult(False, error="Graph did not return a draft message id.")

    try:
        _graph_request(token, "POST", f"/me/messages/{msg_id}/send", None)
    except urllib.error.HTTPError as exc:
        return SendResult(False, error=_http_error(exc))
    except Exception as exc:
        return SendResult(False, error=f"Network error during send ({type(exc).__name__}).")

    return SendResult(
        True,
        conversation_id=created.get("conversationId"),
        message_id=msg_id,
        internet_message_id=created.get("internetMessageId"),
    )


def list_inbox(client_id: str, top: int = 40):
    """Return (messages, error). Messages are recent inbox items (plain preview)."""
    token = acquire_token(client_id)
    if not token:
        return [], "Not signed in to Microsoft."
    params = urlencode(
        {
            "$top": top,
            "$orderby": "receivedDateTime desc",
            "$select": "id,conversationId,subject,from,receivedDateTime,bodyPreview",
        },
        quote_via=quote,
    )
    try:
        _, data = _graph_request(token, "GET", f"/me/mailFolders/inbox/messages?{params}", None)
    except urllib.error.HTTPError as exc:
        return [], _http_error(exc)
    except Exception as exc:
        return [], f"Network error reaching Graph ({type(exc).__name__})."
    return data.get("value", []), None

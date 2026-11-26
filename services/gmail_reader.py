"""Read-only Gmail access for ORBIT: OAuth (desktop loopback + PKCE), inbox fetch, and spam filtering.

Uses only the Python standard library so no extra pip packages are required.

Setup (one time):
    1. Put the Google OAuth "Desktop app" client JSON at secrets/google_client_secret.json
    2. Run:  .venv\\Scripts\\python.exe scripts\\gmail_auth.py
       A browser window opens; sign in and allow read-only access.
       A refresh token is saved to secrets/gmail_token.json (git-ignored).
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import logging
import os
import re
import secrets as _secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime
from email.utils import parseaddr
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger("orbit.gmail")

BASE_DIR = Path(__file__).resolve().parent.parent
SECRETS_DIR = BASE_DIR / "secrets"
CLIENT_SECRET_PATH = Path(
    os.environ.get("ORBIT_GMAIL_CLIENT_SECRET", str(SECRETS_DIR / "google_client_secret.json"))
)
TOKEN_PATH = Path(os.environ.get("ORBIT_GMAIL_TOKEN_PATH", str(SECRETS_DIR / "gmail_token.json")))

SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"
HTTP_TIMEOUT = 10.0
CACHE_SECONDS = 120.0

# Gmail search query: unread inbox mail from the last day, skipping Gmail's own spam/promo/social buckets.
DEFAULT_QUERY = (
    "in:inbox is:unread newer_than:1d "
    "-in:spam -in:trash -category:promotions -category:social -category:forums"
)

_SPAM_LABELS = {"SPAM", "TRASH", "CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL", "CATEGORY_FORUMS"}
_KEEP_LABELS = {"IMPORTANT", "STARRED"}
_BULK_SENDER = re.compile(
    r"(?:no-?reply|do-?not-?reply|newsletter|news|marketing|promo|offers?|deals?|"
    r"mailer|notifications?|digest|campaign|hello|info)@",
    re.IGNORECASE,
)
_SPAMMY_SUBJECT = re.compile(
    r"(?:\b\d{1,2}\s?%\s?off\b|\bsale\b|\bdiscount\b|\bcoupon\b|\bcashback\b|\bdeal(?:s)?\b|"
    r"\blimited[\s-]time\b|\bfree\s+(?:gift|trial|shipping)\b|\bwinner\b|\byou(?:'ve| have)\s+won\b|"
    r"\blottery\b|\bclaim\s+(?:your|now)\b|\bexclusive\s+offer\b|\bunsubscribe\b|\bact\s+now\b|"
    r"\bcongratulations\b|\bspecial\s+offer\b|\bflash\s+sale\b|\bbuy\s+now\b|\bmega\s+sale\b)",
    re.IGNORECASE,
)

_cache_lock = threading.Lock()
_cache: dict[str, Any] = {"at": 0.0, "key": None, "value": None}


class GmailNotConnected(RuntimeError):
    """Raised when Gmail has not been authorized yet."""


# ---------------------------------------------------------------------------
# Config / token storage
# ---------------------------------------------------------------------------

def _load_client_config() -> dict[str, Any]:
    if not CLIENT_SECRET_PATH.is_file():
        raise GmailNotConnected(
            f"Google client secret not found at {CLIENT_SECRET_PATH}. "
            "Download the OAuth Desktop-app JSON from Google Cloud Console and save it there."
        )
    data = json.loads(CLIENT_SECRET_PATH.read_text(encoding="utf-8"))
    cfg = data.get("installed") or data.get("web") or {}
    if not cfg.get("client_id") or not cfg.get("client_secret"):
        raise GmailNotConnected("Google client secret JSON is missing client_id / client_secret.")
    return cfg


def _load_token() -> dict[str, Any] | None:
    if not TOKEN_PATH.is_file():
        return None
    try:
        return json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_token(token: dict[str, Any]) -> None:
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(json.dumps(token, indent=2), encoding="utf-8")


def is_configured() -> bool:
    return CLIENT_SECRET_PATH.is_file()


def is_connected() -> bool:
    token = _load_token()
    return bool(token and token.get("refresh_token"))


def gmail_status() -> dict[str, Any]:
    return {"configured": is_configured(), "connected": is_connected()}


def disconnect() -> bool:
    """Forget the saved Gmail token."""
    try:
        TOKEN_PATH.unlink()
        return True
    except FileNotFoundError:
        return False


# ---------------------------------------------------------------------------
# OAuth (installed-app loopback flow with PKCE)
# ---------------------------------------------------------------------------

def _post_form(url: str, fields: dict[str, str]) -> dict[str, Any]:
    body = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Google token endpoint error {exc.code}: {detail}") from exc


def run_oauth_flow(open_browser: bool = True, timeout_seconds: int = 300) -> dict[str, Any]:
    """Open the Google consent screen, capture the code on localhost, and save a refresh token."""
    cfg = _load_client_config()
    verifier = _secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = _secrets.token_urlsafe(24)
    result: dict[str, str] = {}

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - http.server API
            params = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(self.path).query))
            if "code" in params or "error" in params:
                result.update(params)
                ok = "code" in params and params.get("state") == state
                msg = (
                    "ORBIT is now connected to Gmail (read-only). You can close this tab."
                    if ok
                    else "Gmail authorization failed or was cancelled. You can close this tab."
                )
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(
                    f"<html><body style='font-family:sans-serif;background:#0b0a09;color:#f2efe9;"
                    f"padding:40px'><h2>{html.escape(msg)}</h2></body></html>".encode("utf-8")
                )
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *_args):  # silence default stderr logging
            return

    server = HTTPServer(("127.0.0.1", 0), _Handler)
    redirect_uri = f"http://127.0.0.1:{server.server_port}"
    auth_url = cfg.get("auth_uri", AUTH_URI) + "?" + urllib.parse.urlencode(
        {
            "client_id": cfg["client_id"],
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )

    print("\nOpen this URL to connect ORBIT to Gmail (read-only):\n")
    print(auth_url + "\n")
    if open_browser:
        webbrowser.open(auth_url)

    server.timeout = 1.0
    deadline = time.monotonic() + timeout_seconds
    try:
        while not result and time.monotonic() < deadline:
            server.handle_request()
    finally:
        server.server_close()

    if "error" in result:
        raise RuntimeError(f"Google authorization error: {result['error']}")
    if not result.get("code"):
        raise RuntimeError("Timed out waiting for Google authorization.")
    if result.get("state") != state:
        raise RuntimeError("OAuth state mismatch; please try again.")

    token = _post_form(
        cfg.get("token_uri", TOKEN_URI),
        {
            "code": result["code"],
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "code_verifier": verifier,
        },
    )
    if not token.get("refresh_token"):
        raise RuntimeError("Google did not return a refresh token. Remove ORBIT's access in your Google account and retry.")
    token["expires_at"] = time.time() + float(token.get("expires_in", 3600)) - 60
    _save_token(token)
    return token


def _access_token() -> str:
    token = _load_token()
    if not token or not token.get("refresh_token"):
        raise GmailNotConnected("Gmail is not connected yet.")
    if token.get("access_token") and float(token.get("expires_at", 0)) > time.time():
        return token["access_token"]

    cfg = _load_client_config()
    refreshed = _post_form(
        cfg.get("token_uri", TOKEN_URI),
        {
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "refresh_token": token["refresh_token"],
            "grant_type": "refresh_token",
        },
    )
    token["access_token"] = refreshed["access_token"]
    token["expires_at"] = time.time() + float(refreshed.get("expires_in", 3600)) - 60
    _save_token(token)
    return token["access_token"]


def _api_get(path: str, params: dict[str, Any] | list[tuple[str, str]] | None = None) -> dict[str, Any]:
    query = urllib.parse.urlencode(params or {}, doseq=True)
    url = f"{GMAIL_API}/{path}" + (f"?{query}" if query else "")
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {_access_token()}"})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            # Force a refresh on the next call
            token = _load_token() or {}
            token["expires_at"] = 0
            _save_token(token)
        raise RuntimeError(f"Gmail API error {exc.code}") from exc


# ---------------------------------------------------------------------------
# Spam / bulk-mail filtering
# ---------------------------------------------------------------------------

def _blocked_senders() -> list[str]:
    raw = os.environ.get("ORBIT_GMAIL_BLOCK_SENDERS", "")
    return [s.strip().lower() for s in raw.split(",") if s.strip()]


def spam_reason(email: dict[str, Any]) -> str | None:
    """Return why an email looks like spam/bulk mail, or None if it looks worth reading."""
    labels = set(email.get("labels") or [])
    if labels & {"SPAM", "TRASH"}:
        return "gmail-spam"

    sender = (email.get("from_email") or "").lower()
    for blocked in _blocked_senders():
        if blocked and blocked in sender:
            return "blocked-sender"

    # Starred / Gmail-marked-important mail always gets through
    if labels & _KEEP_LABELS:
        return None

    if labels & _SPAM_LABELS:
        return "gmail-category"
    if (email.get("precedence") or "").lower() in {"bulk", "list", "junk"}:
        return "bulk-precedence"
    subject = email.get("subject") or ""
    if _SPAMMY_SUBJECT.search(subject):
        return "promo-subject"
    if email.get("list_unsubscribe") and _BULK_SENDER.search(sender):
        return "newsletter"
    return None


# ---------------------------------------------------------------------------
# Fetch & summarize
# ---------------------------------------------------------------------------

def _header(headers: list[dict[str, str]], name: str) -> str:
    low = name.lower()
    for h in headers:
        if h.get("name", "").lower() == low:
            return h.get("value", "")
    return ""


def _parse_message(raw: dict[str, Any], tz=None) -> dict[str, Any]:
    payload = raw.get("payload") or {}
    headers = payload.get("headers") or []
    display, addr = parseaddr(_header(headers, "From"))
    received = ""
    try:
        ts = int(raw.get("internalDate", "0")) / 1000.0
        if ts:
            received = datetime.fromtimestamp(ts, tz).strftime("%I:%M %p").lstrip("0")
    except Exception:
        pass
    return {
        "id": raw.get("id"),
        "thread_id": raw.get("threadId"),
        "from_name": display or addr,
        "from_email": addr,
        "subject": _header(headers, "Subject").strip() or "(no subject)",
        "snippet": html.unescape(raw.get("snippet") or "").strip(),
        "labels": raw.get("labelIds") or [],
        "list_unsubscribe": _header(headers, "List-Unsubscribe"),
        "precedence": _header(headers, "Precedence"),
        "received": received,
    }


def fetch_inbox(
    max_results: int = 8,
    query: str | None = None,
    include_read: bool = False,
    use_cache: bool = True,
) -> dict[str, Any]:
    """Fetch recent inbox mail and split it into worth-reading vs. filtered-out spam/bulk."""
    q = query or os.environ.get("ORBIT_GMAIL_QUERY", "").strip() or DEFAULT_QUERY
    if include_read:
        q = q.replace("is:unread", "").strip()
    max_results = max(1, min(int(max_results or 8), 20))
    cache_key = f"{q}|{max_results}"

    if use_cache:
        with _cache_lock:
            if _cache["key"] == cache_key and (time.monotonic() - _cache["at"]) < CACHE_SECONDS:
                return _cache["value"]

    try:
        from memory import LOCAL_TIMEZONE as tz
    except Exception:  # pragma: no cover - defensive
        tz = None

    listing = _api_get("messages", {"q": q, "maxResults": max_results * 3})
    ids = [m["id"] for m in (listing.get("messages") or [])]
    important: list[dict[str, Any]] = []
    filtered: list[dict[str, Any]] = []
    for mid in ids:
        raw = _api_get(
            f"messages/{mid}",
            [
                ("format", "metadata"),
                ("metadataHeaders", "From"),
                ("metadataHeaders", "Subject"),
                ("metadataHeaders", "List-Unsubscribe"),
                ("metadataHeaders", "Precedence"),
            ],
        )
        email = _parse_message(raw, tz)
        reason = spam_reason(email)
        if reason:
            email["filtered_reason"] = reason
            filtered.append(email)
        else:
            important.append(email)
        if len(important) >= max_results:
            break

    result = {
        "emails": important,
        "filtered_count": len(filtered),
        "total_matched": int(listing.get("resultSizeEstimate") or len(ids)),
        "query": q,
    }
    with _cache_lock:
        _cache.update({"at": time.monotonic(), "key": cache_key, "value": result})
    return result


def clear_cache() -> None:
    with _cache_lock:
        _cache.update({"at": 0.0, "key": None, "value": None})


def _shorten(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def format_email_summary(result: dict[str, Any], heading: bool = True) -> str:
    emails = result.get("emails") or []
    filtered = int(result.get("filtered_count") or 0)
    spam_note = f" (skipped {filtered} promo/spam)" if filtered else ""
    if not emails:
        return f"📭 No new important emails{spam_note}."

    lines = [f"📬 **{len(emails)} new email{'s' if len(emails) != 1 else ''} worth a look**{spam_note}:"] if heading else []
    for e in emails:
        star = "⭐ " if "IMPORTANT" in (e.get("labels") or []) or "STARRED" in (e.get("labels") or []) else ""
        when = f" · {e['received']}" if e.get("received") else ""
        lines.append(f"- {star}**{_shorten(e['from_name'], 32)}** — {_shorten(e['subject'], 70)}{when}")
        if e.get("snippet"):
            lines.append(f"  _{_shorten(e['snippet'], 110)}_")
    return "\n".join(lines)


def email_digest_text(max_results: int = 6, include_read: bool = False) -> str:
    """User-facing digest string; never raises (returns setup/failure hints instead)."""
    if not is_configured():
        return (
            "Gmail isn't set up yet — save your Google OAuth client JSON as "
            "`secrets/google_client_secret.json`, then run `python scripts/gmail_auth.py`."
        )
    if not is_connected():
        return "Gmail isn't connected yet — run `python scripts/gmail_auth.py` once to sign in (read-only)."
    try:
        return format_email_summary(fetch_inbox(max_results=max_results, include_read=include_read))
    except GmailNotConnected as exc:
        return str(exc)
    except Exception as exc:
        LOGGER.warning("Gmail fetch failed: %s", exc)
        return "I couldn't reach Gmail right now — I'll try again next time."

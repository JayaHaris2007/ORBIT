"""Tests for read-only Gmail digest: spam filtering, chat routing, morning greeting, and agent tool."""

import app
from agent.tools import ToolContext, validate_and_execute_tool
from services import gmail_reader


def _email(subject, sender="Alice <alice@example.com>", labels=None, unsub="", precedence=""):
    name, _, addr = sender.partition("<")
    return {
        "from_name": name.strip() or addr.rstrip(">"),
        "from_email": addr.rstrip(">") if addr else sender,
        "subject": subject,
        "snippet": "Preview text",
        "labels": labels or ["INBOX", "UNREAD"],
        "list_unsubscribe": unsub,
        "precedence": precedence,
        "received": "9:15 AM",
    }


def test_spam_filter_blocks_promos_and_keeps_real_mail(monkeypatch):
    monkeypatch.setenv("ORBIT_GMAIL_BLOCK_SENDERS", "spammy.biz")

    assert gmail_reader.spam_reason(_email("Interview scheduled for Friday")) is None
    assert gmail_reader.spam_reason(_email("Flash sale: 70% off everything")) == "promo-subject"
    assert gmail_reader.spam_reason(_email("You have won a lottery!")) == "promo-subject"
    assert gmail_reader.spam_reason(_email("Hi", labels=["SPAM"])) == "gmail-spam"
    assert gmail_reader.spam_reason(_email("Weekly", labels=["CATEGORY_PROMOTIONS"])) == "gmail-category"
    assert gmail_reader.spam_reason(_email("Digest", precedence="bulk")) == "bulk-precedence"
    assert (
        gmail_reader.spam_reason(
            _email("This week in tech", sender="News <newsletter@site.com>", unsub="<mailto:x>")
        )
        == "newsletter"
    )
    assert gmail_reader.spam_reason(_email("Hello", sender="Bad <a@spammy.biz>")) == "blocked-sender"
    # Gmail-important / starred mail always passes even if it looks promotional
    assert gmail_reader.spam_reason(_email("50% off your tuition fee", labels=["IMPORTANT"])) is None


def test_format_summary_mentions_skipped_spam():
    text = gmail_reader.format_email_summary(
        {"emails": [_email("Project review at 3 PM", labels=["IMPORTANT"])], "filtered_count": 4}
    )
    assert "1 new email" in text
    assert "skipped 4 promo/spam" in text
    assert "Project review at 3 PM" in text
    assert "⭐" in text

    empty = gmail_reader.format_email_summary({"emails": [], "filtered_count": 2})
    assert "No new important emails" in empty


def test_email_command_when_not_connected_gives_setup_hint():
    reply = app._handle_local_command("check my email", "chat-1")
    assert reply is not None
    text, provider = reply
    assert provider == "local-email"
    assert "gmail_auth.py" in text


def _connect_fake_gmail(monkeypatch, emails, filtered=0):
    calls = {}

    def fake_fetch(max_results=8, query=None, include_read=False, use_cache=True):
        calls["include_read"] = include_read
        return {"emails": emails, "filtered_count": filtered, "total_matched": len(emails), "query": "q"}

    monkeypatch.setattr(gmail_reader, "is_configured", lambda: True)
    monkeypatch.setattr(gmail_reader, "is_connected", lambda: True)
    monkeypatch.setattr(gmail_reader, "fetch_inbox", fake_fetch)
    return calls


def test_email_command_routes_and_ignores_send_requests(monkeypatch):
    calls = _connect_fake_gmail(monkeypatch, [_email("Offer letter from Acme")], filtered=3)

    for phrase in ("check my email", "any new mails?", "read my inbox", "what's in my gmail"):
        text, provider = app._handle_local_command(phrase, "chat-1")
        assert provider == "local-email", phrase
        assert "Offer letter from Acme" in text
        assert "skipped 3" in text

    app._handle_local_command("show all emails today", "chat-1")
    assert calls["include_read"] is True

    # Writing/sending or creating tasks about email must NOT trigger the inbox reader
    chat_id = app.memory_store.create_chat()["id"]
    for phrase in ("send an email to my manager", "add task reply to emails", "remind me to check email at 5pm"):
        res = app._handle_local_command(phrase, chat_id)
        assert res is None or res[1] != "local-email", phrase


def test_good_morning_includes_email_digest_and_day_summary(monkeypatch):
    _connect_fake_gmail(monkeypatch, [_email("Your exam timetable is out", labels=["IMPORTANT"])], filtered=5)
    app.memory_store.create_task("Finish DBMS assignment", priority="high")

    text, provider = app._handle_local_command("good morning buddy", "chat-1")
    assert provider == "local-greeting"
    assert text.startswith("Good morning")
    assert "Your exam timetable is out" in text
    assert "skipped 5 promo/spam" in text
    assert "1** open task" in text

    # A plain "hey" stays a quick greeting with no email fetch
    hey_text, _ = app._handle_local_command("hey", "chat-1")
    assert "exam timetable" not in hey_text


def test_good_morning_without_gmail_still_greets(monkeypatch):
    text, provider = app._handle_local_command("good morning", "chat-1")
    assert provider == "local-greeting"
    assert "gmail" not in text.lower() or "isn't" not in text.lower()


def test_check_email_agent_tool(monkeypatch):
    ctx = ToolContext(deps=app.agent_deps, chat_id="chat-1")
    not_connected = validate_and_execute_tool("check_email", {}, ctx)
    assert not_connected["status"] == "error"

    _connect_fake_gmail(monkeypatch, [_email("Bank OTP 123456", labels=["IMPORTANT"])], filtered=2)
    res = validate_and_execute_tool("check_email", {"max_results": 5}, ctx)
    assert res["status"] == "ok"
    assert res["emails"][0]["subject"] == "Bank OTP 123456"
    assert res["emails"][0]["important"] is True
    assert res["filtered_spam_count"] == 2

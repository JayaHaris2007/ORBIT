"""One-time Gmail sign-in for ORBIT (read-only).

Usage:
    .venv\\Scripts\\python.exe scripts\\gmail_auth.py            # connect / re-connect
    .venv\\Scripts\\python.exe scripts\\gmail_auth.py --test     # show a quick inbox digest
    .venv\\Scripts\\python.exe scripts\\gmail_auth.py --logout   # forget the saved token
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import gmail_reader  # noqa: E402


def main() -> int:
    args = set(sys.argv[1:])
    if "--logout" in args:
        removed = gmail_reader.disconnect()
        print("Gmail token removed." if removed else "No Gmail token was saved.")
        return 0

    if "--test" not in args:
        if not gmail_reader.is_configured():
            print(f"Missing client secret: {gmail_reader.CLIENT_SECRET_PATH}")
            return 1
        try:
            gmail_reader.run_oauth_flow()
        except Exception as exc:
            print(f"\nGmail connection failed: {exc}")
            return 1
        print(f"\n✅ Gmail connected. Token saved to {gmail_reader.TOKEN_PATH}")

    print("\nInbox check:\n")
    print(gmail_reader.email_digest_text(max_results=6))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

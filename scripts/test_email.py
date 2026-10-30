"""
scripts/test_email.py
------------------------
Standalone SMTP test — sends one real test email using whatever's in your
.env, completely independent of the Flask app or the register/forgot-
password flow. Run this FIRST when debugging email, since it gives you
the exact error immediately instead of digging through server logs.

Usage:
    python scripts/test_email.py you@example.com

A successful run means SMTP is genuinely working — if register/forgot-
password still don't email you after this passes, restart the Flask
server (env vars are only read once, at startup — editing .env while
the server is running has no effect until you restart it).
"""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv  # noqa: E402

# Explicit path, matching app.py — removes any ambiguity about which .env
# gets read regardless of the directory this script is run from.
_env_path = os.path.join(PROJECT_ROOT, ".env")
if not os.path.exists(_env_path):
    print(f"❌ No .env file found at {_env_path} — create one (copy .env.example to .env) first.")
    sys.exit(1)
print(f"Reading {_env_path}")

# Catches the single most common real-world mistake: pasting an entire
# ```dotenv ... ``` markdown code block (fences included) straight from a
# chat/README into .env instead of just the KEY=VALUE lines. A stray
# backtick line doesn't crash dotenv, but it silently breaks parsing of
# whatever follows it depending on the parser version, and the resulting
# "not configured" error gives no hint that this was the cause.
with open(_env_path, encoding="utf-8") as _f:
    _raw_lines = _f.readlines()
_fence_lines = [i + 1 for i, line in enumerate(_raw_lines) if line.strip().startswith("```")]
if _fence_lines:
    print(f"⚠️  Found markdown code-fence line(s) (```) at line(s) {_fence_lines} in .env — "
          f"if you pasted an example block that included the ``` lines, delete those two lines "
          f"and keep only the KEY=VALUE lines themselves.")

load_dotenv(_env_path)

import auth  # noqa: E402


def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/test_email.py you@example.com")
        sys.exit(1)

    to_email = sys.argv[1]

    print("Checking configuration...")
    brevo_key = os.getenv("BREVO_API_KEY")
    brevo_sender = os.getenv("BREVO_SENDER_EMAIL")

    if brevo_key and brevo_sender:
        print("   Using Brevo API (takes priority over SMTP when both are set)")
        print(f"   BREVO_API_KEY={'*' * len(brevo_key)} ({len(brevo_key)} characters)")
        print(f"   BREVO_SENDER_EMAIL={brevo_sender}")
        print("   Note: this must be an email you've verified as a sender in your Brevo")
        print("   account (Settings > Senders) — an unverified sender is the most common")
        print("   real send failure with Brevo.")
    else:
        host = os.getenv("SMTP_HOST")
        port = os.getenv("SMTP_PORT")
        user = os.getenv("SMTP_USER")
        password = os.getenv("SMTP_PASSWORD")

        missing = [name for name, val in
                   [("SMTP_HOST", host), ("SMTP_PORT", port), ("SMTP_USER", user), ("SMTP_PASSWORD", password)]
                   if not val]
        if missing:
            print(f"\n❌ Not configured — set either BREVO_API_KEY + BREVO_SENDER_EMAIL, or all of "
                  f"SMTP_HOST/PORT/USER/PASSWORD, in .env.")
            print("   Missing from SMTP option:", ", ".join(missing))
            print("   (Brevo is recommended if you're deploying to Render or a similar host — see")
            print("    .env.example for setup. Most cloud hosts block outbound SMTP on free tiers.)")
            sys.exit(1)

        print(f"   SMTP_HOST={host}")
        print(f"   SMTP_PORT={port}")
        print(f"   SMTP_USER={user}")
        print(f"   SMTP_PASSWORD={'*' * len(password)} ({len(password)} characters"
              f"{', contains spaces' if ' ' in password else ''})")
        if " " in password and len(password.replace(" ", "")) == 16:
            print("   ⚠️  Your password has spaces and is 16 characters without them — this looks like a")
            print("      Gmail App Password copied straight from Google's site with its display spacing")
            print("      (\"xxxx xxxx xxxx xxxx\") kept in. This usually still works, but if the send below")
            print("      fails with an auth error, try removing the spaces in .env and re-running this.")

    print(f"\nSending a test email to {to_email}...")

    result = auth.send_email(
        to_email, "Krushi email test",
        "If you're reading this, your Krushi email configuration is working correctly. "
        "Real emails (welcome message, password reset codes) will now be delivered for real.",
    )

    if result["sent"]:
        print(f"\n✅ Sent successfully — check {to_email}'s inbox (and spam folder).")
        print("   If register/forgot-password in the web app still don't email you, restart the")
        print("   Flask server (or redeploy, if hosted) — env vars are only read once at startup.")
    else:
        print(f"\n❌ Send failed: {result.get('detail', 'unknown error')}")
        if brevo_key and brevo_sender:
            print("   Common causes with Brevo:")
            print("   - BREVO_SENDER_EMAIL isn't verified as a sender in your Brevo account yet")
            print("   - Wrong API key (make sure it's a plain API key, not an SMTP key or MCP")
            print("     server token — those are different credentials)")
            print("   - Over the free tier's 300 emails/day limit")
        else:
            print("   Common causes with SMTP:")
            print("   - Using your normal Gmail password instead of an App Password")
            print("   - 2-Step Verification not turned on for the Gmail account (required before")
            print("     App Passwords can be generated)")
            print("   - Wrong port (587 for STARTTLS, which is what this app uses)")
            print("   - Your host blocking outbound port 587 (common on free tiers of Render and")
            print("     similar platforms — switch to Brevo in that case, see .env.example)")


if __name__ == "__main__":
    main()

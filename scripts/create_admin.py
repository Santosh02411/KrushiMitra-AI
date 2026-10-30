"""
scripts/create_admin.py
------------------------
Creates (or promotes an existing user to) an admin account. This is
deliberately a command-line script, NOT an API endpoint — registration
through the web API always creates a "farmer" role (see app.py), so that
nobody can grant themselves admin access by sending {"role": "admin"} in a
request body. Only someone with direct access to the server/database can
create an admin, by running this script.

Usage:
    python scripts/create_admin.py you@example.com "Your Name" yourpassword

If the email already has an account, it will be promoted to admin instead
of creating a duplicate.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import auth  # noqa: E402


def main():
    if len(sys.argv) != 4:
        print("Usage: python scripts/create_admin.py <email> <name> <password>")
        sys.exit(1)

    email, name, password = sys.argv[1], sys.argv[2], sys.argv[3]
    auth.init_auth_tables()

    conn = auth.get_db()
    existing = conn.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()
    conn.close()

    if existing:
        conn = auth.get_db()
        conn.execute("UPDATE users SET role = 'admin' WHERE id = ?", (existing["id"],))
        conn.commit()
        conn.close()
        print(f"Promoted existing account {email} to admin.")
    else:
        result = auth.register_user(name=name, email=email, password=password, role="admin")
        if result["success"]:
            print(f"Created admin account for {email}.")
        else:
            print(f"Failed: {result['error']}")


if __name__ == "__main__":
    main()

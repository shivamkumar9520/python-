"""
IT Helpdesk & Ticket Management System (Console Edition)
-----------------------------------------------------------
A single-file, menu-driven Python + SQLite command-line app for raising,
tracking, and resolving IT support tickets. No web framework required —
just plain Python and the built-in sqlite3 module.

Roles:
    user  -> raise tickets, view/comment on their own tickets
    admin -> view all tickets, change status/priority, assign an agent

Run:
    python helpdesk.py

First run auto-creates an admin account:
    username: admin   password: admin123   (change this after first login)
"""

import sqlite3
import getpass
import hashlib
import os
from datetime import datetime

DB_FILE = "helpdesk.db"
STATUSES = ["Open", "In Progress", "Resolved", "Closed"]
PRIORITIES = ["Low", "Medium", "High", "Critical"]


# --------------------------------------------------------------- database --
def get_conn():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    first_run = not os.path.exists(DB_FILE)
    conn = get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'General',
            status TEXT NOT NULL DEFAULT 'Open',
            priority TEXT NOT NULL DEFAULT 'Medium',
            created_by INTEGER NOT NULL,
            assigned_to TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (created_by) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            author TEXT NOT NULL,
            body TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (ticket_id) REFERENCES tickets (id) ON DELETE CASCADE
        );
        """
    )
    if first_run:
        conn.execute(
            "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, 'admin', ?)",
            ("admin", hash_password("admin123"), datetime.now().isoformat()),
        )
        print("First run: created default admin account -> admin / admin123 (change this!)\n")
    conn.commit()
    conn.close()


# ----------------------------------------------------------------- helpers --
def hash_password(password: str) -> str:
    """Salted SHA-256 hash. (For production use, prefer bcrypt/argon2.)"""
    salt = "helpdesk_static_salt_v1"  # demo-only static salt; use a per-user random salt in production
    return hashlib.sha256((salt + password).encode()).hexdigest()


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def pause():
    input("\nPress Enter to continue...")


def ask_choice(prompt: str, options: list) -> str:
    print(prompt)
    for i, opt in enumerate(options, 1):
        print(f"  {i}. {opt}")
    while True:
        choice = input(f"Choose (1-{len(options)}): ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            return options[int(choice) - 1]
        print("Invalid choice, try again.")


# -------------------------------------------------------------------- auth --
def register(conn):
    print("\n--- Register ---")
    username = input("Choose a username: ").strip()
    if not username:
        print("Username cannot be empty.")
        return
    if conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
        print("That username is already taken.")
        return
    password = getpass.getpass("Choose a password: ")
    if not password:
        print("Password cannot be empty.")
        return
    conn.execute(
        "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, 'user', ?)",
        (username, hash_password(password), datetime.now().isoformat()),
    )
    conn.commit()
    print(f"Account '{username}' created. You can now log in.")


def login(conn):
    print("\n--- Log in ---")
    username = input("Username: ").strip()
    password = getpass.getpass("Password: ")
    user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if user and user["password_hash"] == hash_password(password):
        print(f"\nWelcome, {user['username']}! ({user['role']})")
        return dict(user)
    print("Invalid username or password.")
    return None


# ------------------------------------------------------------------ tickets --
def raise_ticket(conn, user):
    print("\n--- Raise a New Ticket ---")
    title = input("Title: ").strip()
    description = input("Description: ").strip()
    if not title or not description:
        print("Title and description are required.")
        return
    category = ask_choice("Category:", ["General", "Hardware", "Software", "Network", "Account Access"])
    priority = ask_choice("Priority:", PRIORITIES)
    ts = now_str()
    conn.execute(
        "INSERT INTO tickets (title, description, category, priority, status, created_by, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, 'Open', ?, ?, ?)",
        (title, description, category, priority, user["id"], ts, ts),
    )
    conn.commit()
    print("Ticket raised successfully!")


def list_tickets(conn, user):
    print("\n--- " + ("All Tickets" if user["role"] == "admin" else "My Tickets") + " ---")
    if user["role"] == "admin":
        rows = conn.execute(
            "SELECT t.*, u.username AS raised_by FROM tickets t "
            "JOIN users u ON u.id = t.created_by ORDER BY t.created_at DESC"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT t.*, u.username AS raised_by FROM tickets t "
            "JOIN users u ON u.id = t.created_by WHERE t.created_by = ? ORDER BY t.created_at DESC",
            (user["id"],),
        ).fetchall()

    if not rows:
        print("No tickets found.")
        return []

    print(f"{'ID':<4}{'Title':<28}{'Category':<14}{'Priority':<10}{'Status':<13}{'Assigned':<14}{'By'}")
    print("-" * 95)
    for t in rows:
        print(f"{t['id']:<4}{t['title'][:26]:<28}{t['category']:<14}{t['priority']:<10}"
              f"{t['status']:<13}{(t['assigned_to'] or '-'):<14}{t['raised_by']}")
    return rows


def view_ticket(conn, user):
    rows = list_tickets(conn, user)
    if not rows:
        return
    tid = input("\nEnter ticket ID to open (or blank to cancel): ").strip()
    if not tid.isdigit():
        return
    tid = int(tid)
    ticket = conn.execute(
        "SELECT t.*, u.username AS raised_by FROM tickets t "
        "JOIN users u ON u.id = t.created_by WHERE t.id = ?", (tid,)
    ).fetchone()
    if not ticket:
        print("Ticket not found.")
        return
    if user["role"] != "admin" and ticket["created_by"] != user["id"]:
        print("You can only view your own tickets.")
        return

    print(f"\n#{ticket['id']} — {ticket['title']}")
    print(f"Raised by: {ticket['raised_by']}  |  Category: {ticket['category']}  |  Created: {ticket['created_at']}")
    print(f"Priority: {ticket['priority']}  |  Status: {ticket['status']}  |  Assigned to: {ticket['assigned_to'] or '-'}")
    print(f"\nDescription:\n  {ticket['description']}")

    comments = conn.execute(
        "SELECT * FROM comments WHERE ticket_id = ? ORDER BY created_at", (tid,)
    ).fetchall()
    print(f"\nComments ({len(comments)}):")
    for c in comments:
        print(f"  [{c['created_at']}] {c['author']}: {c['body']}")

    if user["role"] == "admin":
        if input("\nUpdate this ticket? (y/N): ").strip().lower() == "y":
            status = ask_choice("New status:", STATUSES)
            priority = ask_choice("New priority:", PRIORITIES)
            assigned_to = input(f"Assign to (username, current: '{ticket['assigned_to']}'): ").strip()
            conn.execute(
                "UPDATE tickets SET status = ?, priority = ?, assigned_to = ?, updated_at = ? WHERE id = ?",
                (status, priority, assigned_to, now_str(), tid),
            )
            conn.commit()
            print("Ticket updated.")

    if input("\nAdd a comment? (y/N): ").strip().lower() == "y":
        body = input("Comment: ").strip()
        if body:
            conn.execute(
                "INSERT INTO comments (ticket_id, author, body, created_at) VALUES (?, ?, ?, ?)",
                (tid, user["username"], body, now_str()),
            )
            conn.commit()
            print("Comment added.")


def delete_ticket(conn, user):
    rows = list_tickets(conn, user)
    if not rows:
        return
    tid = input("\nEnter ticket ID to delete (or blank to cancel): ").strip()
    if not tid.isdigit():
        return
    tid = int(tid)
    ticket = conn.execute("SELECT * FROM tickets WHERE id = ?", (tid,)).fetchone()
    if not ticket:
        print("Ticket not found.")
        return
    if user["role"] != "admin" and ticket["created_by"] != user["id"]:
        print("You can only delete your own tickets.")
        return
    conn.execute("DELETE FROM tickets WHERE id = ?", (tid,))
    conn.commit()
    print("Ticket deleted.")


def dashboard_counts(conn, user):
    rows = conn.execute("SELECT status FROM tickets") if user["role"] == "admin" else \
        conn.execute("SELECT status FROM tickets WHERE created_by = ?", (user["id"],))
    rows = rows.fetchall()
    counts = {s: sum(1 for r in rows if r["status"] == s) for s in STATUSES}
    print("\n--- Ticket Summary ---")
    for s, n in counts.items():
        print(f"  {s}: {n}")


# -------------------------------------------------------------------- menus --
def user_menu(conn, user):
    while True:
        print(f"\n===== Dashboard: {user['username']} ({user['role']}) =====")
        dashboard_counts(conn, user)
        options = [
            "Raise a new ticket",
            "View / update a ticket",
            "List all my tickets" if user["role"] != "admin" else "List all tickets",
            "Delete a ticket",
            "Log out",
        ]
        choice = ask_choice("\nWhat would you like to do?", options)
        if choice == "Raise a new ticket":
            raise_ticket(conn, user)
        elif choice == "View / update a ticket":
            view_ticket(conn, user)
        elif choice.startswith("List"):
            list_tickets(conn, user)
        elif choice == "Delete a ticket":
            delete_ticket(conn, user)
        elif choice == "Log out":
            print("Logged out.\n")
            break
        pause()


def main_menu():
    init_db()
    conn = get_conn()
    print("=" * 50)
    print("   IT HELPDESK & TICKET MANAGEMENT SYSTEM")
    print("=" * 50)
    while True:
        choice = ask_choice("\nMain Menu:", ["Login", "Register", "Exit"])
        if choice == "Login":
            user = login(conn)
            if user:
                user_menu(conn, user)
        elif choice == "Register":
            register(conn)
        elif choice == "Exit":
            print("Goodbye!")
            break
    conn.close()


if __name__ == "__main__":
    main_menu()
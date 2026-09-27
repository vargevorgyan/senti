"""Create a demo "company server" for the Senti server gateway: shared files + a SQLite database. All data is fake.

Usage: python3 demo/make-server-data.py [DIR]   (default: backend/data) → DIR/server-files/ and DIR/server.db
"""
import json
import sqlite3
import sys
from pathlib import Path

out = Path(sys.argv[1] if len(sys.argv) > 1 else "backend/data")
root = out / "server-files"

customers = [
    (1, "Anna Petrosyan", "anna@example.com", "+374 91 000001", "4111 1111 1111 1111", "Yerevan, Abovyan 1"),
    (2, "Ben Carter", "ben@example.com", "+44 7700 900002", "5500 0000 0000 0004", "London, 2 High St"),
    (3, "Chen Li", "chen@example.com", "+86 10 0000 0003", "3400 0000 0000 009", "Beijing, 3 Road"),
]
tickets = [
    (101, 1, "Printer invoice shows the wrong amount", "open", "2026-09-20"),
    (102, 2, "Cannot log in after password reset", "open", "2026-09-22"),
    (103, 3, "Refund for duplicate order", "pending", "2026-09-24"),
    (104, 1, "Change delivery address", "closed", "2026-09-10"),
]
files = {
    **{f"tickets/{t[0]}.md": f"# Ticket {t[0]}: {t[2]}\nCustomer: {customers[t[1] - 1][1]}\nStatus: {t[3]}\n\nDetails from the customer...\n"
       for t in tickets},
    "tickets/notes/README.md": "Support notes go here, one file per ticket.\n",
    **{f"customers/{c[0]}.json": json.dumps({"id": c[0], "name": c[1], "email": c[2], "phone": c[3]}, indent=2) for c in customers},
    "payments/cards.csv": "customer_id,card_number,expiry\n" + "".join(f"{c[0]},{c[4]},12/29\n" for c in customers),
    "payments/refunds.csv": "ticket,amount,status\n103,49.90,approved\n",
    "hr/salaries.csv": "employee,salary\nGagik,4200\nVarzhan,4100\n",
    "reports/q3-summary.md": "# Q3 summary\nRevenue up 12%. 214 tickets closed. Median response 3h.\n",
    ".env": "STRIPE_SECRET_KEY=sk_live_FAKE_DEMO_ONLY\nDATABASE_URL=postgres://admin:hunter2@db/prod\n",
}
for rel, text in files.items():
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)

db = out / "server.db"
db.unlink(missing_ok=True)
con = sqlite3.connect(db)
con.executescript("""
create table customers(id integer primary key, name text, email text, phone text, card_number text, address text);
create table tickets(id integer primary key, customer_id int, subject text, status text, created text);
create table orders(id integer primary key, customer_id int, total real, created text);
create table employees(id integer primary key, name text, salary int);
""")
con.executemany("insert into customers values (?,?,?,?,?,?)", customers)
con.executemany("insert into tickets values (?,?,?,?,?)", tickets)
con.executemany("insert into orders values (?,?,?,?)", [(1, 1, 49.9, "2026-09-01"), (2, 2, 120.0, "2026-09-03"),
                                                         (3, 3, 49.9, "2026-09-05"), (4, 3, 49.9, "2026-09-05")])
con.executemany("insert into employees values (?,?,?)", [(1, "Gagik", 4200), (2, "Varzhan", 4100)])
con.commit()
con.close()
print(f"Demo server data: {root} and {db}")

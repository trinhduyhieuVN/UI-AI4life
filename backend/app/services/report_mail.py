"""Durable per-recipient deliveries for completed replay sessions."""
import asyncio
from contextlib import closing, suppress
from email.headerregistry import Address
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
import logging
import os
import smtplib
import sqlite3
import ssl
import time

from ..config import ROOT

log = logging.getLogger(__name__)
DATABASE = ROOT / "data" / "report_mail.db"


def settings():
    sender = os.getenv("NEVAI_GMAIL_FROM", "").strip()
    password = os.getenv("NEVAI_GMAIL_APP_PASSWORD", "").replace(" ", "")
    raw = os.getenv("NEVAI_REPORT_RECIPIENTS", "")
    recipients = set()
    for address in raw.split(","):
        if address.strip():
            address = Address(addr_spec=address.strip())
            if not address.domain:
                raise ValueError("Recipient must have a domain")
            recipients.add(address.addr_spec)
    enabled = os.getenv("NEVAI_SEND_REPLAY_REPORTS") == "1"
    return sender, password, sorted(recipients), enabled


def connection():
    db = sqlite3.connect(DATABASE, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("""CREATE TABLE IF NOT EXISTS deliveries (
        day TEXT, recipient TEXT COLLATE NOCASE, subject TEXT, body TEXT, message_id TEXT,
        status TEXT, attempts INTEGER DEFAULT 0, due REAL DEFAULT 0,
        PRIMARY KEY(day, recipient))""")
    return db


def enqueue(report):
    sender, password, recipients, enabled = settings()
    if not (sender and password and recipients and enabled):
        return "preview"
    with closing(connection()) as db, db:
        for address in recipients:
            db.execute("""INSERT OR IGNORE INTO deliveries
                (day,recipient,subject,body,message_id,status) VALUES (?,?,?,?,?,'pending')""",
                (report["day"], address, report["subject"], report["body"], make_msgid()))
    return "queued"


def deliver_one():
    sender, password, recipients, enabled = settings()
    if not (sender and password and recipients and enabled and DATABASE.exists()):
        return False
    with closing(connection()) as db:
        with db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("""SELECT * FROM deliveries WHERE status='pending' AND due<=?
                                ORDER BY due, day LIMIT 1""", (time.time(),)).fetchone()
            if not row:
                return False
            key = (row["day"], row["recipient"])
            if row["recipient"] not in recipients:
                db.execute("UPDATE deliveries SET status='cancelled' WHERE day=? AND recipient=?", key)
                return True
            db.execute("UPDATE deliveries SET status='sending', attempts=attempts+1 WHERE day=? AND recipient=?", key)
        stage = "login"
        status = "sent"
        try:
            message = EmailMessage()
            message["From"], message["To"], message["Subject"] = sender, row["recipient"], row["subject"]
            message["Date"], message["Message-ID"] = formatdate(localtime=False), row["message_id"]
            message.set_content(row["body"])
            smtp = smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=15)
            try:
                smtp.login(sender, password)
                stage = "submit"
                smtp.send_message(message)
            finally:
                with suppress(OSError, smtplib.SMTPException):
                    smtp.quit()
        except smtplib.SMTPRecipientsRefused as error:
            status = "pending" if all(code < 500 for code, _ in error.recipients.values()) else "failed"
        except smtplib.SMTPResponseException as error:
            status = "pending" if error.smtp_code < 500 else "failed"
        except (OSError, smtplib.SMTPException):
            status = "uncertain" if stage == "submit" else "pending"
        except ValueError:
            status = "failed"
        attempts = row["attempts"] + 1
        if status == "pending" and attempts >= 5:
            status = "failed"
        with db:
            db.execute("UPDATE deliveries SET status=?,due=? WHERE day=? AND recipient=?",
                       (status, time.time() + min(1800, 30 * 2**attempts), *key))
        log.info("Session report %s: %s", row["day"], status)
        return True


async def worker():
    while True:
        try:
            if await asyncio.to_thread(deliver_one):
                continue
        except Exception as error:
            log.warning("Report delivery unavailable: %s", type(error).__name__)
        await asyncio.sleep(10)

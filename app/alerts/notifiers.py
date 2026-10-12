"""Notification clients: SMTP Email and Twilio SMS using standard Python libraries."""
import os
import base64
import smtplib
import urllib.parse
import urllib.request
from email.message import EmailMessage
from typing import Protocol
from dotenv import load_dotenv
load_dotenv()


class Notifier(Protocol):
    channel: str
    def send(self, recipient: str, subject: str, body: str) -> None: ...


class SmtpEmailNotifier:
    channel = "email"

    def __init__(self):
        self.host = os.getenv("SMTP_HOST", "localhost")
        self.port = int(os.getenv("SMTP_PORT", "587"))
        self.user = os.getenv("SMTP_USER", "")
        self.password = os.getenv("SMTP_PASSWORD", "")
        self.sender = os.getenv("SMTP_FROM", "alerts@document-assistant.local")

    def send(self, recipient: str, subject: str, body: str) -> None:
        if not self.host or self.host == "localhost":
            print(f"[SMTP SIMULATION] To: {recipient} | Subject: {subject}\n{body}\n")
            return

        import ssl
        msg = EmailMessage()
        msg["From"] = self.sender
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.set_content(body)

        ctx = ssl.create_default_context()
        if self.port == 465:
            with smtplib.SMTP_SSL(self.host, self.port, timeout=15, context=ctx) as s:
                if self.user:
                    s.login(self.user, self.password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(self.host, self.port, timeout=15) as s:
                s.starttls(context=ctx)
                if self.user:
                    s.login(self.user, self.password)
                s.send_message(msg)

    @property
    def configured(self) -> bool:
        return bool(self.host) and self.host != "localhost"


class TwilioSmsNotifier:
    channel = "sms"

    def __init__(self):
        self.sid = os.getenv("TWILIO_ACCOUNT_SID", "")
        self.token = os.getenv("TWILIO_AUTH_TOKEN", "")
        self.sender = os.getenv("TWILIO_FROM", "")

    def send(self, recipient: str, subject: str, body: str) -> None:
        if not self.sid or not self.token:
            print(f"[SMS SIMULATION] To: {recipient} | Message: {subject} - {body[:140]}...\n")
            return

        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.sid}/Messages.json"
        text_payload = f"{subject}\n{body}"[:600]
        data = urllib.parse.urlencode({"To": recipient, "From": self.sender, "Body": text_payload}).encode("utf-8")
        
        req = urllib.request.Request(url, data=data)
        auth_header = base64.b64encode(f"{self.sid}:{self.token}".encode("utf-8")).decode("utf-8")
        req.add_header("Authorization", f"Basic {auth_header}")
        urllib.request.urlopen(req, timeout=15).read()

    @property
    def configured(self) -> bool:
        return bool(self.sid and self.token and self.sender)
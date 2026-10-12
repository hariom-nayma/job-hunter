import os
import smtplib
import asyncio
import mimetypes
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from typing import Tuple, Optional
from pathlib import Path

GMAIL_SMTP_HOST = "smtp.gmail.com"
GMAIL_SMTP_PORT = 587

def _test_credentials_sync(gmail_address: str, app_password: str) -> Tuple[bool, Optional[str]]:
    """Synchronously tests login with Gmail SMTP."""
    try:
        clean_password = app_password.replace(" ", "")
        with smtplib.SMTP(GMAIL_SMTP_HOST, GMAIL_SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(gmail_address, clean_password)
            return True, None
    except smtplib.SMTPAuthenticationError as e:
        return False, "Authentication failed. Check your Gmail address and 16-character Google App Password."
    except Exception as e:
        return False, f"Connection failed: {str(e)}"

async def verify_smtp_credentials(gmail_address: str, app_password: str) -> Tuple[bool, Optional[str]]:
    """Async wrapper to verify Gmail credentials."""
    return await asyncio.to_thread(_test_credentials_sync, gmail_address, app_password)

def _send_email_sync(
    from_address: str,
    app_password: str,
    sender_name: Optional[str],
    to_address: str,
    subject: str,
    body: str,
    resume_path: Optional[str] = None,
    resume_display_name: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """Synchronously connects to Gmail SMTP and sends an email with attachment."""
    try:
        clean_password = app_password.replace(" ", "")
        msg = MIMEMultipart()
        display_from = f"{sender_name} <{from_address}>" if sender_name else from_address
        msg["From"] = display_from
        msg["To"] = to_address
        msg["Subject"] = subject

        # Support HTML or plain text body
        if "<html>" in body.lower() or "<p>" in body.lower() or "<br" in body.lower():
            msg.attach(MIMEText(body, "html", "utf-8"))
        else:
            msg.attach(MIMEText(body, "plain", "utf-8"))

        # Attach resume if provided
        if resume_path and os.path.exists(resume_path):
            file_name = resume_display_name or os.path.basename(resume_path)
            content_type, encoding = mimetypes.guess_type(resume_path)
            if content_type is None or encoding is not None:
                content_type = "application/octet-stream"
            main_type, sub_type = content_type.split("/", 1)

            with open(resume_path, "rb") as f:
                part = MIMEBase(main_type, sub_type)
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f'attachment; filename="{file_name}"'
            )
            msg.attach(part)

        with smtplib.SMTP(GMAIL_SMTP_HOST, GMAIL_SMTP_PORT, timeout=25) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(from_address, clean_password)
            server.send_message(msg)

        return True, None
    except smtplib.SMTPAuthenticationError:
        return False, "Authentication failed. App Password may be invalid."
    except smtplib.SMTPRecipientsRefused:
        return False, f"Recipient email refused: {to_address}"
    except Exception as e:
        return False, str(e)

async def send_email(
    from_address: str,
    app_password: str,
    sender_name: Optional[str],
    to_address: str,
    subject: str,
    body: str,
    resume_path: Optional[str] = None,
    resume_display_name: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """Async wrapper for sending email."""
    return await asyncio.to_thread(
        _send_email_sync,
        from_address,
        app_password,
        sender_name,
        to_address,
        subject,
        body,
        resume_path,
        resume_display_name
    )

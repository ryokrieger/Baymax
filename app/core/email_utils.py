"""
Every email Baymax sends lives here. View files never build or send mail.

Emails are plain text on purpose: they render the same everywhere and need
no inline styling. Each function returns True if the message was handed to
the mail server and False if sending failed (the failure is logged); callers
decide what to tell the person.
"""
import logging

from django.conf import settings
from django.core.mail import EmailMessage

logger = logging.getLogger(__name__)

_SIGNATURE = '\n\n- Baymax\nYour university wellbeing companion'


def _send(subject, body, recipient):
    try:
        EmailMessage(
            subject=subject,
            body=body + _SIGNATURE,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient],
        ).send()
        return True
    except Exception:
        # Never let a mail failure crash a request, and never log the body:
        # it can contain a verification code.
        logger.exception('Could not send "%s" email', subject)
        return False


def send_otp_email(to_email, full_name, code, minutes=10):
    """The six-digit code that verifies a new student's email address."""
    body = (
        f'Hi {full_name},\n\n'
        f'Your Baymax verification code is:\n\n'
        f'    {code}\n\n'
        f'It expires in {minutes} minutes. If you did not try to create a '
        f'Baymax account, you can ignore this email.'
    )
    return _send('Your Baymax verification code', body, to_email)


def send_password_changed_email(to_email, full_name):
    """Security notice after a password change."""
    body = (
        f'Hi {full_name},\n\n'
        f'The password on your Baymax account was just changed.\n\n'
        f'If this was you, there is nothing more to do. If it was not, '
        f'contact your university\'s Admin IT team straight away.'
    )
    return _send('Your Baymax password was changed', body, to_email)
from django.conf import settings
from django.core.mail import send_mail


def send_otp_email(email: str, otp_code: str) -> None:
    """
    Send a registration verification code to a prospective student.
    """
    subject = 'Your Baymax verification code'
    message = (
        f'Your Baymax verification code is: {otp_code}\n\n'
        'This code expires in 10 minutes. If you did not request this, '
        'you can safely ignore this email.'
    )
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [email],
        fail_silently=False,
    )
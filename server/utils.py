from django.core.mail import send_mail
from django.conf import settings
from urllib.parse import urlparse

BLOCKED_DOMAINS = ['gmail.com', 'hotmail.com', 'gmx.de', 'web.de']

def extract_main_domain(email):
    domain = email.split('@')[1].lower()
    parts = domain.split('.')
    if len(parts) >= 2:
        return '.'.join(parts[-2:])
    return domain

def is_blocked_domain(domain):
    return domain.lower() in BLOCKED_DOMAINS


#====================================================================================
#                    E-MAILS
#====================================================================================


def send_company_verification_email(to_email, token):
    link = f"{settings.FRONTEND_URL}/verify-company/{token}/"
    subject = "Bestätige deine Firma auf Slide Components"
    message = f"Klicke auf den folgenden Link, um deine Firma zu bestätigen:\n\n{link}"

    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [to_email])

def send_company_invite_mail(invite, inviter):
    invite_link = f"{settings.FRONTEND_URL}/signup?invite_token={invite.token}"
    send_mail(
        subject="Einladung zu Slide Components",
        message=(
            f"{inviter.email} hat dich eingeladen, dem Team '{invite.company.companyname}' beizutreten.\n\n"
            f"Zum Beitreten bitte diesen Link öffnen:\n\n{invite_link}\n\n"
            f"Falls du keine Einladung erwartest, kannst du diese Mail ignorieren."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[invite.email],
        fail_silently=False
    )
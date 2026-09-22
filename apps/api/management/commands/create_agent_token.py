"""Provision a service user + API token for the agent (idempotent).

Usage:
    python manage.py create_agent_token agent-n8n [--rotate]

Prints the token to stdout exactly once per rotation — store it in the
orchestrator's secret manager (never in code or version control).
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from rest_framework.authtoken.models import Token

User = get_user_model()


class Command(BaseCommand):
    help = "Create (or rotate) the service user and API token for the agent."

    def add_arguments(self, parser):
        parser.add_argument("username", type=str)
        parser.add_argument(
            "--rotate",
            action="store_true",
            help="Delete the existing token and issue a new one.",
        )

    def handle(self, *args, **options):
        username = options["username"]
        user, created = User.objects.get_or_create(
            username=username,
            defaults={"is_staff": True, "is_active": True, "is_superuser": False},
        )
        if created:
            user.set_unusable_password()
            user.save()
            self.stdout.write(f"Service user '{username}' created.")
        else:
            changed = False
            if not user.is_staff or not user.is_active:
                user.is_staff = True
                user.is_active = True
                changed = True
            if user.is_superuser:
                user.is_superuser = False
                changed = True
            if changed:
                user.save()
                self.stdout.write(f"Service user '{username}' normalized.")

        if options["rotate"]:
            Token.objects.filter(user=user).delete()

        token, token_created = Token.objects.get_or_create(user=user)
        if token_created:
            self.stdout.write(f"New token: {token.key}")
        else:
            self.stdout.write(
                "Token already exists (not shown). Use --rotate to issue a new one."
            )

from __future__ import annotations

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create or update the default testing user."

    def add_arguments(self, parser):
        parser.add_argument("--username", default=None)
        parser.add_argument("--password", default=None)

    def handle(self, *args, **options):
        username = options["username"] or os.getenv("DEFAULT_TEST_USERNAME")
        password = options["password"] or os.getenv("DEFAULT_TEST_PASSWORD")

        if not username or not password:
            self.stdout.write(
                self.style.WARNING(
                    "DEFAULT_TEST_USERNAME or DEFAULT_TEST_PASSWORD is missing. "
                    "Skipping default user creation."
                )
            )
            return

        user_model = get_user_model()
        user, created = user_model.objects.get_or_create(username=username)
        user.set_password(password)
        user.is_active = True
        user.save()

        if created:
            self.stdout.write(self.style.SUCCESS(f"Created default user '{username}'"))
        else:
            self.stdout.write(self.style.SUCCESS(f"Updated default user '{username}'"))

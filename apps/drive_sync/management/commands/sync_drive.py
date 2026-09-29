"""Sync products from Google Drive.

    python manage.py sync_drive            # one pass
    python manage.py sync_drive --watch    # keep running (every DRIVE_SYNC_INTERVAL s)
"""
import time

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.drive_sync.services import sync_drive


class Command(BaseCommand):
    help = "Sincroniza fotos do Google Drive com os produtos do site."

    def add_arguments(self, parser):
        parser.add_argument("--watch", action="store_true", help="Executa em loop contínuo.")
        parser.add_argument("--interval", type=int, default=None, help="Segundos entre ciclos.")
        parser.add_argument("--max-runs", type=int, default=None, help=argparse_hidden())

    def handle(self, *args, **options):
        interval = options["interval"] or settings.DRIVE_SYNC_INTERVAL
        runs = 0
        while True:
            try:
                report = sync_drive()
                self.stdout.write(self.style.SUCCESS(f"Sync Drive: {report}"))
                for error in report.errors:
                    self.stderr.write(f"  erro: {error}")
            except Exception as exc:
                if not options["watch"]:
                    raise
                self.stderr.write(f"Falha no ciclo de sync: {exc}")
            runs += 1
            if not options["watch"] or (options["max_runs"] and runs >= options["max_runs"]):
                return
            time.sleep(interval)


def argparse_hidden():
    import argparse

    return argparse.SUPPRESS

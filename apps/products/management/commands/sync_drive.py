from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.products.services.drive_sync import run_drive_sync
from apps.products.services.google_drive import DriveNotConfigured


class Command(BaseCommand):
    help = "Importa categorias e produtos a partir das pastas e fotos do Google Drive."

    def add_arguments(self, parser):
        parser.add_argument("--folder", help="ID ou link da pasta raiz (padrão: GOOGLE_DRIVE_ROOT_FOLDER_ID)")
        parser.add_argument("--no-ai", action="store_true", help="Não gerar descrições com Gemini")
        parser.add_argument("--regenerate", action="store_true", help="Regerar todas as descrições")
        parser.add_argument("--unpublish-missing", action="store_true",
                            help="Despublicar produtos cujas fotos saíram do Drive")

    def handle(self, *args, **opts):
        folder = opts.get("folder") or settings.GOOGLE_DRIVE_ROOT_FOLDER_ID
        if not folder or "API AQUI" in folder:
            raise CommandError("Configure GOOGLE_DRIVE_ROOT_FOLDER_ID no .env ou use --folder.")
        try:
            report = run_drive_sync(
                folder,
                use_ai=not opts["no_ai"],
                regenerate=opts["regenerate"],
                unpublish_missing=opts["unpublish_missing"],
            )
        except DriveNotConfigured as exc:
            raise CommandError(str(exc))
        r = report
        self.stdout.write(self.style.SUCCESS(
            f"Categorias novas: {r.categories_created} | Produtos novos: {r.products_created} | "
            f"Atualizados: {r.products_updated} | Despublicados: {r.products_unpublished} | "
            f"Descrições IA: {r.descriptions_generated}"
        ))
        for s in r.skipped:
            self.stdout.write(self.style.WARNING(f"Ignorado: {s}"))
        for e in r.errors:
            self.stdout.write(self.style.ERROR(f"Erro: {e}"))

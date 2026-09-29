import io
import json
import shutil
from decimal import Decimal
from unittest import mock

import pytest
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from PIL import Image

from apps.audit.models import AuditLog
from apps.drive_sync import describer
from apps.drive_sync.client import FOLDER_MIME, GoogleDriveClient
from apps.drive_sync.parser import detect_line, parse_filename
from apps.drive_sync.services import sync_drive
from apps.products.models import Product


def _png(color="red"):
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), color).save(buf, format="PNG")
    return buf.getvalue()


class FakeDrive:
    """In-memory stand-in for GoogleDriveClient."""

    def __init__(self):
        self.tree = {"root-test": []}
        self.blobs = {}
        self.downloads = []

    def folder(self, parent, fid, name):
        self.tree[parent].append({"id": fid, "name": name, "mimeType": FOLDER_MIME})
        self.tree[fid] = []

    def image(self, parent, fid, name, md5="v1", data=None, mime="image/png"):
        self.tree[parent] = [f for f in self.tree[parent] if f["id"] != fid]
        self.tree[parent].append({"id": fid, "name": name, "mimeType": mime, "md5Checksum": md5})
        self.blobs[fid] = data if data is not None else _png()

    def remove(self, parent, fid):
        self.tree[parent] = [f for f in self.tree[parent] if f["id"] != fid]

    def list_children(self, folder_id):
        return list(self.tree.get(folder_id, []))

    def download(self, file_id):
        self.downloads.append(file_id)
        return self.blobs[file_id]


def fake_describer(parsed, category, data, mime):
    return f"Legenda IA: {parsed.name} ({category})"


@pytest.fixture(autouse=True)
def _media():
    yield
    shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)


@pytest.fixture
def drive():
    d = FakeDrive()
    d.folder("root-test", "f-cam", "Camisetas UV")
    return d


def run(drive):
    return sync_drive(client=drive, describer=fake_describer)


# ---------- parser ----------

class TestParser:
    def test_full_dash_format(self):
        p = parse_filename("Camiseta UV - Azul, Preto - P ao G - 49,90 - 44,90 - 42,90.jpg")
        assert p.name == "Camiseta UV"
        assert p.color == "Azul, Preto"
        assert p.size_range == "P ao G"
        assert p.price == Decimal("49.90")
        assert p.wholesale_price_6 == Decimal("44.90")
        assert p.wholesale_price_24 == Decimal("42.90")

    def test_underscore_format(self):
        p = parse_filename("Vestido_Azul_P-GG_89,90.jpg")
        assert (p.name, p.color, p.size_range, p.price) == ("Vestido", "Azul", "P-GG", Decimal("89.90"))
        assert p.wholesale_price_6 is None and p.wholesale_price_24 is None

    def test_numeric_size_is_not_price(self):
        p = parse_filename("Bermuda - Preta - 38 - 59.jpg")
        assert p.size_range == "38"
        assert p.price == Decimal("59.00")

    def test_name_only(self):
        p = parse_filename("Jaqueta.png")
        assert p.name == "Jaqueta" and p.price is None and p.color == ""

    def test_empty_and_no_extension(self):
        assert parse_filename("   ").name == "Produto"
        assert parse_filename("Bone - R$ 30,00").price == Decimal("30.00")

    def test_detect_line(self):
        assert detect_line("Inverno 2026", "x.jpg") == "inverno"
        assert detect_line("Camisetas", "Blue Line - x.jpg") == "inverno"
        assert detect_line("Camisetas UV", None) == "verao"


# ---------- sync service ----------

@pytest.mark.django_db
class TestSync:
    def test_new_photo_creates_published_product_with_image(self, drive):
        drive.image("f-cam", "a1", "Camiseta UV - Azul - P ao G - 49,90 - 44,90 - 42,90.png")
        report = run(drive)
        assert report.created == 1 and not report.errors
        p = Product.objects.get(drive_file_id="a1")
        assert p.category.name == "Camisetas UV"
        assert p.price == Decimal("49.90")
        assert p.wholesale_price == p.wholesale_price_6 == Decimal("44.90")
        assert p.wholesale_price_24 == Decimal("42.90")
        assert p.is_published is True
        assert p.description == "Legenda IA: Camiseta UV (Camisetas UV)"
        img = p.images.get()
        assert img.is_primary and img.image.name.endswith(".png")
        assert AuditLog.objects.filter(actor_id="drive-sync", action="create").count() == 1

    def test_unchanged_photo_is_skipped(self, drive):
        drive.image("f-cam", "a1", "Camiseta - Azul - P - 10,00.png")
        run(drive)
        report = run(drive)
        assert report.unchanged == 1 and report.updated == 0
        assert drive.downloads == ["a1"]

    def test_rename_updates_data_without_redownload(self, drive):
        drive.image("f-cam", "a1", "Camiseta - Azul - P - 10,00.png")
        run(drive)
        drive.image("f-cam", "a1", "Camiseta Nova - Verde - M - 20,00.png")
        report = run(drive)
        assert report.updated == 1
        p = Product.objects.get(drive_file_id="a1")
        assert (p.name, p.color, p.price) == ("Camiseta Nova", "Verde", Decimal("20.00"))
        assert drive.downloads == ["a1"]
        assert p.images.count() == 1

    def test_replaced_photo_redownloads_and_regenerates_caption(self, drive):
        drive.image("f-cam", "a1", "Camiseta - Azul - P - 10,00.png")
        run(drive)
        calls = []
        drive.image("f-cam", "a1", "Camiseta - Azul - P - 10,00.png", md5="v2", data=_png("blue"))
        sync_drive(client=drive, describer=lambda *a: calls.append(a) or "Nova legenda")
        p = Product.objects.get(drive_file_id="a1")
        assert p.description == "Nova legenda" and len(calls) == 1
        assert p.images.count() == 1
        assert drive.downloads == ["a1", "a1"]

    def test_moving_to_other_folder_changes_category(self, drive):
        drive.folder("root-test", "f-inv", "Inverno")
        drive.image("f-cam", "a1", "Moletom - Cinza - M - 99,90.png")
        run(drive)
        drive.remove("f-cam", "a1")
        drive.image("f-inv", "a1", "Moletom - Cinza - M - 99,90.png")
        run(drive)
        p = Product.objects.get(drive_file_id="a1")
        assert p.category.name == "Inverno" and p.line == "inverno"

    def test_removed_photo_unpublishes_product(self, drive):
        drive.image("f-cam", "a1", "Camiseta - Azul - P - 10,00.png")
        run(drive)
        drive.remove("f-cam", "a1")
        report = run(drive)
        assert report.unpublished == 1
        p = Product.objects.get(drive_file_id="a1")
        assert p.is_published is False and p.is_active is True
        assert AuditLog.objects.filter(action="unpublish").exists()

    def test_photo_without_price_is_created_unpublished(self, drive):
        drive.image("f-cam", "a1", "Camiseta.png")
        run(drive)
        p = Product.objects.get(drive_file_id="a1")
        assert p.price == 0 and p.is_published is False

    def test_root_images_go_to_default_category_and_subfolders_inherit(self, drive):
        drive.image("root-test", "r1", "Bone - Preto - U - 30,00.png")
        drive.folder("f-cam", "f-sub", "Lançamentos")
        drive.image("f-sub", "s1", "Regata - Branca - M - 40,00.png")
        run(drive)
        assert Product.objects.get(drive_file_id="r1").category.name == "Geral"
        assert Product.objects.get(drive_file_id="s1").category.name == "Camisetas UV"

    def test_non_images_are_ignored(self, drive):
        drive.image("f-cam", "d1", "tabela.pdf", mime="application/pdf")
        drive.image("f-cam", "d2", "semextensao", mime="image/png")
        assert run(drive).created == 0

    def test_invalid_or_oversized_image_is_reported_not_fatal(self, drive):
        drive.image("f-cam", "bad", "Quebrada - Azul - P - 10,00.png", data=b"not an image")
        drive.image("f-cam", "big", "Grande - Azul - P - 10,00.png", data=b"0" * (5 * 1024 * 1024 + 1))
        drive.image("f-cam", "ok", "Boa - Azul - P - 10,00.png")
        report = run(drive)
        assert report.created == 1 and len(report.errors) == 2
        assert not Product.objects.filter(drive_file_id__in=["bad", "big"]).exists()

    def test_missing_root_folder_raises(self, drive, settings):
        settings.DRIVE_ROOT_FOLDER_ID = ""
        with pytest.raises(ImproperlyConfigured):
            sync_drive(client=drive, describer=fake_describer)

    def test_report_str(self, drive):
        assert "criados=0" in str(run(drive))


# ---------- management command ----------

@pytest.mark.django_db
class TestCommand:
    def test_single_run(self, drive, capsys):
        drive.image("f-cam", "a1", "Camiseta - Azul - P - 10,00.png")
        drive.image("f-cam", "bad", "X - Azul - P - 10,00.png", data=b"x")
        with mock.patch.object(GoogleDriveClient, "from_settings", return_value=drive), \
             mock.patch("apps.drive_sync.services.generate_description", fake_describer):
            call_command("sync_drive")
        out = capsys.readouterr()
        assert "criados=1" in out.out and "erro" in out.err

    def test_single_run_propagates_errors(self):
        with mock.patch("apps.drive_sync.management.commands.sync_drive.sync_drive",
                        side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError):
                call_command("sync_drive")

    def test_watch_survives_failures(self, capsys):
        with mock.patch("apps.drive_sync.management.commands.sync_drive.sync_drive",
                        side_effect=RuntimeError("boom")), \
             mock.patch("apps.drive_sync.management.commands.sync_drive.time.sleep") as sleep:
            call_command("sync_drive", "--watch", "--interval", "1", "--max-runs", "2")
        assert "boom" in capsys.readouterr().err
        sleep.assert_called_once_with(1)


# ---------- drive client (with a mocked googleapiclient service) ----------

class TestClient:
    def test_list_children_paginates(self):
        service = mock.MagicMock()
        service.files().list().execute.side_effect = [
            {"files": [{"id": "1"}], "nextPageToken": "t"},
            {"files": [{"id": "2"}]},
        ]
        assert [f["id"] for f in GoogleDriveClient(service).list_children("root")] == ["1", "2"]

    def test_download(self):
        service = mock.MagicMock()

        class FakeDownloader:
            def __init__(self, buffer, request):
                self.buffer = buffer

            def next_chunk(self):
                self.buffer.write(b"img")
                return None, True

        with mock.patch("googleapiclient.http.MediaIoBaseDownload", FakeDownloader):
            assert GoogleDriveClient(service).download("x") == b"img"


# ---------- AI describer ----------

class TestDescriber:
    parsed = parse_filename("Camiseta - Azul - P ao G - 49,90 - 44,90 - 42,90.jpg")

    def test_template_when_ai_not_configured(self):
        text = describer.generate_description(self.parsed, "Camisetas", b"x", "image/jpeg")
        assert "Camiseta da categoria Camisetas." in text
        assert "Tamanhos: P ao G." in text and "R$ 42.90" in text

    def test_calls_ai_api(self, settings):
        settings.AI_API_KEY, settings.AI_MODEL = "k", "m"
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(
            {"choices": [{"message": {"content": " Legenda gerada "}}]}
        ).encode()
        with mock.patch("urllib.request.urlopen", return_value=response) as urlopen:
            text = describer.generate_description(self.parsed, "Camisetas", b"x", "image/jpeg")
        assert text == "Legenda gerada"
        req = urlopen.call_args[0][0]
        assert req.full_url.endswith("/chat/completions")
        assert json.loads(req.data)["model"] == "m"

    def test_falls_back_on_ai_error(self, settings):
        settings.AI_API_KEY, settings.AI_MODEL = "k", "m"
        with mock.patch("urllib.request.urlopen", side_effect=OSError("down")):
            text = describer.generate_description(self.parsed, "Camisetas", b"x", "image/jpeg")
        assert text.startswith("Camiseta da categoria")

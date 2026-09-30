from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.test import override_settings

from apps.products.filename_parser import detect_season, normalize, parse_filename
from apps.products.models import Category, Product
from apps.products.services import ai_descriptions, drive_sync, google_drive
from apps.products.services.drive_sync import DriveSync, run_drive_sync
from apps.products.services.google_drive import (
    FOLDER_MIME, DriveCatalogClient, DriveFolder, DriveImage, DriveNotConfigured,
)


# ---------------- nome do arquivo ----------------
@pytest.mark.parametrize("name,expected", [
    ("Jaqueta Puffer, Preto/Vinho, P ao GG, 189.90.jpg",
     ("Jaqueta Puffer", "Preto, Vinho", "P ao GG", "189.90", None, None)),
    ("Camiseta UV, Branco / Azul, P-M-G, R$ 59,90, 49,90, 44,90.png",
     ("Camiseta UV", "Branco, Azul", "P-M-G", "59.90", "49.90", "44.90")),
    ("Legging, Preto e Cinza, 36 ao 44, 79.jpeg",
     ("Legging", "Preto, Cinza", "36 ao 44", "79.00", None, None)),
])
def test_parse_filename(name, expected):
    p = parse_filename(name)
    got = (p.name, p.color, p.size_range, str(p.price),
           p.wholesale_price_6 and str(p.wholesale_price_6),
           p.wholesale_price_24 and str(p.wholesale_price_24))
    assert got == expected
    assert p.is_valid


def test_parse_invalid_and_season():
    assert not parse_filename("foto sem preco.jpg").is_valid
    assert not parse_filename("").is_valid
    assert detect_season("INVERNO 2026") == "inverno"
    assert detect_season("Verão") == "verao"
    assert detect_season("Frio") == "inverno"
    assert detect_season("Calor") == "verao"
    assert detect_season("Outros") is None
    assert normalize("Ção") == "cao"


# ---------------- fakes ----------------
class FakeClient:
    def __init__(self, tree):
        self.tree = tree
        self.downloads = []

    def get_tree(self, folder_id, name=""):
        return self.tree

    def download_bytes(self, file_id):
        self.downloads.append(file_id)
        return b"\x89PNG fake"


class FakeDescriber:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    def describe(self, **kw):
        self.calls.append(kw)
        if self.fail:
            raise RuntimeError("quota")
        return f"Descrição IA de {kw['name']}"


def img(i, name):
    return DriveImage(id=i, name=name, mime_type="image/jpeg")


def sample_tree():
    return DriveFolder(id="root", name="raiz", children=[
        DriveFolder(id="inv", name="Inverno", images=[img("solta", "Solta, Preto, M, 10.jpg")], children=[
            DriveFolder(id="jf", name="Jaquetas Femininas", images=[
                img("f1", "Jaqueta Puffer, Preto/Vinho, P ao GG, 189.90.jpg"),
                img("f2", "sem padrao.jpg"),
            ], children=[
                DriveFolder(id="jfc", name="Couro", images=[img("f3", "Jaqueta Couro, Marrom, M, 299.jpg")]),
            ]),
        ]),
        DriveFolder(id="ver", name="Verão", children=[
            DriveFolder(id="uv", name="Camiseta UV", images=[
                img("f4", "Camiseta UV, Branco/Azul, P ao GG, R$ 59,90, 49,90, 44,90.jpg"),
            ]),
        ]),
        DriveFolder(id="x", name="Arquivo antigo"),
    ])


# ---------------- sincronização ----------------
@pytest.mark.django_db
class TestDriveSync:
    def test_creates_categories_products_and_ai_descriptions(self):
        describer = FakeDescriber()
        client = FakeClient(sample_tree())
        report = run_drive_sync("root", client=client, describer=describer)

        assert report.products_created == 3
        assert report.descriptions_generated == 3
        assert report.categories_created == 3
        jf = Category.objects.get(name="Jaquetas Femininas")
        assert jf.parent is None and jf.line == "inverno"
        couro = Category.objects.get(name="Couro")
        assert couro.parent == jf
        assert Category.objects.get(name="Camiseta UV").line == "verao"

        puffer = Product.objects.get(drive_file_id="f1")
        assert puffer.line == "inverno" and puffer.category == jf
        assert puffer.color == "Preto, Vinho" and puffer.size_range == "P ao GG"
        assert puffer.price == Decimal("189.90") and puffer.is_published
        assert puffer.description == "Descrição IA de Jaqueta Puffer"
        assert "thumbnail?id=f1" in puffer.image_url
        uv = Product.objects.get(drive_file_id="f4")
        assert uv.wholesale_price_6 == Decimal("49.90")
        assert uv.wholesale_price_24 == Decimal("44.90")
        assert any("sem padrao" in s for s in report.skipped)
        assert any("Arquivo antigo" in s for s in report.skipped)
        assert any("soltas" in s for s in report.skipped)
        assert set(client.downloads) == {"f1", "f3", "f4"}

    def test_resync_updates_without_regenerating_and_unpublishes(self):
        run_drive_sync("root", client=FakeClient(sample_tree()), describer=FakeDescriber())
        tree = sample_tree()
        tree.children[1].children[0].images[0].name = "Camiseta UV, Branco, P ao GG, 65.jpg"
        tree.children[0].children[0].children = []  # removeu a foto f3
        describer = FakeDescriber()
        report = run_drive_sync("root", client=FakeClient(tree), describer=describer,
                                unpublish_missing=True)
        assert report.products_created == 0 and report.products_updated == 2
        assert describer.calls == []  # descrição mantida
        assert Product.objects.get(drive_file_id="f4").price == Decimal("65.00")
        assert report.products_unpublished == 1
        assert not Product.objects.get(drive_file_id="f3").is_published

        report = run_drive_sync("root", client=FakeClient(tree), describer=describer, regenerate=True)
        assert report.descriptions_generated == 2

    def test_ai_failure_uses_fallback(self):
        report = run_drive_sync("root", client=FakeClient(sample_tree()), describer=FakeDescriber(fail=True))
        p = Product.objects.get(drive_file_id="f1")
        assert "Jaqueta Puffer da Red Blue Line" in p.description and "Tamanhos: P ao GG" in p.description
        assert len(report.errors) == 3

    def test_without_gemini_key_uses_fallback(self):
        report = run_drive_sync("root", client=FakeClient(sample_tree()))  # GEMINI_API_KEY = "API AQUI"
        assert report.descriptions_generated == 0
        assert Product.objects.get(drive_file_id="f4").description.startswith("Camiseta UV")

    def test_name_clash_between_seasons(self):
        Category.objects.create(name="Camiseta UV", line="inverno")
        run_drive_sync("root", client=FakeClient(sample_tree()), use_ai=False)
        verao = Category.objects.get(name="Camiseta UV (Verão)")
        assert Product.objects.get(drive_file_id="f4").category == verao
        # segunda sincronização reaproveita a mesma categoria
        run_drive_sync("root", client=FakeClient(sample_tree()), use_ai=False)
        assert Category.objects.filter(name__startswith="Camiseta UV").count() == 2

    def test_existing_category_without_line_gets_line(self):
        Category.objects.create(name="Camiseta UV")
        run_drive_sync("root", client=FakeClient(sample_tree()), use_ai=False)
        assert Category.objects.get(name="Camiseta UV").line == "verao"

    def test_product_error_does_not_stop_sync(self, monkeypatch):
        sync = DriveSync(FakeClient(sample_tree()))
        monkeypatch.setattr(sync, "_upsert_product", lambda *a: (_ for _ in ()).throw(ValueError("x")))
        report = sync.run(sample_tree())
        assert len(report.errors) == 3 and report.as_dict()["errors"]


# ---------------- cliente Drive ----------------
class FakeRequest:
    def __init__(self, value):
        self.value = value

    def execute(self):
        return self.value


class FakeFiles:
    def __init__(self):
        self.pages = {
            ("root", None): {"files": [
                {"id": "a", "name": "Verão", "mimeType": FOLDER_MIME},
                {"id": "t", "name": "notas.txt", "mimeType": "text/plain"},
            ], "nextPageToken": "p2"},
            ("root", "p2"): {"files": [{"id": "i0", "name": "b.jpg", "mimeType": "image/jpeg"}]},
            ("a", None): {"files": [{"id": "i1", "name": "x.png", "mimeType": "image/png"}]},
        }

    def list(self, q, pageToken=None, **kw):
        folder = q.split("'")[1]
        return FakeRequest(self.pages.get((folder, pageToken), {"files": []}))

    def get_media(self, fileId, **kw):
        return FakeRequest(b"bytes-" + fileId.encode())


class FakeService:
    def __init__(self):
        self._files = FakeFiles()

    def files(self):
        return self._files


def test_drive_client_tree_and_download():
    client = DriveCatalogClient(service=FakeService())
    tree = client.get_tree("root", "raiz")
    assert [c.name for c in tree.children] == ["Verão"]
    assert [i.name for i in tree.images] == ["b.jpg"]
    assert tree.children[0].images[0].id == "i1"
    assert client.download_bytes("i1") == b"bytes-i1"


def test_drive_not_configured():
    with pytest.raises(DriveNotConfigured):
        google_drive.build_drive_service()


@override_settings(GOOGLE_SERVICE_ACCOUNT_FILE="/tmp/sa.json")
def test_build_drive_service_uses_service_account(monkeypatch):
    from google.oauth2 import service_account
    import googleapiclient.discovery as disc
    seen = {}
    monkeypatch.setattr(service_account.Credentials, "from_service_account_file",
                        classmethod(lambda cls, f, scopes: seen.update(f=f, scopes=scopes) or "creds"))
    monkeypatch.setattr(disc, "build", lambda *a, **kw: ("svc", a, kw["credentials"]))
    svc = google_drive.build_drive_service()
    assert svc == ("svc", ("drive", "v3"), "creds")
    assert seen["scopes"] == ["https://www.googleapis.com/auth/drive.readonly"]


# ---------------- Gemini / LangChain ----------------
class FakeLLM:
    def __init__(self, content):
        self.content = content
        self.messages = None

    def invoke(self, messages):
        self.messages = messages
        return type("R", (), {"content": self.content})()


def test_describer_builds_multimodal_message():
    llm = FakeLLM("  Jaqueta linda.  ")
    text = ai_descriptions.ProductDescriber(llm=llm).describe(
        image_bytes=b"abc", mime_type="image/jpeg", name="Jaqueta", season="inverno",
        category="Jaquetas", color="Preto", sizes="P ao GG")
    assert text == "Jaqueta linda."
    human = llm.messages[1].content
    assert "Inverno / Frio" in human[0]["text"] and "Jaqueta" in human[0]["text"]
    assert human[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_describer_handles_block_content():
    llm = FakeLLM([{"type": "text", "text": "Parte 1."}, "Parte 2."])
    text = ai_descriptions.ProductDescriber(llm=llm).describe(
        image_bytes=b"a", mime_type="image/png", name="X", season="verao", category="", color="", sizes="")
    assert text == "Parte 1. Parte 2."


def test_gemini_not_configured():
    with pytest.raises(ai_descriptions.GeminiNotConfigured):
        ai_descriptions.build_llm()


@override_settings(GEMINI_API_KEY="chave-teste", GEMINI_MODEL="gemini-3.8-flash")
def test_build_llm_with_key():
    llm = ai_descriptions.build_llm()
    assert llm.model.endswith("gemini-3.8-flash")


# ---------------- comando ----------------
@pytest.mark.django_db
@override_settings(GOOGLE_DRIVE_ROOT_FOLDER_ID="API AQUI")
def test_command_requires_folder():
    with pytest.raises(CommandError, match="GOOGLE_DRIVE_ROOT_FOLDER_ID"):
        call_command("sync_drive")


def test_default_folder_is_redblueline():
    from django.conf import settings
    assert settings.GOOGLE_DRIVE_ROOT_FOLDER_ID == "17aVjdXzO65x1LbpCclqJTzhX9zRJnWb0"


@pytest.mark.django_db
def test_command_reports_drive_errors(monkeypatch):
    def boom(*a, **kw):
        raise DriveNotConfigured("sem acesso")
    monkeypatch.setattr("apps.products.management.commands.sync_drive.run_drive_sync", boom)
    with pytest.raises(CommandError, match="sem acesso"):
        call_command("sync_drive", "--folder", "abc", "--no-ai")


@pytest.mark.django_db
def test_command_runs_and_prints_report(monkeypatch):
    monkeypatch.setattr(drive_sync, "get_catalog_client", lambda: FakeClient(sample_tree()))
    out = StringIO()
    call_command("sync_drive", "--folder", "https://drive.google.com/drive/u/3/folders/root", "--no-ai", stdout=out)
    text = out.getvalue()
    assert "Produtos novos: 3" in text and "Ignorado:" in text

    monkeypatch.setattr(drive_sync.DriveSync, "_upsert_product",
                        lambda *a: (_ for _ in ()).throw(ValueError("falhou")))
    out = StringIO()
    call_command("sync_drive", "--folder", "root", "--no-ai", stdout=out)
    assert "Erro:" in out.getvalue()


# ---------------- nomes reais da pasta REDBLUELINE (padrão com hífens) ----------------
@pytest.mark.parametrize("filename,name,color,sizes,price", [
    ("Jaqueta-bomber-faixa-refletiva-punho-na-manga-capuz-removivel-p-m-g-gg-preto-cinza.claro-cinza.escuro-165.00.jpg",
     "Jaqueta bomber faixa refletiva punho na manga capuz removivel", "Preto, Cinza Claro, Cinza Escuro", "P, M, G, GG", "165.00"),
    ("Corta-Vento-Feminino-Impermeável-Filtro-solar-UV-50-p-m-g-gg-azul-branco-off-75.00.jpg",
     "Corta Vento Feminino Impermeável Filtro solar UV 50", "Azul, Branco, Off White", "P, M, G, GG", "75.00"),
    ("camiseta-uv-infantil-azul-amarelo-verdelimao-azulroyal-roxo-amarelo-preto-branco-tamanho-04-ao-16-30.00.jpg",
     "Camiseta uv infantil", "Azul, Amarelo, Verde Limão, Azul Royal, Roxo, Preto, Branco", "04 ao 16", "30.00"),
    ("vestido-indiano-branco-azulmarinho-preto-p-ao-gg-85.00.jpg",
     "Vestido indiano", "Branco, Azul Marinho, Preto", "P ao GG", "85.00"),
    ("Conjunto-plush-infantil-forrado-capuz-removivel--6-8-10-12-14-16-marrom-bege-preto-marinho-180.00.jpg",
     "Conjunto plush infantil forrado capuz removivel", "Marrom, Bege, Preto, Marinho", "6, 8, 10, 12, 14, 16", "180.00"),
    ("jaqueta-bomber-plus-forrada-touca-removivel-G1-G2-G3-G4-preto-rosa-bege-branco-190.00.jpg",
     "Jaqueta bomber plus forrada touca removivel", "Preto, Rosa, Bege, Branco", "G1, G2, G3, G4", "190.00"),
    ("Jaqueta-gominho-forrado-p-m-g-gg-bege,preto,azul-rosa-135.00.jpg",
     "Jaqueta gominho forrado", "Bege, Preto, Azul, Rosa", "P, M, G, GG", "135.00"),
    ("Jaqueta-naylon-forrada-touca-removivel-p-m-g-gg-Somente-na-cor-Rosa-100.00.jpg",
     "Jaqueta naylon forrada touca removivel", "Rosa", "P, M, G, GG", "100.00"),
    ("Jaqueta-gominho-dupla-face-capuz-removivel-forrada-p-m-g-gg-preta-camufrada-185.00.jpg",
     "Jaqueta gominho dupla face capuz removivel forrada", "Preto, Camuflada", "P, M, G, GG", "185.00"),
    ("Jaqueta-bomber-rosa-forrada-capuz-removivel-impermeavel-punho-interno-p-m-g-gg-rosa-100.00.png",
     "Jaqueta bomber rosa forrada capuz removivel impermeavel punho interno", "Rosa", "P, M, G, GG", "100.00"),
    ("camiseta-uv-adulto-feminina-tamanho-azul-branco-p-ao-gg-30.00.jpg",
     "Camiseta uv adulto feminina", "Azul, Branco", "P ao GG", "30.00"),
])
def test_parse_hyphen_filenames(filename, name, color, sizes, price):
    p = parse_filename(filename)
    assert (p.name, p.color, p.size_range, str(p.price)) == (name, color, sizes, price)


def test_parse_hyphen_edge_cases():
    p = parse_filename("bone-preto-azul-25.jpg")  # sem tamanhos
    assert (p.name, p.color, p.size_range, str(p.price)) == ("Bone", "Preto, Azul", "", "25.00")
    p = parse_filename("meia-kit-p-m-listrada-10.jpg")  # cor fora do dicionário
    assert p.color == "Listrada" and p.size_range == "P, M"
    assert not parse_filename("foto-sem-preco.jpg").is_valid
    assert parse_filename("---.jpg").name == ""


def test_sizes_list_to_buttons():
    prod = Product(size_range="P, M, G, GG")
    assert prod.available_sizes() == ["P", "M", "G", "GG"]
    from apps.products.templatetags.size_tags import expand_sizes
    assert expand_sizes("6, 8, 10") == ["6", "8", "10"]


def test_extract_folder_id():
    from apps.products.services.google_drive import extract_folder_id
    url = "https://drive.google.com/drive/u/3/folders/17aVjdXzO65x1LbpCclqJTzhX9zRJnWb0"
    assert extract_folder_id(url) == "17aVjdXzO65x1LbpCclqJTzhX9zRJnWb0"
    assert extract_folder_id("https://drive.google.com/open?id=abc_123") == "abc_123"
    assert extract_folder_id(" xyz ") == "xyz"


# ---------------- leitura da pasta pública ----------------
def _entry(i, title, folder=False):
    href = f"https://drive.google.com/drive/folders/{i}" if folder else f"https://drive.google.com/file/d/{i}/view"
    return (f'<div class="flip-entry" id="entry-{i}" tabindex="0"><div class="flip-entry-info">'
            f'<a href="{href}" target="_blank"><div class="flip-entry-title">{title}</div></a></div></div>')


PAGES = {
    "root": _entry("inv", "INVERNO", True) + _entry("ver", "VER&Atilde;O", True),
    "inv": _entry("jf", "Jaquetas Femininas ", True),
    "jf": _entry("f1", "parka-l&atilde;-batida-p-m-g-gg-preto-bege-190.00.jpg") + _entry("t", "leia.txt"),
    "ver": _entry("uv", "Camisas UV", True),
    "uv": _entry("f2", "camiseta-uv-azul-p-ao-gg-30.00.png"),
}


def fake_fetch(url):
    if "uc?export=download" in url:
        return b"IMG-" + url.rsplit("=", 1)[1].encode()
    return PAGES[url.rsplit("=", 1)[1]].encode()


@pytest.mark.django_db
def test_public_client_full_sync():
    from apps.products.services.google_drive import PublicDriveClient
    client = PublicDriveClient(fetch=fake_fetch)
    tree = client.get_tree("root", "raiz")
    assert [c.name for c in tree.children] == ["INVERNO", "VERÃO"]
    assert tree.children[0].children[0].name == "Jaquetas Femininas"
    assert [i.name for i in tree.children[0].children[0].images] == ["parka-lã-batida-p-m-g-gg-preto-bege-190.00.jpg"]
    assert tree.children[1].children[0].images[0].mime_type == "image/png"
    assert client.download_bytes("f1") == b"IMG-f1"

    report = run_drive_sync("root", client=client, describer=FakeDescriber())
    assert report.products_created == 2 and report.descriptions_generated == 2
    parka = Product.objects.get(drive_file_id="f1")
    assert parka.name == "Parka lã batida" and parka.line == "inverno"
    assert parka.category.name == "Jaquetas Femininas"
    assert Product.objects.get(drive_file_id="f2").line == "verao"


def test_public_client_http_and_depth(monkeypatch):
    from apps.products.services import google_drive as gd
    calls = []

    class Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return PAGES["inv"].encode()

    monkeypatch.setattr(gd.urllib.request, "urlopen", lambda req, timeout: calls.append(req.full_url) or Resp())
    tree = gd.PublicDriveClient().get_tree("inv", "x", max_depth=0)
    assert tree.children == [] and calls == ["https://drive.google.com/embeddedfolderview?id=inv"]


def test_get_catalog_client_fallbacks(monkeypatch):
    from apps.products.services import google_drive as gd
    assert isinstance(gd.get_catalog_client(), gd.PublicDriveClient)
    monkeypatch.setattr(gd, "build_drive_service", lambda: FakeService())
    assert isinstance(gd.get_catalog_client(), gd.DriveCatalogClient)


@override_settings(GOOGLE_API_KEY="chave")
def test_build_drive_service_with_api_key(monkeypatch):
    import googleapiclient.discovery as disc
    monkeypatch.setattr(disc, "build", lambda *a, **kw: ("svc", kw.get("developerKey")))
    assert google_drive.build_drive_service() == ("svc", "chave")


@pytest.mark.django_db
def test_duplicate_photo_names_skipped():
    tree = DriveFolder(id="r", name="raiz", children=[DriveFolder(id="i", name="Inverno", children=[
        DriveFolder(id="c", name="Moletons", images=[
            img("a", "moletom-p-m-preto-150.jpg"), img("b", "moletom-p-m-preto-150.jpg")]),
    ])])
    report = run_drive_sync("r", client=FakeClient(tree), use_ai=False)
    assert report.products_created == 1 and "repetida" in report.skipped[0]

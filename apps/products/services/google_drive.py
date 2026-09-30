"""Leitura do catálogo no Google Drive (somente leitura).

Estrutura de pastas esperada dentro da pasta raiz (GOOGLE_DRIVE_ROOT_FOLDER_ID):

    Raiz/
    ├── Inverno/
    │   ├── Jaquetas Femininas/
    │   │   └── Jaqueta Puffer, Preto/Vinho, P ao GG, 189.90.jpg
    │   └── Moletons/
    └── Verão/
        └── Camiseta UV/
            └── Camiseta UV Manga Longa, Branco/Azul, P ao GG, 59.90.jpg

- Pastas de 1º nível definem a estação (Verão/Inverno).
- Pastas de 2º nível viram categorias (abas); níveis mais fundos viram subcategorias.
- Cada imagem vira um produto; o nome do arquivo traz nome, cor, tamanhos e preço.
"""
from __future__ import annotations

import html
import logging
import re
import urllib.request
from dataclasses import dataclass, field

from django.conf import settings

logger = logging.getLogger("apps.products")

FOLDER_MIME = "application/vnd.google-apps.folder"
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


class DriveNotConfigured(RuntimeError):
    pass


@dataclass
class DriveImage:
    id: str
    name: str
    mime_type: str


@dataclass
class DriveFolder:
    id: str
    name: str
    images: list[DriveImage] = field(default_factory=list)
    children: list["DriveFolder"] = field(default_factory=list)


def public_image_url(file_id: str, width: int = 1000) -> str:
    """URL de exibição da imagem (arquivo precisa estar compartilhado como
    'Qualquer pessoa com o link')."""
    return f"https://drive.google.com/thumbnail?id={file_id}&sz=w{width}"


def _configured(value) -> bool:
    return bool(value) and "API AQUI" not in str(value)


def extract_folder_id(value: str) -> str:
    """Aceita o ID puro ou o link da pasta (https://drive.google.com/.../folders/<id>)."""
    value = (value or "").strip()
    m = re.search(r"/folders/([A-Za-z0-9_-]+)", value) or re.search(r"[?&]id=([A-Za-z0-9_-]+)", value)
    return m.group(1) if m else value


def build_drive_service():
    """Cliente oficial da Drive API: conta de serviço (preferido) ou chave de API
    (suficiente quando a pasta é pública)."""
    from googleapiclient.discovery import build

    creds_file = settings.GOOGLE_SERVICE_ACCOUNT_FILE
    if _configured(creds_file):
        from google.oauth2 import service_account

        credentials = service_account.Credentials.from_service_account_file(
            creds_file, scopes=DRIVE_SCOPES
        )
        return build("drive", "v3", credentials=credentials, cache_discovery=False)
    api_key = settings.GOOGLE_API_KEY
    if _configured(api_key):
        return build("drive", "v3", developerKey=api_key, cache_discovery=False)
    raise DriveNotConfigured(
        "Configure GOOGLE_SERVICE_ACCOUNT_FILE ou GOOGLE_API_KEY no .env."
    )


def get_catalog_client():
    """Escolhe o cliente: API oficial quando há credencial; senão, leitura da
    pasta pública (sem chave)."""
    try:
        return DriveCatalogClient(service=build_drive_service())
    except DriveNotConfigured:
        logger.warning("Drive sem credencial: usando leitura da pasta pública.")
        return PublicDriveClient()


class DriveCatalogClient:
    def __init__(self, service=None):
        self.service = service or build_drive_service()

    def _list_children(self, folder_id: str) -> list[dict]:
        files, page_token = [], None
        while True:
            resp = (
                self.service.files()
                .list(
                    q=f"'{folder_id}' in parents and trashed = false",
                    fields="nextPageToken, files(id, name, mimeType)",
                    pageSize=1000,
                    pageToken=page_token,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                )
                .execute()
            )
            files.extend(resp.get("files", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                return files

    def get_tree(self, folder_id: str, name: str = "", depth: int = 0, max_depth: int = 5) -> DriveFolder:
        folder = DriveFolder(id=folder_id, name=name)
        for f in self._list_children(folder_id):
            mime = f.get("mimeType", "")
            if mime == FOLDER_MIME and depth < max_depth:
                folder.children.append(self.get_tree(f["id"], f["name"].strip(), depth + 1, max_depth))
            elif mime.startswith("image/"):
                folder.images.append(DriveImage(id=f["id"], name=f["name"], mime_type=mime))
        folder.children.sort(key=lambda c: c.name.lower())
        folder.images.sort(key=lambda i: i.name.lower())
        return folder

    def download_bytes(self, file_id: str) -> bytes:
        return self.service.files().get_media(fileId=file_id, supportsAllDrives=True).execute()


class PublicDriveClient:
    """Lê uma pasta compartilhada como "Qualquer pessoa com o link", sem chave.

    Usa a página pública de visualização de pastas do Drive. Não é uma API
    oficial: serve para começar sem configurar nada. Para produção, prefira
    GOOGLE_API_KEY ou a conta de serviço.
    """

    LIST_URL = "https://drive.google.com/embeddedfolderview?id={id}"
    DOWNLOAD_URL = "https://drive.google.com/uc?export=download&id={id}"
    _ENTRY_RE = re.compile(
        r'<div class="flip-entry" id="entry-([A-Za-z0-9_-]+)".*?<a href="([^"]+)".*?'
        r'flip-entry-title">([^<]*)<',
        re.S,
    )
    _IMAGE_EXT = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                  "webp": "image/webp", "gif": "image/gif", "heic": "image/heic"}

    def __init__(self, fetch=None, timeout=30):
        self.timeout = timeout
        self._fetch = fetch or self._http_get

    def _http_get(self, url: str) -> bytes:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 RedBlueLine-Sync"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310 (URL fixa do Drive)
            return resp.read()

    def _list(self, folder_id: str):
        page = self._fetch(self.LIST_URL.format(id=folder_id)).decode("utf-8", "replace")
        for file_id, href, title in self._ENTRY_RE.findall(page):
            yield file_id, html.unescape(title).strip(), "/folders/" in href

    def get_tree(self, folder_id: str, name: str = "", depth: int = 0, max_depth: int = 5) -> DriveFolder:
        folder = DriveFolder(id=folder_id, name=name)
        for file_id, title, is_folder in self._list(folder_id):
            if is_folder:
                if depth < max_depth:
                    folder.children.append(self.get_tree(file_id, title, depth + 1, max_depth))
                continue
            ext = title.rsplit(".", 1)[-1].lower() if "." in title else ""
            if ext in self._IMAGE_EXT:
                folder.images.append(DriveImage(id=file_id, name=title, mime_type=self._IMAGE_EXT[ext]))
        folder.children.sort(key=lambda c: c.name.lower())
        folder.images.sort(key=lambda i: i.name.lower())
        return folder

    def download_bytes(self, file_id: str) -> bytes:
        return self._fetch(self.DOWNLOAD_URL.format(id=file_id))

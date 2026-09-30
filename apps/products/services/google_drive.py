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
from dataclasses import dataclass, field

from django.conf import settings

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


def build_drive_service():
    """Cria o cliente da Drive API a partir da conta de serviço."""
    creds_file = settings.GOOGLE_SERVICE_ACCOUNT_FILE
    if not creds_file or "API AQUI" in creds_file:
        raise DriveNotConfigured(
            "Configure GOOGLE_SERVICE_ACCOUNT_FILE no .env (caminho do JSON da conta de serviço)."
        )
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    credentials = service_account.Credentials.from_service_account_file(
        creds_file, scopes=DRIVE_SCOPES
    )
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


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
                folder.children.append(self.get_tree(f["id"], f["name"], depth + 1, max_depth))
            elif mime.startswith("image/"):
                folder.images.append(DriveImage(id=f["id"], name=f["name"], mime_type=mime))
        folder.children.sort(key=lambda c: c.name.lower())
        folder.images.sort(key=lambda i: i.name.lower())
        return folder

    def download_bytes(self, file_id: str) -> bytes:
        return self.service.files().get_media(fileId=file_id, supportsAllDrives=True).execute()

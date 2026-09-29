"""Thin Google Drive client (service account, read-only)."""
import io
import json

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
FOLDER_MIME = "application/vnd.google-apps.folder"
FILE_FIELDS = "nextPageToken, files(id, name, mimeType, modifiedTime, md5Checksum, size)"


class GoogleDriveClient:
    def __init__(self, service):
        self._service = service

    @classmethod
    def from_settings(cls):  # pragma: no cover - requires real Google credentials
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        if settings.GOOGLE_SERVICE_ACCOUNT_JSON:
            info = json.loads(settings.GOOGLE_SERVICE_ACCOUNT_JSON)
            creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
        elif settings.GOOGLE_SERVICE_ACCOUNT_FILE:
            creds = service_account.Credentials.from_service_account_file(
                settings.GOOGLE_SERVICE_ACCOUNT_FILE, scopes=SCOPES
            )
        else:
            raise ImproperlyConfigured(
                "Defina GOOGLE_SERVICE_ACCOUNT_FILE ou GOOGLE_SERVICE_ACCOUNT_JSON."
            )
        return cls(build("drive", "v3", credentials=creds, cache_discovery=False))

    def list_children(self, folder_id):
        files, token = [], None
        while True:
            response = (
                self._service.files()
                .list(
                    q=f"'{folder_id}' in parents and trashed = false",
                    fields=FILE_FIELDS,
                    pageSize=1000,
                    pageToken=token,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                )
                .execute()
            )
            files.extend(response.get("files", []))
            token = response.get("nextPageToken")
            if not token:
                return files

    def download(self, file_id):
        from googleapiclient.http import MediaIoBaseDownload

        request = self._service.files().get_media(fileId=file_id, supportsAllDrives=True)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return buffer.getvalue()

import json
import os

from qgis.core import QgsBlockingNetworkRequest
from PyQt6.QtNetwork import QNetworkRequest
from PyQt6.QtCore import QUrl, QUrlQuery, QByteArray

BASE_URL = "https://waystones.cloud"


class WaystonesAPIError(Exception):
    pass


class WaystonesAPI:
    def __init__(self, api_key: str, base_url: str = BASE_URL):
        self.base_url = base_url.rstrip("/")
        self._auth = f"Bearer {api_key}".encode()

    def _req(self, path: str, params: dict = None, auth: bool = True) -> QNetworkRequest:
        url = QUrl(f"{self.base_url}{path}")
        if params:
            q = QUrlQuery()
            for k, v in params.items():
                q.addQueryItem(k, str(v))
            url.setQuery(q)
        req = QNetworkRequest(url)
        if auth:
            req.setRawHeader(b"Authorization", self._auth)
        return req

    def _parse_reply(self, blocker: QgsBlockingNetworkRequest, err) -> bytes:
        if err == QgsBlockingNetworkRequest.ErrorCode.NetworkError:
            raise WaystonesAPIError(f"Network error: {blocker.errorMessage()}")
        reply = blocker.reply()
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        content = bytes(reply.content())
        if status is None:
            raise WaystonesAPIError(f"No response: {blocker.errorMessage()}")
        if not (200 <= int(status) < 300):
            try:
                msg = json.loads(content).get("error") or content.decode()
            except Exception:
                msg = content.decode(errors="replace")
            raise WaystonesAPIError(f"HTTP {status}: {msg}")
        return content

    def _json(self, method: str, path: str, params: dict = None, json_body=None):
        req = self._req(path, params=params)
        data = QByteArray()
        if json_body is not None:
            req.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
            data = QByteArray(json.dumps(json_body).encode())

        blocker = QgsBlockingNetworkRequest()
        if method == "GET":
            err = blocker.get(req, forceRefresh=True)
        elif method == "POST":
            err = blocker.post(req, data)
        elif method == "PATCH":
            err = blocker.sendCustomRequest(req, b"PATCH", data)
        elif method == "DELETE":
            err = blocker.deleteResource(req)
        else:
            raise WaystonesAPIError(f"Unsupported method: {method}")

        content = self._parse_reply(blocker, err)
        if content:
            try:
                return json.loads(content)
            except Exception:
                return None
        return None

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------

    def verify_key(self) -> list:
        return self._json("GET", "/api/projects")

    def list_projects(self) -> list:
        return self._json("GET", "/api/projects")

    def get_project(self, project_id: str) -> dict:
        return self._json("GET", f"/api/projects/{project_id}")

    def update_project(self, project_id: str, **fields) -> dict:
        return self._json("PATCH", f"/api/projects/{project_id}", json_body=fields)

    def replace_project_file(self, project_id: str, object_key: str, file_size_bytes: int) -> dict:
        return self._json("POST", f"/api/projects/{project_id}/replace", json_body={
            "objectKey": object_key,
            "fileSizeBytes": file_size_bytes,
        })

    def delete_project(self, project_id: str) -> None:
        self._json("DELETE", f"/api/projects/{project_id}")

    # ------------------------------------------------------------------
    # Project API keys
    # ------------------------------------------------------------------

    def list_project_api_keys(self, project_id: str) -> list:
        return self._json("GET", f"/api/projects/{project_id}/api-keys").get("keys", [])

    def create_project_api_key(self, project_id: str, label: str) -> dict:
        return self._json("POST", f"/api/projects/{project_id}/api-keys", json_body={"label": label})

    def revoke_project_api_key(self, project_id: str, key_id: str) -> None:
        self._json("DELETE", f"/api/projects/{project_id}/api-keys/{key_id}")

    # ------------------------------------------------------------------
    # Deployments
    # ------------------------------------------------------------------

    def delete_deployment(self, deployment_id: str) -> None:
        self._json("DELETE", f"/api/deployments/{deployment_id}")

    def retry_deployment(self, deployment_id: str) -> None:
        self._json("POST", f"/api/deployments/{deployment_id}/retry")

    def remove_deployment_service(self, deployment_id: str, service: str) -> dict:
        return self._json("POST", f"/api/deployments/{deployment_id}/services",
                          json_body={"action": "delete", "service": service})

    def get_deployment(self, deployment_id: str) -> dict:
        return self._json("GET", f"/api/deployments/{deployment_id}")

    def delete_tiles(self, project_id: str) -> None:
        self._json("DELETE", f"/api/projects/{project_id}/tiles")

    def delete_stac(self, project_id: str) -> None:
        self._json("DELETE", f"/api/projects/{project_id}/stac")

    def check_slug(self, slug: str, domain: str = "waystones.cloud") -> dict:
        return self._json("GET", "/api/deployments/check-slug", params={"slug": slug, "domain": domain})

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------

    def get_upload_url(self, filename: str, is_private: bool = False, data_region: str = "default") -> dict:
        return self._json("POST", "/api/upload", json_body={
            "filename": filename,
            "contentType": "application/octet-stream",
            "isPrivate": is_private,
            "dataRegion": data_region,
        })

    def upload_file(self, presigned_url: str, file_path: str, progress_callback=None):
        file_size = os.path.getsize(file_path)
        with open(file_path, "rb") as f:
            data = f.read()

        req = QNetworkRequest(QUrl(presigned_url))
        req.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/octet-stream")

        blocker = QgsBlockingNetworkRequest()
        err = blocker.put(req, QByteArray(data))

        if err == QgsBlockingNetworkRequest.ErrorCode.NetworkError:
            raise WaystonesAPIError(f"Upload failed: {blocker.errorMessage()}")
        reply = blocker.reply()
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        if status and not (200 <= int(status) < 300):
            raise WaystonesAPIError(f"Upload failed: HTTP {status}")

        if progress_callback:
            progress_callback(file_size, file_size)

    # ------------------------------------------------------------------
    # Create project
    # ------------------------------------------------------------------

    def create_project(
        self,
        name: str,
        object_key: str,
        file_size_bytes: int,
        is_private: bool = False,
        data_region: str = "default",
        data_model: dict = None,
        partition_strategy: str = None,
        partition_column: str = None,
    ) -> dict:
        body = {
            "name": name,
            "sourceType": "geopackage",
            "objectKey": object_key,
            "fileSizeBytes": file_size_bytes,
            "isPrivate": is_private,
            "dataRegion": data_region,
        }
        if data_model is not None:
            body["dataModel"] = data_model
        if partition_strategy is not None:
            body["partitionStrategy"] = partition_strategy
        if partition_column is not None:
            body["partitionColumn"] = partition_column
        return self._json("POST", "/api/projects", json_body=body)

    # ------------------------------------------------------------------
    # Deploy
    # ------------------------------------------------------------------

    def deploy(
        self,
        project_id: str,
        slug: str,
        services: list[str],
        mode: str = "on_demand",
        domain: str = "waystones.cloud",
    ) -> dict:
        return self._json("POST", f"/api/projects/{project_id}/deploy", json_body={
            "slug": slug,
            "mode": mode,
            "services": services,
            "domain": domain,
        })

    # ------------------------------------------------------------------
    # Tiles / STAC
    # ------------------------------------------------------------------

    def get_tiles_status(self, project_id: str) -> dict:
        return self._json("GET", f"/api/projects/{project_id}/tiles")

    def get_stac_status(self, project_id: str) -> dict:
        return self._json("GET", f"/api/projects/{project_id}/stac/worker")

    def generate_tiles(
        self,
        project_id: str,
        auto_zoom: bool = True,
        min_zoom: int = 0,
        max_zoom: int = 14,
        simplification: float = None,
        exclude_layers: list[str] = None,
        exclude_attributes: list[str] = None,
    ) -> dict:
        body = {
            "autoZoom": auto_zoom,
            "minZoom": min_zoom,
            "maxZoom": max_zoom,
            "force": True,
        }
        if simplification is not None:
            body["simplification"] = simplification
        if exclude_layers:
            body["excludeLayers"] = exclude_layers
        if exclude_attributes:
            body["excludeAttributes"] = exclude_attributes
        return self._json("POST", f"/api/projects/{project_id}/tiles", json_body=body)

    def generate_stac(
        self,
        project_id: str,
        partition_strategy: str = "none",
        partition_column: str | None = None,
    ) -> dict:
        body: dict = {"partitionStrategy": partition_strategy, "regenerate": True}
        if partition_column:
            body["partitionColumn"] = partition_column
        return self._json("POST", f"/api/projects/{project_id}/stac", json_body=body)

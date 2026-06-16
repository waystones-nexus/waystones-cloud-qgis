import os
import requests

BASE_URL = "https://waystones.cloud"


class WaystonesAPIError(Exception):
    pass


class WaystonesAPI:
    def __init__(self, api_key: str, base_url: str = BASE_URL):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {api_key}"})

    def _raise_for_status(self, resp) -> None:
        if not resp.ok:
            try:
                msg = resp.json().get("error") or resp.text
            except Exception:
                msg = resp.text
            raise WaystonesAPIError(f"HTTP {resp.status_code}: {msg}")

    def _json(self, method: str, path: str, **kwargs):
        kwargs.setdefault("timeout", 15)
        resp = self.session.request(method, f"{self.base_url}{path}", **kwargs)
        self._raise_for_status(resp)
        return resp.json()

    # ------------------------------------------------------------------
    # Step 1: get presigned upload URL
    # ------------------------------------------------------------------
    def verify_key(self) -> list:
        """Returns project list (even empty) to confirm the key is valid. Raises on 401."""
        return self._json("GET", "/api/projects")

    def list_projects(self) -> list:
        return self._json("GET", "/api/projects")

    def get_project(self, project_id: str) -> dict:
        return self._json("GET", f"/api/projects/{project_id}")

    def update_project(self, project_id: str, **fields) -> dict:
        return self._json("PATCH", f"/api/projects/{project_id}", json=fields)

    def replace_project_file(self, project_id: str, object_key: str, file_size_bytes: int) -> dict:
        return self._json("POST", f"/api/projects/{project_id}/replace", json={
            "objectKey": object_key,
            "fileSizeBytes": file_size_bytes,
        })

    def list_project_api_keys(self, project_id: str) -> list:
        return self._json("GET", f"/api/projects/{project_id}/api-keys").get("keys", [])

    def create_project_api_key(self, project_id: str, label: str) -> dict:
        return self._json("POST", f"/api/projects/{project_id}/api-keys", json={"label": label})

    def revoke_project_api_key(self, project_id: str, key_id: str) -> None:
        resp = self.session.request("DELETE", f"{self.base_url}/api/projects/{project_id}/api-keys/{key_id}")
        self._raise_for_status(resp)

    def delete_deployment(self, deployment_id: str) -> None:
        resp = self.session.request("DELETE", f"{self.base_url}/api/deployments/{deployment_id}")
        self._raise_for_status(resp)

    def delete_project(self, project_id: str) -> None:
        resp = self.session.request("DELETE", f"{self.base_url}/api/projects/{project_id}")
        self._raise_for_status(resp)

    def get_upload_url(self, filename: str, is_private: bool = False, data_region: str = "default") -> dict:
        return self._json("POST", "/api/upload", json={
            "filename": filename,
            "contentType": "application/octet-stream",
            "isPrivate": is_private,
            "dataRegion": data_region,
        })

    # ------------------------------------------------------------------
    # Step 2: upload file to R2 via presigned URL
    # ------------------------------------------------------------------
    def upload_file(self, presigned_url: str, file_path: str, progress_callback=None):
        file_size = os.path.getsize(file_path)
        # Read fully before uploading — R2 presigned URLs reject chunked/streaming
        # transfers because they sign an exact Content-Length up front.
        with open(file_path, "rb") as f:
            data = f.read()
        if progress_callback:
            progress_callback(file_size, file_size)
        resp = requests.put(
            presigned_url,
            data=data,
            headers={"Content-Type": "application/octet-stream"},
        )
        if not resp.ok:
            raise WaystonesAPIError(f"Upload failed: HTTP {resp.status_code}")

    # ------------------------------------------------------------------
    # Step 3: create project
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
        return self._json("POST", "/api/projects", json=body)

    # ------------------------------------------------------------------
    # Slug availability check (no side effects)
    # ------------------------------------------------------------------
    def check_slug(self, slug: str, domain: str = "waystones.cloud") -> dict:
        return self._json("GET", "/api/deployments/check-slug", params={"slug": slug, "domain": domain})

    # ------------------------------------------------------------------
    # Step 4: deploy
    # ------------------------------------------------------------------
    def deploy(
        self,
        project_id: str,
        slug: str,
        services: list[str],
        mode: str = "on_demand",
        domain: str = "waystones.cloud",
    ) -> dict:
        return self._json("POST", f"/api/projects/{project_id}/deploy", json={
            "slug": slug,
            "mode": mode,
            "services": services,
            "domain": domain,
        })

    # ------------------------------------------------------------------
    # Step 5: poll deployment status
    # ------------------------------------------------------------------
    def get_deployment(self, deployment_id: str) -> dict:
        return self._json("GET", f"/api/deployments/{deployment_id}")

    # ------------------------------------------------------------------
    # Optional: trigger tiles / STAC generation
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
    ) -> dict:
        body = {
            "autoZoom": auto_zoom,
            "minZoom": min_zoom,
            "maxZoom": max_zoom,
            "force": True,
        }
        if simplification is not None:
            body["simplification"] = simplification
        return self._json("POST", f"/api/projects/{project_id}/tiles", json=body)

    def generate_stac(
        self,
        project_id: str,
        partition_strategy: str = "none",
        partition_column: str | None = None,
    ) -> dict:
        body: dict = {"partitionStrategy": partition_strategy, "regenerate": True}
        if partition_column:
            body["partitionColumn"] = partition_column
        return self._json("POST", f"/api/projects/{project_id}/stac", json=body)

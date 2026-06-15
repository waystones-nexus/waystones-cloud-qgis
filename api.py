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

    def _json(self, method: str, path: str, **kwargs):
        resp = self.session.request(method, f"{self.base_url}{path}", **kwargs)
        if not resp.ok:
            try:
                msg = resp.json().get("error") or resp.text
            except Exception:
                msg = resp.text
            raise WaystonesAPIError(f"HTTP {resp.status_code}: {msg}")
        return resp.json()

    # ------------------------------------------------------------------
    # Step 1: get presigned upload URL
    # ------------------------------------------------------------------
    def get_upload_url(self, filename: str, is_private: bool = False, data_region: str = "default") -> dict:
        return self._json("POST", "/api/upload", json={
            "filename": filename,
            "contentType": "application/octet-stream",
            "isPrivate": is_private,
            "dataRegion": data_region,
        })

    # ------------------------------------------------------------------
    # Step 2: upload file to R2 via presigned URL (streaming, with progress)
    # ------------------------------------------------------------------
    def upload_file(self, presigned_url: str, file_path: str, progress_callback=None):
        file_size = os.path.getsize(file_path)
        uploaded = 0

        def _read_chunks(f, chunk_size=1024 * 256):
            nonlocal uploaded
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                uploaded += len(chunk)
                if progress_callback:
                    progress_callback(uploaded, file_size)
                yield chunk

        with open(file_path, "rb") as f:
            resp = requests.put(
                presigned_url,
                data=_read_chunks(f),
                headers={"Content-Type": "application/octet-stream", "Content-Length": str(file_size)},
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
    ) -> dict:
        return self._json("POST", "/api/projects", json={
            "name": name,
            "sourceType": "geopackage",
            "objectKey": object_key,
            "fileSizeBytes": file_size_bytes,
            "isPrivate": is_private,
            "dataRegion": data_region,
        })

    # ------------------------------------------------------------------
    # Step 4: deploy
    # ------------------------------------------------------------------
    def deploy(
        self,
        project_id: str,
        slug: str,
        services: list[str],
        mode: str = "on_demand",
    ) -> dict:
        return self._json("POST", f"/api/projects/{project_id}/deploy", json={
            "slug": slug,
            "mode": mode,
            "services": services,
        })

    # ------------------------------------------------------------------
    # Step 5: poll deployment status
    # ------------------------------------------------------------------
    def get_deployment(self, deployment_id: str) -> dict:
        return self._json("GET", f"/api/deployments/{deployment_id}")

    # ------------------------------------------------------------------
    # Optional: trigger tiles / STAC generation
    # ------------------------------------------------------------------
    def generate_tiles(self, project_id: str) -> dict:
        return self._json("POST", f"/api/projects/{project_id}/tiles/generate", json={})

    def generate_stac(self, project_id: str) -> dict:
        return self._json("POST", f"/api/projects/{project_id}/stac/worker", json={})

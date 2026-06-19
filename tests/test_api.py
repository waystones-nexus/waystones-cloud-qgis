"""Tests for WaystonesAPI — all network calls are mocked."""
import json
import os
import sys
import tempfile
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PATCH_TARGET = "api.QgsBlockingNetworkRequest"


@contextmanager
def mock_response(status: int, body=None, network_error: bool = False):
    """Context manager that patches QgsBlockingNetworkRequest with a fake response."""
    with patch(_PATCH_TARGET) as MockClass:
        instance = MagicMock()
        MockClass.return_value = instance

        if network_error:
            err = MockClass.ErrorCode.NetworkError
        else:
            err = MagicMock()  # any object that != NetworkError

        for method in ("get", "post", "put", "deleteResource", "sendCustomRequest"):
            getattr(instance, method).return_value = err

        mock_reply = MagicMock()
        mock_reply.attribute.return_value = status
        body_bytes = json.dumps(body).encode() if body is not None else b""
        mock_reply.content.return_value = body_bytes
        instance.reply.return_value = mock_reply

        yield MockClass, instance


def make_api(base_url="https://waystones.cloud"):
    from api import WaystonesAPI
    return WaystonesAPI("test-key", base_url=base_url)


def _called_url(instance):
    """Return the URL string from the first call to get/post/put/delete/sendCustomRequest."""
    for method_name in ("get", "post", "put", "deleteResource", "sendCustomRequest"):
        m = getattr(instance, method_name)
        if m.called:
            req_arg = m.call_args[0][0]
            return req_arg.url().toString()
    return None


def _called_body(instance):
    """Return the decoded JSON body bytes from the first POST/PATCH/PUT call."""
    for method_name in ("post", "sendCustomRequest"):
        m = getattr(instance, method_name)
        if m.called:
            args = m.call_args[0]
            # post(req, data) → args[1]; sendCustomRequest(req, verb, data) → args[2]
            data_arg = args[2] if method_name == "sendCustomRequest" else args[1]
            raw = bytes(data_arg)
            return json.loads(raw) if raw else None
    return None


# ---------------------------------------------------------------------------
# _parse_reply error paths
# ---------------------------------------------------------------------------

class TestParseReply:
    def test_network_error_raises(self):
        from api import WaystonesAPIError
        with mock_response(0, network_error=True):
            api = make_api()
            with pytest.raises(WaystonesAPIError, match="Network error"):
                api.list_projects()

    def test_none_status_raises(self):
        from api import WaystonesAPIError
        with patch(_PATCH_TARGET) as MockClass:
            instance = MagicMock()
            MockClass.return_value = instance
            # err != NetworkError
            instance.get.return_value = MagicMock()
            mock_reply = MagicMock()
            mock_reply.attribute.return_value = None  # no HTTP status
            mock_reply.content.return_value = b""
            instance.reply.return_value = mock_reply

            api = make_api()
            with pytest.raises(WaystonesAPIError, match="No response"):
                api.list_projects()

    def test_4xx_with_json_error_field_raises(self):
        from api import WaystonesAPIError
        with mock_response(404, {"error": "Not found"}) as (_, _inst):
            api = make_api()
            with pytest.raises(WaystonesAPIError, match="HTTP 404: Not found"):
                api.get_project("xyz")

    def test_4xx_with_non_json_body_raises(self):
        from api import WaystonesAPIError
        with patch(_PATCH_TARGET) as MockClass:
            instance = MagicMock()
            MockClass.return_value = instance
            instance.get.return_value = MagicMock()
            mock_reply = MagicMock()
            mock_reply.attribute.return_value = 500
            mock_reply.content.return_value = b"Internal Server Error"
            instance.reply.return_value = mock_reply

            api = make_api()
            with pytest.raises(WaystonesAPIError, match="HTTP 500"):
                api.list_projects()

    def test_2xx_with_json_body_returns_dict(self):
        with mock_response(200, {"id": "abc"}):
            api = make_api()
            result = api.get_project("abc")
            assert result == {"id": "abc"}

    def test_2xx_empty_body_returns_none(self):
        with mock_response(204, None):
            api = make_api()
            result = api.delete_project("abc")
            assert result is None


# ---------------------------------------------------------------------------
# HTTP method dispatch
# ---------------------------------------------------------------------------

class TestHttpMethodDispatch:
    def test_get_calls_blocker_get(self):
        with mock_response(200, []) as (_, inst):
            make_api().list_projects()
            assert inst.get.called

    def test_post_calls_blocker_post(self):
        with mock_response(200, {"id": "x"}) as (_, inst):
            make_api().create_project_api_key("p1", "my-key")
            assert inst.post.called

    def test_patch_calls_send_custom_request_with_verb(self):
        with mock_response(200, {}) as (_, inst):
            make_api().update_project("p1", name="x")
            assert inst.sendCustomRequest.called
            verb = inst.sendCustomRequest.call_args[0][1]
            assert verb == b"PATCH"

    def test_delete_calls_blocker_delete_resource(self):
        with mock_response(204, None) as (_, inst):
            make_api().delete_project("p1")
            assert inst.deleteResource.called


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

class TestProjects:
    def test_list_projects_get_path(self):
        with mock_response(200, []) as (_, inst):
            make_api().list_projects()
            url = _called_url(inst)
            assert url.endswith("/api/projects")

    def test_verify_key_same_as_list(self):
        with mock_response(200, [{"id": "1"}]) as (_, _inst):
            result = make_api().verify_key()
            assert result == [{"id": "1"}]

    def test_get_project_path(self):
        with mock_response(200, {"id": "abc"}) as (_, inst):
            make_api().get_project("abc")
            assert "/api/projects/abc" in _called_url(inst)

    def test_update_project_patch_with_fields(self):
        with mock_response(200, {}) as (_, inst):
            make_api().update_project("p1", name="New Name")
            body = _called_body(inst)
            assert body == {"name": "New Name"}

    def test_delete_project_path(self):
        with mock_response(204, None) as (_, inst):
            make_api().delete_project("p1")
            url = _called_url(inst)
            assert url.endswith("/api/projects/p1")

    def test_replace_project_file_body(self):
        with mock_response(200, {}) as (_, inst):
            make_api().replace_project_file("p1", "uploads/file.gpkg", 12345)
            body = _called_body(inst)
            assert body["objectKey"] == "uploads/file.gpkg"
            assert body["fileSizeBytes"] == 12345

    def test_create_project_required_fields(self):
        with mock_response(200, {"id": "new"}) as (_, inst):
            make_api().create_project("My Project", "key/file.gpkg", 9999)
            body = _called_body(inst)
            assert body["name"] == "My Project"
            assert body["objectKey"] == "key/file.gpkg"
            assert body["fileSizeBytes"] == 9999
            assert body["sourceType"] == "geopackage"
            assert "dataModel" not in body
            assert "partitionStrategy" not in body
            assert "partitionColumn" not in body

    def test_create_project_optional_fields_included_when_set(self):
        with mock_response(200, {"id": "new"}) as (_, inst):
            make_api().create_project(
                "P", "key.gpkg", 1,
                data_model={"layers": []},
                partition_strategy="custom_column",
                partition_column="region",
            )
            body = _called_body(inst)
            assert body["dataModel"] == {"layers": []}
            assert body["partitionStrategy"] == "custom_column"
            assert body["partitionColumn"] == "region"


# ---------------------------------------------------------------------------
# Project API keys
# ---------------------------------------------------------------------------

class TestProjectApiKeys:
    def test_list_returns_keys_list(self):
        with mock_response(200, {"keys": [{"id": "k1"}, {"id": "k2"}]}):
            result = make_api().list_project_api_keys("p1")
            assert result == [{"id": "k1"}, {"id": "k2"}]

    def test_list_returns_empty_list_when_key_missing(self):
        with mock_response(200, {}):
            result = make_api().list_project_api_keys("p1")
            assert result == []

    def test_create_key_body(self):
        with mock_response(200, {"id": "new-key"}) as (_, inst):
            make_api().create_project_api_key("p1", "ci-key")
            body = _called_body(inst)
            assert body == {"label": "ci-key"}
            assert "/api/projects/p1/api-keys" in _called_url(inst)

    def test_revoke_key_path(self):
        with mock_response(204, None) as (_, inst):
            make_api().revoke_project_api_key("p1", "k99")
            url = _called_url(inst)
            assert url.endswith("/api/projects/p1/api-keys/k99")


# ---------------------------------------------------------------------------
# Deployments
# ---------------------------------------------------------------------------

class TestDeployments:
    def test_get_deployment_path(self):
        with mock_response(200, {"status": "ready"}) as (_, inst):
            make_api().get_deployment("dep1")
            assert "/api/deployments/dep1" in _called_url(inst)

    def test_delete_deployment_path(self):
        with mock_response(204, None) as (_, inst):
            make_api().delete_deployment("dep1")
            assert "/api/deployments/dep1" in _called_url(inst)

    def test_retry_deployment_path(self):
        with mock_response(200, {}) as (_, inst):
            make_api().retry_deployment("dep1")
            assert "/api/deployments/dep1/retry" in _called_url(inst)

    def test_remove_deployment_service_body(self):
        with mock_response(200, {}) as (_, inst):
            make_api().remove_deployment_service("dep1", "tiles")
            body = _called_body(inst)
            assert body == {"action": "delete", "service": "tiles"}

    def test_deploy_body(self):
        with mock_response(200, {"deploymentId": "d1"}) as (_, inst):
            make_api().deploy("p1", "my-slug", ["oapif"], mode="on_demand", domain="waystones.cloud")
            body = _called_body(inst)
            assert body["slug"] == "my-slug"
            assert body["services"] == ["oapif"]
            assert body["mode"] == "on_demand"
            assert body["domain"] == "waystones.cloud"

    def test_delete_tiles_path(self):
        with mock_response(204, None) as (_, inst):
            make_api().delete_tiles("p1")
            assert "/api/projects/p1/tiles" in _called_url(inst)

    def test_delete_stac_path(self):
        with mock_response(204, None) as (_, inst):
            make_api().delete_stac("p1")
            assert "/api/projects/p1/stac" in _called_url(inst)


# ---------------------------------------------------------------------------
# Slug check
# ---------------------------------------------------------------------------

class TestCheckSlug:
    def test_check_slug_sends_query_params(self):
        with mock_response(200, {"available": True}) as (_, inst):
            make_api().check_slug("my-dataset", "waystones.cloud")
            url = _called_url(inst)
            assert "slug=my-dataset" in url
            assert "domain=waystones.cloud" in url


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

class TestUpload:
    def test_get_upload_url_body(self):
        with mock_response(200, {"presignedUrl": "https://s3/url", "objectKey": "abc"}) as (_, inst):
            make_api().get_upload_url("test.gpkg", is_private=True, data_region="eu")
            body = _called_body(inst)
            assert body["filename"] == "test.gpkg"
            assert body["contentType"] == "application/octet-stream"
            assert body["isPrivate"] is True
            assert body["dataRegion"] == "eu"

    def test_upload_file_puts_to_presigned_url(self):
        with mock_response(200, None) as (MockClass, inst):
            # We need the PUT method on the instance
            inst.put.return_value = MagicMock()  # != NetworkError

            with tempfile.NamedTemporaryFile(delete=False, suffix=".gpkg") as f:
                f.write(b"fake gpkg data")
                tmp_path = f.name
            try:
                make_api().upload_file("https://s3.example.com/presigned", tmp_path)
                assert inst.put.called
            finally:
                os.unlink(tmp_path)

    def test_upload_file_raises_on_network_error(self):
        from api import WaystonesAPIError
        with patch(_PATCH_TARGET) as MockClass:
            instance = MagicMock()
            MockClass.return_value = instance
            instance.put.return_value = MockClass.ErrorCode.NetworkError

            with tempfile.NamedTemporaryFile(delete=False, suffix=".gpkg") as f:
                f.write(b"data")
                tmp_path = f.name
            try:
                api = make_api()
                with pytest.raises(WaystonesAPIError, match="Upload failed"):
                    api.upload_file("https://s3/url", tmp_path)
            finally:
                os.unlink(tmp_path)

    def test_upload_file_raises_on_non_2xx(self):
        from api import WaystonesAPIError
        with patch(_PATCH_TARGET) as MockClass:
            instance = MagicMock()
            MockClass.return_value = instance
            ok_err = MagicMock()
            instance.put.return_value = ok_err
            mock_reply = MagicMock()
            mock_reply.attribute.return_value = 403
            instance.reply.return_value = mock_reply

            with tempfile.NamedTemporaryFile(delete=False, suffix=".gpkg") as f:
                f.write(b"data")
                tmp_path = f.name
            try:
                api = make_api()
                with pytest.raises(WaystonesAPIError, match="HTTP 403"):
                    api.upload_file("https://s3/url", tmp_path)
            finally:
                os.unlink(tmp_path)

    def test_upload_file_calls_progress_callback(self):
        with patch(_PATCH_TARGET) as MockClass:
            instance = MagicMock()
            MockClass.return_value = instance
            instance.put.return_value = MagicMock()
            mock_reply = MagicMock()
            mock_reply.attribute.return_value = 200
            instance.reply.return_value = mock_reply

            progress_calls = []
            with tempfile.NamedTemporaryFile(delete=False, suffix=".gpkg") as f:
                f.write(b"hello")
                tmp_path = f.name
            try:
                make_api().upload_file("https://s3/url", tmp_path,
                                       progress_callback=lambda d, t: progress_calls.append((d, t)))
                assert len(progress_calls) == 1
                done, total = progress_calls[0]
                assert done == total == 5
            finally:
                os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# Tiles / STAC
# ---------------------------------------------------------------------------

class TestTilesStac:
    def test_get_tiles_status_path(self):
        with mock_response(200, {"status": "ready"}) as (_, inst):
            make_api().get_tiles_status("p1")
            assert "/api/projects/p1/tiles" in _called_url(inst)

    def test_get_stac_status_path(self):
        with mock_response(200, {}) as (_, inst):
            make_api().get_stac_status("p1")
            assert "/api/projects/p1/stac/worker" in _called_url(inst)

    def test_generate_tiles_default_body(self):
        with mock_response(200, {}) as (_, inst):
            make_api().generate_tiles("p1")
            body = _called_body(inst)
            assert body["autoZoom"] is True
            assert body["force"] is True
            assert "simplification" not in body
            assert "excludeLayers" not in body
            assert "excludeAttributes" not in body

    def test_generate_tiles_with_optional_params(self):
        with mock_response(200, {}) as (_, inst):
            make_api().generate_tiles(
                "p1",
                auto_zoom=False,
                min_zoom=3,
                max_zoom=10,
                simplification=0.5,
                exclude_layers=["building"],
                exclude_attributes=["name"],
            )
            body = _called_body(inst)
            assert body["autoZoom"] is False
            assert body["minZoom"] == 3
            assert body["maxZoom"] == 10
            assert body["simplification"] == 0.5
            assert body["excludeLayers"] == ["building"]
            assert body["excludeAttributes"] == ["name"]

    def test_generate_stac_default_body(self):
        with mock_response(200, {}) as (_, inst):
            make_api().generate_stac("p1")
            body = _called_body(inst)
            assert body["partitionStrategy"] == "none"
            assert body["regenerate"] is True
            assert "partitionColumn" not in body

    def test_generate_stac_with_partition_column(self):
        with mock_response(200, {}) as (_, inst):
            make_api().generate_stac("p1", partition_strategy="custom_column", partition_column="region")
            body = _called_body(inst)
            assert body["partitionColumn"] == "region"

"""Tests for pure-Python helpers in dialog_utils.py — no QGIS required."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from unittest.mock import MagicMock  # noqa: E402

from dialog_utils import table_name, gpkg_table_name, field_base_type, is_valid_url  # noqa: E402


# ---------------------------------------------------------------------------
# table_name
# ---------------------------------------------------------------------------

class TestTableName:
    def test_lowercases_and_replaces_spaces(self):
        assert table_name("My Layer") == "my_layer"

    def test_replaces_hyphens_and_dots(self):
        assert table_name("roads-2024.shp") == "roads_2024_shp"

    def test_strips_leading_trailing_underscores(self):
        assert table_name("__roads__") == "roads"

    def test_truncates_at_63_chars(self):
        long_name = "a" * 80
        result = table_name(long_name)
        assert len(result) == 63

    def test_all_punctuation_becomes_empty(self):
        assert table_name("---") == ""

    def test_mixed_unicode_non_alnum_replaced(self):
        assert table_name("café réseau") == "caf_r_seau"


# ---------------------------------------------------------------------------
# gpkg_table_name
# ---------------------------------------------------------------------------

class TestGpkgTableName:
    def _layer(self, source, name="fallback"):
        m = MagicMock()
        m.source.return_value = source
        m.name.return_value = name
        return m

    def test_extracts_layername_from_gpkg_source(self):
        layer = self._layer("/data/file.gpkg|layername=roads")
        assert gpkg_table_name(layer) == "roads"

    def test_extracts_layername_ignores_trailing_pipe_segments(self):
        layer = self._layer("/data/file.gpkg|layername=parcels|subset=fid>0")
        assert gpkg_table_name(layer) == "parcels"

    def test_falls_back_to_table_name_when_no_layername(self):
        layer = self._layer("/data/file.geojson", name="My Roads")
        assert gpkg_table_name(layer) == "my_roads"

    def test_falls_back_for_postgis_source(self):
        layer = self._layer("host=localhost dbname=gis table=admin_units", name="Admin Units")
        assert gpkg_table_name(layer) == "admin_units"


# ---------------------------------------------------------------------------
# field_base_type
# ---------------------------------------------------------------------------

class TestFieldBaseType:
    def _field(self, type_name):
        m = MagicMock()
        m.typeName.return_value = type_name
        return m

    def test_integer(self):
        assert field_base_type(self._field("Integer")) == "integer"

    def test_int4(self):
        assert field_base_type(self._field("int4")) == "integer"

    def test_serial(self):
        assert field_base_type(self._field("serial")) == "integer"

    def test_bigint(self):
        assert field_base_type(self._field("bigint")) == "integer"

    def test_float8(self):
        assert field_base_type(self._field("float8")) == "number"

    def test_double_precision(self):
        assert field_base_type(self._field("double precision")) == "number"

    def test_numeric(self):
        assert field_base_type(self._field("numeric")) == "number"

    def test_decimal(self):
        assert field_base_type(self._field("decimal")) == "number"

    def test_real(self):
        assert field_base_type(self._field("real")) == "number"

    def test_boolean(self):
        assert field_base_type(self._field("bool")) == "boolean"

    def test_boolean_long(self):
        assert field_base_type(self._field("boolean")) == "boolean"

    def test_timestamp(self):
        assert field_base_type(self._field("timestamp")) == "date-time"

    def test_datetime(self):
        assert field_base_type(self._field("datetime")) == "date-time"

    def test_date_only(self):
        # "date" must not match "date-time" path; timestamp/datetime checked first
        assert field_base_type(self._field("date")) == "date"

    def test_varchar(self):
        assert field_base_type(self._field("varchar")) == "string"

    def test_text(self):
        assert field_base_type(self._field("text")) == "string"

    def test_unknown_defaults_to_string(self):
        assert field_base_type(self._field("geometry")) == "string"


# ---------------------------------------------------------------------------
# is_valid_url
# ---------------------------------------------------------------------------

class TestIsValidUrl:
    def test_https(self):
        assert is_valid_url("https://example.com") is True

    def test_http_with_path_and_query(self):
        assert is_valid_url("http://foo.bar/path?q=1") is True

    def test_ftp_rejected(self):
        assert is_valid_url("ftp://example.com") is False

    def test_plain_string_rejected(self):
        assert is_valid_url("not-a-url") is False

    def test_empty_string_rejected(self):
        assert is_valid_url("") is False

    def test_scheme_only_rejected(self):
        assert is_valid_url("https://") is False

    def test_no_scheme_rejected(self):
        assert is_valid_url("example.com") is False

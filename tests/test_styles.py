"""Tests for renderer_to_layer_style() — requires a running QgsApplication (pytest-qgis)."""
import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


@pytest.fixture(scope="module", autouse=True)
def _ensure_qgis(qgis_app):
    """Ensure the QGIS app fixture is running for this module."""
    pass


from qgis.core import (  # noqa: E402
    Qgis,
    QgsSingleSymbolRenderer, QgsCategorizedSymbolRenderer,
    QgsSimpleMarkerSymbolLayer, QgsSimpleLineSymbolLayer,
    QgsSimpleFillSymbolLayer, QgsLinePatternFillSymbolLayer,
    QgsVectorLayerSimpleLabeling,
)
from style_utils import renderer_to_layer_style, DEFAULT_COLOR, _MM_TO_PX, _PT_TO_PX  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers to build mock layers / renderers
# ---------------------------------------------------------------------------

def _sym(color="#ff0000", opacity=1.0, symbol_layers=None):
    """Build a mock symbol."""
    s = MagicMock()
    s.color.return_value.name.return_value = color
    s.opacity.return_value = opacity
    sls = symbol_layers or []
    s.symbolLayerCount.return_value = len(sls)
    s.symbolLayer.side_effect = lambda i: sls[i]
    return s


def _layer(renderer=None, labeling=None):
    lyr = MagicMock()
    lyr.renderer.return_value = renderer
    lyr.labeling.return_value = labeling
    return lyr


def _marker_sl(size=4.0, shape_name="circle",
               size_unit=Qgis.RenderUnit.Millimeters):
    sl = MagicMock(spec=QgsSimpleMarkerSymbolLayer)
    sl.size.return_value = size
    sl.sizeUnit.return_value = size_unit
    sl.shape.return_value.name.lower.return_value = shape_name
    return sl


def _line_sl(width=1.0, pen_name="solidline",
             width_unit=Qgis.RenderUnit.Millimeters):
    sl = MagicMock(spec=QgsSimpleLineSymbolLayer)
    sl.width.return_value = width
    sl.widthUnit.return_value = width_unit
    sl.penStyle.return_value.name.lower.return_value = pen_name
    return sl


def _fill_sl(opacity=1.0, stroke_name="solidline", stroke_width=0.5, brush_name="solid",
             stroke_width_unit=Qgis.RenderUnit.Millimeters):
    sl = MagicMock(spec=QgsSimpleFillSymbolLayer)
    sl.strokeStyle.return_value.name.lower.return_value = stroke_name
    sl.strokeWidth.return_value = stroke_width
    sl.strokeWidthUnit.return_value = stroke_width_unit
    sl.brushStyle.return_value.name.lower.return_value = brush_name
    return sl


def _line_pattern_sl(distance=10.0, angle=0.0,
                     distance_unit=Qgis.RenderUnit.Millimeters):
    sl = MagicMock(spec=QgsLinePatternFillSymbolLayer)
    sl.distance.return_value = distance
    sl.distanceUnit.return_value = distance_unit
    sl.lineAngle.return_value = angle
    return sl


def _single_renderer(symbol):
    r = MagicMock(spec=QgsSingleSymbolRenderer)
    r.symbol.return_value = symbol
    return r


def _categorized_renderer(attribute, categories):
    """categories = list of (value, symbol)"""
    r = MagicMock(spec=QgsCategorizedSymbolRenderer)
    r.classAttribute.return_value = attribute
    cats = []
    for val, sym in categories:
        cat = MagicMock()
        cat.value.return_value = val
        cat.symbol.return_value = sym
        cats.append(cat)
    r.categories.return_value = cats
    return r


# ---------------------------------------------------------------------------
# No renderer
# ---------------------------------------------------------------------------

class TestNoRenderer:
    def test_none_renderer_returns_default(self):
        result = renderer_to_layer_style(_layer(renderer=None))
        assert result == {"type": "simple", "simpleColor": DEFAULT_COLOR}


# ---------------------------------------------------------------------------
# Single symbol — marker
# ---------------------------------------------------------------------------

class TestSingleMarker:
    def test_circle_shape(self):
        sl = _marker_sl(size=4.0, shape_name="circle")
        lyr = _layer(_single_renderer(_sym("#aabbcc", 0.8, [sl])))
        result = renderer_to_layer_style(lyr)
        assert result["type"] == "simple"
        assert result["simpleColor"] == "#aabbcc"
        assert result["pointIcon"] == "circle"
        assert result["pointSize"] == pytest.approx(4.0 * _MM_TO_PX / 2, rel=1e-3)
        assert result["pointOpacity"] == 0.8

    def test_square_shape(self):
        sl = _marker_sl(shape_name="square")
        lyr = _layer(_single_renderer(_sym(symbol_layers=[sl])))
        assert renderer_to_layer_style(lyr)["pointIcon"] == "square"

    def test_rectangle_shape(self):
        sl = _marker_sl(shape_name="rectangle")
        lyr = _layer(_single_renderer(_sym(symbol_layers=[sl])))
        assert renderer_to_layer_style(lyr)["pointIcon"] == "square"

    def test_triangle_shape(self):
        sl = _marker_sl(shape_name="triangle")
        lyr = _layer(_single_renderer(_sym(symbol_layers=[sl])))
        assert renderer_to_layer_style(lyr)["pointIcon"] == "triangle"

    def test_star_shape(self):
        sl = _marker_sl(shape_name="regularstar")
        lyr = _layer(_single_renderer(_sym(symbol_layers=[sl])))
        assert renderer_to_layer_style(lyr)["pointIcon"] == "star"

    def test_unknown_shape_defaults_to_circle(self):
        sl = _marker_sl(shape_name="cross")
        lyr = _layer(_single_renderer(_sym(symbol_layers=[sl])))
        assert renderer_to_layer_style(lyr)["pointIcon"] == "circle"


# ---------------------------------------------------------------------------
# Single symbol — line
# ---------------------------------------------------------------------------

class TestSingleLine:
    def test_solid_line(self):
        sl = _line_sl(width=2.0, pen_name="solidline")
        lyr = _layer(_single_renderer(_sym("#112233", 1.0, [sl])))
        result = renderer_to_layer_style(lyr)
        assert result["lineDash"] == "solid"
        assert result["lineWidth"] == pytest.approx(2.0 * _MM_TO_PX, rel=1e-3)
        assert result["lineOpacity"] == 1.0

    def test_dashed_line(self):
        sl = _line_sl(pen_name="dashline")
        lyr = _layer(_single_renderer(_sym(symbol_layers=[sl])))
        assert renderer_to_layer_style(lyr)["lineDash"] == "dashed"

    def test_dotted_line(self):
        sl = _line_sl(pen_name="dotline")
        lyr = _layer(_single_renderer(_sym(symbol_layers=[sl])))
        assert renderer_to_layer_style(lyr)["lineDash"] == "dotted"

    def test_unknown_pen_defaults_to_solid(self):
        sl = _line_sl(pen_name="custompenstyle")
        lyr = _layer(_single_renderer(_sym(symbol_layers=[sl])))
        assert renderer_to_layer_style(lyr)["lineDash"] == "solid"


# ---------------------------------------------------------------------------
# Single symbol — fill
# ---------------------------------------------------------------------------

class TestSingleFill:
    def test_solid_fill_with_outline(self):
        sl = _fill_sl(stroke_name="solidline", stroke_width=0.5, brush_name="solid")
        lyr = _layer(_single_renderer(_sym("#223344", 0.9, [sl])))
        result = renderer_to_layer_style(lyr)
        assert result["fillOpacity"] == 0.9
        assert result["showOutline"] is True
        assert result["lineWidth"] == pytest.approx(0.5 * _MM_TO_PX, rel=1e-3)
        assert result["lineDash"] == "solid"
        assert "hatchStyle" not in result

    def test_fill_no_outline_when_nopen(self):
        sl = _fill_sl(stroke_name="nopen")
        lyr = _layer(_single_renderer(_sym(symbol_layers=[sl])))
        result = renderer_to_layer_style(lyr)
        assert result["showOutline"] is False

    def test_horizontal_hatch(self):
        sl = _fill_sl(brush_name="horpattern")
        lyr = _layer(_single_renderer(_sym(symbol_layers=[sl])))
        assert renderer_to_layer_style(lyr)["hatchStyle"] == "horizontal"

    def test_diagonal_hatch(self):
        sl = _fill_sl(brush_name="bdiagpattern")
        lyr = _layer(_single_renderer(_sym(symbol_layers=[sl])))
        assert renderer_to_layer_style(lyr)["hatchStyle"] == "b_diagonal"

    def test_solid_brush_no_hatch_style(self):
        sl = _fill_sl(brush_name="solid")
        lyr = _layer(_single_renderer(_sym(symbol_layers=[sl])))
        assert "hatchStyle" not in renderer_to_layer_style(lyr)


# ---------------------------------------------------------------------------
# Single symbol — line pattern fill
# ---------------------------------------------------------------------------

class TestLinePatternFill:
    def test_horizontal_angle_0(self):
        sl = _line_pattern_sl(distance=8.0, angle=0.0)
        lyr = _layer(_single_renderer(_sym(symbol_layers=[sl])))
        result = renderer_to_layer_style(lyr)
        assert result["hatchStyle"] == "horizontal"
        assert result["hatchSpacing"] == pytest.approx(8.0 * _MM_TO_PX, rel=1e-3)

    def test_vertical_angle_90(self):
        sl = _line_pattern_sl(angle=90.0)
        lyr = _layer(_single_renderer(_sym(symbol_layers=[sl])))
        assert renderer_to_layer_style(lyr)["hatchStyle"] == "vertical"

    def test_b_diagonal_angle_45(self):
        sl = _line_pattern_sl(angle=45.0)
        lyr = _layer(_single_renderer(_sym(symbol_layers=[sl])))
        assert renderer_to_layer_style(lyr)["hatchStyle"] == "b_diagonal"

    def test_f_diagonal_angle_135(self):
        sl = _line_pattern_sl(angle=135.0)
        lyr = _layer(_single_renderer(_sym(symbol_layers=[sl])))
        assert renderer_to_layer_style(lyr)["hatchStyle"] == "f_diagonal"

    def test_angle_mod_180(self):
        # 270 % 180 = 90 → vertical
        sl = _line_pattern_sl(angle=270.0)
        lyr = _layer(_single_renderer(_sym(symbol_layers=[sl])))
        assert renderer_to_layer_style(lyr)["hatchStyle"] == "vertical"


# ---------------------------------------------------------------------------
# Categorized renderer
# ---------------------------------------------------------------------------

class TestCategorized:
    def test_type_and_property_id(self):
        renderer = _categorized_renderer("landuse", [("park", _sym("#00ff00")), ("road", _sym("#888888"))])
        result = renderer_to_layer_style(_layer(renderer))
        assert result["type"] == "categorized"
        assert result["propertyId"] == "landuse"

    def test_categorized_values_collected(self):
        renderer = _categorized_renderer("type", [("a", _sym()), ("b", _sym())])
        result = renderer_to_layer_style(_layer(renderer))
        assert set(result["categorizedValues"]) == {"a", "b"}

    def test_empty_value_category_excluded_from_values(self):
        renderer = _categorized_renderer("type", [
            ("", _sym("#fallback")),
            ("road", _sym("#112233")),
        ])
        result = renderer_to_layer_style(_layer(renderer))
        assert "" not in result["categorizedValues"]
        assert "road" in result["categorizedValues"]

    def test_empty_value_updates_fallback_color(self):
        renderer = _categorized_renderer("type", [("", _sym("#aabbcc")), ("x", _sym())])
        result = renderer_to_layer_style(_layer(renderer))
        assert result["simpleColor"] == "#aabbcc"

    def test_each_category_has_color(self):
        renderer = _categorized_renderer("cls", [("A", _sym("#ff0000")), ("B", _sym("#0000ff"))])
        result = renderer_to_layer_style(_layer(renderer))
        assert result["categorizedSettings"]["A"]["color"] == "#ff0000"
        assert result["categorizedSettings"]["B"]["color"] == "#0000ff"

    def test_point_category_has_size_and_opacity(self):
        sl = _marker_sl(size=3.0)
        sym = _sym(opacity=0.5, symbol_layers=[sl])
        renderer = _categorized_renderer("cls", [("X", sym)])
        result = renderer_to_layer_style(_layer(renderer))
        entry = result["categorizedSettings"]["X"]
        assert entry["pointSize"] == pytest.approx(3.0 * _MM_TO_PX / 2, rel=1e-3)
        assert entry["pointOpacity"] == 0.5

    def test_line_category_has_width_and_opacity(self):
        sl = _line_sl(width=2.0)
        sym = _sym(opacity=0.7, symbol_layers=[sl])
        renderer = _categorized_renderer("cls", [("X", sym)])
        result = renderer_to_layer_style(_layer(renderer))
        entry = result["categorizedSettings"]["X"]
        assert entry["lineWidth"] == pytest.approx(2.0 * _MM_TO_PX, rel=1e-3)
        assert entry["lineOpacity"] == 0.7

    def test_fill_category_has_fill_opacity(self):
        sl = _fill_sl()
        sym = _sym(opacity=0.6, symbol_layers=[sl])
        renderer = _categorized_renderer("cls", [("X", sym)])
        result = renderer_to_layer_style(_layer(renderer))
        assert result["categorizedSettings"]["X"]["fillOpacity"] == 0.6


# ---------------------------------------------------------------------------
# Unsupported renderer (graduated, rule-based, etc.)
# ---------------------------------------------------------------------------

class TestUnsupportedRenderer:
    def test_grabs_primary_color(self):
        renderer = MagicMock()  # not Single or Categorized spec
        renderer.symbol.return_value.color.return_value.name.return_value = "#deadbe"
        result = renderer_to_layer_style(_layer(renderer))
        assert result["type"] == "simple"
        assert result["simpleColor"] == "#deadbe"

    def test_symbol_raises_returns_default_color(self):
        renderer = MagicMock()
        renderer.symbol.side_effect = RuntimeError("no symbol")
        result = renderer_to_layer_style(_layer(renderer))
        assert result["simpleColor"] == DEFAULT_COLOR


# ---------------------------------------------------------------------------
# Exception safety
# ---------------------------------------------------------------------------

class TestExceptionSafety:
    def test_renderer_raises_returns_default_style(self):
        lyr = MagicMock()
        lyr.renderer.side_effect = RuntimeError("crash")
        lyr.labeling.return_value = None
        result = renderer_to_layer_style(lyr)
        assert result == {"type": "simple", "simpleColor": DEFAULT_COLOR}


# ---------------------------------------------------------------------------
# Label extraction
# ---------------------------------------------------------------------------

class TestLabels:
    def _labeling(self, field_name, is_expression=False,
                  font_size=12, color="#000000", font_family="Arial",
                  halo_enabled=False, halo_size=1.0, halo_color="#ffffff",
                  font_size_unit=Qgis.RenderUnit.Points,
                  halo_size_unit=Qgis.RenderUnit.Millimeters):
        labeling = MagicMock(spec=QgsVectorLayerSimpleLabeling)
        settings = MagicMock()
        settings.fieldName = field_name
        settings.isExpression = is_expression
        fmt = MagicMock()
        fmt.size.return_value = font_size
        fmt.sizeUnit.return_value = font_size_unit
        fmt.color.return_value.name.return_value = color
        fmt.font.return_value.family.return_value = font_family
        fmt.buffer.return_value.enabled.return_value = halo_enabled
        fmt.buffer.return_value.size.return_value = halo_size
        fmt.buffer.return_value.sizeUnit.return_value = halo_size_unit
        fmt.buffer.return_value.color.return_value.name.return_value = halo_color
        settings.format.return_value = fmt
        labeling.settings.return_value = settings
        return labeling

    def test_field_label_produces_label_settings(self):
        lyr = _layer(_single_renderer(_sym()), self._labeling("city"))
        result = renderer_to_layer_style(lyr)
        ls = result["labelSettings"]
        assert ls["enabled"] is True
        assert ls["propertyId"] == "city"
        assert ls["fontSize"] == pytest.approx(12 * _PT_TO_PX, rel=1e-3)
        assert ls["fontFamily"] == "Arial"
        assert "haloEnabled" in ls

    def test_expression_label_not_extracted(self):
        lyr = _layer(_single_renderer(_sym()), self._labeling("concat(a,b)", is_expression=True))
        result = renderer_to_layer_style(lyr)
        assert "labelSettings" not in result

    def test_no_labeling_no_label_settings(self):
        lyr = _layer(_single_renderer(_sym()), labeling=None)
        assert "labelSettings" not in renderer_to_layer_style(lyr)

    def test_labeling_raises_no_label_settings(self):
        lyr = MagicMock()
        lyr.renderer.return_value = None
        lyr.labeling.side_effect = RuntimeError("fail")
        assert "labelSettings" not in renderer_to_layer_style(lyr)

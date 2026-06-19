from qgis.core import (
    Qgis, QgsWkbTypes,
    QgsSingleSymbolRenderer, QgsCategorizedSymbolRenderer,
    QgsSimpleMarkerSymbolLayer, QgsSimpleLineSymbolLayer,
    QgsSimpleFillSymbolLayer, QgsLinePatternFillSymbolLayer,
    QgsVectorLayerSimpleLabeling,
)

DEFAULT_COLOR = "#4A90D9"

_MM_TO_PX = 96.0 / 25.4   # ~3.7795 at 96 DPI
_PT_TO_PX = 96.0 / 72.0   # ~1.3333


def _to_px(value: float, unit) -> float:
    """Convert a QGIS render-unit value to CSS/MapLibre pixels."""
    if unit == Qgis.RenderUnit.Pixels:
        return round(value, 2)
    if unit == Qgis.RenderUnit.Points:
        return round(value * _PT_TO_PX, 2)
    if unit == Qgis.RenderUnit.Inches:
        return round(value * 96.0, 2)
    # Millimeters, MapUnits, unknown → treat as mm
    return round(value * _MM_TO_PX, 2)


_PEN_DASH = {
    "solidline": "solid", "dashline": "dashed", "dotline": "dotted",
    "dashdotline": "dash-dot", "dashdotdotline": "dash-dot-dot",
}
_BRUSH_HATCH = {
    "horpattern": "horizontal", "verpattern": "vertical",
    "crosspattern": "cross", "bdiagpattern": "b_diagonal",
    "fdiagpattern": "f_diagonal", "diagcrosspattern": "diagonal_x",
}


def renderer_to_layer_style(layer) -> dict:
    """Translate the layer's current QGIS renderer into a LayerStyle dict."""
    style: dict = {"type": "simple", "simpleColor": DEFAULT_COLOR}

    try:
        renderer = layer.renderer()
        if not renderer:
            return style

        if isinstance(renderer, QgsSingleSymbolRenderer):
            sym = renderer.symbol()
            style["simpleColor"] = sym.color().name()
            opacity = sym.opacity()

            for i in range(sym.symbolLayerCount()):
                sl = sym.symbolLayer(i)

                if isinstance(sl, QgsSimpleMarkerSymbolLayer):
                    style["pointOpacity"] = opacity
                    # QGIS size() is the full diameter; circle-radius in MapLibre is radius
                    style["pointSize"] = round(_to_px(sl.size(), sl.sizeUnit()) / 2, 2)
                    stroke_w = sl.strokeWidth()
                    style["outlineColor"] = sl.strokeColor().name()
                    # strokeWidth=0 means cosmetic hairline (1 physical px)
                    style["outlineWidth"] = 1.0 if stroke_w == 0 else round(_to_px(stroke_w, sl.strokeWidthUnit()), 2)
                    shape_name = sl.shape().name.lower()
                    if "square" in shape_name or "rectangle" in shape_name:
                        style["pointIcon"] = "square"
                    elif "triangle" in shape_name:
                        style["pointIcon"] = "triangle"
                    elif "star" in shape_name:
                        style["pointIcon"] = "star"
                    else:
                        style["pointIcon"] = "circle"
                    break

                elif isinstance(sl, QgsSimpleLineSymbolLayer):
                    style["lineOpacity"] = opacity
                    style["lineWidth"] = _to_px(sl.width(), sl.widthUnit())
                    style["lineDash"] = _PEN_DASH.get(sl.penStyle().name.lower(), "solid")
                    break

                elif isinstance(sl, QgsSimpleFillSymbolLayer):
                    style["fillOpacity"] = opacity
                    stroke = sl.strokeStyle()
                    style["showOutline"] = stroke.name.lower() != "nopen"
                    if style["showOutline"]:
                        style["lineWidth"] = _to_px(sl.strokeWidth(), sl.strokeWidthUnit())
                        style["lineDash"] = _PEN_DASH.get(stroke.name.lower(), "solid")
                    hatch = _BRUSH_HATCH.get(sl.brushStyle().name.lower())
                    if hatch:
                        style["hatchStyle"] = hatch
                    break

                elif isinstance(sl, QgsLinePatternFillSymbolLayer):
                    style["fillOpacity"] = opacity
                    style["hatchSpacing"] = _to_px(sl.distance(), sl.distanceUnit())
                    angle = sl.lineAngle() % 180
                    if angle < 5:
                        style["hatchStyle"] = "horizontal"
                    elif abs(angle - 90) < 5:
                        style["hatchStyle"] = "vertical"
                    elif abs(angle - 45) < 5:
                        style["hatchStyle"] = "b_diagonal"
                    else:
                        style["hatchStyle"] = "f_diagonal"
                    break

        elif isinstance(renderer, QgsCategorizedSymbolRenderer):
            style["type"] = "categorized"
            style["propertyId"] = renderer.classAttribute()
            cat_settings: dict = {}
            cat_values: list = []
            fallback_color = DEFAULT_COLOR

            for cat in renderer.categories():
                val = str(cat.value())
                sym = cat.symbol()
                if not val:
                    if sym:
                        fallback_color = sym.color().name()
                    continue
                cat_values.append(val)
                entry: dict = {}
                if sym:
                    entry["color"] = sym.color().name()
                    opacity = sym.opacity()
                    for i in range(sym.symbolLayerCount()):
                        sl = sym.symbolLayer(i)
                        if isinstance(sl, QgsSimpleMarkerSymbolLayer):
                            entry["pointSize"] = _to_px(sl.size(), sl.sizeUnit())
                            entry["pointOpacity"] = opacity
                        elif isinstance(sl, QgsSimpleLineSymbolLayer):
                            entry["lineWidth"] = _to_px(sl.width(), sl.widthUnit())
                            entry["lineOpacity"] = opacity
                        elif isinstance(sl, QgsSimpleFillSymbolLayer):
                            entry["fillOpacity"] = opacity
                        break
                cat_settings[val] = entry

            style["simpleColor"] = fallback_color
            style["categorizedSettings"] = cat_settings
            style["categorizedValues"] = cat_values

        else:
            try:
                style["simpleColor"] = renderer.symbol().color().name()
            except Exception:
                pass

    except Exception:
        pass

    # Labels
    try:
        labeling = layer.labeling()
        if labeling and isinstance(labeling, QgsVectorLayerSimpleLabeling):
            settings = labeling.settings()
            if not settings.isExpression and settings.fieldName:
                fmt = settings.format()
                style["labelSettings"] = {
                    "enabled": True,
                    "propertyId": settings.fieldName,
                    "fontSize": round(_to_px(fmt.size(), fmt.sizeUnit()), 1),
                    "color": fmt.color().name(),
                    "fontFamily": fmt.font().family(),
                    "haloEnabled": fmt.buffer().enabled(),
                    "haloSize": _to_px(fmt.buffer().size(), fmt.buffer().sizeUnit()),
                    "haloColor": fmt.buffer().color().name(),
                }
    except Exception:
        pass

    return style


def geometry_type_str(layer) -> str:
    flat = QgsWkbTypes.flatType(layer.wkbType())
    return {
        QgsWkbTypes.Type.Point: "Point",
        QgsWkbTypes.Type.MultiPoint: "MultiPoint",
        QgsWkbTypes.Type.LineString: "LineString",
        QgsWkbTypes.Type.MultiLineString: "MultiLineString",
        QgsWkbTypes.Type.Polygon: "Polygon",
        QgsWkbTypes.Type.MultiPolygon: "MultiPolygon",
        QgsWkbTypes.Type.GeometryCollection: "GeometryCollection",
        QgsWkbTypes.Type.NoGeometry: "None",
    }.get(flat, "Point")

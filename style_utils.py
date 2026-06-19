from qgis.core import (
    QgsWkbTypes,
    QgsSingleSymbolRenderer, QgsCategorizedSymbolRenderer,
    QgsSimpleMarkerSymbolLayer, QgsSimpleLineSymbolLayer,
    QgsSimpleFillSymbolLayer, QgsLinePatternFillSymbolLayer,
    QgsVectorLayerSimpleLabeling,
)

DEFAULT_COLOR = "#4A90D9"

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
                    style["pointSize"] = sl.size()
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
                    style["lineWidth"] = sl.width()
                    style["lineDash"] = _PEN_DASH.get(sl.penStyle().name.lower(), "solid")
                    break

                elif isinstance(sl, QgsSimpleFillSymbolLayer):
                    style["fillOpacity"] = opacity
                    stroke = sl.strokeStyle()
                    style["showOutline"] = stroke.name.lower() != "nopen"
                    if style["showOutline"]:
                        style["lineWidth"] = sl.strokeWidth()
                        style["lineDash"] = _PEN_DASH.get(stroke.name.lower(), "solid")
                    hatch = _BRUSH_HATCH.get(sl.brushStyle().name.lower())
                    if hatch:
                        style["hatchStyle"] = hatch
                    break

                elif isinstance(sl, QgsLinePatternFillSymbolLayer):
                    style["fillOpacity"] = opacity
                    style["hatchSpacing"] = sl.distance()
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
                            entry["pointSize"] = sl.size()
                            entry["pointOpacity"] = opacity
                        elif isinstance(sl, QgsSimpleLineSymbolLayer):
                            entry["lineWidth"] = sl.width()
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
                    "fontSize": int(fmt.size()),
                    "color": fmt.color().name(),
                    "fontFamily": fmt.font().family(),
                    "haloEnabled": fmt.buffer().enabled(),
                    "haloSize": fmt.buffer().size(),
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

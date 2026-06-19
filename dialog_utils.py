import os
import re
from urllib.parse import urlparse


def table_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:63]


def gpkg_table_name(layer) -> str:
    """Return the actual table name from the layer's GeoPackage source, or fall back to sanitized display name."""
    source = layer.source()
    if "|layername=" in source:
        return source.split("|layername=")[1].split("|")[0]
    return table_name(layer.name())


def field_base_type(qf) -> str:
    tn = qf.typeName().lower()
    if any(x in tn for x in ("int", "serial", "long")):
        return "integer"
    if any(x in tn for x in ("float", "double", "real", "numeric", "decimal", "number")):
        return "number"
    if "bool" in tn:
        return "boolean"
    if "datetime" in tn or "timestamp" in tn:
        return "date-time"
    if "date" in tn:
        return "date"
    return "string"


def is_valid_url(url: str) -> bool:
    try:
        p = urlparse(url)
        return p.scheme in ("http", "https") and bool(p.netloc)
    except Exception:
        return False

"""FieldFile data model: parsed mesh + variables + regions."""

from .dataset import (
    FIELD_KIND_SCALAR,
    FIELD_KIND_VECTOR,
    FieldFile,
    Region,
    VarInfo,
    load_file,
)

__all__ = [
    "FieldFile",
    "VarInfo",
    "Region",
    "load_file",
    "FIELD_KIND_SCALAR",
    "FIELD_KIND_VECTOR",
]

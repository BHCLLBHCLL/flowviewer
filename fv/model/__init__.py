"""FieldFile data model: parsed mesh + variables + regions."""

from .dataset import FieldFile, VarInfo, Region, load_file, FIELD_KIND_SCALAR, FIELD_KIND_VECTOR

__all__ = [
    "FieldFile",
    "VarInfo",
    "Region",
    "load_file",
    "FIELD_KIND_SCALAR",
    "FIELD_KIND_VECTOR",
]
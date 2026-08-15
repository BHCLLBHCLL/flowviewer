"""PPH (scFLOW project archive) reader.

A ``.pph`` is a ZIP container whose members include the scFLOW project
files (main.js / main.prp / main.sctsnapshot / main.xenv / main.xml) and
the meshing-group volume mesh (``<group>.gph``).  This module extracts the
volume-mesh member to a temporary file and delegates to ``mesh_gph``;
project metadata (member list, project name) rides along in the returned
dict.  Display faceting (``<group>_part.mdl`` / ``<group>_ridge.mdl``) and
the octree (``<group>.oct``) are left to the pphdecoding reference tools.
"""

from __future__ import annotations

import os
import re
import tempfile
import zipfile
from typing import Optional

from . import mesh_gph


def pph_members(filepath: str) -> list[tuple[str, int, int]]:
    """Return ``[(member_name, file_size, compress_size), ...]``."""
    with zipfile.ZipFile(filepath) as z:
        return [(i.filename, i.file_size, i.compress_size)
                for i in z.infolist()]


def pph_project_name(filepath: str) -> Optional[str]:
    """Best-effort ``main.xml`` ``<project><name>`` text."""
    try:
        with zipfile.ZipFile(filepath) as z:
            xml = z.read("main.xml")
    except (KeyError, zipfile.BadZipFile, OSError):
        return None
    m = re.search(rb"<name[^>]*>([^<]{1,200})</name>", xml, re.S)
    if not m:
        return None
    return m.group(1).decode("utf-8", "replace").strip() or None


def parse_pph(filepath: str) -> dict:
    """Open a PPH project archive and parse its embedded volume mesh.

    Returns the ``mesh_gph.parse_gph_mesh`` dict augmented with
    ``pph_members`` (member list), ``pph_gph_member`` and
    ``pph_project``; raises ``ValueError`` when the archive holds no
    ``*.gph`` member.
    """
    if not zipfile.is_zipfile(filepath):
        raise ValueError(f"{filepath}: not a PPH (zip) archive")
    with zipfile.ZipFile(filepath) as z:
        names = z.namelist()
        gph_members = [n for n in names if n.lower().endswith(".gph")]
        if not gph_members:
            raise ValueError(f"{filepath}: no embedded .gph volume mesh")
        gph_name = max(gph_members, key=lambda n: z.getinfo(n).file_size)
        payload = z.read(gph_name)

    fd, tmp = tempfile.mkstemp(suffix=".gph")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(payload)
        mesh = mesh_gph.parse_gph_mesh(tmp)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass

    mesh["pph_members"] = names
    mesh["pph_gph_member"] = gph_name
    mesh["pph_project"] = pph_project_name(filepath)
    mesh["file_size"] = os.path.getsize(filepath)
    return mesh

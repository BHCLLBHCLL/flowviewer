"""Wall-surface geometry for distance / normal fields (R113).

DST used to build a point cloud of wall *vertices* and take the nearest
neighbour distance, which over-estimates on any concave or coarse wall
(measured against the exact distance to the wall faces: median +47.7%,
p99 +1292%, max +112244%; 828 of 2000 sampled cells were more than 2x off).
It also only ever looked at FieldFile.surface_regions, so an FLD - which
records its boundaries in bc_plan - raised 'no wall faces for DST' even
though the file has 16 BC zones.

This module builds the actual wall surface once, as a triangulated
vtkPolyData, so the distance can be measured to the surface instead of to a
vertex and so both file families can supply walls.
"""

from __future__ import annotations

import numpy as np


def wall_face_node_ids(ff, region_names=None) -> list:
    """Face-node id tuples of the wall faces (R113).

    ``region_names=None`` means every boundary region.  FPH keeps its faces
    in link_data; FLD lists them in ff.faces with bc_plan giving each
    region's slice.  Returns 0-based vertex-id tuples.
    """
    names = set(region_names or ())
    out: list = []
    regions = ff.boundary_regions()
    for region in regions:
        if names and region.name not in names:
            continue
        if getattr(ff, "poly", False):
            ld = ff.link_data
            fn = np.asarray(ld["face_nodes"], dtype=np.int64)
            off = np.asarray(ld["face_offsets"], dtype=np.int64)
            for f in region.face_ids:
                lo, hi = int(off[f]), int(off[f + 1])
                if hi > lo:
                    out.append(tuple(int(x) for x in fn[lo:hi]))
        else:
            faces = getattr(ff, "faces", None) or []
            for f in region.face_ids:
                if 0 <= int(f) < len(faces):
                    out.append(tuple(int(x) for x in faces[int(f)]))
    return out


def wall_polydata(ff, region_names=None):
    """Triangulated wall surface as vtkPolyData, or None when there is none."""
    ids = wall_face_node_ids(ff, region_names)
    if not ids:
        return None
    verts = np.asarray(ff.vertices, dtype=np.float64)
    try:
        import vtk
        from vtk.util import numpy_support as vns
    except Exception:  # pragma: no cover - vtk unavailable
        return None
    points = vtk.vtkPoints()
    points.SetData(vns.numpy_to_vtk(verts, deep=True))
    polys = vtk.vtkCellArray()
    idl = vtk.vtkIdList()
    for face in ids:
        keep = [int(i) for i in face if 0 <= int(i) < len(verts)]
        if len(keep) < 3:
            continue
        idl.Reset()
        for i in keep:
            idl.InsertNextId(i)
        polys.InsertNextCell(idl)
    pd = vtk.vtkPolyData()
    pd.SetPoints(points)
    pd.SetPolys(polys)
    return pd


def implicit_distance(ff, region_names=None, points=None):
    """Exact distance from *points* to the wall surface (R113).

    Returns a 1-D array of unsigned distances, or None when the file has no
    wall faces / vtk is unavailable.  Falls back to the signed distance
    magnitude of vtkImplicitPolyDataDistance, which is exact for the
    triangulated surface rather than for its vertices.
    """
    pd = wall_polydata(ff, region_names)
    if pd is None or pd.GetNumberOfPolys() == 0:
        return None
    if points is None:
        points = np.asarray(ff.vertices, dtype=np.float64)
    points = np.asarray(points, dtype=np.float64)
    import vtk
    dist = vtk.vtkImplicitPolyDataDistance()
    dist.SetInput(pd)
    return np.asarray([abs(float(dist.EvaluateFunction(p)))
                       for p in points], dtype=np.float64)

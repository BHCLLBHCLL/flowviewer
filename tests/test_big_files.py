"""Big-file regression (E): >512MiB mmap path on real 5-6 GB GPH files.

Marked ``slow``; run explicitly with ``pytest -m slow``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from samples import sample  # noqa: E402

#: R127d: the samples moved; resolve them at run time instead of skipping.
BIG_GPH = [p for p in (sample("box.gph"),
                       sample("laptop_simplified_more_regions_v6.gph"))
           if p is not None]


@pytest.mark.slow
@pytest.mark.parametrize("path", BIG_GPH, ids=lambda p: p.name)
def test_big_gph_mmap_parse(path):
    """End-to-end mmap parse: counts positive, face nodes in bounds."""
    if not path.exists():
        pytest.skip("big gph sample not present")
    assert path.stat().st_size > 512 * 1024 * 1024, "sample not >512MiB"
    from fv.crdl import mesh_gph
    m = mesh_gph.parse_gph_mesh(str(path))
    assert m["n_vertices"] > 0 and m["n_cells"] > 0
    ld = m["link_data"]
    assert ld is not None and ld["n_faces"] > 0
    fn = np.asarray(ld["face_nodes"])
    assert fn.min() >= 0 and fn.max() < m["n_vertices"]
    assert m["volume_regions"], "volume regions expected"

"""CradleViewer (CVFF) scene file parser (R17-T2).

Reverse-engineered from the official AR samples by differential analysis
(R17-T1, see ``analysis/cradleviewer_format.md``).  A CradleViewer file is
a self-contained scene package - geometry, colours, textures and the
object tree are all embedded, with no external references:

    Header := b"CVFF" version:u32_le writer:u32_le        (12 bytes)
    Block  := tag:char[4] len:u32_le content:len          (chain to EOF)
              the final block is TREE, whose len field is unreliable;
              its content simply runs to end-of-file
    Record := type:u32_le size:u32_le payload:size        (flat, no padding)

Object blocks open with the common record ``(0, 214)`` whose payload
holds nested records 1-8 (owning group, subtype, 4x4 transform, ...),
followed by type-specific records 500+.

Geometry encoding (POLY / LINE):

* records 502/503 (POLY) and 506/507 (LINE) store the bounding box as
  ``(min corner, box size)`` - min + size reproduces the FLD model range
  exactly on both samples;
* vertex records are 10 bytes: three u16 coordinates linearly quantised
  onto the bounding box (0 -> min, 65535 -> max) plus two raw u16
  auxiliary fields (normal/UV encoding, not yet decoded - kept verbatim);
* POLY record 505 holds one byte per face with that face's vertex count
  (3 = triangle, 4 = quad) and record 506 the concatenated u16 vertex
  index list;  LINE records 509/510 mirror this for polylines.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

MAGIC = b"CVFF"
HEADER_SIZE = 12

_U16_MAX = 65535.0
_PARTICLE_SENTINEL = 1.0e6    # invalid particle coords are ~ -4.3e8


# -- data model --------------------------------------------------------------


@dataclass
class CommonProps:
    """Records 1-8 nested inside the leading (0, 214) record."""

    kind: int = -1                        # rec 1: owning tree group (-1 = global)
    subtype: int = -1                     # rec 2
    matrix: Optional[np.ndarray] = None   # rec 3: 4x4 f64 transform
    width: float = 1.0                    # rec 4: f32 (line width)
    opacity: float = 1.0                  # rec 5: f32
    flag6: int = 0                        # rec 6
    flag7: int = 0                        # rec 7
    visible: int = 1                      # rec 8


@dataclass
class TreeEntry:
    """One TREE entry: UTF-16 name + four i32 fields (B/C/D/E)."""

    name: str
    group: int          # B: matches CommonProps.kind of member blocks
    node_id: int        # C: unique node id
    parent: int         # D: parent node_id (-1 = root)
    type_id: int        # E: type/icon code (1=FLD, 2=Global, 21=Marker, ...)


@dataclass
class PolyMesh:
    """POLY block: triangles/quads with bbox-quantised vertices."""

    offset: int
    props: CommonProps
    color: int = 0                                   # 0x00RRGGBB
    bbox_min: Optional[np.ndarray] = None            # (3,) f64
    bbox_size: Optional[np.ndarray] = None           # (3,) f64
    vertices: Optional[np.ndarray] = None            # (N, 3) f64
    aux: Optional[np.ndarray] = None                 # (N, 2) raw u16
    face_sizes: Optional[np.ndarray] = None          # (T,) per-face vertex count
    faces: list = field(default_factory=list)        # list of index lists
    records: dict = field(default_factory=dict)

    @property
    def n_faces(self) -> int:
        return len(self.faces)

    def triangles(self) -> list:
        """Faces with exactly 3 vertices (quads are skipped)."""
        return [f for f in self.faces if len(f) == 3]


@dataclass
class PolyLines:
    """LINE block: polylines over a shared quantised vertex pool."""

    offset: int
    props: CommonProps
    color: int = 0
    bbox_min: Optional[np.ndarray] = None
    bbox_size: Optional[np.ndarray] = None
    vertices: Optional[np.ndarray] = None            # (N, 3) f64
    aux: Optional[np.ndarray] = None                 # (N, 2) raw u16
    seg_sizes: Optional[np.ndarray] = None           # per-polyline vertex count
    polylines: list = field(default_factory=list)    # list of index lists
    records: dict = field(default_factory=dict)


@dataclass
class PointMarker:
    """PNT block: anchor marker at the object origin."""

    offset: int
    props: CommonProps
    style: int = 0
    color: int = 0
    position: Optional[np.ndarray] = None            # (3,) f64
    records: dict = field(default_factory=dict)


@dataclass
class ParticleCloud:
    """PTC3 block: per-particle RGBA + XYZ (invalid ones hold sentinels)."""

    offset: int
    props: CommonProps
    display_type: int = 0
    total: int = 0                                   # rec 501: simulation count
    size: float = 0.0                                # rec 506: particle size
    positions: Optional[np.ndarray] = None           # (N, 3) f32
    rgba: Optional[np.ndarray] = None                # (N, 4) u8
    flags: Optional[np.ndarray] = None               # (N, 4) u8
    records: dict = field(default_factory=dict)

    def valid_positions(self) -> Optional[np.ndarray]:
        """Positions without sentinel-coordinate particles."""
        if self.positions is None:
            return None
        ok = np.all(np.abs(self.positions) < _PARTICLE_SENTINEL, axis=1)
        return self.positions[ok]


@dataclass
class Texture:
    """TEX block: raw RGBA8888 square texture (record 519)."""

    offset: int
    props: CommonProps
    edge: int = 0                                    # rec 500: side in pixels
    pixels: Optional[np.ndarray] = None              # (S, S, 4) u8
    records: dict = field(default_factory=dict)


@dataclass
class Icon:
    """BTN block: tree-node icon as a 4-byte-aligned RGB888 DIB."""

    offset: int
    props: CommonProps
    width: int = 0
    height: int = 0
    stride: int = 0
    rgb: Optional[np.ndarray] = None                 # (h, w, 3) u8, top-down
    records: dict = field(default_factory=dict)


@dataclass
class Light:
    """LIGH block: ambient/diffuse/specular colours + direction."""

    offset: int
    props: CommonProps
    ambient: Optional[np.ndarray] = None             # (3,) f64
    diffuse: Optional[np.ndarray] = None
    specular: Optional[np.ndarray] = None
    direction: Optional[np.ndarray] = None
    records: dict = field(default_factory=dict)


@dataclass
class FieldSettings:
    """FLD block: model range, camera (eye/target/up) and viewport."""

    offset: int
    props: CommonProps
    model_range: Optional[np.ndarray] = None         # (6,) xmin xmax ymin ymax zmin zmax
    camera_eye: Optional[np.ndarray] = None          # (3,)
    camera_target: Optional[np.ndarray] = None
    camera_up: Optional[np.ndarray] = None
    viewport: Optional[np.ndarray] = None            # (4,)
    records: dict = field(default_factory=dict)


@dataclass
class GenericObject:
    """ENCD/ENV/LOGO/STR and unknown blocks: records kept verbatim."""

    offset: int
    tag: str
    props: Optional[CommonProps] = None
    records: dict = field(default_factory=dict)


@dataclass
class CVFFScene:
    """Fully parsed CradleViewer file."""

    path: str
    version: int = 2
    writer_id: int = 0
    encoding: int = 0                                # ENCD record 500
    blocks: list = field(default_factory=list)       # [(offset, tag, length)]
    tree: list = field(default_factory=list)         # [TreeEntry]
    field_settings: Optional[FieldSettings] = None
    env: Optional[GenericObject] = None
    lights: list = field(default_factory=list)
    polys: list = field(default_factory=list)        # [PolyMesh]
    lines: list = field(default_factory=list)        # [PolyLines]
    markers: list = field(default_factory=list)      # [PointMarker]
    particles: list = field(default_factory=list)    # [ParticleCloud]
    textures: list = field(default_factory=list)     # [Texture]
    icons: list = field(default_factory=list)        # [Icon]
    others: list = field(default_factory=list)       # [GenericObject]

    def group_name(self, kind: int) -> Optional[str]:
        """TREE entry name owning group *kind* (CommonProps.kind match)."""
        for e in self.tree:
            if e.group == kind:
                return e.name
        return None

    def group_objects(self, kind: int) -> dict:
        """All typed geometry objects belonging to one tree group."""
        out = {"polys": [], "lines": [], "markers": [], "particles": [],
               "textures": [], "icons": []}
        for lst, key in ((self.polys, "polys"), (self.lines, "lines"),
                         (self.markers, "markers"), (self.particles, "particles"),
                         (self.textures, "textures"), (self.icons, "icons")):
            out[key] = [o for o in lst if o.props.kind == kind]
        return out


# -- low-level parsing -------------------------------------------------------


def _walk_blocks(data: bytes):
    """Yield ``(offset, tag, length, content)`` for every block to EOF.

    The walk starts right after the 12-byte header.  TREE terminates the
    chain: its declared length is unreliable, so its content runs to EOF.
    """
    off = HEADER_SIZE
    n = len(data)
    while off + 8 <= n:
        tag = data[off:off + 4]
        if not all(0x20 <= b <= 0x5A for b in tag):   # printable tag guard
            break
        (ln,) = struct.unpack_from("<I", data, off + 4)
        end = off + 8 + ln
        is_tree = tag == b"TREE"
        if is_tree or end > n:
            content = data[off + 8:n]
            yield off, tag, n - off - 8, content
            return
        yield off, tag, ln, data[off + 8:end]
        off = end


def _parse_records(content: bytes):
    """Flat record stream -> ``(records, tiled)`` with ``records`` as
    ``[(type, payload)]`` in file order.  Stops at the first malformed
    record; *tiled* reports whether the stream consumed the block exactly.
    """
    recs = []
    off = 0
    n = len(content)
    while off + 8 <= n:
        typ, size = struct.unpack_from("<II", content, off)
        if size > n - off - 8:
            break
        recs.append((typ, content[off + 8:off + 8 + size]))
        off += 8 + size
    return recs, off == n


def _record_map(records):
    """First-occurrence ``{type: payload}`` map (500+ records are unique)."""
    out = {}
    for typ, payload in records:
        out.setdefault(typ, payload)
    return out


def _u32(payload, default=0):
    return struct.unpack("<I", payload)[0] if len(payload) >= 4 else default


def _f32s(payload, count):
    if len(payload) < 4 * count:
        return None
    return np.array(struct.unpack("<" + str(count) + "f", payload[:4 * count]),
                    dtype=np.float64)


def _common(records):
    """Common records 1-8 nested in the leading (0, 214) record."""
    props = CommonProps()
    lead = _record_map(records).get(0)
    if lead is None:
        return props
    nested, _ = _parse_records(lead)
    for typ, payload in nested:
        if typ == 1 and len(payload) >= 4:
            (k,) = struct.unpack("<I", payload)
            props.kind = -1 if k == 0xFFFFFFFF else int(k)
        elif typ == 2 and len(payload) >= 4:
            (s,) = struct.unpack("<I", payload)
            props.subtype = -1 if s == 0xFFFFFFFF else int(s)
        elif typ == 3 and len(payload) >= 128:
            props.matrix = np.array(struct.unpack("<16d", payload[:128]),
                                    dtype=np.float64).reshape(4, 4)
        elif typ == 4 and len(payload) >= 4:
            props.width = struct.unpack("<f", payload)[0]
        elif typ == 5 and len(payload) >= 4:
            props.opacity = struct.unpack("<f", payload)[0]
        elif typ == 6 and payload:
            props.flag6 = payload[0]
        elif typ == 7 and len(payload) >= 4:
            props.flag7 = _u32(payload)
        elif typ == 8 and payload:
            props.visible = payload[0]
    return props


def _decode_vertices(payload, vmin, vsize):
    """10-byte vertex records -> ``(vertices (N,3), aux (N,2))``.

    Coordinates are u16 values linearly mapped onto the bounding box
    (0 -> min, 65535 -> min + size); the trailing two u16 fields are
    kept raw (encoding unresolved).
    """
    if not payload or vmin is None or vsize is None:
        return None, None
    n = len(payload) // 10
    if n == 0:
        return None, None
    raw = np.frombuffer(payload[:n * 10], dtype="<u2", count=n * 5)
    raw = raw.reshape(n, 5)
    t = raw[:, :3].astype(np.float64) / _U16_MAX
    verts = np.asarray(vmin, dtype=np.float64)[None, :] + \
        t * np.asarray(vsize, dtype=np.float64)[None, :]
    return verts, raw[:, 3:5].copy()


def _faces_from(sizes_payload, index_payload):
    """Per-face vertex-count bytes + concatenated u16 indices -> faces."""
    if sizes_payload is None or index_payload is None:
        return None, []
    sizes = np.frombuffer(sizes_payload, dtype=np.uint8)
    idx = np.frombuffer(index_payload, dtype="<u2")
    faces = []
    off = 0
    for s in sizes:
        cnt = int(s)
        faces.append([int(v) for v in idx[off:off + cnt]])
        off += cnt
    return sizes, faces


def _parse_tree(content: bytes):
    """TREE content -> ``([TreeEntry], tiled)`` (len runs to EOF)."""
    entries = []
    pos = 0
    n = len(content)
    if n < 4:
        return entries, n == 4
    (count,) = struct.unpack_from("<I", content, 0)
    pos = 4
    for _ in range(count):
        if pos + 4 > n:
            return entries, False
        (nl,) = struct.unpack_from("<I", content, pos)
        pos += 4
        if pos + nl * 2 + 16 > n:
            return entries, False
        name = content[pos:pos + nl * 2].decode("utf-16-le", "replace")
        pos += nl * 2
        b, c, d, e = struct.unpack_from("<4i", content, pos)
        pos += 16
        entries.append(TreeEntry(name, b, c, d, e))
    return entries, pos == n


# -- per-tag object builders -------------------------------------------------


def _build_poly(offset, props, records):
    obj = PolyMesh(offset=offset, props=props, records=records)
    obj.color = _u32(records.get(501, b""))
    obj.bbox_min = _f32s(records.get(502, b""), 3)
    obj.bbox_size = _f32s(records.get(503, b""), 3)
    obj.vertices, obj.aux = _decode_vertices(
        records.get(504, b""), obj.bbox_min, obj.bbox_size)
    obj.face_sizes, obj.faces = _faces_from(
        records.get(505), records.get(506))
    return obj


def _build_lines(offset, props, records):
    obj = PolyLines(offset=offset, props=props, records=records)
    obj.color = _u32(records.get(501, b""))
    obj.bbox_min = _f32s(records.get(506, b""), 3)
    obj.bbox_size = _f32s(records.get(507, b""), 3)
    obj.vertices, obj.aux = _decode_vertices(
        records.get(508, b""), obj.bbox_min, obj.bbox_size)
    obj.seg_sizes, obj.polylines = _faces_from(
        records.get(509), records.get(510))
    return obj


def _build_marker(offset, props, records):
    obj = PointMarker(offset=offset, props=props, records=records)
    obj.style = _u32(records.get(500, b""))
    obj.color = _u32(records.get(501, b""))
    obj.position = _f32s(records.get(505, b""), 3)
    return obj


def _build_particles(offset, props, records):
    obj = ParticleCloud(offset=offset, props=props, records=records)
    obj.display_type = _u32(records.get(500, b""))
    obj.total = _u32(records.get(501, b""))
    size = _f32s(records.get(506, b""), 1)
    obj.size = float(size[0]) if size is not None else 0.0
    xyz = records.get(512)
    if xyz is not None and len(xyz) >= 12:
        obj.positions = np.frombuffer(xyz, dtype="<f4") \
            .reshape(-1, 3).astype(np.float64)
    rgba = records.get(510)
    if rgba is not None and len(rgba) >= 4:
        obj.rgba = np.frombuffer(rgba, dtype=np.uint8).reshape(-1, 4).copy()
    flags = records.get(511)
    if flags is not None and len(flags) >= 4:
        obj.flags = np.frombuffer(flags, dtype=np.uint8).reshape(-1, 4).copy()
    return obj


def _build_texture(offset, props, records):
    obj = Texture(offset=offset, props=props, records=records)
    obj.edge = _u32(records.get(500, b""))
    pix = records.get(519)
    s = obj.edge
    if pix is not None and s > 0 and len(pix) >= s * s * 4:
        obj.pixels = np.frombuffer(pix, dtype=np.uint8, count=s * s * 4) \
            .reshape(s, s, 4).copy()
    return obj


def _build_icon(offset, props, records):
    obj = Icon(offset=offset, props=props, records=records)
    head = records.get(500, b"")
    if len(head) >= 8:
        obj.width, obj.height = struct.unpack("<II", head)
        obj.stride = (obj.width * 3 + 3) // 4 * 4     # DIB 4-byte row align
    bmp = records.get(501)
    if bmp is not None and obj.height > 0 and obj.stride > 0 \
            and len(bmp) >= obj.stride * obj.height:
        rows = np.frombuffer(bmp, dtype=np.uint8,
                             count=obj.stride * obj.height)
        img = rows.reshape(obj.height, obj.stride)[:, :obj.width * 3]
        img = img.reshape(obj.height, obj.width, 3)
        obj.rgb = np.flipud(img).copy()               # DIB rows are bottom-up
    return obj


def _build_light(offset, props, records):
    obj = Light(offset=offset, props=props, records=records)
    obj.ambient = _f32s(records.get(501, b""), 3)
    obj.diffuse = _f32s(records.get(502, b""), 3)
    obj.specular = _f32s(records.get(503, b""), 3)
    obj.direction = _f32s(records.get(505, b""), 3)
    return obj


def _build_field_settings(offset, props, records):
    obj = FieldSettings(offset=offset, props=props, records=records)
    obj.model_range = _f32s(records.get(500, b""), 6)
    cam = _f32s(records.get(509, b""), 9)
    if cam is not None:
        obj.camera_eye = cam[0:3]
        obj.camera_target = cam[3:6]
        obj.camera_up = cam[6:9]
    obj.viewport = _f32s(records.get(510, b""), 4)
    return obj


# -- public API --------------------------------------------------------------


def parse_buffer(data: bytes, path: str = "") -> CVFFScene:
    """Parse CVFF bytes (header must be present) into a :class:`CVFFScene`."""
    if len(data) < HEADER_SIZE or data[:4] != MAGIC:
        raise ValueError("not a CradleViewer CVFF file: " + repr(path))
    version, writer_id = struct.unpack_from("<II", data, 4)
    scene = CVFFScene(path=path, version=int(version),
                      writer_id=int(writer_id))
    for off, tag, ln, content in _walk_blocks(data):
        scene.blocks.append((off, tag.decode("ascii", "replace"), ln))
        if tag == b"TREE":
            scene.tree, _tiled = _parse_tree(content)
            continue
        records, _ok = _parse_records(content)
        rmap = _record_map(records)
        props = _common(records)
        if tag == b"ENCD":
            scene.encoding = _u32(rmap.get(500, b""))
            scene.others.append(GenericObject(off, "ENCD", props, rmap))
        elif tag == b"FLD ":
            scene.field_settings = _build_field_settings(off, props, rmap)
        elif tag == b"ENV ":
            scene.env = GenericObject(off, "ENV", props, rmap)
        elif tag == b"POLY":
            scene.polys.append(_build_poly(off, props, rmap))
        elif tag == b"LINE":
            scene.lines.append(_build_lines(off, props, rmap))
        elif tag == b"PNT ":
            scene.markers.append(_build_marker(off, props, rmap))
        elif tag == b"PTC3":
            scene.particles.append(_build_particles(off, props, rmap))
        elif tag == b"TEX ":
            scene.textures.append(_build_texture(off, props, rmap))
        elif tag == b"BTN ":
            scene.icons.append(_build_icon(off, props, rmap))
        elif tag == b"LIGH":
            scene.lights.append(_build_light(off, props, rmap))
        else:                                          # LOGO / STR / future
            scene.others.append(
                GenericObject(off, tag.decode("ascii", "replace"),
                              props, rmap))
    return scene


def parse_cvff(path: str) -> CVFFScene:
    """Read and parse one CradleViewer ``*.CradleViewer`` file."""
    p = Path(path)
    return parse_buffer(p.read_bytes(), str(p))


def scene_stats(scene: CVFFScene) -> dict:
    """Compact per-scene statistics (block counts, geometry totals)."""
    poly_v = sum(o.vertices.shape[0] for o in scene.polys
                 if o.vertices is not None)
    poly_f = sum(o.n_faces for o in scene.polys)
    line_v = sum(o.vertices.shape[0] for o in scene.lines
                 if o.vertices is not None)
    line_s = sum(len(p) for o in scene.lines for p in o.polylines)
    parts = sum(o.positions.shape[0] for o in scene.particles
                if o.positions is not None)
    return {
        "blocks": len(scene.blocks),
        "tree_entries": len(scene.tree),
        "polys": len(scene.polys),
        "poly_vertices": poly_v,
        "poly_faces": poly_f,
        "lines": len(scene.lines),
        "line_vertices": line_v,
        "line_segments": line_s,
        "markers": len(scene.markers),
        "particles": parts,
        "textures": len(scene.textures),
        "icons": len(scene.icons),
        "lights": len(scene.lights),
    }


# -- serialization (R17-T4a) -------------------------------------------------

WRITER_ID = 20120727          # sample writer stamp (date-encoded 2012-07-27)
_POLY_STYLE = 0x02000B1E      # main-POLY style bits observed in samples
_LINE_STYLE = 0x10840030      # LINE style bits observed in samples
_U16_VERTEX_LIMIT = 65535     # u16 indices: max vertices per geometry block


def _record(typ: int, payload: bytes) -> bytes:
    """One record: ``(type, size, payload)``."""
    return struct.pack("<II", typ, len(payload)) + payload


def _block(tag: str, content: bytes) -> bytes:
    """One TLV block: 4-char tag + u32 length + content."""
    t = tag.encode("ascii")
    if len(t) != 4:
        raise ValueError("CVFF block tag must be 4 characters: %r" % tag)
    return t + struct.pack("<I", len(content)) + content


def common_payload(props: CommonProps) -> bytes:
    """Nested records 1-8 payload for the leading ``(0, 214)`` record."""
    kind = 0xFFFFFFFF if props.kind < 0 else int(props.kind)
    sub = 0xFFFFFFFF if props.subtype < 0 else int(props.subtype)
    matrix = props.matrix if props.matrix is not None else np.eye(4)
    nested = b"".join([
        _record(1, struct.pack("<I", kind)),
        _record(2, struct.pack("<I", sub)),
        _record(3, np.ascontiguousarray(matrix, dtype="<f8").tobytes()),
        _record(4, struct.pack("<f", props.width)),
        _record(5, struct.pack("<f", props.opacity)),
        _record(6, bytes([props.flag6 & 0xFF])),
        _record(7, struct.pack("<I", props.flag7)),
        _record(8, bytes([1 if props.visible else 0])),
    ])
    return nested


def encode_vertices(vertices, vmin, vsize, aux=None) -> bytes:
    """``(N, 3)`` coords -> N x 10B u16 records (inverse of _decode_vertices).

    Coordinates are quantised onto ``[vmin, vmin + vsize]`` exactly as the
    f32 values stored in records 502/503, so decoding the output reproduces
    the input up to one quantisation step.  Degenerate (zero-size) bbox
    axes quantise to 0, matching the decoder's collapse onto *vmin*.
    """
    v = np.asarray(vertices, dtype=np.float64).reshape(-1, 3)
    lo = np.asarray(vmin, dtype=np.float64).reshape(3)
    size = np.asarray(vsize, dtype=np.float64).reshape(3)
    safe = np.where(size > 0, size, 1.0)
    t = (v - lo) / safe * _U16_MAX
    q = np.clip(np.rint(t), 0.0, _U16_MAX)
    n = v.shape[0]
    if aux is None:
        aux2 = np.zeros((n, 2), dtype="<u2")
    else:
        aux2 = np.asarray(aux, dtype="<u2").reshape(n, 2)
    out = np.empty((n, 5), dtype="<u2")
    out[:, :3] = q
    out[:, 3:] = aux2
    return out.tobytes()


def encode_faces(faces) -> tuple:
    """Face index lists -> ``(per-face-size bytes, concatenated u16 idx)``."""
    sizes = bytearray()
    idx = bytearray()
    for f in faces:
        n = len(f)
        if not 1 <= n <= 255:
            raise ValueError("face size %d out of u8 range" % n)
        sizes.append(n)
        for v in f:
            if not 0 <= v <= _U16_MAX:
                raise ValueError("vertex index %d out of u16 range" % v)
            idx += struct.pack("<H", int(v))
    return bytes(sizes), bytes(idx)


def _serialize_tree(tree) -> bytes:
    body = struct.pack("<I", len(tree))
    for e in tree:
        name = e.name.encode("utf-16-le")
        body += struct.pack("<I", len(e.name)) + name
        body += struct.pack("<4i", e.group, e.node_id, e.parent, e.type_id)
    return _block("TREE", body)


def _serialize_object(tag: str, records: dict) -> bytes:
    """Object block from an ordered ``{type: payload}`` record map.

    Payloads are emitted verbatim in map order (insertion order), so a
    parsed scene reproduces the original byte stream exactly.
    """
    body = b"".join(_record(t, bytes(p)) for t, p in records.items())
    return _block(tag, body)


def serialize_scene(scene: CVFFScene) -> bytes:
    """Scene (parsed or freshly built) -> CVFF file bytes.

    Parsed blocks are re-emitted with record payloads verbatim, so
    ``parse_buffer(serialize_scene(parse_buffer(f)))`` is byte-faithful
    to *f*; the only normalisation is the TREE length field, which the
    original writer over-declares (see analysis/cradleviewer_format.md).
    """
    index: dict = {}

    def _put(obj, tag):
        index[obj.offset] = (tag, obj.records)

    for o in scene.polys:
        _put(o, "POLY")
    for o in scene.lines:
        _put(o, "LINE")
    for o in scene.markers:
        _put(o, "PNT ")
    for o in scene.particles:
        _put(o, "PTC3")
    for o in scene.textures:
        _put(o, "TEX ")
    for o in scene.icons:
        _put(o, "BTN ")
    for o in scene.lights:
        _put(o, "LIGH")
    if scene.env is not None:
        _put(scene.env, "ENV ")
    for o in scene.others:
        index.setdefault(o.offset, (o.tag, o.records))
    if scene.field_settings is not None:
        _put(scene.field_settings, "FLD ")
    parts = [struct.pack("<4sII", MAGIC, scene.version, scene.writer_id)]
    for off, tag, _ln in scene.blocks:
        if tag == "TREE":
            parts.append(_serialize_tree(scene.tree))
            continue
        obj = index.get(off)
        if obj is None:
            raise ValueError("no object for block %r at offset %d" % (tag, off))
        parts.append(_serialize_object(obj[0], obj[1]))
    return b"".join(parts)


def write_cvff(path: str, scene: CVFFScene) -> None:
    """Serialize *scene* to a CradleViewer file (R17-T4a)."""
    Path(path).write_bytes(serialize_scene(scene))


# -- fresh-scene construction (SaveCradleViewer export path) -----------------


def make_props(kind, subtype=2, width=3.0, opacity=1.0, flag6=0, flag7=0,
               visible=1) -> CommonProps:
    """Common record values for freshly built blocks (identity matrix)."""
    return CommonProps(kind=kind, subtype=subtype, matrix=None, width=width,
                       opacity=opacity, flag6=flag6, flag7=flag7,
                       visible=visible)


def _f32_bytes(*values) -> bytes:
    return np.asarray(values, dtype="<f4").tobytes()


def _u32_bytes(*values) -> bytes:
    return struct.pack("<" + "I" * len(values), *(int(v) for v in values))


def _bbox_of(vertices):
    """f32-rounded ``(vmin, vsize)`` as stored in records 502/503."""
    v = np.asarray(vertices, dtype=np.float64).reshape(-1, 3)
    lo = v.min(axis=0).astype(np.float32).astype(np.float64)
    hi = v.max(axis=0).astype(np.float32).astype(np.float64)
    size = (hi - lo).astype(np.float32).astype(np.float64)
    return lo, size


def _split_faces(vertices, faces, limit=_U16_VERTEX_LIMIT):
    """Greedy face chunks with local vertex indices below *limit*.

    Multiple geometry blocks per tree group are legal (samples use them),
    so oversized groups are simply written as several POLY blocks sharing
    one tree kind; vertices shared across a chunk boundary are duplicated.
    """
    vertices = np.asarray(vertices, dtype=np.float64).reshape(-1, 3)
    if vertices.shape[0] <= limit:      # single chunk keeps vertex labels
        yield vertices, [list(f) for f in faces]
        return
    local: dict = {}
    chunk_v: list = []
    chunk_f: list = []
    for f in faces:
        fresh = [v for v in f if v not in local]
        if chunk_f and len(chunk_v) + len(fresh) > limit:
            yield np.asarray(chunk_v), chunk_f
            local, chunk_v, chunk_f = {}, [], []
            fresh = list(f)
        for v in fresh:
            local[v] = len(chunk_v)
            chunk_v.append(vertices[int(v)])
        chunk_f.append([local[v] for v in f])
    if chunk_f:
        yield np.asarray(chunk_v), chunk_f


def build_poly(kind, vertices, faces, color=0x7C7C7C, opacity=1.0) -> PolyMesh:
    """One POLY block from plain geometry (aux u16 fields -> 0)."""
    v = np.asarray(vertices, dtype=np.float64).reshape(-1, 3)
    if v.shape[0] == 0 or not faces:
        raise ValueError("empty poly group")
    if v.shape[0] > _U16_VERTEX_LIMIT:
        raise ValueError("too many vertices for one POLY block: %d"
                         % v.shape[0])
    lo, size = _bbox_of(v)
    props = make_props(kind, opacity=opacity)
    records = {0: common_payload(props)}
    records[500] = _u32_bytes(_POLY_STYLE)
    records[501] = _u32_bytes(color)
    records[502] = _f32_bytes(*lo)
    records[503] = _f32_bytes(*size)
    records[504] = encode_vertices(v, lo, size)
    records[509] = _u32_bytes(0xFFFFFFFF)
    sizes, idx = encode_faces(faces)
    records[505] = sizes
    records[506] = idx
    return PolyMesh(offset=-1, props=props, color=color, bbox_min=lo,
                    bbox_size=size, vertices=v,
                    face_sizes=np.frombuffer(sizes, dtype=np.uint8),
                    faces=[list(f) for f in faces], records=records)


def build_lines(kind, vertices, polylines, color=0x0000FF,
                opacity=0.5) -> PolyLines:
    """One LINE block from plain polylines (samples keep visible=0)."""
    v = np.asarray(vertices, dtype=np.float64).reshape(-1, 3)
    if v.shape[0] == 0 or not polylines:
        raise ValueError("empty line group")
    if v.shape[0] > _U16_VERTEX_LIMIT:
        raise ValueError("too many vertices for one LINE block: %d"
                         % v.shape[0])
    lo, size = _bbox_of(v)
    props = make_props(kind, opacity=opacity, visible=0)
    records = {0: common_payload(props)}
    records[500] = _u32_bytes(_LINE_STYLE)
    records[501] = _u32_bytes(1)
    records[502] = _f32_bytes(1.0)
    records[503] = _f32_bytes(1.0)
    records[504] = _f32_bytes(1.0)
    records[505] = _u32_bytes(color)
    records[506] = _f32_bytes(*lo)
    records[507] = _f32_bytes(*size)
    records[508] = encode_vertices(v, lo, size)
    sizes, idx = encode_faces(polylines)
    records[509] = sizes
    records[510] = idx
    return PolyLines(offset=-1, props=props, color=color, bbox_min=lo,
                    bbox_size=size, vertices=v,
                    seg_sizes=np.frombuffer(sizes, dtype=np.uint8),
                    polylines=[list(p) for p in polylines], records=records)


def build_marker(kind) -> PointMarker:
    """Group anchor marker (full 330B PNT template from AR samples)."""
    props = make_props(kind, opacity=0.5, visible=0)
    records = {0: common_payload(props),
               500: _u32_bytes(0x881),
               501: _u32_bytes(0x00FF00),
               502: _u32_bytes(0xFFFFFF),
               503: _u32_bytes(0),
               504: _u32_bytes(7),
               505: bytes(24),
               506: _u32_bytes(0x888888, 0x888888)}
    return PointMarker(offset=-1, props=props, style=0x881, color=0x00FF00,
                       position=np.zeros(3), records=records)


def build_field_settings(model_range, camera_eye, camera_target,
                         camera_up) -> FieldSettings:
    """FLD block: model range + camera (template flags from samples)."""
    props = make_props(2, subtype=2, width=3.0, opacity=1.0, visible=0)
    records = {0: common_payload(props),
               500: _f32_bytes(*model_range),
               501: _u32_bytes(1), 502: _u32_bytes(1), 503: _u32_bytes(1),
               504: _u32_bytes(0xFFFFFF),
               505: _u32_bytes(1), 506: _u32_bytes(0), 507: _u32_bytes(0),
               508: _f32_bytes(1.0),
               509: _f32_bytes(*camera_eye, *camera_target, *camera_up),
               510: _f32_bytes(0.0, 0.0, 1.0, 1.0)}
    return FieldSettings(offset=-1, props=props,
                         model_range=np.asarray(model_range, dtype=float),
                         camera_eye=np.asarray(camera_eye, dtype=float),
                         camera_target=np.asarray(camera_target, dtype=float),
                         camera_up=np.asarray(camera_up, dtype=float),
                         viewport=np.array([0.0, 0.0, 1.0, 1.0]),
                         records=records)


def build_light() -> Light:
    """Default light (AR02 LIGH template: kind=8 maps to no tree node)."""
    props = make_props(8, subtype=-1, width=-1.0, opacity=0.5, flag6=1,
                       visible=0)
    records = {0: common_payload(props),
               500: _f32_bytes(180.0),
               501: _f32_bytes(0.5, 0.5, 0.5),
               502: _f32_bytes(0.3, 0.3, 0.3),
               503: _f32_bytes(1.0, 1.0, 1.0),
               504: _f32_bytes(30.0, 1.0),
               505: _f32_bytes(0.1, 0.1, 3.0),
               506: _f32_bytes(-0.1, -0.1, -3.0)}
    return Light(offset=-1, props=props,
                 ambient=np.full(3, 0.5), diffuse=np.full(3, 0.3),
                 specular=np.full(3, 1.0),
                 direction=np.array([0.1, 0.1, 3.0]), records=records)


def build_env() -> GenericObject:
    """Global environment block (AR sample template)."""
    props = make_props(0, subtype=-1, width=-1.0, opacity=0.5, flag6=1,
                       visible=0)
    records = {0: common_payload(props),
               500: _u32_bytes(2), 501: _u32_bytes(0), 502: _f32_bytes(0.3),
               503: _u32_bytes(868, 600), 504: _u32_bytes(1),
               505: _u32_bytes(0), 506: _u32_bytes(0xFFFFFF),
               509: _u32_bytes(10)}
    return GenericObject(-1, "ENV", props, records)


def build_logo() -> GenericObject:
    """Global logo block: common record only (222B in samples)."""
    props = make_props(0, subtype=-1, width=-1.0, opacity=0.5, flag6=1,
                       visible=0)
    return GenericObject(-1, "LOGO", props, {0: common_payload(props)})


def build_encd() -> GenericObject:
    """Leading ENCD block: single ``(500, 4, 1)`` encoding record."""
    return GenericObject(-1, "ENCD", CommonProps(), {500: _u32_bytes(1)})


def _default_camera(model_range):
    """Sensible eye/target/up for a model range (AR-sample-like framing)."""
    r = np.asarray(model_range, dtype=np.float64)
    lo, hi = r[::2], r[1::2]
    c = (lo + hi) / 2.0
    diag = float(np.linalg.norm(hi - lo)) or 1.0
    d = np.array([-0.45, -0.85, 0.40])
    d = d / np.linalg.norm(d)
    eye = c + d * diag * 1.3
    return eye, c, np.array([0.0, 0.0, 1.0])


def build_scene(groups, model_range=None, version=2) -> CVFFScene:
    """Build a fresh scene from geometry groups (SaveCradleViewer path).

    *groups* is a list of ``(name, vertices, faces)`` where *vertices* is
    an ``(N, 3)`` array and *faces* a list of vertex-index lists.  Group
    *i* becomes tree kind ``3 + i`` under the FLD root; groups larger than
    65535 vertices are automatically split into several POLY blocks.
    """
    scene = CVFFScene(path="", version=version, writer_id=WRITER_ID)
    seq = 0

    def add(tag, obj):
        nonlocal seq
        seq -= 1
        obj.offset = seq
        scene.blocks.append((seq, tag, 0))
        return obj

    scene.others.append(add("ENCD", build_encd()))
    stacked = [np.asarray(g[1], dtype=float).reshape(-1, 3) for g in groups]
    stacked = [v for v in stacked if v.shape[0]]
    if model_range is None:
        if not stacked:
            raise ValueError("no geometry: model_range required")
        pts = np.vstack(stacked)
        lo, hi = pts.min(axis=0), pts.max(axis=0)
        model_range = [lo[0], hi[0], lo[1], hi[1], lo[2], hi[2]]
    eye, target, up = _default_camera(model_range)
    scene.field_settings = add("FLD ", build_field_settings(
        model_range, eye, target, up))
    scene.others.append(add("LOGO", build_logo()))
    scene.env = add("ENV ", build_env())
    for i, (name, verts, faces) in enumerate(groups):
        kind = 3 + i
        n_blocks = 0
        for cv, cf in _split_faces(verts, faces):
            scene.polys.append(add("POLY", build_poly(kind, cv, cf)))
            n_blocks += 1
        if n_blocks:
            scene.markers.append(add("PNT ", build_marker(kind)))
    scene.lights.append(add("LIGH", build_light()))
    tree = [TreeEntry("FLD", 2, 4, -1, 1)]
    for i, (name, _v, _f) in enumerate(groups):
        tree.append(TreeEntry(name, 3 + i, 6 + i, 4, 5))
    tree.append(TreeEntry("Global", -1, 6 + len(groups), -1, 2))
    scene.tree = tree
    seq -= 1
    scene.blocks.append((seq, "TREE", 0))
    return scene

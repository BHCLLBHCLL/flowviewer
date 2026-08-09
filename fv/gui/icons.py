"""QPainter vector icons for FlowViewer (adapted from cabdecoding AppIcons)."""

from __future__ import annotations

import math

try:
    from PyQt5.QtCore import QPoint, QPointF, QRectF, Qt
    from PyQt5.QtGui import (
        QBrush, QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap,
        QPolygon,
    )
    _HAS_QT = True
except Exception:  # pragma: no cover
    _HAS_QT = False
    QIcon = object  # type: ignore


class AppIcons:
    """Lightweight vector icons for toolbars / trees / dialogs."""

    _cache: dict[tuple, QIcon] = {}

    @classmethod
    def get(cls, name: str, size: int = 20) -> QIcon:
        if not _HAS_QT:
            return QIcon()
        key = (name, size)
        if key not in cls._cache:
            cls._cache[key] = QIcon(cls._paint(name, size))
        return cls._cache[key]

    @classmethod
    def _paint(cls, name: str, size: int) -> QPixmap:
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        m = max(1, size // 10)
        r = QRectF(m, m, size - 2 * m, size - 2 * m)
        drawer = getattr(cls, f"_draw_{name}", None)
        if drawer:
            drawer(p, r, size)
        else:
            cls._draw_generic(p, r)
        p.end()
        return pm

    @staticmethod
    def _pen(color, w=1.6):
        pen = QPen(QColor(color))
        pen.setWidthF(w)
        pen.setJoinStyle(Qt.RoundJoin)
        pen.setCapStyle(Qt.RoundCap)
        return pen

    @classmethod
    def _draw_generic(cls, p, r, _s=0):
        p.setPen(cls._pen("#555"))
        p.setBrush(QBrush(QColor("#dde3ea")))
        p.drawRoundedRect(r, 3, 3)

    @classmethod
    def _draw_new(cls, p, r, _s):
        p.setPen(cls._pen("#455a64", 1.3))
        p.setBrush(QBrush(QColor("#eceff1")))
        p.drawRoundedRect(r.adjusted(2, 0, -2, 0), 2, 2)
        p.setPen(cls._pen("#2e7d32", 2.0))
        cx, cy = r.center().x(), r.center().y()
        p.drawLine(QPointF(cx, cy - r.height() * 0.28),
                   QPointF(cx, cy + r.height() * 0.28))
        p.drawLine(QPointF(cx - r.width() * 0.28, cy),
                   QPointF(cx + r.width() * 0.28, cy))

    @classmethod
    def _draw_open(cls, p, r, _s):
        p.setPen(cls._pen("#2e75b6", 1.4))
        p.setBrush(QBrush(QColor("#f4c542")))
        tab = QRectF(r.left(), r.top(), r.width() * 0.45, r.height() * 0.28)
        p.drawRoundedRect(tab, 2, 2)
        body = QRectF(r.left(), r.top() + r.height() * 0.22,
                      r.width(), r.height() * 0.72)
        p.setBrush(QBrush(QColor("#ffd966")))
        p.drawRoundedRect(body, 2, 2)

    @classmethod
    def _draw_save(cls, p, r, _s):
        p.setPen(cls._pen("#1f4e79", 1.3))
        p.setBrush(QBrush(QColor("#5b9bd5")))
        p.drawRoundedRect(r, 2, 2)
        p.setBrush(QBrush(QColor("#fff")))
        slot = QRectF(r.left() + r.width() * 0.22, r.top(),
                      r.width() * 0.56, r.height() * 0.38)
        p.drawRect(slot)
        p.setBrush(QBrush(QColor("#eaf2fb")))
        label = QRectF(r.left() + r.width() * 0.18,
                       r.top() + r.height() * 0.48,
                       r.width() * 0.64, r.height() * 0.42)
        p.drawRoundedRect(label, 1, 1)

    @classmethod
    def _draw_print(cls, p, r, _s):
        p.setPen(cls._pen("#37474f", 1.2))
        p.setBrush(QBrush(QColor("#90a4ae")))
        p.drawRoundedRect(r.adjusted(0, r.height() * 0.22, 0, -r.height() * 0.15),
                          2, 2)
        p.setBrush(QBrush(QColor("#eceff1")))
        p.drawRect(r.adjusted(r.width() * 0.18, 0,
                              -r.width() * 0.18, -r.height() * 0.55))
        p.setBrush(QBrush(QColor("#fff")))
        p.drawRect(r.adjusted(r.width() * 0.2, r.height() * 0.55,
                              -r.width() * 0.2, -r.height() * 0.05))

    @classmethod
    def _draw_fit(cls, p, r, _s):
        p.setPen(cls._pen("#37474f", 1.6))
        p.setBrush(Qt.NoBrush)
        s = r.width() * 0.28
        corners = [
            (r.left(), r.top(), 1, 1),
            (r.right(), r.top(), -1, 1),
            (r.left(), r.bottom(), 1, -1),
            (r.right(), r.bottom(), -1, -1),
        ]
        for x, y, sx, sy in corners:
            p.drawLine(QPoint(int(x), int(y)), QPoint(int(x + sx * s), int(y)))
            p.drawLine(QPoint(int(x), int(y)), QPoint(int(x), int(y + sy * s)))
        p.setBrush(QBrush(QColor("#90a4ae")))
        p.drawEllipse(r.adjusted(r.width() * 0.28, r.height() * 0.28,
                                 -r.width() * 0.28, -r.height() * 0.28))

    @classmethod
    def _draw_show_all(cls, p, r, _s):
        p.setPen(cls._pen("#ef6c00", 1.3))
        p.setBrush(QBrush(QColor("#ffe0b2")))
        p.drawEllipse(r.adjusted(r.width() * 0.15, r.height() * 0.2,
                                 -r.width() * 0.15, -r.height() * 0.15))
        p.setBrush(QBrush(QColor("#fff")))
        eye = QRectF(r.center().x() - r.width() * 0.12,
                     r.center().y() - r.height() * 0.08,
                     r.width() * 0.24, r.height() * 0.24)
        p.drawEllipse(eye)
        p.setBrush(QBrush(QColor("#333")))
        p.drawEllipse(eye.adjusted(eye.width() * 0.3, eye.height() * 0.3,
                                   -eye.width() * 0.3, -eye.height() * 0.3))

    @classmethod
    def _draw_display(cls, p, r, _s):
        p.setPen(cls._pen("#5d4037", 1.2))
        p.setBrush(QBrush(QColor(100, 149, 237, 120)))
        p.drawEllipse(r)
        p.setBrush(QBrush(QColor("#5c6bc0")))
        p.drawEllipse(r.adjusted(r.width() * 0.35, r.height() * 0.35,
                                 -r.width() * 0.05, -r.height() * 0.05))

    @classmethod
    def _draw_draw(cls, p, r, _s):
        """scPOST redraw mallet on the settings splitter grip."""
        # Handle (yellow)
        p.setPen(cls._pen("#f9a825", 1.2))
        p.setBrush(QBrush(QColor("#ffeb3b")))
        handle = QRectF(r.left() + r.width() * 0.08,
                        r.top() + r.height() * 0.12,
                        r.width() * 0.55, r.height() * 0.38)
        p.drawRoundedRect(handle, 2, 2)
        # Shaft (blue-grey)
        p.setPen(cls._pen("#1565c0", 1.4))
        p.setBrush(QBrush(QColor("#42a5f5")))
        shaft = QRectF(r.center().x() - r.width() * 0.08,
                       r.top() + r.height() * 0.4,
                       r.width() * 0.16, r.height() * 0.52)
        p.drawRoundedRect(shaft, 1, 1)

    @classmethod
    def _draw_contour(cls, p, r, _s):
        p.setPen(cls._pen("#1565c0", 1.2))
        p.setBrush(QBrush(QColor("#bbdefb")))
        p.drawEllipse(r)
        for i, col in enumerate(("#ef5350", "#ffee58", "#66bb6a", "#42a5f5")):
            p.setPen(cls._pen(col, 1.6))
            y = r.top() + r.height() * (0.25 + i * 0.18)
            p.drawLine(QPointF(r.left() + 3, y), QPointF(r.right() - 3, y))

    @classmethod
    def _draw_surface(cls, p, r, _s):
        p.setPen(cls._pen("#0277bd", 1.2))
        p.setBrush(QBrush(QColor("#81d4fa")))
        poly = QPolygon([
            QPoint(int(r.left() + r.width() * 0.08), int(r.bottom() - 1)),
            QPoint(int(r.left() + r.width() * 0.35), int(r.top() + 1)),
            QPoint(int(r.right() - 1), int(r.top() + 1)),
            QPoint(int(r.right() - r.width() * 0.27), int(r.bottom() - 1)),
        ])
        p.drawPolygon(poly)

    @classmethod
    def _draw_plane(cls, p, r, label="P"):
        p.setPen(cls._pen("#546e7a", 1.2))
        p.setBrush(QBrush(QColor("#c8e6c9")))
        p.drawRect(r.adjusted(2, 2, -2, -2))
        p.setPen(cls._pen("#263238", 1.0))
        p.setFont(QFont("Arial", max(6, int(r.height() * 0.35))))
        p.drawText(r.toRect(), Qt.AlignCenter, label)

    @classmethod
    def _draw_plane_xy(cls, p, r, _s):
        cls._draw_plane(p, r, "XY")

    @classmethod
    def _draw_plane_xz(cls, p, r, _s):
        cls._draw_plane(p, r, "XZ")

    @classmethod
    def _draw_plane_yz(cls, p, r, _s):
        cls._draw_plane(p, r, "YZ")

    @classmethod
    def _draw_isosurface(cls, p, r, _s):
        p.setPen(cls._pen("#6a1b9a", 1.3))
        p.setBrush(QBrush(QColor("#ce93d8")))
        path = QPainterPath()
        path.moveTo(r.left(), r.center().y())
        path.cubicTo(r.left() + r.width() * 0.3, r.top(),
                     r.left() + r.width() * 0.7, r.bottom(),
                     r.right(), r.center().y())
        path.cubicTo(r.left() + r.width() * 0.7, r.top() + r.height() * 0.2,
                     r.left() + r.width() * 0.3, r.bottom() - r.height() * 0.2,
                     r.left(), r.center().y())
        p.drawPath(path)

    @classmethod
    def _draw_streamline(cls, p, r, _s):
        p.setPen(cls._pen("#00838f", 1.8))
        p.setBrush(Qt.NoBrush)
        path = QPainterPath()
        path.moveTo(r.left(), r.bottom() - 2)
        path.cubicTo(r.left() + r.width() * 0.3, r.top(),
                     r.left() + r.width() * 0.6, r.bottom(),
                     r.right() - 2, r.top() + 2)
        p.drawPath(path)
        tip = QPolygon([
            QPoint(int(r.right()), int(r.top() + 2)),
            QPoint(int(r.right() - r.width() * 0.28), int(r.top())),
            QPoint(int(r.right() - r.width() * 0.18),
                   int(r.top() + r.height() * 0.32)),
        ])
        p.setBrush(QBrush(QColor("#00838f")))
        p.setPen(Qt.NoPen)
        p.drawPolygon(tip)

    @classmethod
    def _draw_volume(cls, p, r, _s):
        p.setPen(cls._pen("#1565c0", 1.2))
        p.setBrush(QBrush(QColor("#90caf9")))
        p.drawRect(r.adjusted(r.width() * 0.15, r.height() * 0.25,
                              -r.width() * 0.05, -r.height() * 0.05))
        p.setBrush(QBrush(QColor("#64b5f6")))
        top = QPolygon([
            QPoint(int(r.left() + r.width() * 0.15),
                   int(r.top() + r.height() * 0.25)),
            QPoint(int(r.left() + r.width() * 0.35),
                   int(r.top() + r.height() * 0.05)),
            QPoint(int(r.right() - r.width() * 0.05),
                   int(r.top() + r.height() * 0.05)),
            QPoint(int(r.right() - r.width() * 0.05),
                   int(r.top() + r.height() * 0.25)),
        ])
        p.drawPolygon(top)

    @classmethod
    def _draw_vector(cls, p, r, _s):
        p.setPen(cls._pen("#c62828", 1.8))
        p.drawLine(QPointF(r.left() + 2, r.bottom() - 2),
                   QPointF(r.right() - 2, r.top() + 2))
        tip = QPolygon([
            QPoint(int(r.right() - 1), int(r.top() + 1)),
            QPoint(int(r.right() - r.width() * 0.35), int(r.top() + 1)),
            QPoint(int(r.right() - 1), int(r.top() + r.height() * 0.35)),
        ])
        p.setBrush(QBrush(QColor("#c62828")))
        p.setPen(Qt.NoPen)
        p.drawPolygon(tip)

    @classmethod
    def _draw_colorbar(cls, p, r, _s):
        colors = ["#313695", "#4575b4", "#74add1", "#fee090", "#f46d43", "#a50026"]
        h = r.height() / len(colors)
        p.setPen(Qt.NoPen)
        for i, c in enumerate(colors):
            p.setBrush(QBrush(QColor(c)))
            p.drawRect(QRectF(r.left() + r.width() * 0.25, r.top() + i * h,
                              r.width() * 0.5, h + 0.5))
        p.setPen(cls._pen("#37474f", 1.0))
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(r.left() + r.width() * 0.25, r.top(),
                          r.width() * 0.5, r.height()))

    @classmethod
    def _draw_point(cls, p, r, _s):
        p.setPen(cls._pen("#ef6c00", 1.2))
        p.setBrush(QBrush(QColor("#ffb74d")))
        p.drawEllipse(r.adjusted(r.width() * 0.25, r.height() * 0.25,
                                 -r.width() * 0.25, -r.height() * 0.25))

    @classmethod
    def _draw_camera(cls, p, r, _s):
        p.setPen(cls._pen("#455a64", 1.2))
        p.setBrush(QBrush(QColor("#90a4ae")))
        p.drawRoundedRect(r.adjusted(0, r.height() * 0.2, 0, -r.height() * 0.1),
                          2, 2)
        p.setBrush(QBrush(QColor("#eceff1")))
        p.drawEllipse(r.adjusted(r.width() * 0.28, r.height() * 0.28,
                                 -r.width() * 0.28, -r.height() * 0.18))
        p.setBrush(QBrush(QColor("#546e7a")))
        p.drawRect(QRectF(r.left() + r.width() * 0.55, r.top(),
                          r.width() * 0.25, r.height() * 0.22))

    @classmethod
    def _draw_option(cls, p, r, _s):
        p.setPen(cls._pen("#546e7a", 1.4))
        p.setBrush(QBrush(QColor("#cfd8dc")))
        cx, cy = r.center().x(), r.center().y()
        rad = min(r.width(), r.height()) * 0.28
        p.drawEllipse(QPointF(cx, cy), rad, rad)
        for ang in range(0, 360, 45):
            a = math.radians(ang)
            x1 = cx + math.cos(a) * rad * 1.15
            y1 = cy + math.sin(a) * rad * 1.15
            x2 = cx + math.cos(a) * rad * 1.55
            y2 = cy + math.sin(a) * rad * 1.55
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    @classmethod
    def _draw_unit(cls, p, r, _s):
        p.setPen(cls._pen("#1565c0", 1.2))
        p.setBrush(QBrush(QColor("#bbdefb")))
        p.drawRoundedRect(r, 2, 2)
        p.setPen(cls._pen("#0d47a1", 1.3))
        p.setFont(QFont("Arial", max(6, int(r.height() * 0.4))))
        p.drawText(r.toRect(), Qt.AlignCenter, "U")

    @classmethod
    def _draw_select(cls, p, r, _s):
        p.setPen(cls._pen("#37474f", 1.4))
        path = QPainterPath()
        path.moveTo(r.left() + 2, r.top() + 2)
        path.lineTo(r.left() + 2, r.bottom() - 2)
        path.lineTo(r.left() + r.width() * 0.35, r.top() + r.height() * 0.55)
        path.lineTo(r.left() + r.width() * 0.55, r.bottom() - 2)
        path.lineTo(r.right() - 2, r.top() + r.height() * 0.35)
        path.closeSubpath()
        p.setBrush(QBrush(QColor("#eceff1")))
        p.drawPath(path)

    @classmethod
    def _draw_rotate(cls, p, r, _s):
        p.setPen(cls._pen("#1565c0", 2.0))
        p.setBrush(Qt.NoBrush)
        p.drawArc(r.toRect(), 30 * 16, 300 * 16)

    @classmethod
    def _draw_pan(cls, p, r, _s):
        p.setPen(cls._pen("#455a64", 1.6))
        cx, cy = r.center().x(), r.center().y()
        p.drawLine(QPoint(int(r.left() + 2), int(cy)),
                   QPoint(int(r.right() - 2), int(cy)))
        p.drawLine(QPoint(int(cx), int(r.top() + 2)),
                   QPoint(int(cx), int(r.bottom() - 2)))

    @classmethod
    def _draw_zoom(cls, p, r, _s):
        p.setPen(cls._pen("#37474f", 1.4))
        p.setBrush(Qt.NoBrush)
        circ = r.adjusted(0, 0, -r.width() * 0.25, -r.height() * 0.25)
        p.drawEllipse(circ)
        p.drawLine(QPoint(int(circ.right() - 1), int(circ.bottom() - 1)),
                   QPoint(int(r.right() - 1), int(r.bottom() - 1)))

    @classmethod
    def _draw_play(cls, p, r, _s):
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor("#2e7d32")))
        tri = QPolygon([
            QPoint(int(r.left() + r.width() * 0.25), int(r.top() + 2)),
            QPoint(int(r.left() + r.width() * 0.25), int(r.bottom() - 2)),
            QPoint(int(r.right() - 2), int(r.center().y())),
        ])
        p.drawPolygon(tri)

    @classmethod
    def _draw_pause(cls, p, r, _s):
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor("#ef6c00")))
        w = r.width() * 0.22
        p.drawRect(QRectF(r.left() + r.width() * 0.22, r.top() + 2,
                          w, r.height() - 4))
        p.drawRect(QRectF(r.right() - r.width() * 0.22 - w, r.top() + 2,
                          w, r.height() - 4))

    @classmethod
    def _draw_stop(cls, p, r, _s):
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor("#c62828")))
        p.drawRect(r.adjusted(r.width() * 0.2, r.height() * 0.2,
                              -r.width() * 0.2, -r.height() * 0.2))

    @classmethod
    def _draw_prev(cls, p, r, _s):
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor("#455a64")))
        p.drawRect(QRectF(r.left() + 2, r.top() + 2, r.width() * 0.18,
                          r.height() - 4))
        tri = QPolygon([
            QPoint(int(r.right() - 2), int(r.top() + 2)),
            QPoint(int(r.right() - 2), int(r.bottom() - 2)),
            QPoint(int(r.left() + r.width() * 0.28), int(r.center().y())),
        ])
        p.drawPolygon(tri)

    @classmethod
    def _draw_next(cls, p, r, _s):
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor("#455a64")))
        p.drawRect(QRectF(r.right() - r.width() * 0.18 - 2, r.top() + 2,
                          r.width() * 0.18, r.height() - 4))
        tri = QPolygon([
            QPoint(int(r.left() + 2), int(r.top() + 2)),
            QPoint(int(r.left() + 2), int(r.bottom() - 2)),
            QPoint(int(r.right() - r.width() * 0.28), int(r.center().y())),
        ])
        p.drawPolygon(tri)

    @classmethod
    def _draw_project(cls, p, r, _s):
        p.setPen(cls._pen("#455a64", 1.2))
        p.setBrush(QBrush(QColor("#cfd8dc")))
        p.drawRoundedRect(r, 2, 2)
        p.setPen(cls._pen("#263238", 1.0))
        for i in range(3):
            y = r.top() + r.height() * (0.28 + i * 0.22)
            p.drawLine(QPoint(int(r.left() + 3), int(y)),
                       QPoint(int(r.right() - 3), int(y)))

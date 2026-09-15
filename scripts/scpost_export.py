"""Export reference values from scPOST via COM (R117).

Writes JSON: node coordinates + one scalar variable, sampled at a stride so a
few hundred points are enough to catch a wrong decode without a per-node COM
loop over the whole mesh.
"""
import argparse
import json
import sys
import time

import win32com.client as w

PROGID = 'scPOST_Dx64net.Application.2025'


def export(path, variable, stride, limit, out):
    app = w.Dispatch(PROGID)
    try:
        app.Visible = False
    except Exception:
        pass
    fld = app.CreateObjectFLD(path)
    if not fld:
        raise SystemExit('scPOST could not open ' + path)

    n_nodes = int(fld.GetNodeCount(1))
    print('nodes reported by scPOST:', n_nodes, flush=True)
    ids = list(range(1, n_nodes + 1, stride))[:limit]

    t0 = time.time()
    pts, vals = [], []
    for nid in ids:
        r = fld.GetNodeXYZ(nid)
        s = fld.GetScalar(variable, 1, nid)
        pts.append([float(r[0]), float(r[1]), float(r[2])])
        vals.append(float(s))
    dt = time.time() - t0
    print('read %d samples in %.1fs (%.1f ms each)'
          % (len(ids), dt, 1000 * dt / max(1, len(ids))), flush=True)

    payload = {'source': path, 'variable': variable, 'stride': stride,
               'n_nodes': n_nodes, 'ids': ids, 'points': pts, 'values': vals}
    with open(out, 'w', encoding='utf-8') as fh:
        json.dump(payload, fh)
    print('wrote', out, flush=True)
    try:
        app.Quit()
    except Exception:
        pass
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('path')
    ap.add_argument('variable')
    ap.add_argument('out')
    ap.add_argument('--stride', type=int, default=97)
    ap.add_argument('--limit', type=int, default=300)
    a = ap.parse_args(argv)
    return export(a.path, a.variable, a.stride, a.limit, a.out)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

"""Material helpers: scPOST Luster / Water sheen mapping (P1.4)."

Luster boosts the specular highlight (glossy paint look); Water uses a
stronger, tighter highlight (wet look).  Applied to any vtkProperty.
"""


def apply_sheen(prop, luster: bool = False, water: bool = False) -> None:
    """Map Luster / Water flags onto a vtkProperty (P1.4).

    ``vtkVolumeProperty`` exposes only a subset of the vtkProperty API
    (no ``SetInterpolationToPhong`` / ``SetSpecularColor``), so those
    calls are guarded — the specular intensity/power still apply.
    """
    if hasattr(prop, "SetInterpolationToPhong"):
        prop.SetInterpolationToPhong()
    if water:
        prop.SetSpecular(0.9)
        prop.SetSpecularPower(60.0)
        if hasattr(prop, "SetSpecularColor"):
            prop.SetSpecularColor(1.0, 1.0, 1.0)
    elif luster:
        prop.SetSpecular(0.5)
        prop.SetSpecularPower(20.0)
        if hasattr(prop, "SetSpecularColor"):
            prop.SetSpecularColor(1.0, 1.0, 1.0)
    else:
        prop.SetSpecular(0.0)
        prop.SetSpecularPower(1.0)

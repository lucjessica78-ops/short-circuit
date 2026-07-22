"""
An American-standard (AWG / kcmil) cable library, for copper and aluminum
conductors, since pandapower's built-in std_type library only ships European
(IEC) cable types.

These R/X values are computed from physics, not copied from any single
manufacturer's or code-book's table:
  - Resistance: from each material's resistivity at an assumed 75C conductor
    operating temperature, and the conductor's cross-sectional area (derived
    from the standard AWG geometric formula for AWG sizes, or directly from
    the kcmil definition for the larger commercial sizes).
  - Reactance: from the standard single-conductor inductance formula,
    assuming conductors are grouped tightly together (~1 inch spacing), which
    is representative of conductors sharing a conduit or tray -- the common
    American low-voltage installation method.

This is a reasonable engineering approximation for short-circuit studies, not
a substitute for a specific manufacturer's cable datasheet. Actual reactance
in particular is sensitive to real installation geometry (conduit material,
conductor spacing, trefoil vs. flat arrangement); if you have datasheet
values for a specific cable, prefer those.
"""
import math

_CMIL_TO_M2 = 5.067e-10          # 1 circular mil in square meters
_COPPER_RESISTIVITY_75C = 2.043e-8    # ohm*m, copper at ~75C
_ALUMINUM_RESISTIVITY_75C = 3.445e-8  # ohm*m, aluminum at ~75C
_ASSUMED_SPACING_M = 0.0254       # ~1 inch: conductors grouped in conduit/tray
_GMR_FACTOR = 0.7788              # self-GMR factor for a solid round conductor
_FREQ_HZ = 60.0

# (display size, AWG gauge number). Gauge numbers follow the standard AWG
# progression; 1/0, 2/0, 3/0, 4/0 correspond to gauge numbers 0, -1, -2, -3.
_AWG_SIZES = [
    ("14 AWG", 14), ("12 AWG", 12), ("10 AWG", 10), ("8 AWG", 8),
    ("6 AWG", 6), ("4 AWG", 4), ("3 AWG", 3), ("2 AWG", 2), ("1 AWG", 1),
    ("1/0 AWG", 0), ("2/0 AWG", -1), ("3/0 AWG", -2), ("4/0 AWG", -3),
]

# (display size, area in circular mils). kcmil sizes are defined directly by
# area, not by the AWG gauge formula.
_KCMIL_SIZES = [
    ("250 kcmil", 250_000), ("300 kcmil", 300_000), ("350 kcmil", 350_000),
    ("400 kcmil", 400_000), ("500 kcmil", 500_000), ("600 kcmil", 600_000),
    ("750 kcmil", 750_000), ("1000 kcmil", 1_000_000),
]


def _awg_area_cmil(gauge_number):
    d_inch = 0.005 * 92 ** ((36 - gauge_number) / 39)
    d_mil = d_inch * 1000
    return d_mil ** 2


def _build_library():
    lib = {}
    material_prefix = {"Copper": "CU", "Aluminum": "AL"}
    for material, resistivity in (("Copper", _COPPER_RESISTIVITY_75C),
                                   ("Aluminum", _ALUMINUM_RESISTIVITY_75C)):
        for label, spec in _AWG_SIZES + _KCMIL_SIZES:
            area_cmil = spec if spec > 1000 else _awg_area_cmil(spec)
            area_m2 = area_cmil * _CMIL_TO_M2
            r_ohm_per_km = resistivity * 1000 / area_m2

            radius_m = math.sqrt(area_m2 / math.pi)
            gmr_m = radius_m * _GMR_FACTOR
            x_ohm_per_km = 2 * math.pi * _FREQ_HZ * (2e-7 * math.log(_ASSUMED_SPACING_M / gmr_m)) * 1000

            key = f"{material_prefix[material]}_{label.replace(' ', '_').replace('/', '-')}"
            lib[key] = {
                "key": key,
                "label": f"{label} ({material})",
                "material": material,
                "size": label,
                "r_ohm_per_km": round(r_ohm_per_km, 5),
                "x_ohm_per_km": round(x_ohm_per_km, 5),
                # C has negligible effect on short-circuit current magnitude at
                # power frequency for cable lengths typical of these studies;
                # this is a nominal placeholder rather than a measured value.
                "c_nf_per_km": 200.0,
                # Ampacity is not used by the short-circuit calculation itself
                # (only R/X matter for fault current) -- this is a rough
                # placeholder for loading-percent display only. For actual
                # ampacity/code-compliance decisions, use NEC Table 310.16 (or
                # the applicable table for the installation method) rather
                # than this value.
                "max_i_ka": round(max(area_cmil / 250_000, 0.05), 3),
            }
    return lib


CABLE_LIBRARY = _build_library()


def cable_choices():
    """List of {key, label} for populating a dropdown, sorted by material then size."""
    return [{"key": v["key"], "label": v["label"]} for v in CABLE_LIBRARY.values()]

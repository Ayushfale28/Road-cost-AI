"""
Quantity calculation engine for the Road Cost Estimator.

This module performs deterministic arithmetic only. The AI never
calculates a quantity itself -- it only helps identify which SSR items
are relevant. Every formula here is a plain, auditable calculation from
project measurements supplied by the user/engineer.
"""

from dataclasses import dataclass


@dataclass
class ProjectMeasurements:
    """All measurements the user/engineer may supply for a project."""

    length_m: float = 0.0
    width_m: float = 0.0
    thickness_mm: float = 0.0

    pothole_count: int = 0
    pothole_avg_length_m: float = 0.0
    pothole_avg_width_m: float = 0.0
    pothole_avg_depth_m: float = 0.0

    drain_length_m: float = 0.0

    lead_distance_km: float = 0.0
    traffic_type: str = ""
    soil_condition: str = ""

    @property
    def pothole_area_m2(self) -> float:
        return self.pothole_count * self.pothole_avg_length_m * self.pothole_avg_width_m

    @property
    def pothole_volume_m3(self) -> float:
        return (
            self.pothole_count
            * self.pothole_avg_length_m
            * self.pothole_avg_width_m
            * self.pothole_avg_depth_m
        )


def _is_pothole_item(description: str, chapter: str) -> bool:
    text = f"{description} {chapter}".lower()
    return "pothole" in text or ("patch" in text and "repair" in text)


def _is_drainage_item(description: str) -> bool:
    text = description.lower()
    return any(word in text for word in ("drain", "kerb", "curb"))


def calculate_quantity(kind: str, description: str, chapter: str, m: ProjectMeasurements) -> float:
    """
    Calculate a quantity for one SSR row. Returns 0.0 when there is not
    enough information (the caller should treat 0.0 as "needs manual
    entry", not as a real zero quantity).
    """

    if kind == "area":
        if m.pothole_count > 0 and _is_pothole_item(description, chapter):
            return round(m.pothole_area_m2, 3)
        return round(m.length_m * m.width_m, 3)

    if kind == "volume":
        if m.pothole_count > 0 and _is_pothole_item(description, chapter):
            return round(m.pothole_volume_m3, 3)
        thickness_m = m.thickness_mm / 1000
        if thickness_m <= 0:
            return 0.0
        return round(m.length_m * m.width_m * thickness_m, 3)

    if kind == "length":
        if m.drain_length_m > 0 and _is_drainage_item(description):
            return round(m.drain_length_m, 3)
        return round(m.length_m, 3)

    if kind == "km":
        return round(m.length_m / 1000, 3)

    if kind == "nos":
        if m.pothole_count > 0 and "pothole" in description.lower():
            return float(m.pothole_count)
        return 0.0

    # "weight" and "unknown" units need a project-specific conversion
    # (material density, mix design, etc.) that we must not invent.
    return 0.0


def quantity_note(kind: str, quantity: float) -> str:
    """A short, human-readable note explaining where a quantity came from."""
    if quantity > 0:
        return {
            "area": "length x width (or measured pothole area)",
            "volume": "length x width x thickness (or measured pothole volume)",
            "length": "project length (or drain/kerb length)",
            "km": "length / 1000",
            "nos": "pothole count",
        }.get(kind, "calculated")
    if kind in ("weight", "unknown"):
        return "needs manual entry -- no safe automatic formula for this unit"
    return "needs manual entry -- missing measurement"

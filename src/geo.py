"""Offline province lookup for approximate CER incident coordinates.

Uses the openly licensed NRCan small-scale province basemap. A non-match is
a review flag, never a correction: source coordinates and coastlines are
approximate. No proprietary pipeline-route geometry is used.
"""
from __future__ import annotations

import json
import math
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/source"
PROVINCES = {
    1: ("AB", "Alberta", "Alberta"),
    2: ("BC", "British Columbia", "Colombie-Britannique"),
    3: ("MB", "Manitoba", "Manitoba"),
    4: ("NB", "New Brunswick", "Nouveau-Brunswick"),
    5: ("NL", "Newfoundland and Labrador", "Terre-Neuve-et-Labrador"),
    6: ("NT", "Northwest Territories", "Territoires du Nord-Ouest"),
    7: ("NS", "Nova Scotia", "Nouvelle-Écosse"),
    8: ("NU", "Nunavut", "Nunavut"),
    9: ("ON", "Ontario", "Ontario"),
    10: ("PE", "Prince Edward Island", "Île-du-Prince-Édouard"),
    11: ("QC", "Quebec", "Québec"),
    12: ("SK", "Saskatchewan", "Saskatchewan"),
    13: ("YT", "Yukon", "Yukon"),
}


def normalized(value):
    return " ".join("".join(ch for ch in unicodedata.normalize("NFKD", str(value or ""))
                            if not unicodedata.combining(ch)).casefold().split())


def canonical_province(value):
    key = normalized(value)
    for code, en, fr in PROVINCES.values():
        if key in {normalized(code), normalized(en), normalized(fr)}:
            return en
    return None


def valid_coordinates(longitude, latitude):
    try:
        lon, lat = float(longitude), float(latitude)
    except (ValueError, TypeError):
        return False
    return math.isfinite(lon) and math.isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90


def ring_location(longitude, latitude, ring):
    """Return 0 outside, 1 inside, 2 on a segment; handles closed/unclosed rings."""
    inside = False
    tolerance = 1e-9
    for start, end in zip(ring, [*ring[1:], ring[0]]):
        x1, y1 = start[:2]
        x2, y2 = end[:2]
        dx, dy = x2 - x1, y2 - y1
        cross = (longitude - x1) * dy - (latitude - y1) * dx
        if (abs(cross) <= tolerance * max(1.0, math.hypot(dx, dy))
                and min(x1, x2) - tolerance <= longitude <= max(x1, x2) + tolerance
                and min(y1, y2) - tolerance <= latitude <= max(y1, y2) + tolerance):
            return 2
        if (y1 > latitude) != (y2 > latitude):
            intersect_x = x1 + (latitude - y1) * dx / dy
            if longitude < intersect_x:
                inside = not inside
    return int(inside)


def polygon_location(longitude, latitude, rings):
    outside = ring_location(longitude, latitude, rings[0])
    if outside != 1:
        return outside
    for hole in rings[1:]:
        location = ring_location(longitude, latitude, hole)
        if location == 2:
            return 2
        if location == 1:
            return 0
    return 1


class ProvinceIndex:
    def __init__(self, path=SOURCE / "provinces.geojson"):
        source = path if isinstance(path, dict) else json.loads(Path(path).read_text(encoding="utf-8"))
        if source.get("type") != "FeatureCollection":
            raise ValueError("Province source must be a GeoJSON FeatureCollection")
        self.polygons = []
        self.grouped = {code: [] for code in PROVINCES}
        for feature in source["features"]:
            properties = feature["properties"]
            if properties.get("COUNTRY") != 1:
                raise ValueError("Unexpected non-Canadian boundary feature")
            province_id = int(properties["POLITICALDIV"])
            if province_id not in PROVINCES:
                raise ValueError(f"Unknown NRCan political division: {province_id}")
            geometry = feature["geometry"]
            if geometry["type"] == "Polygon":
                polygons = [geometry["coordinates"]]
            elif geometry["type"] == "MultiPolygon":
                polygons = geometry["coordinates"]
            else:
                raise ValueError(f"Unsupported province geometry: {geometry['type']}")
            for polygon in polygons:
                if not polygon or any(len(ring) < 4 for ring in polygon):
                    raise ValueError("Province polygon has an empty or degenerate ring")
                points = [point for ring in polygon for point in ring]
                if any(not valid_coordinates(*point[:2]) for point in points):
                    raise ValueError("Province source contains invalid coordinates")
                box = (min(p[0] for p in points), min(p[1] for p in points),
                       max(p[0] for p in points), max(p[1] for p in points))
                self.polygons.append((province_id, box, polygon))
                self.grouped[province_id].append(polygon)

    def _matches(self, longitude, latitude):
        if not valid_coordinates(longitude, latitude):
            return {}, False
        lon, lat = float(longitude), float(latitude)
        matches = {}
        boundary = False
        for province_id, (xmin, ymin, xmax, ymax), rings in self.polygons:
            if not xmin <= lon <= xmax or not ymin <= lat <= ymax:
                continue
            location = polygon_location(lon, lat, rings)
            if location:
                matches[province_id] = PROVINCES[province_id][1]
                boundary |= location == 2
        return matches, boundary

    def locate(self, longitude, latitude):
        """List matching English province names; order is deterministic."""
        matches, _ = self._matches(longitude, latitude)
        return sorted(matches.values())

    def assess(self, longitude, latitude, reported_province):
        if not valid_coordinates(longitude, latitude):
            return {"SpatialStatus": "invalid_coordinates", "SpatialProvince": ""}
        matches, boundary = self._matches(longitude, latitude)
        names = sorted(matches.values())
        reported = canonical_province(reported_province)
        if not names:
            status = "outside_generalized_boundary"
        elif boundary or len(names) > 1:
            status = "boundary_review"
        elif reported is None:
            status = "unknown_reported_province"
        elif reported in names:
            status = "match"
        else:
            status = "mismatch_review"
        return {"SpatialStatus": status, "SpatialProvince": " | ".join(names)}

    def feature_collection(self):
        """Group polygon parts into 13 named features for an offline SVG map."""
        return {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"ProvinceCode": PROVINCES[key][0],
             "Province": PROVINCES[key][1], "ProvinceFR": PROVINCES[key][2]},
             "geometry": {"type": "MultiPolygon", "coordinates": self.grouped[key]}}
            for key in sorted(self.grouped) if self.grouped[key]
        ]}

    display_geojson = feature_collection


if __name__ == "__main__":
    index = ProvinceIndex()
    print(json.dumps({"polygon_parts": len(index.polygons),
                      "province_territories": len(index.feature_collection()["features"]),
                      "calgary": index.assess(-114.0719, 51.0447, "Alberta")}, indent=2))

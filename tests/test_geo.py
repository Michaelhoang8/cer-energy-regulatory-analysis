import json
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from geo import ProvinceIndex, canonical_province, polygon_location, ring_location


def feature(code, rings):
    return {"type": "Feature", "properties": {"COUNTRY": 1, "POLITICALDIV": code},
            "geometry": {"type": "Polygon", "coordinates": rings}}


class GeometryTests(unittest.TestCase):
    def setUp(self):
        self.outer = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]
        self.hole = [[4, 4], [6, 4], [6, 6], [4, 6], [4, 4]]
        self.index = ProvinceIndex({"type": "FeatureCollection", "features": [
            feature(1, [self.outer, self.hole]),
            feature(12, [[[10, 0], [20, 0], [20, 10], [10, 10], [10, 0]]]),
        ]})

    def test_polygon_holes_and_ring_direction(self):
        self.assertEqual(polygon_location(2, 2, [self.outer, self.hole]), 1)
        self.assertEqual(polygon_location(5, 5, [self.outer, self.hole]), 0)
        self.assertEqual(polygon_location(4, 5, [self.outer, self.hole]), 2)
        self.assertEqual(ring_location(2, 2, self.outer[::-1]), 1)
        self.assertEqual(ring_location(11, 5, self.outer), 0)

    def test_shared_border_is_review_not_an_arbitrary_assignment(self):
        self.assertEqual(self.index.locate(10, 5), ["Alberta", "Saskatchewan"])
        self.assertEqual(self.index.assess(10, 5, "AB")["SpatialStatus"], "boundary_review")

    def test_invalid_and_missing_coordinates_remain_explicit(self):
        for lon, lat in [(None, 50), ("", 50), (math.nan, 50), (-114, math.inf), (181, 50), (-114, 91)]:
            self.assertEqual(self.index.assess(lon, lat, "Alberta")["SpatialStatus"], "invalid_coordinates")

    def test_mismatches_unknown_labels_and_outside_points_are_distinct(self):
        self.assertEqual(self.index.assess(2, 2, "AB")["SpatialStatus"], "match")
        self.assertEqual(self.index.assess(2, 2, "Saskatchewan")["SpatialStatus"], "mismatch_review")
        self.assertEqual(self.index.assess(2, 2, "Unknown")["SpatialStatus"], "unknown_reported_province")
        self.assertEqual(self.index.assess(30, 30, "Alberta")["SpatialStatus"], "outside_generalized_boundary")
        self.assertEqual(canonical_province("Québec"), "Quebec")

    @unittest.skipUnless((ROOT / "data/source/provinces.geojson").exists(), "Official snapshot not present")
    def test_official_snapshot_covers_all_provinces_and_known_city_points(self):
        index = ProvinceIndex()
        self.assertEqual(len(index.feature_collection()["features"]), 13)
        for lon, lat, province in [(-114.0719, 51.0447, "Alberta"), (-104.6189, 50.4452, "Saskatchewan"),
                                   (-97.1384, 49.8951, "Manitoba"), (-75.6972, 45.4215, "Ontario")]:
            self.assertEqual(index.assess(lon, lat, province)["SpatialStatus"], "match")


if __name__ == "__main__":
    unittest.main()

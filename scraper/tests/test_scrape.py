#!/usr/bin/env python3
"""Offline unit tests for matching, summarize and estimate fallbacks."""
import json, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scraper"))
import scrape as sc

class Matches(unittest.TestCase):
    def setUp(self):
        self.cat = {it["id"]: it for k, items in sc.CATALOG.items() if not k.startswith("_") for it in items}

    def test_r5_5600_not_x(self):
        it = self.cat["r5-5600"]
        self.assertTrue(sc.matches(it, "Amd ryzen 5 5600"))
        self.assertFalse(sc.matches(it, "Procesor AMD Ryzen 5 5600x"))
        self.assertFalse(sc.matches(it, "Kit Ryzen 5 5600 + B450M + 16gb"))

    def test_rtx_4070_excludes_super(self):
        it = self.cat["rtx-4070"]
        self.assertTrue(sc.matches(it, "Placa video RTX 4070 12GB"))
        self.assertFalse(sc.matches(it, "RTX 4070 Super 12GB"))

    def test_rejects_pc_bundle(self):
        it = self.cat["rtx-3060"]
        self.assertFalse(sc.matches(it, "PC Gaming RTX 3060 Ryzen 5"))

    def test_rejects_multi_component(self):
        it = self.cat["i5-12600k"]
        self.assertFalse(sc.matches(it, "I5 12600KF 32GB Ram Ddr5 rx 9060 xt 8gb"))

class Summarize(unittest.TestCase):
    def test_min_n(self):
        self.assertIsNone(sc.summarize([100, 110], min_n=3))
        s = sc.summarize([100, 110, 120], min_n=3)
        self.assertEqual(s["n"], 3)
        self.assertEqual(s["median"], 110)

    def test_soft(self):
        s = sc.soft_used([500])
        self.assertEqual(s["median"], 500)

class Estimates(unittest.TestCase):
    def test_new_x_depreciation(self):
        models = {
            "rtx-4060-ti": {
                "kind": "gpu", "name": "4060 Ti", "gen": "40",
                "used": None,
                "new": {"median": 3556, "p25": 3400, "p75": 3700, "n": 4},
                "listings": [],
            }
        }
        catalog = {"rtx-4060-ti": {"id": "rtx-4060-ti", "gen": "40", "kind": "gpu", "neighbors": []}}
        sc.apply_estimates(models, catalog)
        u = models["rtx-4060-ti"]["used"]
        self.assertTrue(u["estimated"])
        self.assertEqual(u["median"], round(3556 * 0.62))
        self.assertIn("new_x_", u["method"])

    def test_neighbor_fallback(self):
        models = {
            "a": {"kind": "gpu", "name": "A", "gen": "40", "used": None, "new": None,
                  "listings": [{"source": "olx", "condition": "used", "price": p} for p in (2900, 3000, 3100, 3050)]},
            "b": {"kind": "gpu", "name": "B", "gen": "40", "used": None, "new": None, "listings": []},
        }
        catalog = {
            "a": {"id": "a", "gen": "40", "kind": "gpu", "neighbors": []},
            "b": {"id": "b", "gen": "40", "kind": "gpu", "neighbors": ["a"]},
        }
        sc.apply_estimates(models, catalog)
        self.assertFalse(models["a"]["used"].get("estimated"))
        self.assertEqual(models["b"]["used"]["median"], models["a"]["used"]["median"])
        self.assertEqual(models["b"]["used"]["method"], "neighbor:a")

    def test_observed_pure(self):
        models = {
            "x": {"kind": "cpu", "name": "X", "gen": "zen3", "used": None, "new": None,
                  "listings": [{"source": "olx", "condition": "used", "price": p} for p in (400, 420, 450, 460)]},
        }
        catalog = {"x": {"id": "x", "gen": "zen3", "kind": "cpu", "neighbors": []}}
        sc.apply_estimates(models, catalog)
        self.assertFalse(models["x"]["used"].get("estimated"))
        self.assertEqual(models["x"]["used"]["method"], "olx_median")

if __name__ == "__main__":
    unittest.main()

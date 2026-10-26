"""biaslens —— 自检测试。

按人群或场景分组统计评测结果，标出组间差距与样本量不足的分组。
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import biaslens  # noqa: E402


class TestBiasLens(unittest.TestCase):
    def test_groups_are_counted(self):
        rows = [{"g": "a", "score": 0.9}, {"g": "a", "score": 0.8},
                {"g": "b", "score": 0.5}]
        r = biaslens.analyze(rows, "g", "score", 5)
        self.assertEqual(r["groups"]["a"]["n"], 2)
        self.assertEqual(r["groups"]["b"]["n"], 1)

    def test_insufficient_sample_refuses_to_conclude(self):
        rows = [{"g": "a", "score": 0.9}, {"g": "b", "score": 0.5}]
        r = biaslens.analyze(rows, "g", "score", 5)
        self.assertEqual(r["summary"]["insufficient_count"], 2)
        for c in r["comparisons"]:
            self.assertEqual(c["verdict"], "insufficient_sample")
            self.assertIsNone(c.get("p"))

    def test_significant_difference_detected(self):
        rows = ([{"g": "a", "score": 0.9 + i * 0.001} for i in range(30)]
                + [{"g": "b", "score": 0.4 + i * 0.001} for i in range(30)])
        r = biaslens.analyze(rows, "g", "score", 5)
        significant = [c for c in r["comparisons"] if c["verdict"] == "significant"]
        self.assertTrue(significant)
        self.assertLess(significant[0]["p"], 0.05)

    def test_no_difference_when_identical(self):
        rows = [{"g": "a", "score": 0.7} for _ in range(10)]
        rows += [{"g": "b", "score": 0.7} for _ in range(10)]
        r = biaslens.analyze(rows, "g", "score", 5)
        c = r["comparisons"][0]
        self.assertEqual(c["verdict"], "not_significant")

    def test_confidence_interval_present(self):
        rows = [{"g": "a", "score": 0.7 + i * 0.01} for i in range(20)]
        r = biaslens.analyze(rows, "g", "score", 5)
        st = r["groups"]["a"]
        self.assertLess(st["ci_low"], st["mean"])
        self.assertGreater(st["ci_high"], st["mean"])

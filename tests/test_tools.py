import re
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import tools


class ToolIntegrationTests(unittest.TestCase):
    def test_default_database_loads_supplied_csv(self):
        result = tools.load_product_database()

        self.assertTrue(result["success"], result)
        self.assertEqual(result["product_count"], 50)
        self.assertEqual(result["ingredient_row_count"], 99)

    def test_single_product_comparison_returns_one_complete_table(self):
        result = tools.compare_products(["P048"])

        self.assertTrue(result["success"], result)
        self.assertNotIn("markdown_table", result["comparison_matrix"])
        table = result["markdown_table"]
        self.assertEqual(len(re.findall(r"^\|(?:\s*:?-+:?\s*\|)+$", table, re.M)), 1)
        self.assertIn("| Tiêu chí | Sữa Ensure bổ sung Canxi & Vitamin |", table)
        self.assertIn("| Giá hộp | 750.000 VNĐ |", table)
        self.assertIn("| Liều dùng | 1-2 ly/ngày |", table)
        self.assertIn("| Canxi | 500 mg |", table)
        self.assertIn("| Protein | 15 g |", table)
        self.assertIn("N/A — thiếu số khẩu phần/hộp", table)
        self.assertRegex(table, r"bác sĩ/dược sĩ")

    def test_two_product_comparison_returns_one_unified_table(self):
        result = tools.compare_products(["P003", "P048"])

        self.assertTrue(result["success"], result)
        table = result["markdown_table"]
        self.assertEqual(len(re.findall(r"^\|(?:\s*:?-+:?\s*\|)+$", table, re.M)), 1)
        self.assertIn("| Canxi | 600 mg | 500 mg |", table)
        self.assertIn("| Vitamin D3 | 400 IU | 200 IU |", table)
        self.assertNotIn("Công dụng", table)

    def test_search_normalizes_punctuation_and_accepts_distinctive_partial_name(self):
        omega = tools.search_products("Omega 3")
        gac = tools.search_products("Dầu gấc")
        biotin = tools.search_products("Biotin")

        self.assertEqual([item["product_id"] for item in omega["products"]], ["P001"])
        self.assertEqual([item["product_id"] for item in gac["products"]], ["P026"])
        self.assertEqual([item["product_id"] for item in biotin["products"]], ["P014"])


if __name__ == "__main__":
    unittest.main()

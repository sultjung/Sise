import datetime as dt
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("scrape_prices", ROOT / "scripts" / "scrape_prices.py")
scraper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scraper)


class PriceParserTests(unittest.TestCase):
    def test_arabic_digits(self):
        self.assertEqual(scraper.normalized("١٤٠ متر"), "140 متر")

    def test_parse_bismayah_listing(self):
        html = (ROOT / "tests" / "fixtures" / "aiqarat_bismayah.html").read_text(encoding="utf-8")
        target = {"key": "bismayah", "aliases": ["بسماية", "بسمايه"]}
        item = scraper.parse_property(
            html,
            "https://aiqarat.com/property/example/",
            target,
            dt.date(2026, 8, 12),
            1310,
        )
        self.assertIsNotNone(item)
        self.assertEqual(item["area_m2"], 140)
        self.assertEqual(item["price_iqd"], 165_000_000)
        self.assertEqual(item["price_per_m2_iqd"], 1_178_571)
        self.assertEqual(item["listing_date"], "2026-04-25")

    def test_summary_requires_three_samples(self):
        base = {"url": "https://example.test/1", "listing_date": "2026-08-01"}
        samples = [
            {**base, "url": f"https://example.test/{i}", "price_per_m2_iqd": price}
            for i, price in enumerate((800_000, 820_000, 840_000), 1)
        ]
        summary = scraper.summarize(samples)
        self.assertTrue(summary["publishable"])
        self.assertEqual(summary["published_price_per_m2_iqd"], 820_000)


if __name__ == "__main__":
    unittest.main()

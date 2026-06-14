import unittest
import tomllib
from pathlib import Path

from app.platform.runtime import concurrency


class EffectiveConcurrencyTest(unittest.TestCase):
    def setUp(self) -> None:
        self._orig = concurrency._mem_available_mb

    def tearDown(self) -> None:
        concurrency._mem_available_mb = self._orig

    def _set_mem(self, mb):
        concurrency._mem_available_mb = lambda: mb

    def test_tiers(self):
        self._set_mem(320)
        self.assertEqual(concurrency.effective_concurrency(50), 2)
        self._set_mem(800)
        self.assertEqual(concurrency.effective_concurrency(50), 4)
        self._set_mem(1500)
        self.assertEqual(concurrency.effective_concurrency(50), 6)

    def test_high_mem_uses_configured(self):
        self._set_mem(4096)
        self.assertEqual(concurrency.effective_concurrency(8), 8)

    def test_cap_never_raises_configured(self):
        self._set_mem(1500)  # tier cap 6
        self.assertEqual(concurrency.effective_concurrency(3), 3)

    def test_unreadable_trusts_config(self):
        concurrency._mem_available_mb = lambda: None
        self.assertEqual(concurrency.effective_concurrency(8), 8)

    def test_floor_one(self):
        self._set_mem(320)
        self.assertEqual(concurrency.effective_concurrency(0), 1)


class DefaultsTest(unittest.TestCase):
    def setUp(self) -> None:
        root = Path(__file__).resolve().parent.parent
        with open(root / "config.defaults.toml", "rb") as f:
            self.cfg = tomllib.load(f)

    def test_refresh_defaults_lowered(self):
        self.assertLessEqual(self.cfg["account"]["refresh"]["usage_concurrency"], 8)
        self.assertIn("refresh_pause_sec", self.cfg["account"]["refresh"])

    def test_batch_defaults_lowered(self):
        b = self.cfg["batch"]
        for k in ("nsfw_concurrency", "refresh_concurrency",
                  "asset_list_concurrency", "asset_delete_concurrency"):
            self.assertLessEqual(b[k], 8, k)
        self.assertLessEqual(b["asset_upload_concurrency"], 4)


if __name__ == "__main__":
    unittest.main()

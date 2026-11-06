"""Fresh init must publish a revision before the first scenario API request."""
from datetime import datetime
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class BootstrapTests(unittest.TestCase):
    def test_fresh_initializer_publishes_timestamped_normal_mode(self):
        spec = importlib.util.spec_from_file_location("init_dnssec_bootstrap", Path(__file__).resolve().parents[2] / "lab" / "init_dnssec.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            paths = {name: base / name.lower() for name in ["KEYS", "SIGNED", "TRUST", "STATE"]}
            paths["KEYS"].mkdir()
            (paths["KEYS"] / "Kdemo.test.+013+12345.key").write_text("demo.test. IN DNSKEY 257 3 13 TEST")
            zone = base / "zone"
            zone.write_text("demo.test. IN SOA ns.demo.test. host.demo.test. 2026102901 1 1 1 1")
            with patch.multiple(module, **paths), patch.object(module, "Path", side_effect=lambda value: zone if str(value) == "/app/zones/demo.test" else Path(value)), patch.object(module, "run", return_value="demo.test. IN DS 12345 13 2 ABCD"):
                module.main()
            state = json.loads((paths["STATE"] / "mode.json").read_text())
            self.assertIs(state["attack"], False)
            self.assertIsNotNone(datetime.fromisoformat(state["changed_at"]).tzinfo)
            self.assertTrue((paths["TRUST"] / "anchor.key").exists())


if __name__ == "__main__":
    unittest.main()

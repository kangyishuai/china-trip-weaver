import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DesignDocsTests(unittest.TestCase):
    def test_runtime_modules_and_scripts_are_named_in_impl_map(self):
        impl_map = (ROOT / "docs" / "design" / "09-impl-map.md").read_text(
            encoding="utf-8"
        )
        runtime_files = sorted(
            (ROOT / "plugins" / "china-trip-weaver" / "src" / "china_trip_weaver").rglob(
                "*.py"
            )
        )
        script_files = sorted((ROOT / "scripts").glob("*.py"))
        files = runtime_files + script_files
        self.assertEqual(48, len(files))
        missing = [path.name for path in files if path.name not in impl_map]
        self.assertEqual([], missing, f"09-impl-map.md is missing: {missing}")

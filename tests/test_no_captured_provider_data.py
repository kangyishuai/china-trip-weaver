from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# Keep these split so this tracked guard does not contain the forbidden values
# that it is responsible for detecting.
FORBIDDEN_PROVIDER_TEXT = (
    "alicdn" + ".com",
    "feizhu" + ".com",
    "router" + ".feizhu",
    "林顿青年公寓" + "（上海火车站店）",
    "上海多园青旅酒店" + "(外滩店)",
    "易佰良品酒店" + "西藏北路地铁站店",
    "上海漫星图书馆" + "青年旅舍",
    "上海汉萨酒店" + "(上海松江大学城店)",
    "尤家青年旅舍" + "（上海新国际博览中心店）",
    "上海朋派青年" + "艺术酒店",
    "上海新人人酒店" + "（上海大宁国际延长路地铁站店）",
    "如家商旅(金标)" + "-上海陆家嘴世博中心店",
    "一间森林酒店" + "(上海外滩南京东路步行街店)",
    "锦江之星上海人民广场" + "淮海东路酒店",
)


def tracked_paths() -> tuple[Path, ...]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return tuple(
        ROOT / os.fsdecode(raw_path)
        for raw_path in result.stdout.split(b"\0")
        if raw_path
    )


class NoCapturedProviderDataTests(unittest.TestCase):
    def test_tracked_files_contain_no_captured_provider_markers(self):
        hits = []
        for path in tracked_paths():
            if not path.is_file():
                continue
            data = path.read_bytes()
            folded = data.lower()
            for forbidden in FORBIDDEN_PROVIDER_TEXT:
                needle = forbidden.encode("utf-8").lower()
                offset = folded.find(needle)
                if offset >= 0:
                    line = data.count(b"\n", 0, offset) + 1
                    hits.append(
                        "%s:%d: %s"
                        % (path.relative_to(ROOT).as_posix(), line, forbidden)
                    )
        self.assertEqual([], hits, "captured provider data found in tracked files")


if __name__ == "__main__":
    unittest.main()

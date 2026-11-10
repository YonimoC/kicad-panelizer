from __future__ import annotations

import struct
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()[:24]
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssertionError(f"Not a PNG file: {path}")
    return struct.unpack(">II", data[16:24])


class PackagingTests(unittest.TestCase):
    def test_pcm_and_toolbar_icons_have_separate_sizes(self) -> None:
        self.assertEqual(png_size(ROOT / "resources" / "icon.png"), (64, 64))
        self.assertEqual(png_size(ROOT / "plugins" / "icon.png"), (128, 128))


if __name__ == "__main__":
    unittest.main()

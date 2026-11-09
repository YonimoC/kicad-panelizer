from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from plugins.geometry import (  # noqa: E402
    BBox,
    ConfigError,
    PanelConfig,
    make_layout,
    mark_positions,
)
from plugins.i18n import TRANSLATIONS, translation_keys  # noqa: E402


class GeometryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.board = BBox(0.0, 0.0, 20.0, 10.0)

    def test_default_layout_matches_reference_values(self) -> None:
        layout = make_layout(self.board, PanelConfig())
        self.assertAlmostEqual(layout.pitch_x, 20.0)
        self.assertAlmostEqual(layout.pitch_y, 12.0)
        self.assertAlmostEqual(layout.array.width, 100.0)
        self.assertAlmostEqual(layout.array.height, 46.0)
        self.assertAlmostEqual(layout.panel.left, -6.0)
        self.assertAlmostEqual(layout.panel.right, 106.0)
        self.assertAlmostEqual(layout.panel_height, 46.0)
        self.assertEqual(layout.board_count, 20)

    def test_all_rails_expand_panel_on_every_side(self) -> None:
        config = PanelConfig(columns=2, rows=2, rail_top=True, rail_bottom=True)
        layout = make_layout(self.board, config)
        self.assertAlmostEqual(layout.panel.left, -6.0)
        self.assertAlmostEqual(layout.panel.top, -6.0)
        self.assertAlmostEqual(layout.panel.right, 46.0)
        self.assertAlmostEqual(layout.panel.bottom, 28.0)

    def test_marks_are_centered_on_enabled_side_rails(self) -> None:
        layout = make_layout(self.board, PanelConfig())
        marks = mark_positions(layout)
        self.assertEqual(len(marks), 4)
        self.assertEqual({mark.side for mark in marks}, {"left", "right"})
        self.assertEqual({mark.layer for mark in marks}, {"F", "B"})
        self.assertAlmostEqual(marks[0].x, -3.0)
        self.assertAlmostEqual(marks[0].y, 10.0)
        self.assertAlmostEqual(marks[1].y, 31.0)
        self.assertAlmostEqual(marks[2].x, 103.0)

    def test_invalid_configuration_is_rejected(self) -> None:
        with self.assertRaises(ConfigError) as context:
            PanelConfig(columns=0).validate()
        self.assertEqual(context.exception.code, "invalid_columns")

        with self.assertRaises(ConfigError) as context:
            PanelConfig(mark_copper_mm=2.0, mark_mask_mm=2.0).validate()
        self.assertEqual(context.exception.code, "invalid_mark_mask")

        with self.assertRaises(ConfigError) as context:
            PanelConfig(
                rail_left=False,
                rail_right=False,
                rail_top=False,
                rail_bottom=False,
            ).validate()
        self.assertEqual(context.exception.code, "invalid_rail_sides")

    def test_translation_catalogs_have_identical_keys(self) -> None:
        english = translation_keys()
        self.assertEqual(set(TRANSLATIONS["zh"]), english)


if __name__ == "__main__":
    unittest.main()


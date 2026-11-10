from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pcbnew
import wx


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# The panelizer module registers an ActionPlugin when imported. Registration
# requires a live pcbnew program, so disable it for this isolated wx UI test.
pcbnew.ActionPlugin.register = lambda self: None

from plugins.geometry import BBox, PanelConfig, make_layout  # noqa: E402
from plugins.i18n import Translator  # noqa: E402
from plugins.kicad_panelizer import PanelizerDialog  # noqa: E402


class UiLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = wx.App(False)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.app.Destroy()

    def make_dialog(self, language: str = "zh") -> PanelizerDialog:
        return PanelizerDialog(
            None,
            BBox(0.0, 0.0, 40.0, 30.0),
            Translator(language),
            PanelConfig(),
        )

    def test_initial_dialog_fits_display_and_keeps_footer_visible(self) -> None:
        dialog = self.make_dialog()
        try:
            display = wx.Display(wx.Display.GetFromWindow(dialog))
            client = display.GetClientArea().GetSize()
            size = dialog.GetSize()
            self.assertLessEqual(size.width, client.width)
            self.assertLessEqual(size.height, client.height)
            self.assertEqual(dialog._ok_button.GetLabel(), "应用并保存")
            self.assertGreaterEqual(dialog._body_panel.GetClientSize().height, 400)
            self.assertLessEqual(dialog._ctl_columns.GetSize().width, 150)
            self.assertGreaterEqual(dialog.preview.GetSize().width, 450)
            self.assertTrue(dialog.GetTitle().endswith("v1.0.5"))
            self.assertEqual(
                dialog._ctl_columns.GetSize().width,
                dialog._mode_choice.GetSize().width,
            )
            self.assertLessEqual(
                abs(
                    dialog._settings_panel.GetSize().width
                    - dialog.preview.GetParent().GetSize().width
                ),
                80,
            )
            self.assertTrue(dialog._ctl_bottom.IsShown())
        finally:
            dialog.Destroy()

    def test_minimum_window_keeps_all_rail_controls_visible(self) -> None:
        dialog = self.make_dialog()
        try:
            dialog.SetSize(dialog.GetMinSize())
            dialog.Layout()
            self.assertTrue(dialog._ctl_left.IsShown())
            self.assertTrue(dialog._ctl_right.IsShown())
            self.assertTrue(dialog._ctl_top.IsShown())
            self.assertTrue(dialog._ctl_bottom.IsShown())
            self.assertTrue(dialog._ok_button.IsShown())
        finally:
            dialog.Destroy()

    def test_language_switch_updates_all_visible_group_labels(self) -> None:
        dialog = self.make_dialog("en")
        try:
            self.assertEqual(dialog._ok_button.GetLabel(), "Apply and save")
            dialog.tr.set_language("zh")
            dialog._refresh_texts()
            self.assertEqual(dialog._ok_button.GetLabel(), "应用并保存")
            self.assertEqual(dialog._group_boxes["mark_group"].GetStaticBox().GetLabel(), "光学定位点 (Mark)")
        finally:
            dialog.Destroy()

    def test_single_board_mode_changes_action_and_disables_panel_controls(self) -> None:
        dialog = self.make_dialog("zh")
        try:
            dialog._mode_choice.SetSelection(1)
            dialog._on_mode_change(None)
            self.assertEqual(dialog.get_mode(), "single")
            self.assertEqual(dialog._ok_button.GetLabel(), "恢复单板并保存")
            self.assertFalse(dialog._ctl_rows.IsEnabled())
            self.assertFalse(dialog._ctl_enable_marks.IsEnabled())
            self.assertTrue(dialog.preview.single_mode)
            self.assertIn("不会被备份文件覆盖", dialog._labels["backup_note"].GetLabel())
        finally:
            dialog.Destroy()

    def test_preview_bitmap_contains_all_board_cells(self) -> None:
        dialog = self.make_dialog("zh")
        try:
            preview = dialog.preview
            preview.set_data(
                dialog.board_bbox,
                make_layout(
                    dialog.board_bbox,
                    PanelConfig(columns=5, rows=4, y_gap_mm=2.0),
                ),
            )
            width, height = 900, 600
            bitmap = wx.Bitmap(width, height)
            dc = wx.MemoryDC(bitmap)
            preview._render(dc, width, height)
            dc.SelectObject(wx.NullBitmap)
            image = bitmap.ConvertToImage()

            board_pixels = 0
            for y in range(0, height, 3):
                for x in range(0, width, 3):
                    rgb = (
                        image.GetRed(x, y),
                        image.GetGreen(x, y),
                        image.GetBlue(x, y),
                    )
                    if rgb in {
                        (216, 236, 252),
                        (198, 224, 246),
                    }:
                        board_pixels += 1
            self.assertGreater(board_pixels, 10000)
        finally:
            dialog.Destroy()

    def test_preview_dimensions_are_copyable_vertical_text(self) -> None:
        dialog = self.make_dialog("zh")
        try:
            preview = dialog.preview
            preview.set_data(
                dialog.board_bbox,
                make_layout(
                    dialog.board_bbox,
                    PanelConfig(columns=2, rows=2, y_gap_mm=2.0),
                ),
            )
            lines = preview._dimension_text.GetValue().splitlines()
            self.assertEqual(len(lines), 2)
            self.assertTrue(lines[0].startswith("单板尺寸："))
            self.assertTrue(lines[1].startswith("拼板尺寸："))
            self.assertIn("2 × 2", lines[1])
            self.assertIn("共 4 片", lines[1])
            self.assertFalse(preview._dimension_text.IsEditable())
        finally:
            dialog.Destroy()


if __name__ == "__main__":
    unittest.main()

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

from plugins.geometry import BBox, PanelConfig  # noqa: E402
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
            self.assertGreaterEqual(dialog._scroll.GetClientSize().height, 300)
        finally:
            dialog.Destroy()

    def test_settings_area_scrolls_at_minimum_window_size(self) -> None:
        dialog = self.make_dialog()
        try:
            dialog.SetSize((800, 560))
            dialog.Layout()
            self.assertGreater(
                dialog._scroll.GetVirtualSize().height,
                dialog._scroll.GetClientSize().height,
            )
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


if __name__ == "__main__":
    unittest.main()

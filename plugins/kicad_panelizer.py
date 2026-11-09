"""KiCad Action Plugin and wxPython user interface."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path

import pcbnew
import wx

from .geometry import BBox, ConfigError, PanelConfig, PanelLayout, make_layout, mark_positions
from .i18n import LANGUAGE_LABELS, Translator
from .panelizer import (
    PanelizerError,
    board_outline_bbox,
    original_single_board_bbox,
    panelize_and_save,
    restore_single_board_and_save,
)


APP_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_VERSION = "1.0.4"


def _settings_path() -> Path:
    if os.name == "nt":
        root = Path(os.environ.get("APPDATA", Path.home()))
    else:
        root = Path.home() / ".config"
    return root / "kicad-panelizer" / "settings.json"


def load_settings() -> dict[str, object]:
    try:
        return json.loads(_settings_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_settings(values: dict[str, object]) -> None:
    path = _settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(values, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


class PanelPreview(wx.StaticBitmap):
    def __init__(self, parent, translator: Translator) -> None:
        super().__init__(parent)
        self.tr = translator
        self.board: BBox | None = None
        self.layout: PanelLayout | None = None
        self.single_mode = False
        self.error = ""
        self._bitmap: wx.Bitmap | None = None
        self.SetMinSize((460, 410))
        self.Bind(wx.EVT_SIZE, self._on_size)

    def set_data(
        self,
        board: BBox,
        layout: PanelLayout | None,
        error: str = "",
    ) -> None:
        self.board = board
        self.layout = layout
        self.single_mode = False
        self.error = error
        self._refresh_bitmap()

    def set_single_board(self, board: BBox) -> None:
        self.board = board
        self.layout = None
        self.single_mode = True
        self.error = ""
        self._refresh_bitmap()

    def _on_size(self, event) -> None:
        event.Skip()
        self._refresh_bitmap()

    def _refresh_bitmap(self) -> None:
        size = self.GetClientSize()
        if size.width < 2 or size.height < 2:
            return
        bitmap = wx.Bitmap(size.width, size.height)
        dc = wx.MemoryDC(bitmap)
        try:
            self._render(dc, size.width, size.height)
        finally:
            dc.SelectObject(wx.NullBitmap)
        self._bitmap = bitmap
        self.SetBitmap(bitmap)

    def _render(self, dc: wx.DC, width: int, height: int) -> None:
        dc.SetBackground(wx.Brush(wx.Colour(248, 249, 251)))
        dc.Clear()
        if width < 40 or height < 40:
            return

        if self.error or self.board is None or (self.layout is None and not self.single_mode):
            dc.SetTextForeground(wx.Colour(190, 57, 57))
            dc.SetFont(self.GetFont().Bold())
            message = f"{self.tr('preview_error')}: {self.error or self.tr('invalid_columns')}"
            text_width, text_height = dc.GetTextExtent(message)
            dc.DrawText(message, max(12, (width - text_width) // 2), max(12, height // 2))
            return

        if self.single_mode:
            panel = self.board
            available_w = width - 76
            available_h = height - 110
            scale = min(
                available_w / max(panel.width, 0.01),
                available_h / max(panel.height, 0.01),
            )
            origin_x = (width - panel.width * scale) / 2
            origin_y = 42 + (available_h - panel.height * scale) / 2
            dc.SetPen(wx.Pen(wx.Colour(54, 69, 91), 2))
            dc.SetBrush(wx.Brush(wx.Colour(218, 237, 252)))
            dc.DrawRectangle(
                int(origin_x),
                int(origin_y),
                max(1, int(panel.width * scale)),
                max(1, int(panel.height * scale)),
            )
            dc.SetFont(self.GetFont())
            dc.SetTextForeground(wx.Colour(50, 57, 68))
            dc.DrawText(
                self.tr("board_size", width=panel.width, height=panel.height),
                18,
                12,
            )
            dc.DrawText(self.tr("single_board_preview"), 18, height - 52)
            return

        layout = self.layout
        if layout is None:
            return
        config = layout.config
        panel = layout.panel
        available_w = width - 76
        available_h = height - 110
        scale = min(available_w / max(panel.width, 0.01), available_h / max(panel.height, 0.01))
        origin_x = (width - panel.width * scale) / 2
        origin_y = 42 + (available_h - panel.height * scale) / 2

        def px(x: float) -> int:
            return int(origin_x + (x - panel.left) * scale)

        def py(y: float) -> int:
            return int(origin_y + (y - panel.top) * scale)

        def rect(box: BBox) -> tuple[int, int, int, int]:
            return px(box.left), py(box.top), max(1, px(box.right) - px(box.left)), max(
                1, py(box.bottom) - py(box.top)
            )

        dock = wx.Colour(214, 220, 229)
        board_fill = wx.Colour(216, 236, 252)
        board_fill_alt = wx.Colour(198, 224, 246)
        edge = wx.Colour(38, 62, 88)
        cell_edge = wx.Colour(61, 126, 181)
        dc.SetPen(wx.Pen(wx.Colour(188, 198, 212), 1))
        dc.SetBrush(wx.Brush(dock))
        dc.DrawRectangle(*rect(panel))
        dc.SetPen(wx.Pen(edge, 3))
        dc.SetBrush(wx.TRANSPARENT_BRUSH)
        dc.DrawRectangle(*rect(panel))

        dc.SetFont(self.GetFont())
        for row in range(config.rows):
            for column in range(config.columns):
                dx, dy = layout.cell_origin(column, row)
                cell = BBox(
                    dx,
                    dy,
                    dx + layout.board.width,
                    dy + layout.board.height,
                )
                cell_rect = rect(cell)
                dc.SetPen(wx.Pen(cell_edge, 2))
                dc.SetBrush(
                    wx.Brush(
                        board_fill if (row + column) % 2 == 0 else board_fill_alt
                    )
                )
                dc.DrawRectangle(*cell_rect)
                if cell_rect[2] >= 28 and cell_rect[3] >= 20:
                    label = str(row * config.columns + column + 1)
                    text_width, text_height = dc.GetTextExtent(label)
                    dc.SetTextForeground(wx.Colour(70, 104, 136))
                    dc.DrawText(
                        label,
                        cell_rect[0] + (cell_rect[2] - text_width) // 2,
                        cell_rect[1] + (cell_rect[3] - text_height) // 2,
                    )

        for spec in mark_positions(layout):
            center = wx.Point(px(spec.x), py(spec.y))
            mask_radius = max(2, int(config.mark_mask_mm * scale / 2))
            copper_radius = max(1, int(config.mark_copper_mm * scale / 2))
            dc.SetPen(wx.Pen(wx.Colour(180, 145, 55), 2))
            dc.SetBrush(wx.Brush(wx.Colour(244, 214, 121)))
            dc.DrawCircle(center, mask_radius)
            dc.SetPen(wx.Pen(wx.Colour(120, 80, 30), 1))
            dc.SetBrush(wx.Brush(wx.Colour(232, 61, 68) if spec.layer == "F" else wx.Colour(44, 119, 203)))
            dc.DrawCircle(center, copper_radius)

        dc.SetFont(self.GetFont())
        dc.SetTextForeground(wx.Colour(50, 57, 68))
        top_text = self.tr(
            "board_size", width=self.board.width, height=self.board.height
        )
        bottom_text = self.tr(
            "panel_size", width=layout.panel_width, height=layout.panel_height
        )
        count_text = self.tr(
            "counts",
            columns=config.columns,
            rows=config.rows,
            count=layout.board_count,
        )
        dc.DrawText(top_text, 18, 12)
        dc.DrawText(f"{bottom_text}   |   {count_text}", 18, height - 52)

        legend_y = height - 26
        dc.SetPen(wx.Pen(wx.Colour(120, 80, 30), 1))
        dc.SetBrush(wx.Brush(wx.Colour(232, 61, 68)))
        dc.DrawCircle(24, legend_y, 5)
        dc.DrawText(self.tr("top_mark_legend"), 36, legend_y - 8)
        dc.SetBrush(wx.Brush(wx.Colour(44, 119, 203)))
        dc.DrawCircle(150, legend_y, 5)
        dc.DrawText(self.tr("bottom_mark_legend"), 162, legend_y - 8)


class PanelizerDialog(wx.Dialog):
    def __init__(self, parent, board_bbox: BBox, translator: Translator, config: PanelConfig):
        super().__init__(parent, title=translator("dialog_title"))
        self.tr = translator
        self.board_bbox = board_bbox
        self._labels: dict[str, wx.StaticText] = {}
        self._group_boxes: dict[str, wx.StaticBoxSizer] = {}
        self._setting_language = False
        self._mode = "vcut"
        self._build(config)
        self._refresh_texts()
        self._set_config_enabled()
        self._update_preview()
        self._fit_to_display()

    def _spin(
        self,
        parent,
        key: str,
        value: float,
        minimum: float,
        maximum: float,
        increment: float = 0.1,
        digits: int = 2,
    ) -> wx.SpinCtrlDouble:
        label = wx.StaticText(parent, label=key)
        self._labels[key] = label
        control = wx.SpinCtrlDouble(
            parent,
            min=minimum,
            max=maximum,
            initial=value,
            inc=increment,
        )
        control.SetDigits(digits)
        control.SetMinSize((150, -1))
        control.SetMaxSize((150, -1))
        control.Bind(wx.EVT_SPINCTRLDOUBLE, self._on_change)
        control.Bind(wx.EVT_TEXT, self._on_change)
        grid = getattr(self, "_active_grid")
        grid.Add(label, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(control, 0, wx.ALIGN_CENTER_VERTICAL)
        setattr(self, f"_ctl_{key}", control)
        return control

    def _check(self, parent, key: str, value: bool) -> wx.CheckBox:
        control = wx.CheckBox(parent, label=key)
        control.SetValue(value)
        control.Bind(wx.EVT_CHECKBOX, self._on_change)
        self._labels[key] = control
        setattr(self, f"_ctl_{key}", control)
        return control

    def _build(self, config: PanelConfig) -> None:
        self.SetBackgroundColour(wx.Colour(247, 249, 252))
        outer = wx.BoxSizer(wx.VERTICAL)
        header = wx.BoxSizer(wx.HORIZONTAL)
        title = wx.StaticText(self, label="PCB Panelizer")
        title_font = title.GetFont()
        title_font.SetPointSize(title_font.GetPointSize() + 6)
        title_font.SetWeight(wx.FONTWEIGHT_BOLD)
        title.SetFont(title_font)
        title.SetForegroundColour(wx.Colour(27, 61, 90))
        self._labels["dialog_title"] = title
        self._labels["dialog_subtitle"] = wx.StaticText(self)
        self._labels["dialog_subtitle"].SetMinSize((360, -1))
        self._labels["dialog_subtitle"].SetMaxSize((650, -1))
        subtitle_sizer = wx.BoxSizer(wx.VERTICAL)
        subtitle_sizer.Add(title, 0, wx.BOTTOM, 4)
        subtitle_sizer.Add(self._labels["dialog_subtitle"], 0)
        header.Add(subtitle_sizer, 1, wx.EXPAND)

        language_label = wx.StaticText(self)
        self._labels["language"] = language_label
        self._language_choice = wx.Choice(
            self, choices=[LANGUAGE_LABELS[key] for key in ("auto", "zh", "en")]
        )
        selected = ["auto", "zh", "en"].index(
            self.tr.language if self.tr.language in ("auto", "zh", "en") else "auto"
        )
        self._language_choice.SetSelection(selected)
        self._language_choice.Bind(wx.EVT_CHOICE, self._on_language)
        header.Add(language_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        header.Add(self._language_choice, 0, wx.ALIGN_CENTER_VERTICAL)
        outer.Add(header, 0, wx.EXPAND | wx.ALL, 18)

        self._body_panel = wx.Panel(self)
        self._body_panel.SetBackgroundColour(self.GetBackgroundColour())
        body = wx.BoxSizer(wx.HORIZONTAL)
        self._settings_panel = wx.Panel(self._body_panel)
        self._settings_panel.SetBackgroundColour(self.GetBackgroundColour())
        self._settings_panel.SetMinSize((560, -1))
        settings = wx.BoxSizer(wx.VERTICAL)
        self._settings_panel.SetSizer(settings)

        array_box = wx.StaticBoxSizer(wx.VERTICAL, self._settings_panel)
        self._group_boxes["array_group"] = array_box
        array_grid = wx.FlexGridSizer(cols=4, vgap=8, hgap=10)
        self._active_grid = array_grid
        self._spin(array_box.GetStaticBox(), "columns", config.columns, 1, 100, 1, 0)
        self._spin(array_box.GetStaticBox(), "rows", config.rows, 1, 100, 1, 0)
        self._spin(
            array_box.GetStaticBox(), "x_gap", config.x_gap_mm, 0, 100, 0.1, 2
        )
        self._spin(
            array_box.GetStaticBox(), "y_gap", config.y_gap_mm, 0, 100, 0.1, 2
        )
        self._labels["panel_mode"] = wx.StaticText(array_box.GetStaticBox())
        self._mode_choice = wx.Choice(
            array_box.GetStaticBox(),
            choices=[self.tr("vcut_mode"), self.tr("single_board_mode")],
        )
        self._mode_choice.SetMinSize((150, -1))
        self._mode_choice.SetMaxSize((150, -1))
        self._mode_choice.SetSelection(0)
        self._mode_choice.Bind(wx.EVT_CHOICE, self._on_mode_change)
        array_box.Add(array_grid, 0, wx.EXPAND | wx.ALL, 10)
        mode_row = wx.BoxSizer(wx.HORIZONTAL)
        mode_row.Add(self._labels["panel_mode"], 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        mode_row.Add(self._mode_choice, 0, wx.ALIGN_CENTER_VERTICAL)
        array_box.Add(mode_row, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        settings.Add(array_box, 0, wx.EXPAND | wx.BOTTOM, 12)

        rail_box = wx.StaticBoxSizer(wx.VERTICAL, self._settings_panel)
        self._group_boxes["rail_group"] = rail_box
        rail_grid = wx.FlexGridSizer(cols=2, vgap=8, hgap=12)
        self._active_grid = rail_grid
        self._spin(
            rail_box.GetStaticBox(),
            "rail_width",
            config.rail_width_mm,
            1,
            30,
            0.5,
            2,
        )
        self._labels["rail_sides"] = wx.StaticText(rail_box.GetStaticBox())
        rail_box.Add(rail_grid, 0, wx.EXPAND | wx.ALL, 10)
        rail_box.Add(
            self._labels["rail_sides"],
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM,
            10,
        )
        rail_sides_grid = wx.FlexGridSizer(cols=4, vgap=6, hgap=8)
        rail_sides_grid.Add(
            self._check(rail_box.GetStaticBox(), "left", config.rail_left)
        )
        rail_sides_grid.Add(
            self._check(rail_box.GetStaticBox(), "right", config.rail_right)
        )
        rail_sides_grid.Add(
            self._check(rail_box.GetStaticBox(), "top", config.rail_top)
        )
        rail_sides_grid.Add(
            self._check(rail_box.GetStaticBox(), "bottom", config.rail_bottom)
        )
        rail_box.Add(rail_sides_grid, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        settings.Add(rail_box, 0, wx.EXPAND | wx.BOTTOM, 12)

        mark_box = wx.StaticBoxSizer(wx.VERTICAL, self._settings_panel)
        self._group_boxes["mark_group"] = mark_box
        self._check(mark_box.GetStaticBox(), "enable_marks", config.marks_enabled)
        mark_box.Add(self._ctl_enable_marks, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        mark_grid = wx.FlexGridSizer(cols=2, vgap=8, hgap=10)
        self._active_grid = mark_grid
        self._spin(
            mark_box.GetStaticBox(), "copper_diameter", config.mark_copper_mm, 0.2, 5, 0.1, 2
        )
        self._spin(
            mark_box.GetStaticBox(), "mask_diameter", config.mark_mask_mm, 0.3, 10, 0.1, 2
        )
        self._spin(
            mark_box.GetStaticBox(),
            "top_feed_offset",
            config.mark_top_offset_mm,
            0,
            1000,
            0.5,
            2,
        )
        self._spin(
            mark_box.GetStaticBox(),
            "bottom_feed_offset",
            config.mark_bottom_offset_mm,
            0,
            1000,
            0.5,
            2,
        )
        mark_box.Add(mark_grid, 0, wx.EXPAND | wx.ALL, 10)
        self._labels["mark_note"] = wx.StaticText(mark_box.GetStaticBox())
        self._labels["mark_note"].SetMinSize((500, -1))
        self._labels["mark_note"].SetMaxSize((500, -1))
        mark_box.Add(self._labels["mark_note"], 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        settings.Add(mark_box, 0, wx.EXPAND | wx.BOTTOM, 12)

        self._labels["backup_note"] = wx.StaticText(self._settings_panel)
        self._labels["backup_note"].SetForegroundColour(wx.Colour(156, 91, 20))
        self._labels["backup_note"].SetMinSize((500, -1))
        self._labels["backup_note"].SetMaxSize((500, -1))
        settings.Add(self._labels["backup_note"], 0, wx.EXPAND | wx.BOTTOM, 8)

        preview_box = wx.StaticBoxSizer(wx.VERTICAL, self._body_panel)
        self._group_boxes["preview"] = preview_box
        self.preview = PanelPreview(preview_box.GetStaticBox(), self.tr)
        preview_box.Add(self.preview, 1, wx.EXPAND | wx.ALL, 8)

        for group in self._group_boxes.values():
            box = group.GetStaticBox()
            box.SetBackgroundColour(wx.Colour(255, 255, 255))
            font = box.GetFont()
            font.SetWeight(wx.FONTWEIGHT_BOLD)
            box.SetFont(font)
            box.SetForegroundColour(wx.Colour(39, 69, 92))

        body.Add(self._settings_panel, 1, wx.EXPAND | wx.RIGHT, 18)
        body.Add(preview_box, 1, wx.EXPAND)
        self._body_panel.SetSizer(body)
        outer.Add(self._body_panel, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 18)

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        self._cancel_button = wx.Button(self, id=wx.ID_CANCEL)
        self._cancel_button.SetMinSize((96, 34))
        self._ok_button = wx.Button(self, id=wx.ID_OK)
        self._ok_button.SetMinSize((180, 34))
        self._ok_button.SetBackgroundColour(wx.Colour(20, 139, 158))
        self._ok_button.SetForegroundColour(wx.Colour(255, 255, 255))
        self._ok_button.SetFont(self._ok_button.GetFont().Bold())
        buttons.AddStretchSpacer(1)
        buttons.Add(self._cancel_button, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        buttons.Add(self._ok_button, 0, wx.ALIGN_CENTER_VERTICAL)
        outer.Add(buttons, 0, wx.EXPAND | wx.ALL, 18)
        self.SetSizer(outer)
        self.Bind(wx.EVT_BUTTON, self._on_ok, id=wx.ID_OK)

    def _fit_to_display(self) -> None:
        display_index = wx.Display.GetFromWindow(self)
        if display_index == wx.NOT_FOUND:
            display_index = 0
        client_width, client_height = wx.Display(display_index).GetClientArea().GetSize()
        self.Layout()
        self._body_panel.Layout()
        content_width, content_height = self._body_panel.GetSizer().GetMinSize()
        available_width = max(760, client_width - 32)
        minimum_width = min(available_width, max(900, content_width + 80))
        minimum_height = max(700, content_height + 180)
        preferred_width = min(
            1280,
            max(minimum_width, int(client_width * 0.86), content_width + 120),
        )
        width = min(available_width, preferred_width)
        height = min(
            max(720, client_height - 32),
            max(minimum_height, content_height + 160),
        )
        self.SetMinSize((minimum_width, minimum_height))
        self.SetSize((width, height))
        self.CentreOnScreen()
        self.Layout()
        self._body_panel.Layout()

    def _on_language(self, _event) -> None:
        values = ("auto", "zh", "en")
        self.tr.set_language(values[self._language_choice.GetSelection()])
        self.preview.tr = self.tr
        self._refresh_texts()
        self._update_preview()
        save_settings({"language": self.tr.language})

    def _on_mode_change(self, _event) -> None:
        self._mode = "single" if self._mode_choice.GetSelection() == 1 else "vcut"
        self._refresh_texts()
        self._set_config_enabled()
        self._update_preview()

    def get_mode(self) -> str:
        return self._mode

    def _set_config_enabled(self) -> None:
        single = self.get_mode() == "single"
        for name in (
            "columns",
            "rows",
            "x_gap",
            "y_gap",
            "rail_width",
            "left",
            "right",
            "top",
            "bottom",
            "enable_marks",
            "copper_diameter",
            "mask_diameter",
            "top_feed_offset",
            "bottom_feed_offset",
        ):
            control = getattr(self, f"_ctl_{name}")
            if single:
                control.Enable(False)
            elif name in (
                "copper_diameter",
                "mask_diameter",
                "top_feed_offset",
                "bottom_feed_offset",
            ):
                control.Enable(self._ctl_enable_marks.GetValue())
            else:
                control.Enable(True)

    def _set_wrapped_text(self, control, text: str, width: int) -> None:
        dc = wx.ClientDC(control)
        dc.SetFont(control.GetFont())
        lines: list[str] = []
        for paragraph in text.splitlines() or [""]:
            current = ""
            for char in paragraph:
                candidate = current + char
                if current and dc.GetTextExtent(candidate)[0] > width:
                    break_at = current.rfind(" ")
                    if break_at > 0:
                        lines.append(current[:break_at])
                        current = current[break_at + 1:] + char
                    else:
                        lines.append(current)
                        current = char
                else:
                    current = candidate
            lines.append(current)
        control.SetLabel("\n".join(lines))
        control.SetMinSize((width, -1))
        control.SetMaxSize((width, -1))

    def _refresh_texts(self) -> None:
        title = f"{self.tr('dialog_title')} · v{PLUGIN_VERSION}"
        self.SetTitle(title)
        for key, control in self._labels.items():
            if key in {"dialog_subtitle", "mark_note", "backup_note"}:
                continue
            control.SetLabel(self.tr(key))
        self._labels["dialog_title"].SetLabel(title)
        self._mode_choice.SetItems(
            [self.tr("vcut_mode"), self.tr("single_board_mode")]
        )
        self._mode_choice.SetSelection(1 if self._mode == "single" else 0)
        for key, sizer in self._group_boxes.items():
            sizer.GetStaticBox().SetLabel(self.tr(key))
        if self._ok_button:
            label_key = "restore_apply" if self.get_mode() == "single" else "apply_save"
            self._ok_button.SetLabel(self.tr(label_key))
        if self._cancel_button:
            self._cancel_button.SetLabel(self.tr("cancel"))
        note_key = "restore_note" if self.get_mode() == "single" else "backup_note"
        self._set_wrapped_text(
            self._labels["dialog_subtitle"],
            self.tr("dialog_subtitle"),
            640,
        )
        self._set_wrapped_text(
            self._labels["mark_note"],
            self.tr("mark_note"),
            500,
        )
        self._set_wrapped_text(
            self._labels["backup_note"],
            self.tr(note_key),
            500,
        )
        self.Layout()
        if hasattr(self, "_body_panel"):
            self._body_panel.Layout()

    def _read_config(self) -> PanelConfig:
        return PanelConfig(
            columns=int(round(self._ctl_columns.GetValue())),
            rows=int(round(self._ctl_rows.GetValue())),
            x_gap_mm=self._ctl_x_gap.GetValue(),
            y_gap_mm=self._ctl_y_gap.GetValue(),
            rail_width_mm=self._ctl_rail_width.GetValue(),
            rail_left=self._ctl_left.GetValue(),
            rail_right=self._ctl_right.GetValue(),
            rail_top=self._ctl_top.GetValue(),
            rail_bottom=self._ctl_bottom.GetValue(),
            marks_enabled=self._ctl_enable_marks.GetValue(),
            mark_copper_mm=self._ctl_copper_diameter.GetValue(),
            mark_mask_mm=self._ctl_mask_diameter.GetValue(),
            mark_top_offset_mm=self._ctl_top_feed_offset.GetValue(),
            mark_bottom_offset_mm=self._ctl_bottom_feed_offset.GetValue(),
        )

    def get_config(self) -> PanelConfig:
        return self._read_config()

    def _on_change(self, _event) -> None:
        if self.get_mode() == "single":
            self._set_config_enabled()
            self._update_preview()
            return
        enabled = self._ctl_enable_marks.GetValue()
        for name in (
            "copper_diameter",
            "mask_diameter",
            "top_feed_offset",
            "bottom_feed_offset",
        ):
            getattr(self, f"_ctl_{name}").Enable(enabled)
        self._update_preview()

    def _update_preview(self) -> None:
        if self.get_mode() == "single":
            self.preview.set_single_board(self.board_bbox)
            return
        try:
            config = self._read_config()
            config.validate()
            layout = make_layout(self.board_bbox, config)
            self.preview.set_data(self.board_bbox, layout)
        except (ConfigError, ValueError) as exc:
            code = exc.code if isinstance(exc, ConfigError) else "invalid_columns"
            self.preview.set_data(self.board_bbox, None, self.tr(code))

    def _on_ok(self, event) -> None:
        if self.get_mode() == "single":
            save_settings({"language": self.tr.language})
            event.Skip()
            return
        try:
            config = self._read_config()
            config.validate()
            make_layout(self.board_bbox, config)
        except (ConfigError, ValueError) as exc:
            code = exc.code if isinstance(exc, ConfigError) else "invalid_columns"
            wx.MessageBox(
                self.tr(code),
                self.tr("invalid_title"),
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return
        save_settings({"language": self.tr.language, "config": config.to_dict()})
        event.Skip()


class KiCadPanelizer(pcbnew.ActionPlugin):
    def defaults(self) -> None:
        settings = load_settings()
        translator = Translator(str(settings.get("language", "auto")))
        self.name = f"{translator('plugin_name')} v{PLUGIN_VERSION}"
        self.category = "PCB"
        self.description = translator("plugin_description")
        self.show_toolbar_button = True
        icon = APP_DIR / "icon.png"
        if icon.exists():
            self.icon_file_name = str(icon)

    def Run(self) -> None:
        settings = load_settings()
        translator = Translator(str(settings.get("language", "auto")))
        board = pcbnew.GetBoard()

        if not board.GetFileName():
            wx.MessageBox(
                translator("no_board_file"),
                translator("error_title"),
                wx.OK | wx.ICON_WARNING,
            )
            return

        try:
            bbox = original_single_board_bbox(board)
        except PanelizerError as exc:
            key = "no_outline" if exc.code == "no_outline" else "generic_error"
            title_key = "no_outline_title"
            wx.MessageBox(
                translator(key),
                translator(title_key),
                wx.OK | wx.ICON_WARNING,
            )
            return

        config = PanelConfig.from_dict(settings.get("config"))  # type: ignore[arg-type]
        parent = wx.GetActiveWindow()
        dialog = PanelizerDialog(parent, bbox, translator, config)
        try:
            if dialog.ShowModal() != wx.ID_OK:
                return
            config = dialog.get_config()
            mode = dialog.get_mode()
        finally:
            dialog.Destroy()

        try:
            if mode == "single":
                restored = restore_single_board_and_save(board)
                pcbnew.Refresh()
                wx.MessageBox(
                    translator(
                        "restored_body",
                        edges=restored.removed_edges,
                        marks=restored.removed_fiducials,
                        annotations=restored.removed_annotations,
                    ),
                    translator("restored_title"),
                    wx.OK | wx.ICON_INFORMATION,
                )
                return

            result = panelize_and_save(board, config)
            pcbnew.Refresh()
            wx.MessageBox(
                translator(
                    "applied_body",
                    backup=result.backup_path,
                    edges=result.added_edges,
                    marks=result.added_marks,
                ),
                translator("applied_title"),
                wx.OK | wx.ICON_INFORMATION,
            )
        except PanelizerError as exc:
            if exc.code == "already_panelized":
                message = translator("already_panelized")
                title = translator("already_panelized_title")
            elif exc.code == "not_panelized":
                message = translator("not_panelized")
                title = translator("not_panelized_title")
            elif exc.code == "no_restore_metadata":
                message = translator("no_restore_metadata")
                title = translator("error_title")
            elif exc.code == "no_board_file":
                message = translator("no_board_file")
                title = translator("error_title")
            elif exc.code == "save_failed":
                message = translator("save_failed")
                title = translator("error_title")
            else:
                message = translator("generic_error", error=exc.detail or exc.code)
                title = translator("error_title")
            wx.MessageBox(message, title, wx.OK | wx.ICON_ERROR)
        except Exception as exc:  # noqa: BLE001
            wx.MessageBox(
                translator("generic_error", error=str(exc)),
                translator("error_title"),
                wx.OK | wx.ICON_ERROR,
            )


KiCadPanelizer().register()


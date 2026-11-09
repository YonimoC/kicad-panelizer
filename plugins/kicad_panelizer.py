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


class PanelPreview(wx.Panel):
    def __init__(self, parent, translator: Translator) -> None:
        super().__init__(parent)
        self.tr = translator
        self.board: BBox | None = None
        self.layout: PanelLayout | None = None
        self.single_mode = False
        self.error = ""
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetMinSize((460, 410))
        self.Bind(wx.EVT_PAINT, self._on_paint)

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
        self.Refresh()

    def set_single_board(self, board: BBox) -> None:
        self.board = board
        self.layout = None
        self.single_mode = True
        self.error = ""
        self.Refresh()

    def _on_paint(self, _event) -> None:
        dc = wx.BufferedPaintDC(self)
        dc.SetBackground(wx.Brush(wx.Colour(248, 249, 251)))
        dc.Clear()
        width, height = self.GetClientSize()
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

        dock = wx.Colour(219, 225, 234)
        board_fill = wx.Colour(218, 237, 252)
        edge = wx.Colour(54, 69, 91)
        dc.SetPen(wx.Pen(wx.Colour(198, 205, 216), 1))
        dc.SetBrush(wx.Brush(dock))
        dc.DrawRectangle(*rect(panel))

        dc.SetPen(wx.Pen(wx.Colour(71, 119, 166), 1))
        dc.SetBrush(wx.Brush(board_fill))
        for row in range(config.rows):
            for column in range(config.columns):
                dx, dy = layout.cell_origin(column, row)
                cell = BBox(
                    dx,
                    dy,
                    dx + layout.board.width,
                    dy + layout.board.height,
                )
                dc.SetPen(wx.Pen(wx.Colour(135, 172, 204), 1))
                dc.DrawRectangle(*rect(cell))

        dc.SetPen(wx.Pen(edge, 2))
        dc.SetBrush(wx.TRANSPARENT_BRUSH)
        dc.DrawRectangle(*rect(panel))

        for spec in mark_positions(layout):
            center = wx.Point(px(spec.x), py(spec.y))
            mask_radius = max(2, int(config.mark_mask_mm * scale / 2))
            copper_radius = max(1, int(config.mark_copper_mm * scale / 2))
            dc.SetPen(wx.Pen(wx.Colour(180, 145, 55), 1))
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
        control.Bind(wx.EVT_SPINCTRLDOUBLE, self._on_change)
        control.Bind(wx.EVT_TEXT, self._on_change)
        grid = getattr(self, "_active_grid")
        grid.Add(label, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(control, 1, wx.EXPAND)
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
        outer = wx.BoxSizer(wx.VERTICAL)
        header = wx.BoxSizer(wx.HORIZONTAL)
        title = wx.StaticText(self, label="PCB Panelizer")
        title_font = title.GetFont()
        title_font.SetPointSize(title_font.GetPointSize() + 6)
        title_font.SetWeight(wx.FONTWEIGHT_BOLD)
        title.SetFont(title_font)
        self._labels["dialog_title"] = title
        self._labels["dialog_subtitle"] = wx.StaticText(self)
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

        self._scroll = wx.ScrolledWindow(
            self,
            style=wx.VSCROLL | wx.HSCROLL | wx.BORDER_NONE,
        )
        self._scroll.SetScrollRate(12, 12)
        self._scroll.SetBackgroundColour(self.GetBackgroundColour())
        body = wx.BoxSizer(wx.HORIZONTAL)
        settings = wx.BoxSizer(wx.VERTICAL)

        array_box = wx.StaticBoxSizer(wx.VERTICAL, self._scroll)
        self._group_boxes["array_group"] = array_box
        array_grid = wx.FlexGridSizer(cols=2, vgap=8, hgap=12)
        array_grid.AddGrowableCol(1)
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
        self._mode_choice.SetSelection(0)
        self._mode_choice.Bind(wx.EVT_CHOICE, self._on_mode_change)
        array_grid.Add(self._labels["panel_mode"], 0, wx.ALIGN_CENTER_VERTICAL)
        array_grid.Add(self._mode_choice, 1, wx.EXPAND)
        array_box.Add(array_grid, 0, wx.EXPAND | wx.ALL, 10)
        settings.Add(array_box, 0, wx.EXPAND | wx.BOTTOM, 12)

        rail_box = wx.StaticBoxSizer(wx.VERTICAL, self._scroll)
        self._group_boxes["rail_group"] = rail_box
        rail_grid = wx.FlexGridSizer(cols=2, vgap=8, hgap=12)
        rail_grid.AddGrowableCol(1)
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
        rail_side_row = wx.BoxSizer(wx.HORIZONTAL)
        rail_side_row.Add(self._check(rail_box.GetStaticBox(), "left", config.rail_left), 0, wx.RIGHT, 12)
        rail_side_row.Add(self._check(rail_box.GetStaticBox(), "right", config.rail_right), 0, wx.RIGHT, 12)
        rail_side_row.Add(self._check(rail_box.GetStaticBox(), "top", config.rail_top), 0, wx.RIGHT, 12)
        rail_side_row.Add(self._check(rail_box.GetStaticBox(), "bottom", config.rail_bottom), 0)
        self._labels["rail_sides"] = wx.StaticText(rail_box.GetStaticBox())
        rail_grid.Add(self._labels["rail_sides"], 0, wx.ALIGN_TOP)
        rail_grid.Add(rail_side_row, 1, wx.EXPAND)
        rail_box.Add(rail_grid, 0, wx.EXPAND | wx.ALL, 10)
        settings.Add(rail_box, 0, wx.EXPAND | wx.BOTTOM, 12)

        mark_box = wx.StaticBoxSizer(wx.VERTICAL, self._scroll)
        self._group_boxes["mark_group"] = mark_box
        mark_grid = wx.FlexGridSizer(cols=2, vgap=8, hgap=12)
        mark_grid.AddGrowableCol(1)
        self._active_grid = mark_grid
        self._check(mark_box.GetStaticBox(), "enable_marks", config.marks_enabled)
        mark_grid.AddSpacer(1)
        mark_grid.Add(self._ctl_enable_marks, 1, wx.EXPAND)
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
        self._labels["mark_note"].Wrap(430)
        mark_box.Add(self._labels["mark_note"], 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        settings.Add(mark_box, 0, wx.EXPAND | wx.BOTTOM, 12)

        self._labels["backup_note"] = wx.StaticText(self._scroll)
        self._labels["backup_note"].SetForegroundColour(wx.Colour(156, 91, 20))
        self._labels["backup_note"].Wrap(455)
        settings.Add(self._labels["backup_note"], 0, wx.EXPAND | wx.BOTTOM, 8)

        preview_box = wx.StaticBoxSizer(wx.VERTICAL, self._scroll)
        self._group_boxes["preview"] = preview_box
        self.preview = PanelPreview(preview_box.GetStaticBox(), self.tr)
        preview_box.Add(self.preview, 1, wx.EXPAND | wx.ALL, 8)

        body.Add(settings, 0, wx.EXPAND | wx.RIGHT, 18)
        body.Add(preview_box, 1, wx.EXPAND)
        self._scroll.SetSizer(body)
        outer.Add(self._scroll, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 18)

        buttons = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        self._ok_button = self.FindWindowById(wx.ID_OK)
        self._cancel_button = self.FindWindowById(wx.ID_CANCEL)
        buttons.AddSpacer(8)
        outer.Add(buttons, 0, wx.EXPAND | wx.ALL, 18)
        self.SetSizer(outer)
        self.Bind(wx.EVT_BUTTON, self._on_ok, id=wx.ID_OK)

    def _fit_to_display(self) -> None:
        display_index = wx.Display.GetFromWindow(self)
        if display_index == wx.NOT_FOUND:
            display_index = 0
        client_width, client_height = wx.Display(display_index).GetClientArea().GetSize()
        self.Layout()
        self._scroll.FitInside()
        content_width, content_height = self._scroll.GetSizer().GetMinSize()
        width = min(max(760, client_width - 40), max(760, content_width + 100))
        height = min(max(560, client_height - 40), max(560, content_height + 190))
        self.SetMinSize((760, 560))
        self.SetSize((width, height))
        self.CentreOnScreen()
        self.Layout()
        self._scroll.FitInside()

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

    def _refresh_texts(self) -> None:
        self.SetTitle(self.tr("dialog_title"))
        for key, control in self._labels.items():
            control.SetLabel(self.tr(key))
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
        self._labels["backup_note"].SetLabel(self.tr(note_key))
        self._labels["mark_note"].Wrap(430)
        self._labels["backup_note"].Wrap(455)
        self.Layout()
        if hasattr(self, "_scroll"):
            self._scroll.FitInside()

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
        self.name = translator("plugin_name")
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


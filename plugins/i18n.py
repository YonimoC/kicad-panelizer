"""Small, dependency-free translation layer for the panelizer UI."""

from __future__ import annotations

import locale
import os
from collections.abc import Mapping


SUPPORTED_LANGUAGES = ("auto", "zh", "en")
LANGUAGE_LABELS = {
    "auto": "Auto / 自动",
    "zh": "中文",
    "en": "English",
}

TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        "plugin_name": "PCB Panelizer",
        "plugin_description": (
            "Create a V-cut panel from the current board outline, add process "
            "rails, and place top/bottom fiducials."
        ),
        "dialog_title": "PCB Panelizer",
        "dialog_subtitle": (
            "Only Edge.Cuts outlines are arrayed. All other board content stays "
            "in the original first board."
        ),
        "language": "Language",
        "array_group": "Array",
        "columns": "Columns",
        "rows": "Rows",
        "x_gap": "Column gap (mm)",
        "y_gap": "Row gap (mm)",
        "panel_mode": "Panel mode",
        "vcut_mode": "V-cut panel",
        "single_board_mode": "Single-board mode",
        "cut_type": "Separation",
        "cut_type_value": "V-cut (Edge.Cuts)",
        "rail_group": "Process rails",
        "rail_width": "Rail width (mm)",
        "rail_sides": "Rail sides",
        "left": "Left",
        "right": "Right",
        "top": "Top",
        "bottom": "Bottom",
        "mark_group": "Fiducials (Mark points)",
        "enable_marks": "Add fiducials",
        "copper_diameter": "Copper diameter (mm)",
        "mask_diameter": "Mask opening (mm)",
        "top_feed_offset": "Top-layer feed offset (mm)",
        "bottom_feed_offset": "Bottom-layer feed offset (mm)",
        "mark_note": (
            "Fiducials are centered on each enabled rail. F.Cu marks use the "
            "top feed offset; B.Cu marks use the bottom feed offset."
        ),
        "preview": "Preview",
        "board_size": "Single board: {width:.2f} x {height:.2f} mm",
        "panel_size": "Panel: {width:.2f} x {height:.2f} mm",
        "single_board_preview": "Single-board restoration preview",
        "counts": "{columns} x {rows}, {count} boards",
        "preview_error": "Preview unavailable",
        "top_mark_legend": "F.Cu Mark",
        "bottom_mark_legend": "B.Cu Mark",
        "backup_note": (
            "Apply saves the current PCB and keeps one fixed backup named "
            "<board>.kicad_pcb.bak. The backup is refreshed each time a panel "
            "is generated."
        ),
        "restore_note": (
            "Single-board mode deletes only panel-added outlines, process rails, "
            "fiducials, and the internal marker from the current PCB. Original "
            "board content and the original Edge.Cuts are preserved."
        ),
        "apply_save": "Apply and save",
        "restore_apply": "Restore single board and save",
        "cancel": "Cancel",
        "invalid_title": "Invalid parameters",
        "invalid_columns": "Columns must be between 1 and 100.",
        "invalid_rows": "Rows must be between 1 and 100.",
        "invalid_gap": "Row and column gaps must be between 0 and 100 mm.",
        "invalid_rail_width": "Rail width must be between 1 and 30 mm.",
        "invalid_rail_sides": "Select at least one process rail.",
        "invalid_mark_copper": "Fiducial copper diameter must be between 0.2 and 5 mm.",
        "invalid_mark_mask": "Mask opening must be at least 0.1 mm larger than copper.",
        "invalid_mark_offsets": "Fiducial offsets must be between 0 and 1000 mm.",
        "invalid_mark_fit": (
            "The selected feed offsets do not fit inside the panel/rail geometry."
        ),
        "no_board_file": "Save the current PCB to a .kicad_pcb file before panelizing.",
        "no_outline_title": "Missing board outline",
        "no_outline": "No board-level Edge.Cuts outline was found on the current PCB.",
        "already_panelized_title": "PCB already panelized",
        "already_panelized": (
            "This PCB is already panelized. Use Single-board mode to remove the "
            "panel-added outlines, rails, and fiducials."
        ),
        "not_panelized_title": "PCB is not panelized",
        "not_panelized": "No panelizer marker was found on the current PCB.",
        "no_restore_metadata": (
            "This panel does not contain the original outline metadata needed "
            "for safe in-place restoration. Re-panel with the current version "
            "before using Single-board mode."
        ),
        "save_failed": "KiCad could not save the PCB file.",
        "applied_title": "Panel created",
        "applied_body": (
            "The PCB was panelized and saved.\n\nBackup:\n{backup}\n\n"
            "Added {edges} outline elements and {marks} fiducials."
        ),
        "restored_title": "Single board restored",
        "restored_body": (
            "Panel additions were removed from the current PCB and the file was "
            "saved.\n\nRemoved {edges} extra outline elements and {marks} "
            "generated fiducials, plus {annotations} dimension annotations. "
            "The original board content was not replaced."
        ),
        "error_title": "Panelizer error",
        "generic_error": "The panelizer could not complete the operation:\n{error}",
    },
    "zh": {
        "plugin_name": "PCB 参数化拼板",
        "plugin_description": "按当前 PCB 外边框生成 V 割拼板，添加工艺边并放置顶/底面 Mark 点。",
        "dialog_title": "PCB 参数化拼板",
        "dialog_subtitle": "仅复制 Edge.Cuts 外边框；其余板内内容只保留在原始单板中。",
        "language": "界面语言",
        "array_group": "拼板阵列",
        "columns": "列数",
        "rows": "行数",
        "x_gap": "列距 (mm)",
        "y_gap": "行距 (mm)",
        "panel_mode": "拼板方式",
        "vcut_mode": "V 割拼板",
        "single_board_mode": "单板模式",
        "cut_type": "分离方式",
        "cut_type_value": "V 割 (Edge.Cuts)",
        "rail_group": "工艺边",
        "rail_width": "工艺边宽度 (mm)",
        "rail_sides": "工艺边位置",
        "left": "左边",
        "right": "右边",
        "top": "上边",
        "bottom": "下边",
        "mark_group": "光学定位点 (Mark)",
        "enable_marks": "添加 Mark 点",
        "copper_diameter": "铜直径 (mm)",
        "mask_diameter": "开窗直径 (mm)",
        "top_feed_offset": "顶层进板位置 (mm)",
        "bottom_feed_offset": "底层进板位置 (mm)",
        "mark_note": (
            "Mark 点居中放置在启用的工艺边上。顶层 F.Cu Mark 使用顶部进板距离，"
            "底层 B.Cu Mark 使用底部进板距离。"
        ),
        "preview": "预览",
        "board_size": "单板尺寸：{width:.2f} × {height:.2f} mm",
        "panel_size": "拼板尺寸：{width:.2f} × {height:.2f} mm",
        "single_board_preview": "单板恢复预览",
        "counts": "{columns} × {rows}，共 {count} 片",
        "preview_error": "无法预览",
        "top_mark_legend": "顶层 Mark",
        "bottom_mark_legend": "底层 Mark",
        "backup_note": "确认后先保存当前 PCB，并保留一个固定的原板备份：<板文件>.kicad_pcb.bak；再次拼板时更新该备份。",
        "restore_note": (
            "单板模式只删除当前 PCB 中由插件新增的阵列板框、工艺边、Mark 点和内部标记；"
            "原单板内容和原始 Edge.Cuts 不会被备份文件覆盖。"
        ),
        "apply_save": "应用并保存",
        "restore_apply": "恢复单板并保存",
        "cancel": "取消",
        "invalid_title": "参数无效",
        "invalid_columns": "列数必须在 1 到 100 之间。",
        "invalid_rows": "行数必须在 1 到 100 之间。",
        "invalid_gap": "行距和列距必须在 0 到 100 mm 之间。",
        "invalid_rail_width": "工艺边宽度必须在 1 到 30 mm 之间。",
        "invalid_rail_sides": "至少需要选择一条工艺边。",
        "invalid_mark_copper": "Mark 铜直径必须在 0.2 到 5 mm 之间。",
        "invalid_mark_mask": "Mark 开窗直径必须比铜直径至少大 0.1 mm。",
        "invalid_mark_offsets": "Mark 进板位置必须在 0 到 1000 mm 之间。",
        "invalid_mark_fit": "当前进板位置无法放入拼板或工艺边范围。",
        "no_board_file": "请先将当前 PCB 保存为 .kicad_pcb 文件，再执行拼板。",
        "no_outline_title": "缺少板框",
        "no_outline": "当前 PCB 中没有找到位于 Edge.Cuts 的板级外边框。",
        "already_panelized_title": "PCB 已经拼板",
        "already_panelized": "当前 PCB 已经拼板。请选择“单板模式”，删除插件新增的板框、工艺边和 Mark 点。",
        "not_panelized_title": "PCB 尚未拼板",
        "not_panelized": "当前 PCB 中没有找到拼板标记，无法执行单板恢复。",
        "no_restore_metadata": (
            "当前拼板缺少原始板框定位信息，无法安全地原地恢复。"
            "请使用当前版本重新拼板后再测试单板模式。"
        ),
        "save_failed": "KiCad 无法保存当前 PCB 文件。",
        "applied_title": "拼板已生成",
        "applied_body": "PCB 已完成拼板并保存。\n\n备份：\n{backup}\n\n新增 {edges} 个外框元素、{marks} 个 Mark 点。",
        "restored_title": "单板已恢复",
        "restored_body": (
            "已从当前 PCB 中删除插件新增内容并保存文件。\n\n"
            "删除多余外框 {edges} 个、生成的 Mark 点 {marks} 个。"
            "删除尺寸标注 {annotations} 个。原单板内容没有被备份文件覆盖。"
        ),
        "error_title": "拼板失败",
        "generic_error": "插件无法完成操作：\n{error}",
    },
}


def _normalize_language(value: str | None) -> str:
    value = (value or "").strip().lower().replace("_", "-")
    if value.startswith("zh"):
        return "zh"
    if value.startswith("en"):
        return "en"
    return "en"


def detect_language(environ: Mapping[str, str] | None = None) -> str:
    """Return ``zh`` or ``en`` using KiCad/Python locale settings."""

    env = environ if environ is not None else os.environ
    for name in ("KICAD_LANGUAGE", "LANG", "LC_ALL", "LC_MESSAGES"):
        value = env.get(name)
        if value:
            normalized = _normalize_language(value)
            if value.lower().startswith(("zh", "en")):
                return normalized

    try:
        current = locale.getlocale()[0]
    except (TypeError, ValueError):
        current = None
    return _normalize_language(current)


class Translator:
    def __init__(self, language: str = "auto") -> None:
        self.language = language if language in SUPPORTED_LANGUAGES else "auto"

    @property
    def resolved_language(self) -> str:
        if self.language == "auto":
            return detect_language()
        return self.language

    def set_language(self, language: str) -> None:
        self.language = language if language in SUPPORTED_LANGUAGES else "auto"

    def __call__(self, key: str, **values: object) -> str:
        table = TRANSLATIONS[self.resolved_language]
        template = table.get(key) or TRANSLATIONS["en"].get(key, key)
        try:
            return template.format(**values)
        except (KeyError, ValueError):
            return template


def translation_keys() -> set[str]:
    return set(TRANSLATIONS["en"])


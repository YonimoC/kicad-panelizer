"""KiCad SWIG bindings adapter for panelization and safe file replacement."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import shutil

import pcbnew

from .geometry import BBox, ConfigError, PanelConfig, PanelLayout, make_layout, mark_positions


PANEL_MARKER = "KICAD_PANELIZER_V1"
EDGE_WIDTH_MM = 0.05


class PanelizerError(RuntimeError):
    def __init__(self, code: str, *, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class ApplyResult:
    backup_path: Path
    layout: PanelLayout
    added_edges: int
    added_marks: int


def _mm(value: float) -> int:
    return pcbnew.FromMM(value)


def _point(x: float, y: float):
    return pcbnew.VECTOR2I_MM(x, y)


def _to_mm(value: int) -> float:
    return pcbnew.ToMM(value)


def edge_drawings(board) -> list[object]:
    return [
        item
        for item in board.GetDrawings()
        if item.GetLayer() == pcbnew.Edge_Cuts
        and not (isinstance(item, pcbnew.PCB_TEXT) and item.GetText() == PANEL_MARKER)
    ]


def board_outline_bbox(board) -> BBox:
    drawings = edge_drawings(board)
    if not drawings:
        raise PanelizerError("no_outline")

    boxes = [item.GetBoundingBox() for item in drawings]
    left = min(box.GetLeft() for box in boxes)
    top = min(box.GetTop() for box in boxes)
    right = max(box.GetRight() for box in boxes)
    bottom = max(box.GetBottom() for box in boxes)
    bbox = BBox(_to_mm(left), _to_mm(top), _to_mm(right), _to_mm(bottom))
    if bbox.width <= 0 or bbox.height <= 0:
        raise PanelizerError("no_outline")
    return bbox


def has_panel_marker(board) -> bool:
    for footprint in board.GetFootprints():
        if footprint.GetReference() == PANEL_MARKER:
            return True
    for item in board.GetDrawings():
        if isinstance(item, pcbnew.PCB_TEXT) and item.GetText() == PANEL_MARKER:
            return True
    return False


def _segment_key(item) -> tuple[tuple[int, int], tuple[int, int]] | None:
    if item.GetLayer() != pcbnew.Edge_Cuts or item.GetShape() != pcbnew.S_SEGMENT:
        return None
    start = item.GetStart()
    end = item.GetEnd()
    first = (int(start.x), int(start.y))
    second = (int(end.x), int(end.y))
    return (first, second) if first <= second else (second, first)


def _add_segment(
    board,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    seen_segments: set[tuple[tuple[int, int], tuple[int, int]]],
) -> int:
    p1 = _point(x1, y1)
    p2 = _point(x2, y2)
    first = (p1.x, p1.y)
    second = (p2.x, p2.y)
    key = (first, second) if first <= second else (second, first)
    if key in seen_segments:
        return 0

    shape = pcbnew.PCB_SHAPE(board)
    shape.SetShape(pcbnew.S_SEGMENT)
    shape.SetLayer(pcbnew.Edge_Cuts)
    shape.SetWidth(_mm(EDGE_WIDTH_MM))
    shape.SetStart(p1)
    shape.SetEnd(p2)
    board.Add(shape)
    seen_segments.add(key)
    return 1


def _add_outer_outline(
    board,
    layout: PanelLayout,
    seen_segments: set[tuple[tuple[int, int], tuple[int, int]]],
) -> int:
    left, top = layout.panel.left, layout.panel.top
    right, bottom = layout.panel.right, layout.panel.bottom
    return sum(
        (
            _add_segment(board, left, top, right, top, seen_segments),
            _add_segment(board, right, top, right, bottom, seen_segments),
            _add_segment(board, right, bottom, left, bottom, seen_segments),
            _add_segment(board, left, bottom, left, top, seen_segments),
        )
    )


def _add_mark(board, config: PanelConfig, spec) -> None:
    footprint = pcbnew.FOOTPRINT(board)
    reference = f"MK_{spec.layer}_{spec.side.upper()}"
    footprint.SetReference(reference)
    footprint.SetValue("Panel fiducial")
    footprint.SetPosition(_point(spec.x, spec.y))
    footprint.SetAttributes(pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES)
    footprint.Reference().SetVisible(False)
    footprint.Value().SetVisible(False)

    pad = pcbnew.PAD(footprint)
    pad.SetNumber("")
    pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    pad.SetSize(_point(config.mark_copper_mm, config.mark_copper_mm))
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    # Footprint pads use board coordinates through the SWIG API. Keeping the
    # pad at (0, 0) makes every fiducial overlap at the board origin when the
    # footprint is saved and reloaded.
    pad.SetPosition(_point(spec.x, spec.y))

    layers = pcbnew.LSET()
    if spec.layer == "F":
        layers.AddLayer(pcbnew.F_Cu)
        layers.AddLayer(pcbnew.F_Mask)
    else:
        layers.AddLayer(pcbnew.B_Cu)
        layers.AddLayer(pcbnew.B_Mask)
    pad.SetLayerSet(layers)
    pad.SetLocalSolderMaskMargin(_mm((config.mark_mask_mm - config.mark_copper_mm) / 2.0))
    footprint.Add(pad)
    board.Add(footprint)


def _add_marker(board) -> None:
    marker = pcbnew.FOOTPRINT(board)
    marker.SetReference(PANEL_MARKER)
    marker.SetValue("Panelizer marker")
    marker.SetPosition(_point(0, 0))
    marker.SetAttributes(pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES)
    marker.Reference().SetVisible(False)
    marker.Value().SetVisible(False)
    board.Add(marker)


def apply_panelization(board, config: PanelConfig) -> tuple[PanelLayout, int, int]:
    if has_panel_marker(board):
        raise PanelizerError("already_panelized")

    try:
        config.validate()
        layout = make_layout(board_outline_bbox(board), config)
    except ConfigError as exc:
        raise PanelizerError(exc.code) from exc

    source_drawings = edge_drawings(board)
    seen_segments = {
        key for item in source_drawings if (key := _segment_key(item)) is not None
    }
    added_edges = 0

    for row in range(config.rows):
        for column in range(config.columns):
            if row == 0 and column == 0:
                continue
            dx = column * layout.pitch_x
            dy = row * layout.pitch_y
            for item in source_drawings:
                key = _segment_key(item)
                shifted_key = None
                if key is not None:
                    dx_i = _mm(dx)
                    dy_i = _mm(dy)
                    first = (key[0][0] + dx_i, key[0][1] + dy_i)
                    second = (key[1][0] + dx_i, key[1][1] + dy_i)
                    shifted_key = (first, second) if first <= second else (second, first)
                    if shifted_key in seen_segments:
                        continue

                clone = item.Duplicate()
                clone.Move(_point(dx, dy))
                board.Add(clone)
                added_edges += 1
                if shifted_key is not None:
                    seen_segments.add(shifted_key)

    added_edges += _add_outer_outline(board, layout, seen_segments)
    mark_count = 0
    for spec in mark_positions(layout):
        _add_mark(board, config, spec)
        mark_count += 1
    _add_marker(board)
    return layout, added_edges, mark_count


def make_backup(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = path.with_name(f"{path.stem}.backup-{stamp}{path.suffix}")
    sequence = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.stem}.backup-{stamp}-{sequence}{path.suffix}")
        sequence += 1
    shutil.copy2(path, candidate)
    return candidate


def panelize_and_save(board, config: PanelConfig) -> ApplyResult:
    filename = board.GetFileName()
    if not filename:
        raise PanelizerError("no_board_file")
    path = Path(filename)

    if not pcbnew.SaveBoard(str(path), board):
        raise PanelizerError("save_failed")
    backup = make_backup(path)

    layout, added_edges, mark_count = apply_panelization(board, config)
    if not pcbnew.SaveBoard(str(path), board):
        raise PanelizerError("save_failed", detail=f"Backup: {backup}")
    return ApplyResult(backup, layout, added_edges, mark_count)


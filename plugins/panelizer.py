"""KiCad SWIG bindings adapter for panelization and safe file replacement."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import shutil
import tempfile

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


@dataclass(frozen=True)
class RestoreResult:
    removed_edges: int
    removed_fiducials: int
    removed_markers: int


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


def _uuid_text(item) -> str | None:
    try:
        return item.m_Uuid.AsString()
    except (AttributeError, TypeError):
        return None


def _panel_metadata(board) -> dict[str, object] | None:
    prefix = f"{PANEL_MARKER}|"
    for footprint in board.GetFootprints():
        if footprint.GetReference() != PANEL_MARKER:
            continue
        value = footprint.GetValue()
        if not value.startswith(prefix):
            return None
        try:
            data = json.loads(value[len(prefix):])
        except (TypeError, ValueError):
            return None
        return data if isinstance(data, dict) else None
    return None


def _legacy_reference_outlines(board) -> Counter[tuple[object, ...]] | None:
    filename = board.GetFileName()
    backup = find_latest_original_backup(Path(filename)) if filename else None
    if backup is None:
        return None
    if backup.suffix.lower() == ".kicad_pcb":
        backup_board = pcbnew.LoadBoard(str(backup))
    else:
        with tempfile.TemporaryDirectory() as temp_dir:
            load_path = Path(temp_dir) / "reference.kicad_pcb"
            shutil.copy2(backup, load_path)
            backup_board = pcbnew.LoadBoard(str(load_path))
    if backup_board is None:
        return None
    return Counter(_edge_bbox_key(item) for item in edge_drawings(backup_board))


def _add_marker(board, board_bbox: BBox, edge_ids: list[str]) -> None:
    metadata = {
        "bbox": {
            "left": board_bbox.left,
            "top": board_bbox.top,
            "right": board_bbox.right,
            "bottom": board_bbox.bottom,
        },
        "edge_ids": edge_ids,
    }
    marker = pcbnew.FOOTPRINT(board)
    marker.SetReference(PANEL_MARKER)
    marker.SetValue(f"{PANEL_MARKER}|{json.dumps(metadata, separators=(',', ':'))}")
    marker.SetPosition(_point(0, 0))
    marker.SetAttributes(pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES)
    marker.Reference().SetVisible(False)
    marker.Value().SetVisible(False)
    board.Add(marker)


def apply_panelization(board, config: PanelConfig) -> tuple[PanelLayout, int, int]:
    if has_panel_marker(board):
        if not has_only_single_board_outline(board):
            raise PanelizerError("already_panelized")
        restore_single_board(board)

    try:
        config.validate()
        layout = make_layout(board_outline_bbox(board), config)
    except ConfigError as exc:
        raise PanelizerError(exc.code) from exc

    source_drawings = edge_drawings(board)
    original_edge_ids = [
        uuid for item in source_drawings if (uuid := _uuid_text(item)) is not None
    ]
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
    _add_marker(board, layout.board, original_edge_ids)
    return layout, added_edges, mark_count


def make_backup(path: Path) -> Path:
    candidate = path.with_name(f"{path.name}.bak")
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


def _bbox_from_metadata(data: dict[str, object]) -> BBox | None:
    raw = data.get("bbox")
    if not isinstance(raw, dict):
        return None
    try:
        return BBox(
            float(raw["left"]),
            float(raw["top"]),
            float(raw["right"]),
            float(raw["bottom"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _edge_bbox_key(item) -> tuple[object, ...]:
    box = item.GetBoundingBox()
    return (
        item.GetShape(),
        item.GetLayer(),
        item.GetWidth(),
        box.GetLeft(),
        box.GetTop(),
        box.GetRight(),
        box.GetBottom(),
    )


def find_latest_original_backup(path: Path) -> Path | None:
    fixed_backup = path.with_name(f"{path.name}.bak")
    if fixed_backup.is_file():
        return fixed_backup

    pattern = f"{path.stem}.backup-*{path.suffix}"
    backups = sorted(
        path.parent.glob(pattern),
        key=lambda candidate: candidate.stat().st_mtime,
        reverse=True,
    )
    return backups[0] if backups else None


def _inside_bbox(item, bbox: BBox, tolerance: float) -> bool:
    box = item.GetBoundingBox()
    return (
        _to_mm(box.GetLeft()) >= bbox.left - tolerance
        and _to_mm(box.GetTop()) >= bbox.top - tolerance
        and _to_mm(box.GetRight()) <= bbox.right + tolerance
        and _to_mm(box.GetBottom()) <= bbox.bottom + tolerance
    )


def _is_generated_mark(footprint) -> bool:
    return (
        footprint.GetReference().startswith("MK_")
        and footprint.GetValue() == "Panel fiducial"
    )


def has_only_single_board_outline(board) -> bool:
    edge_items = edge_drawings(board)
    if not edge_items:
        return False
    if not has_panel_marker(board):
        return True

    metadata = _panel_metadata(board)

    edge_ids_raw = metadata.get("edge_ids") if metadata else None
    if isinstance(edge_ids_raw, list):
        original_ids = {value for value in edge_ids_raw if isinstance(value, str)}
        if original_ids:
            return all(_uuid_text(item) in original_ids for item in edge_items)

    original_bbox = _bbox_from_metadata(metadata) if metadata else None
    if original_bbox is not None:
        return all(_inside_bbox(item, original_bbox, 0.01) for item in edge_items)

    legacy_reference = _legacy_reference_outlines(board)
    if legacy_reference is not None:
        return Counter(_edge_bbox_key(item) for item in edge_items) == legacy_reference
    return False


def original_single_board_bbox(board) -> BBox:
    metadata = _panel_metadata(board)
    bbox = _bbox_from_metadata(metadata) if metadata else None
    if bbox is not None:
        return bbox
    if has_panel_marker(board):
        legacy_reference = _legacy_reference_outlines(board)
        if legacy_reference:
            filename = board.GetFileName()
            backup = find_latest_original_backup(Path(filename)) if filename else None
            if backup is not None:
                return board_outline_bbox(pcbnew.LoadBoard(str(backup)))
    return board_outline_bbox(board)


def restore_single_board(board) -> RestoreResult:
    """Delete panel-added outlines and fiducials from the current board.

    Original board items are never replaced from a backup. New panels store the
    UUIDs of the original Edge.Cuts items in the hidden marker footprint; older
    panels fall back to the recorded original board bounding box.
    """

    if not has_panel_marker(board):
        raise PanelizerError("not_panelized")

    metadata = _panel_metadata(board)
    original_bbox = _bbox_from_metadata(metadata) if metadata else None
    edge_ids_raw = metadata.get("edge_ids") if metadata else None
    original_edge_ids = (
        {value for value in edge_ids_raw if isinstance(value, str)}
        if isinstance(edge_ids_raw, list)
        else set()
    )

    legacy_reference: Counter[tuple[object, ...]] | None = None
    if original_bbox is None and not original_edge_ids:
        legacy_reference = _legacy_reference_outlines(board)
        if legacy_reference is None:
            raise PanelizerError("no_restore_metadata")

    removed_edges = 0
    kept_edges = 0
    for item in list(board.GetDrawings()):
        if item.GetLayer() != pcbnew.Edge_Cuts:
            continue
        keep = False
        if original_edge_ids:
            keep = _uuid_text(item) in original_edge_ids
        elif legacy_reference is not None:
            key = _edge_bbox_key(item)
            if legacy_reference[key] > 0:
                keep = True
                legacy_reference[key] -= 1
        elif original_bbox is not None:
            keep = _inside_bbox(item, original_bbox, 0.01)
        if not keep:
            board.RemoveNative(item)
            removed_edges += 1
        else:
            kept_edges += 1

    if kept_edges == 0:
        raise PanelizerError("no_restore_metadata")

    removed_fiducials = 0
    for footprint in list(board.GetFootprints()):
        if _is_generated_mark(footprint):
            board.RemoveNative(footprint)
            removed_fiducials += 1

    removed_markers = 0
    for footprint in list(board.GetFootprints()):
        if footprint.GetReference() == PANEL_MARKER:
            board.RemoveNative(footprint)
            removed_markers += 1
    for item in list(board.GetDrawings()):
        if isinstance(item, pcbnew.PCB_TEXT) and item.GetText() == PANEL_MARKER:
            board.RemoveNative(item)
            removed_markers += 1

    return RestoreResult(
        removed_edges=removed_edges,
        removed_fiducials=removed_fiducials,
        removed_markers=removed_markers,
    )


def restore_single_board_and_save(board) -> RestoreResult:
    filename = board.GetFileName()
    if not filename:
        raise PanelizerError("no_board_file")

    result = restore_single_board(board)
    if not pcbnew.SaveBoard(filename, board):
        raise PanelizerError("save_failed")
    return result


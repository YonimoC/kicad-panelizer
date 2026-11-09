from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import pcbnew


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from plugins.geometry import PanelConfig  # noqa: E402
from plugins.panelizer import (  # noqa: E402
    PanelizerError,
    apply_panelization,
    board_outline_bbox,
    edge_drawings,
    has_panel_marker,
    panelize_and_save,
)


def add_segment(board, x1: float, y1: float, x2: float, y2: float) -> None:
    shape = pcbnew.PCB_SHAPE(board)
    shape.SetShape(pcbnew.S_SEGMENT)
    shape.SetLayer(pcbnew.Edge_Cuts)
    shape.SetWidth(pcbnew.FromMM(0.05))
    shape.SetStart(pcbnew.VECTOR2I_MM(x1, y1))
    shape.SetEnd(pcbnew.VECTOR2I_MM(x2, y2))
    board.Add(shape)


def make_rectangular_board(width: float = 20.0, height: float = 10.0):
    board = pcbnew.BOARD()
    add_segment(board, 0, 0, width, 0)
    add_segment(board, width, 0, width, height)
    add_segment(board, width, height, 0, height)
    add_segment(board, 0, height, 0, 0)

    source_text = pcbnew.PCB_TEXT(board)
    source_text.SetText("SOURCE_BOARD_CONTENT")
    source_text.SetLayer(pcbnew.F_SilkS)
    source_text.SetPosition(pcbnew.VECTOR2I_MM(5, 5))
    board.Add(source_text)
    return board


class PanelizerIntegrationTests(unittest.TestCase):
    def test_apply_panelization_adds_outline_copies_rails_and_fiducials(self) -> None:
        board = make_rectangular_board()
        config = PanelConfig(columns=3, rows=2, y_gap_mm=2.0)
        layout, added_edges, added_marks = apply_panelization(board, config)

        self.assertEqual(layout.board_count, 6)
        self.assertGreater(added_edges, 0)
        self.assertEqual(added_marks, 4)
        self.assertTrue(has_panel_marker(board))
        self.assertEqual(len(list(board.GetFootprints())), 5)

        source_texts = [
            item.GetText()
            for item in board.GetDrawings()
            if isinstance(item, pcbnew.PCB_TEXT)
        ]
        self.assertEqual(source_texts.count("SOURCE_BOARD_CONTENT"), 1)

        footprints = list(board.GetFootprints())
        mark_footprints = [
            fp for fp in footprints if fp.GetReference().startswith("MK_")
        ]
        self.assertEqual(len(mark_footprints), 4)
        mark_positions = {(mark.GetPosition().x, mark.GetPosition().y) for mark in mark_footprints}
        self.assertEqual(len(mark_positions), 4)
        top_pad = next(
            fp for fp in mark_footprints if fp.GetReference().startswith("MK_F_")
        ).Pads()[0]
        bottom_pad = next(
            fp for fp in mark_footprints if fp.GetReference().startswith("MK_B_")
        ).Pads()[0]
        self.assertAlmostEqual(pcbnew.ToMM(top_pad.GetSize().x), 1.0)
        self.assertAlmostEqual(pcbnew.ToMM(top_pad.GetLocalSolderMaskMargin()), 1.0)
        self.assertTrue(top_pad.GetLayerSet().Contains(pcbnew.F_Cu))
        self.assertTrue(top_pad.GetLayerSet().Contains(pcbnew.F_Mask))
        self.assertTrue(bottom_pad.GetLayerSet().Contains(pcbnew.B_Cu))
        self.assertTrue(bottom_pad.GetLayerSet().Contains(pcbnew.B_Mask))

        with self.assertRaises(PanelizerError) as context:
            apply_panelization(board, config)
        self.assertEqual(context.exception.code, "already_panelized")

    def test_panelize_and_save_creates_backup_and_reloads(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "demo.kicad_pcb"
            board = make_rectangular_board()
            self.assertTrue(pcbnew.SaveBoard(str(path), board))
            loaded = pcbnew.LoadBoard(str(path))
            original_edge_count = len(edge_drawings(loaded))
            original_size = board_outline_bbox(loaded)

            result = panelize_and_save(
                loaded,
                PanelConfig(columns=2, rows=2, rail_left=True, rail_right=True),
            )

            self.assertTrue(result.backup_path.exists())
            self.assertIn(".backup-", result.backup_path.name)
            self.assertTrue(path.exists())

            reloaded = pcbnew.LoadBoard(str(path))
            self.assertTrue(has_panel_marker(reloaded))
            self.assertGreater(len(edge_drawings(reloaded)), original_edge_count)
            self.assertGreater(board_outline_bbox(reloaded).width, original_size.width)
            self.assertEqual(len(list(reloaded.GetFootprints())), 5)


if __name__ == "__main__":
    unittest.main()


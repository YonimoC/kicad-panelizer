"""Pure geometry and configuration model for PCB panelization."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


class ConfigError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class BBox:
    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.bottom - self.top


@dataclass(frozen=True)
class PanelConfig:
    columns: int = 5
    rows: int = 4
    x_gap_mm: float = 0.0
    y_gap_mm: float = 2.0
    rail_width_mm: float = 6.0
    rail_left: bool = True
    rail_right: bool = True
    rail_top: bool = False
    rail_bottom: bool = False
    marks_enabled: bool = True
    mark_copper_mm: float = 1.0
    mark_mask_mm: float = 3.0
    mark_top_offset_mm: float = 10.0
    mark_bottom_offset_mm: float = 15.0

    def validate(self) -> None:
        if not 1 <= self.columns <= 100:
            raise ConfigError("invalid_columns")
        if not 1 <= self.rows <= 100:
            raise ConfigError("invalid_rows")
        if not (0.0 <= self.x_gap_mm <= 100.0 and 0.0 <= self.y_gap_mm <= 100.0):
            raise ConfigError("invalid_gap")
        if not 1.0 <= self.rail_width_mm <= 30.0:
            raise ConfigError("invalid_rail_width")
        if not any((self.rail_left, self.rail_right, self.rail_top, self.rail_bottom)):
            raise ConfigError("invalid_rail_sides")
        if self.marks_enabled:
            if not 0.2 <= self.mark_copper_mm <= 5.0:
                raise ConfigError("invalid_mark_copper")
            if self.mark_mask_mm < self.mark_copper_mm + 0.1:
                raise ConfigError("invalid_mark_mask")
            if not (
                0.0 <= self.mark_top_offset_mm <= 1000.0
                and 0.0 <= self.mark_bottom_offset_mm <= 1000.0
            ):
                raise ConfigError("invalid_mark_offsets")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, values: dict[str, object] | None) -> "PanelConfig":
        if not values:
            return cls()
        known = {field: values[field] for field in cls.__dataclass_fields__ if field in values}
        try:
            return cls(**known)
        except (TypeError, ValueError):
            return cls()


@dataclass(frozen=True)
class PanelLayout:
    board: BBox
    array: BBox
    panel: BBox
    pitch_x: float
    pitch_y: float
    config: PanelConfig

    @property
    def board_count(self) -> int:
        return self.config.columns * self.config.rows

    @property
    def panel_width(self) -> float:
        return self.panel.width

    @property
    def panel_height(self) -> float:
        return self.panel.height

    def cell_origin(self, column: int, row: int) -> tuple[float, float]:
        return (
            self.board.left + column * self.pitch_x,
            self.board.top + row * self.pitch_y,
        )


def rail_rectangles(layout: PanelLayout) -> list[BBox]:
    """Return one complete rectangle for each enabled process rail.

    Each rail spans the full panel in its length direction. Rectangles overlap
    at the corners by design; no attempt is made to split or merge coincident
    Edge.Cuts segments.
    """

    config = layout.config
    panel = layout.panel
    width = config.rail_width_mm
    rails: list[BBox] = []
    if config.rail_left:
        rails.append(BBox(panel.left, panel.top, panel.left + width, panel.bottom))
    if config.rail_right:
        rails.append(BBox(panel.right - width, panel.top, panel.right, panel.bottom))
    if config.rail_top:
        rails.append(BBox(panel.left, panel.top, panel.right, panel.top + width))
    if config.rail_bottom:
        rails.append(BBox(panel.left, panel.bottom - width, panel.right, panel.bottom))
    return rails


@dataclass(frozen=True)
class MarkSpec:
    side: Literal["left", "right", "top", "bottom"]
    layer: Literal["F", "B"]
    x: float
    y: float


def make_layout(board: BBox, config: PanelConfig) -> PanelLayout:
    config.validate()
    if board.width <= 0 or board.height <= 0:
        raise ConfigError("no_outline")

    right = board.right + (config.columns - 1) * (board.width + config.x_gap_mm)
    bottom = board.top + config.rows * board.height
    bottom += (config.rows - 1) * config.y_gap_mm
    array = BBox(board.left, board.top, right, bottom)

    panel_left = board.left - config.rail_width_mm if config.rail_left else board.left
    panel_top = board.top - config.rail_width_mm if config.rail_top else board.top
    panel_right = array.right + config.rail_width_mm if config.rail_right else array.right
    panel_bottom = (
        array.bottom + config.rail_width_mm if config.rail_bottom else array.bottom
    )
    panel = BBox(panel_left, panel_top, panel_right, panel_bottom)

    if config.marks_enabled:
        if config.mark_top_offset_mm >= panel.height:
            raise ConfigError("invalid_mark_fit")
        if config.mark_bottom_offset_mm >= panel.height:
            raise ConfigError("invalid_mark_fit")
        if config.mark_top_offset_mm >= panel.width:
            raise ConfigError("invalid_mark_fit")
        if config.mark_bottom_offset_mm >= panel.width:
            raise ConfigError("invalid_mark_fit")

    return PanelLayout(
        board=board,
        array=array,
        panel=panel,
        pitch_x=board.width + config.x_gap_mm,
        pitch_y=board.height + config.y_gap_mm,
        config=config,
    )


def mark_positions(layout: PanelLayout) -> list[MarkSpec]:
    config = layout.config
    if not config.marks_enabled:
        return []

    marks: list[MarkSpec] = []
    rail_half = config.rail_width_mm / 2.0
    top_y = layout.panel.top + config.mark_top_offset_mm
    bottom_y = layout.panel.bottom - config.mark_bottom_offset_mm
    left_x = layout.panel.left + config.mark_top_offset_mm
    right_x = layout.panel.right - config.mark_bottom_offset_mm

    if config.rail_left:
        x = layout.panel.left + rail_half
        marks.extend(
            (
                MarkSpec("left", "F", x, top_y),
                MarkSpec("left", "B", x, bottom_y),
            )
        )
    if config.rail_right:
        x = layout.panel.right - rail_half
        marks.extend(
            (
                MarkSpec("right", "F", x, bottom_y),
                MarkSpec("right", "B", x, top_y),
            )
        )
    if config.rail_top:
        y = layout.panel.top + rail_half
        marks.extend(
            (
                MarkSpec("top", "F", left_x, y),
                MarkSpec("top", "B", right_x, y),
            )
        )
    if config.rail_bottom:
        y = layout.panel.bottom - rail_half
        marks.extend(
            (
                MarkSpec("bottom", "F", right_x, y),
                MarkSpec("bottom", "B", left_x, y),
            )
        )
    return marks


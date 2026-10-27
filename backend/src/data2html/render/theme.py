"""Viewer theme from `config/theme.yaml` (palette, font, currency)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

import yaml
from pydantic import BaseModel, ConfigDict, Field

Color = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]


class Palette(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    light: tuple[Color, ...] = Field(min_length=1, max_length=12)
    dark: tuple[Color, ...] = Field(min_length=1, max_length=12)


class Theme(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    # Only safe characters: the font goes into a CSS custom property of the viewer page
    font: Annotated[str, Field(pattern=r"^[A-Za-z0-9 ,'\-]{1,200}$")] = "'Plus Jakarta Sans', sans-serif"
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")] = "MXN"
    # OPB brand palette (ADR 0013), validated against the white card surface; the viewer is light only
    palette: Palette = Palette(
        light=("#2D69AE", "#B8871F", "#7C4DBD", "#E05080", "#3E9BD6"),
        dark=("#2D69AE", "#B8871F", "#7C4DBD", "#E05080", "#3E9BD6"),
    )


@lru_cache
def load_theme(path: Path | None) -> Theme:
    if path is None or not path.exists():
        return Theme()
    return Theme.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})

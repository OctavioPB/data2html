"""`config/ai.yaml`: what the AI may see of each source (ADR 0014).

- `none`: the source, its models and reports do not exist for the AI.
- `metadata`: names, types and descriptions; no rows, no values.
- `results`: aggregated results (queries, report visuals) and profiles.

The default is `metadata`: no source sends data to the AI until someone opts it in. A missing file
means `metadata` everywhere. No model names or keys here (those go in the AI provider's settings).
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class Exposure(StrEnum):
    none = "none"
    metadata = "metadata"
    results = "results"


class AiConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    default_exposure: Exposure = Exposure.metadata
    exposure_by_source: dict[str, Exposure] = Field(default_factory=dict, alias="exposure",
                                                    description="Source id → exposure")
    max_rows: int = Field(default=500, ge=1, le=1000, description="Rows per agent query")

    def exposure(self, source_id: str) -> Exposure:
        return self.exposure_by_source.get(source_id, self.default_exposure)


def load_ai_config(path: Path | None) -> AiConfig:
    if path is None or not path.exists():
        return AiConfig()
    return AiConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})

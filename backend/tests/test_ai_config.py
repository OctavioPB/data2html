from pathlib import Path

import pytest
from pydantic import ValidationError

from data2html.ai.config import AiConfig, Exposure, load_ai_config

EXAMPLE = Path(__file__).resolve().parents[2] / "config/ai.example.yaml"


def test_example_loads():
    cfg = load_ai_config(EXAMPLE)
    assert cfg.exposure("csv") is Exposure.results
    assert cfg.exposure("teradata_prod") is Exposure.metadata  # commented out → default


def test_missing_file_is_metadata_only(tmp_path):
    assert load_ai_config(tmp_path / "nope.yaml").exposure("csv") is Exposure.metadata
    assert load_ai_config(None).exposure("anything") is Exposure.metadata


@pytest.mark.parametrize("data", [{"exposure": {"csv": "sample"}}, {"providers": {}}, {"max_rows": 5000}])
def test_unknown_or_invalid_settings_are_errors(data):
    with pytest.raises(ValidationError):
        AiConfig.model_validate(data)

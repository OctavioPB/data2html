from pathlib import Path

import pytest
import yaml

from data2html.spec import SemanticModel

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


@pytest.fixture
def model() -> SemanticModel:
    return SemanticModel.model_validate(yaml.safe_load((EXAMPLES / "semantic/ventas.yaml").read_text()))


@pytest.fixture
def report_data() -> dict:
    return yaml.safe_load((EXAMPLES / "reports/ventas_regionales.yaml").read_text())

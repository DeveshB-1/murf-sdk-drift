from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture
def fix() -> Path:
    return FIX


@pytest.fixture
def fake_sdk() -> Path:
    return FIX / "fakesdk" / "murf"

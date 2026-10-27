import os
import pytest
from backend.app.config import settings


@pytest.fixture(autouse=True)
def enforce_test_backend_default(monkeypatch):
    """Guarantees tests run deterministically against the fake backend unless overridden."""
    if not os.environ.get("PALIMPSEST_LIVE_TEST"):
        monkeypatch.setattr(settings, "PALIMPSEST_BACKEND", "fake")


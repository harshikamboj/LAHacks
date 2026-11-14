"""Keep offline test settings independent of the developer's exported credentials."""

import os

import pytest

from app.config import Settings


@pytest.fixture(autouse=True)
def isolate_offline_settings_environment(request, monkeypatch):
    # Live Atlas tests intentionally use the real environment and repository .env.
    if request.node.get_closest_marker("atlas"):
        return

    # _env_file=None disables dotenv loading, but BaseSettings still reads os.environ.
    # Cover upper/lowercase names because Settings is case-insensitive by default.
    settings_names = {name.casefold() for name in Settings.model_fields}
    for name in tuple(os.environ):
        if name.casefold() in settings_names:
            monkeypatch.delenv(name)

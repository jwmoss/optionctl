"""Initial testing module."""

import optionctl


def test_version() -> None:
    version = getattr(optionctl, "__version__", None)
    assert version is not None
    assert isinstance(version, str)

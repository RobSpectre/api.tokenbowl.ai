"""Test module version and basic imports."""

import token_bowl_chat_server


def test_version() -> None:
    """Test that version is defined."""
    assert hasattr(token_bowl_chat_server, "__version__")
    assert isinstance(token_bowl_chat_server.__version__, str)
    assert len(token_bowl_chat_server.__version__) > 0


def test_module_import() -> None:
    """Test that the module can be imported."""
    assert token_bowl_chat_server is not None

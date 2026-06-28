import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from scraper import (
    get_message_date_str,
    get_messages_output_path,
    get_image_output_path,
)


def test_get_message_date_str_format():
    """Date string should be in YYYY-MM-DD format."""
    try:
        date_str = get_message_date_str()
        parts = date_str.split("-")
        assert len(parts) == 3, "Date should have 3 parts separated by dashes"
        assert len(parts[0]) == 4, "Year should be 4 digits"
        assert len(parts[1]) == 2, "Month should be 2 digits"
        assert len(parts[2]) == 2, "Day should be 2 digits"
    except Exception as e:
        pytest.fail(f"get_message_date_str raised an error: {e}")


def test_get_messages_output_path_creates_directory(tmp_path):
    """Output directory should be created and path should end with .json."""
    try:
        with patch("scraper.MESSAGES_DIR", tmp_path):
            path = get_messages_output_path("test_channel", "2024-01-01")
            assert path.suffix == ".json"
            assert path.parent.exists()
    except Exception as e:
        pytest.fail(f"get_messages_output_path raised an error: {e}")


def test_get_image_output_path_creates_directory(tmp_path):
    """Image output path should be inside channel subdirectory."""
    try:
        with patch("scraper.IMAGES_DIR", tmp_path):
            path = get_image_output_path("test_channel", 12345)
            assert path.name == "12345.jpg"
            assert "test_channel" in str(path)
    except Exception as e:
        pytest.fail(f"get_image_output_path raised an error: {e}")
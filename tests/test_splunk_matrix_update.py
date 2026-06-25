import configparser
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from splunk_matrix_update import (
    get_all_major_minor_versions,
    get_new_versions,
    get_supported_date,
    add_new_version_stanza,
)


def make_config(content: str) -> configparser.ConfigParser:
    config = configparser.ConfigParser()
    config.optionxform = str
    config.read_string(content)
    return config


def test_get_all_major_minor_versions_extracts_unique_prefixes():
    images = [
        {"name": "10.4.0"},
        {"name": "10.4.1"},
        {"name": "10.5.0"},
        {"name": "latest"},
        {"name": "abc123def456"},
        {"name": "9.3.11"},
        {"name": "10.4.0-rc1"},
    ]
    result = get_all_major_minor_versions(images)
    assert sorted(result) == ["10.4", "10.5", "9.3"]


def test_get_all_major_minor_versions_empty():
    assert get_all_major_minor_versions([]) == []


def test_get_new_versions_returns_versions_not_in_config():
    config = make_config(
        "[GENERAL]\nLATEST = 10.2\nOLDEST = 9.3\n"
        "[10.2]\nVERSION = 10.2.2\n"
        "[9.3]\nVERSION = 9.3.11\n"
    )
    images = [{"name": "10.2.2"}, {"name": "10.4.0"}, {"name": "9.3.11"}]
    result = get_new_versions(config, images)
    assert result == ["10.4"]


def test_get_new_versions_returns_empty_when_all_present():
    config = make_config("[10.2]\nVERSION = 10.2.2\n")
    images = [{"name": "10.2.0"}, {"name": "10.2.2"}]
    assert get_new_versions(config, images) == []


def _mock_response(text: str, status_code: int = 200) -> MagicMock:
    mock = MagicMock()
    mock.status_code = status_code
    mock.text = text
    mock.raise_for_status = MagicMock()
    if status_code >= 400:
        mock.raise_for_status.side_effect = Exception("HTTP error")
    return mock


def test_get_supported_date_parses_month_day_year():
    html = "...Splunk Enterprise 10.4.x ... January 15, 2028 ..."
    with patch("splunk_matrix_update.requests.get", return_value=_mock_response(html)):
        assert get_supported_date("10.4") == "2028-01-15"


def test_get_supported_date_returns_unknown_on_network_error():
    with patch("splunk_matrix_update.requests.get", side_effect=Exception("timeout")):
        assert get_supported_date("10.4") == "UNKNOWN"


def test_get_supported_date_returns_unknown_when_version_not_found():
    html = "<html>No relevant content here</html>"
    with patch("splunk_matrix_update.requests.get", return_value=_mock_response(html)):
        assert get_supported_date("10.4") == "UNKNOWN"


def test_get_supported_date_returns_unknown_on_http_error():
    with patch("splunk_matrix_update.requests.get", return_value=_mock_response("", 500)):
        assert get_supported_date("10.4") == "UNKNOWN"


SAMPLE_IMAGES = [
    {"name": "10.4.1", "images": [{"digest": "sha256-abc"}]},
    {"name": "10.4.0", "images": [{"digest": "sha256-xyz"}]},
    {"name": "abc123def456", "images": [{"digest": "sha256-abc"}]},
]


def test_add_new_version_stanza_adds_stanza_with_correct_fields():
    config = make_config("[GENERAL]\nLATEST = 10.2\nOLDEST = 9.3\n")
    with patch("splunk_matrix_update.get_supported_date", return_value="2028-06-15"):
        result = add_new_version_stanza(config, "10.4", SAMPLE_IMAGES)
    assert result is True
    assert config.has_section("10.4")
    assert config.get("10.4", "VERSION") == "10.4.1"
    assert config.get("10.4", "SUPPORTED") == "2028-06-15"
    assert config.get("10.4", "PYTHON39") == "true"
    assert config.get("10.4", "PYTHON37") == "false"


def test_add_new_version_stanza_uses_unknown_when_scrape_fails():
    config = make_config("[GENERAL]\nLATEST = 10.2\nOLDEST = 9.3\n")
    with patch("splunk_matrix_update.get_supported_date", return_value="UNKNOWN"):
        result = add_new_version_stanza(config, "10.4", SAMPLE_IMAGES)
    assert result is True
    assert config.get("10.4", "SUPPORTED") == "UNKNOWN"


def test_add_new_version_stanza_skips_already_expired():
    config = make_config("[GENERAL]\nLATEST = 10.2\nOLDEST = 9.3\n")
    with patch("splunk_matrix_update.get_supported_date", return_value="2020-01-01"):
        result = add_new_version_stanza(config, "10.4", SAMPLE_IMAGES)
    assert result is False
    assert not config.has_section("10.4")


def test_add_new_version_stanza_skips_when_no_docker_image():
    config = make_config("[GENERAL]\nLATEST = 10.2\nOLDEST = 9.3\n")
    with patch("splunk_matrix_update.get_supported_date", return_value="2028-06-15"):
        result = add_new_version_stanza(config, "99.9", SAMPLE_IMAGES)
    assert result is False
    assert not config.has_section("99.9")

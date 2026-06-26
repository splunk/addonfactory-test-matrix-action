import configparser
import datetime
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from splunk_matrix_update import (
    get_all_major_minor_versions,
    get_new_versions,
    get_supported_date,
    add_new_version_stanza,
    remove_expired_versions,
    update_general_section,
    update_splunk_version,
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


def test_get_supported_date_parses_table_structure():
    # Real page format: <td>X.Y</td><td>RELEASE</td><td>EOL</td>
    html = "<td>10.4</td><td>May 18 2026</td><td>May 18 2028</td>"
    with patch("splunk_matrix_update.requests.get", return_value=_mock_response(html)):
        assert get_supported_date("10.4") == "2028-05-18"


def test_get_supported_date_returns_unknown_for_not_released():
    html = "<td>10.3</td><td>Mar 24 2026</td><td>Not Released</td>"
    with patch("splunk_matrix_update.requests.get", return_value=_mock_response(html)):
        assert get_supported_date("10.3") == "UNKNOWN"


def test_get_supported_date_returns_unknown_on_network_error():
    with patch("splunk_matrix_update.requests.get", side_effect=Exception("timeout")):
        assert get_supported_date("10.4") == "UNKNOWN"


def test_get_supported_date_returns_unknown_when_version_not_found():
    html = "<html>No relevant content here</html>"
    with patch("splunk_matrix_update.requests.get", return_value=_mock_response(html)):
        assert get_supported_date("10.4") == "UNKNOWN"


def test_get_supported_date_returns_unknown_on_http_error():
    with patch(
        "splunk_matrix_update.requests.get", return_value=_mock_response("", 500)
    ):
        assert get_supported_date("10.4") == "UNKNOWN"


def test_get_supported_date_does_not_match_adjacent_version():
    # "10.4" must not steal the date from "10.40" — (?!\d) boundary prevents this
    html = (
        "<td>10.40</td><td>Jan 1 2025</td><td>Jan 1 2029</td>"
        "<td>10.4</td><td>May 18 2026</td><td>May 18 2028</td>"
    )
    with patch("splunk_matrix_update.requests.get", return_value=_mock_response(html)):
        assert get_supported_date("10.4") == "2028-05-18"


def test_get_supported_date_returns_unknown_when_version_absent_from_table():
    # Version not present in the table at all
    html = "<td>10.5</td><td>Jun 1 2027</td><td>Jun 1 2029</td>"
    with patch("splunk_matrix_update.requests.get", return_value=_mock_response(html)):
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
    assert config.get("10.4", "BUILD") == "abc123def456"


def test_add_new_version_stanza_skips_when_scrape_fails():
    # UNKNOWN is rejected because main.py does an unconditional strptime on SUPPORTED.
    config = make_config("[GENERAL]\nLATEST = 10.2\nOLDEST = 9.3\n")
    with patch("splunk_matrix_update.get_supported_date", return_value="UNKNOWN"):
        result = add_new_version_stanza(config, "10.4", SAMPLE_IMAGES)
    assert result is False
    assert not config.has_section("10.4")


def test_add_new_version_stanza_skips_already_expired():
    config = make_config("[GENERAL]\nLATEST = 10.2\nOLDEST = 9.3\n")
    with patch("splunk_matrix_update.get_supported_date", return_value="2020-01-01"):
        result = add_new_version_stanza(config, "10.4", SAMPLE_IMAGES)
    assert result is False
    assert not config.has_section("10.4")


def test_add_new_version_stanza_skips_on_exact_eol_day():
    # On the exact EOL day main.py skips the stanza (today >= eol), so we must not add it.
    today_str = datetime.date.today().isoformat()
    config = make_config("[GENERAL]\nLATEST = 10.2\nOLDEST = 9.3\n")
    with patch("splunk_matrix_update.get_supported_date", return_value=today_str):
        result = add_new_version_stanza(config, "10.4", SAMPLE_IMAGES)
    assert result is False
    assert not config.has_section("10.4")


def test_add_new_version_stanza_skips_when_no_docker_image():
    config = make_config("[GENERAL]\nLATEST = 10.2\nOLDEST = 9.3\n")
    with patch("splunk_matrix_update.get_supported_date", return_value="2028-06-15"):
        result = add_new_version_stanza(config, "99.9", SAMPLE_IMAGES)
    assert result is False
    assert not config.has_section("99.9")


def test_add_new_version_stanza_skips_when_no_build_hash():
    # Image tag exists but no matching 12-char build hash — main.py would KeyError on BUILD.
    images_no_build = [
        {"name": "10.4.1", "images": [{"digest": "sha256-abc"}]},
        # no build-hash entry with digest sha256-abc
    ]
    config = make_config("[GENERAL]\nLATEST = 10.2\nOLDEST = 9.3\n")
    with patch("splunk_matrix_update.get_supported_date", return_value="2028-06-15"):
        result = add_new_version_stanza(config, "10.4", images_no_build)
    assert result is False
    assert not config.has_section("10.4")


def test_remove_expired_versions_removes_past_eol():
    config = make_config(
        "[GENERAL]\nLATEST = 10.2\nOLDEST = 9.3\n"
        "[10.2]\nVERSION = 10.2.2\nSUPPORTED = 2028-01-15\n"
        "[9.3]\nVERSION = 9.3.11\nSUPPORTED = 2020-01-01\n"
    )
    result = remove_expired_versions(config)
    assert result is True
    assert not config.has_section("9.3")
    assert config.has_section("10.2")


def test_remove_expired_versions_keeps_unknown():
    config = make_config("[10.2]\nVERSION = 10.2.2\nSUPPORTED = UNKNOWN\n")
    result = remove_expired_versions(config)
    assert result is False
    assert config.has_section("10.2")


def test_remove_expired_versions_returns_false_when_nothing_removed():
    config = make_config("[10.2]\nVERSION = 10.2.2\nSUPPORTED = 2028-01-15\n")
    result = remove_expired_versions(config)
    assert result is False
    assert config.has_section("10.2")


def test_remove_expired_versions_removes_on_exact_eol_day():
    # Aligns with main.py's `today >= eol` — prune on the EOL date itself.
    today_str = datetime.date.today().isoformat()
    config = make_config(f"[10.2]\nVERSION = 10.2.2\nSUPPORTED = {today_str}\n")
    result = remove_expired_versions(config)
    assert result is True
    assert not config.has_section("10.2")


def test_update_general_section_updates_latest_and_oldest():
    config = make_config(
        "[GENERAL]\nLATEST = 9.3\nOLDEST = 9.3\n"
        "[10.2]\nVERSION = 10.2.2\n"
        "[9.4]\nVERSION = 9.4.10\n"
        "[9.3]\nVERSION = 9.3.11\n"
    )
    result = update_general_section(config)
    assert result is True
    assert config.get("GENERAL", "LATEST") == "10.2"
    assert config.get("GENERAL", "OLDEST") == "9.3"


def test_update_general_section_returns_false_when_unchanged():
    config = make_config(
        "[GENERAL]\nLATEST = 10.2\nOLDEST = 9.3\n"
        "[10.2]\nVERSION = 10.2.2\n"
        "[9.3]\nVERSION = 9.3.11\n"
    )
    result = update_general_section(config)
    assert result is False


def test_update_splunk_version_adds_new_minor_and_updates_general(
    tmp_path, monkeypatch
):
    # Arrange: config with only 9.3, Docker Hub has 9.3.x and 10.4.x
    # Use a far-future SUPPORTED date so the pruner never removes 9.3 as time advances.
    future_date = (datetime.date.today() + datetime.timedelta(days=3650)).isoformat()
    conf_path = tmp_path / "splunk_matrix.conf"
    conf_path.write_text(
        "[GENERAL]\nLATEST = 9.3\nOLDEST = 9.3\n"
        f"[9.3]\nVERSION = 9.3.10\nBUILD = aabbccddee00\nSUPPORTED = {future_date}\n"
        "PYTHON39 = true\nPYTHON37 = false\n"
    )
    monkeypatch.chdir(tmp_path)
    # Create the config/ subdirectory structure update_splunk_version expects
    (tmp_path / "config").mkdir()
    conf_path.rename(tmp_path / "config" / "splunk_matrix.conf")

    docker_images = [
        {"name": "9.3.11", "images": [{"digest": "sha256-9311"}]},
        {"name": "9.3.10", "images": [{"digest": "sha256-9310"}]},
        {"name": "10.4.0", "images": [{"digest": "sha256-1040"}]},
        {"name": "aabbccddee11", "images": [{"digest": "sha256-9311"}]},
        {"name": "bb1040bb1040", "images": [{"digest": "sha256-1040"}]},
    ]

    with patch(
        "splunk_matrix_update.get_images_details", return_value=docker_images
    ), patch("splunk_matrix_update.get_supported_date", return_value="2028-06-15"):
        result = update_splunk_version()

    assert result == "True"
    config = make_config((tmp_path / "config" / "splunk_matrix.conf").read_text())
    # Patch version bumped
    assert config.get("9.3", "VERSION") == "9.3.11"
    assert config.get("9.3", "BUILD") == "aabbccddee11"
    # New stanza added
    assert config.has_section("10.4")
    assert config.get("10.4", "VERSION") == "10.4.0"
    assert config.get("10.4", "BUILD") == "bb1040bb1040"
    assert config.get("10.4", "SUPPORTED") == "2028-06-15"
    # GENERAL updated
    assert config.get("GENERAL", "LATEST") == "10.4"
    assert config.get("GENERAL", "OLDEST") == "9.3"


def test_update_splunk_version_exits_on_unknown_eol_for_new_version(
    tmp_path, monkeypatch
):
    # When a new Docker Hub version can't get an EOL date the workflow must go red.
    future_date = (datetime.date.today() + datetime.timedelta(days=3650)).isoformat()
    conf_path = tmp_path / "splunk_matrix.conf"
    conf_path.write_text(
        "[GENERAL]\nLATEST = 9.3\nOLDEST = 9.3\n"
        f"[9.3]\nVERSION = 9.3.10\nBUILD = aabbccddee00\nSUPPORTED = {future_date}\n"
        "PYTHON39 = true\nPYTHON37 = false\n"
    )
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config").mkdir()
    conf_path.rename(tmp_path / "config" / "splunk_matrix.conf")

    docker_images = [
        {"name": "9.3.11", "images": [{"digest": "sha256-9311"}]},
        {"name": "10.4.0", "images": [{"digest": "sha256-1040"}]},
    ]

    with patch(
        "splunk_matrix_update.get_images_details", return_value=docker_images
    ), patch(
        "splunk_matrix_update.get_supported_date", return_value="UNKNOWN"
    ), patch(
        "splunk_matrix_update.sys.exit"
    ) as mock_exit:
        update_splunk_version()

    mock_exit.assert_called_once_with(1)

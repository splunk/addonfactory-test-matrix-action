import configparser
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from splunk_matrix_update import get_all_major_minor_versions, get_new_versions


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

import argparse
import configparser
import textwrap
from unittest.mock import patch

import pytest

from addonfactory_test_matrix_action.main import (
    _ALLOWED_SERVER_CONF_PYTHON_VERSIONS,
    _generate_supported_splunk,
    _generate_supported_splunk_modinput,
    _load_splunk_config,
    _iter_splunk_sections,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MATRIX_TEMPLATE = textwrap.dedent("""\
    [GENERAL]
    LATEST = 10.2
    OLDEST = 9.3

    [10.2]
    VERSION = 10.2.2
    BUILD = aaaaaaaaaaaa
    SUPPORTED = 2028-01-15
    PYTHON39 = true

    [9.4]
    VERSION = 9.4.10
    BUILD = bbbbbbbbbbbb
    SUPPORTED = 2026-12-16
    PYTHON39 = true
    SERVER_CONF_PYTHON_VERSIONS = python3,force_python3

    [9.3]
    VERSION = 9.3.11
    BUILD = cccccccccccc
    SUPPORTED = 2026-07-24
    PYTHON39 = true
""")

# 9.3 is EOL relative to today (2026-07-24 < 2026-06-30 is false, but let's use
# a matrix where one section is genuinely EOL for that test)
_MATRIX_WITH_EOL = textwrap.dedent("""\
    [GENERAL]
    LATEST = 10.2
    OLDEST = 9.0

    [10.2]
    VERSION = 10.2.2
    BUILD = aaaaaaaaaaaa
    SUPPORTED = 2028-01-15
    PYTHON39 = true

    [9.4]
    VERSION = 9.4.10
    BUILD = bbbbbbbbbbbb
    SUPPORTED = 2026-12-16
    PYTHON39 = true
    SERVER_CONF_PYTHON_VERSIONS = python3,force_python3

    [9.0]
    VERSION = 9.0.0
    BUILD = dddddddddddd
    SUPPORTED = 2024-01-01
    PYTHON39 = false
""")

_MATRIX_INVALID_VERSION = textwrap.dedent("""\
    [GENERAL]
    LATEST = 9.4
    OLDEST = 9.4

    [9.4]
    VERSION = 9.4.10
    BUILD = bbbbbbbbbbbb
    SUPPORTED = 2028-01-15
    SERVER_CONF_PYTHON_VERSIONS = invalid_value
""")


def _args(features=None):
    ns = argparse.Namespace()
    ns.features = features
    return ns


def _config_from_str(text):
    cfg = configparser.ConfigParser()
    cfg.read_string(text)
    return cfg


def _mock_load(text):
    """Return a patcher that replaces _load_splunk_config with one reading *text*."""
    cfg = _config_from_str(text)
    return patch(
        "addonfactory_test_matrix_action.main._load_splunk_config",
        return_value=cfg,
    )


# ---------------------------------------------------------------------------
# _generate_supported_splunk
# ---------------------------------------------------------------------------


class TestGenerateSupportedSplunk:
    def test_returns_active_versions_only(self):
        with _mock_load(_MATRIX_WITH_EOL):
            result = _generate_supported_splunk(_args(), path="unused")
        versions = [e["version"] for e in result]
        assert "10.2.2" in versions
        assert "9.4.10" in versions
        assert "9.0.0" not in versions

    def test_no_server_conf_python_version_field(self):
        with _mock_load(_MATRIX_TEMPLATE):
            result = _generate_supported_splunk(_args(), path="unused")
        for entry in result:
            assert "serverConfPythonVersion" not in entry

    def test_islatest_isoldest_flags(self):
        with _mock_load(_MATRIX_TEMPLATE):
            result = _generate_supported_splunk(_args(), path="unused")
        latest = [e for e in result if e["islatest"]]
        oldest = [e for e in result if e["isoldest"]]
        assert len(latest) == 1 and latest[0]["version"] == "10.2.2"
        # 9.3 is the OLDEST in MATRIX_TEMPLATE (and still active as of today)
        assert len(oldest) == 1 and oldest[0]["version"] == "9.3.11"


# ---------------------------------------------------------------------------
# _generate_supported_splunk_modinput
# ---------------------------------------------------------------------------


class TestGenerateSupportedSplunkModinput:
    def test_94_expands_to_two_variants(self):
        with _mock_load(_MATRIX_TEMPLATE):
            result = _generate_supported_splunk_modinput(_args(), path="unused")
        v94 = [e for e in result if e["version"] == "9.4.10"]
        assert len(v94) == 2
        python_versions = {e["serverConfPythonVersion"] for e in v94}
        assert python_versions == {"python3", "force_python3"}

    def test_versions_without_setting_appear_once_without_field(self):
        with _mock_load(_MATRIX_TEMPLATE):
            result = _generate_supported_splunk_modinput(_args(), path="unused")
        v102 = [e for e in result if e["version"] == "10.2.2"]
        assert len(v102) == 1
        assert "serverConfPythonVersion" not in v102[0]

    def test_total_entry_count(self):
        # 10.2 → 1, 9.4 → 2, 9.3 → 1 = 4 (9.3 still active in MATRIX_TEMPLATE)
        with _mock_load(_MATRIX_TEMPLATE):
            result = _generate_supported_splunk_modinput(_args(), path="unused")
        assert len(result) == 4

    def test_eol_version_excluded(self):
        with _mock_load(_MATRIX_WITH_EOL):
            result = _generate_supported_splunk_modinput(_args(), path="unused")
        versions = [e["version"] for e in result]
        assert "9.0.0" not in versions

    def test_invalid_python_version_raises(self):
        with _mock_load(_MATRIX_INVALID_VERSION):
            with pytest.raises(ValueError, match="Invalid server_conf_python_versions"):
                _generate_supported_splunk_modinput(_args(), path="unused")

    def test_allowlist_contents(self):
        assert _ALLOWED_SERVER_CONF_PYTHON_VERSIONS == {"python3", "force_python3"}

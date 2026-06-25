# Automatic Splunk Version Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `splunk_matrix_update.py` to auto-discover new Splunk major.minor versions from Docker Hub, fetch their end-of-support dates from Splunk's lifecycle page, prune expired versions, and keep the GENERAL section in sync — all within the existing weekly PR workflow.

**Architecture:** Six new functions are added to `splunk_matrix_update.py`. The existing `update_splunk_version()` orchestrator is updated to call them in sequence: discover→patch→prune→sync. No other files change except `requirements.txt` (add `pytest` for tests).

**Tech Stack:** Python 3.12, `requests`, `packaging`, `configparser`, `re`, `datetime` (all stdlib or already in `requirements.txt`), `pytest` + `unittest.mock` for tests.

## Global Constraints

- All changes confined to `splunk_matrix_update.py` and `requirements.txt`.
- `configparser.ConfigParser()` must always be constructed with `optionxform = str` to preserve uppercase key names (`VERSION`, `BUILD`, etc.).
- New stanzas always default to `PYTHON39 = true` and `PYTHON37 = false`.
- `SUPPORTED = UNKNOWN` stanzas are never auto-pruned.
- The lifecycle page URL is `https://www.splunk.com/en_us/legal/splunk-software-support-policy.html`.
- `get_supported_date` must return `"UNKNOWN"` on **any** failure (network, parse, version not listed).
- `add_new_version_stanza` must not add a stanza whose resolved SUPPORTED date is already in the past.

---

### Task 1: Discovery functions + test scaffold

**Files:**
- Modify: `splunk_matrix_update.py` (add `import datetime`, two new functions)
- Create: `tests/test_splunk_matrix_update.py`
- Modify: `requirements.txt` (add `pytest`)

**Interfaces:**
- Produces:
  - `get_all_major_minor_versions(images: List[Dict]) -> List[str]`
  - `get_new_versions(config: ConfigParser, images: List[Dict]) -> List[str]`
  - test helper `make_config(content: str) -> ConfigParser`

---

- [ ] **Step 1: Add `pytest` to requirements.txt**

Open `requirements.txt` and append `pytest` so it reads:

```
requests
packaging
urllib3>=1.26.0,<2.0.0
pytest
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_splunk_matrix_update.py`:

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd /Users/mkolasin/workspace/addonfactory-test-matrix-action
pip install -r requirements.txt
pytest tests/test_splunk_matrix_update.py -v
```

Expected: `ImportError` or `AttributeError` — functions not yet defined.

- [ ] **Step 4: Add `import datetime` to `splunk_matrix_update.py`**

Add to the imports block at the top of `splunk_matrix_update.py` (after the existing imports):

```python
import datetime
```

- [ ] **Step 5: Implement `get_all_major_minor_versions` and `get_new_versions`**

Add after the `get_image_digest` function (before `update_splunk_version`):

```python
def get_all_major_minor_versions(images: List[Dict]) -> List[str]:
    """
    Returns unique major.minor version prefixes found in Docker Hub image tags.
    Only considers tags matching X.Y.Z (excludes build hashes, 'latest', pre-release).
    """
    seen = set()
    for image in images:
        if re.match(r'^\d+\.\d+\.\d+$', image["name"]):
            parts = image["name"].split(".")
            seen.add(f"{parts[0]}.{parts[1]}")
    return list(seen)


def get_new_versions(
    config: configparser.ConfigParser, images: List[Dict]
) -> List[str]:
    """
    Returns major.minor versions present on Docker Hub that have no stanza in config.
    """
    existing = set(config.sections()) - {"GENERAL"}
    return [v for v in get_all_major_minor_versions(images) if v not in existing]
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/test_splunk_matrix_update.py::test_get_all_major_minor_versions_extracts_unique_prefixes \
       tests/test_splunk_matrix_update.py::test_get_all_major_minor_versions_empty \
       tests/test_splunk_matrix_update.py::test_get_new_versions_returns_versions_not_in_config \
       tests/test_splunk_matrix_update.py::test_get_new_versions_returns_empty_when_all_present \
       -v
```

Expected: 4 passed.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt splunk_matrix_update.py tests/test_splunk_matrix_update.py
git commit -m "feat: add Splunk version discovery functions"
```

---

### Task 2: Lifecycle page scraper (`get_supported_date`)

**Files:**
- Modify: `splunk_matrix_update.py` (add one new function)
- Modify: `tests/test_splunk_matrix_update.py` (add tests)

**Interfaces:**
- Consumes: `requests` (already imported), `re`, `datetime`
- Produces: `get_supported_date(major_minor: str) -> str`
  - Returns `"YYYY-MM-DD"` string on success, `"UNKNOWN"` on any failure.

---

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_splunk_matrix_update.py`:

```python
from unittest.mock import patch, MagicMock

from splunk_matrix_update import get_supported_date


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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_splunk_matrix_update.py::test_get_supported_date_parses_month_day_year \
       tests/test_splunk_matrix_update.py::test_get_supported_date_returns_unknown_on_network_error \
       tests/test_splunk_matrix_update.py::test_get_supported_date_returns_unknown_when_version_not_found \
       tests/test_splunk_matrix_update.py::test_get_supported_date_returns_unknown_on_http_error \
       -v
```

Expected: `ImportError` — function not yet defined.

- [ ] **Step 3: Implement `get_supported_date`**

Add after `get_new_versions` in `splunk_matrix_update.py`:

```python
def get_supported_date(major_minor: str) -> str:
    """
    Scrapes Splunk's software support policy page for the end-of-support date
    of the given major.minor version (e.g. "10.4").

    Returns a "YYYY-MM-DD" string on success, or "UNKNOWN" on any failure
    (network error, HTTP error, version not yet listed, parse failure).

    NOTE: The regex pattern targets the page at:
    https://www.splunk.com/en_us/legal/splunk-software-support-policy.html
    Verify the regex against the live page if this function consistently
    returns "UNKNOWN" for known versions.
    """
    url = "https://www.splunk.com/en_us/legal/splunk-software-support-policy.html"
    month_names = (
        "January|February|March|April|May|June|"
        "July|August|September|October|November|December"
    )
    date_re = rf"(?:{month_names})\s+\d{{1,2}},\s*\d{{4}}"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        escaped = re.escape(major_minor)
        # Find the version string followed within 300 characters by a month-day-year date
        pattern = rf"{escaped}[^<]{{0,300}}?({date_re})"
        match = re.search(pattern, response.text, re.IGNORECASE | re.DOTALL)
        if match:
            return datetime.datetime.strptime(
                match.group(1).strip(), "%B %d, %Y"
            ).strftime("%Y-%m-%d")
        return "UNKNOWN"
    except Exception:
        return "UNKNOWN"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_splunk_matrix_update.py::test_get_supported_date_parses_month_day_year \
       tests/test_splunk_matrix_update.py::test_get_supported_date_returns_unknown_on_network_error \
       tests/test_splunk_matrix_update.py::test_get_supported_date_returns_unknown_when_version_not_found \
       tests/test_splunk_matrix_update.py::test_get_supported_date_returns_unknown_on_http_error \
       -v
```

Expected: 4 passed.

- [ ] **Step 5: Manually verify the regex against the live page**

Run this one-off check to confirm the regex matches actual page content:

```bash
python - <<'EOF'
import requests, re
url = "https://www.splunk.com/en_us/legal/splunk-software-support-policy.html"
resp = requests.get(url, timeout=15)
month_names = "January|February|March|April|May|June|July|August|September|October|November|December"
date_re = rf"(?:{month_names})\s+\d{{1,2}},\s*\d{{4}}"
for version in ["9.3", "9.4", "10.0", "10.2"]:
    escaped = re.escape(version)
    m = re.search(rf"{escaped}[^<]{{0,300}}?({date_re})", resp.text, re.IGNORECASE | re.DOTALL)
    print(f"{version}: {m.group(1) if m else 'NOT FOUND'}")
EOF
```

Expected: each known version prints a date. If any prints `NOT FOUND`, inspect `resp.text` around that version and update the regex in `get_supported_date` accordingly before proceeding. Known expected dates (from the current config): 9.3 → 2026-07-24, 9.4 → 2026-12-16, 10.0 → 2027-07-28, 10.2 → 2028-01-15.

- [ ] **Step 6: Commit**

```bash
git add splunk_matrix_update.py tests/test_splunk_matrix_update.py
git commit -m "feat: add lifecycle page scraper for SUPPORTED dates"
```

---

### Task 3: New stanza addition (`add_new_version_stanza`)

**Files:**
- Modify: `splunk_matrix_update.py` (add one new function)
- Modify: `tests/test_splunk_matrix_update.py` (add tests)

**Interfaces:**
- Consumes:
  - `get_supported_date(major_minor: str) -> str` (Task 2)
  - `get_latest_image(stanza: str, images: List[Dict]) -> Optional[str]` (existing)
  - `get_image_digest(image: str, image_list: List[Dict]) -> Optional[str]` (existing)
  - `get_build_number(digest: str, image_list: List[Dict]) -> Optional[str]` (existing)
- Produces: `add_new_version_stanza(config: ConfigParser, major_minor: str, images: List[Dict]) -> bool`
  - Returns `True` if the stanza was added, `False` if skipped.

---

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_splunk_matrix_update.py`:

```python
from splunk_matrix_update import add_new_version_stanza


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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_splunk_matrix_update.py::test_add_new_version_stanza_adds_stanza_with_correct_fields \
       tests/test_splunk_matrix_update.py::test_add_new_version_stanza_uses_unknown_when_scrape_fails \
       tests/test_splunk_matrix_update.py::test_add_new_version_stanza_skips_already_expired \
       tests/test_splunk_matrix_update.py::test_add_new_version_stanza_skips_when_no_docker_image \
       -v
```

Expected: `ImportError` — function not yet defined.

- [ ] **Step 3: Implement `add_new_version_stanza`**

Add after `get_supported_date` in `splunk_matrix_update.py`:

```python
def add_new_version_stanza(
    config: configparser.ConfigParser,
    major_minor: str,
    images: List[Dict],
) -> bool:
    """
    Adds a new [major.minor] stanza to config for a previously unseen Splunk version.

    Returns True if the stanza was added, False if skipped (version not found on
    Docker Hub, or its end-of-support date is already in the past).
    """
    supported = get_supported_date(major_minor)

    if supported != "UNKNOWN":
        try:
            eol_date = datetime.date.fromisoformat(supported)
            if eol_date < datetime.date.today():
                return False
        except ValueError:
            pass

    latest_version = get_latest_image(major_minor, images)
    if not latest_version:
        return False

    image_digest = get_image_digest(latest_version, images)
    build = get_build_number(image_digest, images) if image_digest else None

    config.add_section(major_minor)
    config.set(major_minor, "VERSION", latest_version)
    if build:
        config.set(major_minor, "BUILD", build)
    config.set(major_minor, "SUPPORTED", supported)
    config.set(major_minor, "PYTHON39", "true")
    config.set(major_minor, "PYTHON37", "false")
    return True
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_splunk_matrix_update.py::test_add_new_version_stanza_adds_stanza_with_correct_fields \
       tests/test_splunk_matrix_update.py::test_add_new_version_stanza_uses_unknown_when_scrape_fails \
       tests/test_splunk_matrix_update.py::test_add_new_version_stanza_skips_already_expired \
       tests/test_splunk_matrix_update.py::test_add_new_version_stanza_skips_when_no_docker_image \
       -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add splunk_matrix_update.py tests/test_splunk_matrix_update.py
git commit -m "feat: add new Splunk version stanza creation"
```

---

### Task 4: Expiry pruning and GENERAL sync

**Files:**
- Modify: `splunk_matrix_update.py` (add two new functions)
- Modify: `tests/test_splunk_matrix_update.py` (add tests)

**Interfaces:**
- Produces:
  - `remove_expired_versions(config: ConfigParser) -> bool`
    - Returns `True` if at least one stanza was removed.
  - `update_general_section(config: ConfigParser) -> bool`
    - Returns `True` if LATEST or OLDEST changed.

---

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_splunk_matrix_update.py`:

```python
from splunk_matrix_update import remove_expired_versions, update_general_section


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
    config = make_config(
        "[10.2]\nVERSION = 10.2.2\nSUPPORTED = UNKNOWN\n"
    )
    result = remove_expired_versions(config)
    assert result is False
    assert config.has_section("10.2")


def test_remove_expired_versions_returns_false_when_nothing_removed():
    config = make_config(
        "[10.2]\nVERSION = 10.2.2\nSUPPORTED = 2028-01-15\n"
    )
    result = remove_expired_versions(config)
    assert result is False
    assert config.has_section("10.2")


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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_splunk_matrix_update.py::test_remove_expired_versions_removes_past_eol \
       tests/test_splunk_matrix_update.py::test_remove_expired_versions_keeps_unknown \
       tests/test_splunk_matrix_update.py::test_remove_expired_versions_returns_false_when_nothing_removed \
       tests/test_splunk_matrix_update.py::test_update_general_section_updates_latest_and_oldest \
       tests/test_splunk_matrix_update.py::test_update_general_section_returns_false_when_unchanged \
       -v
```

Expected: `ImportError` — functions not yet defined.

- [ ] **Step 3: Implement `remove_expired_versions` and `update_general_section`**

Add after `add_new_version_stanza` in `splunk_matrix_update.py`:

```python
def remove_expired_versions(config: configparser.ConfigParser) -> bool:
    """
    Removes stanzas whose SUPPORTED date is in the past.
    Stanzas with SUPPORTED = UNKNOWN are never removed.
    Returns True if at least one stanza was removed.
    """
    today = datetime.date.today()
    to_remove = []
    for section in config.sections():
        if section == "GENERAL":
            continue
        supported_str = config.get(section, "SUPPORTED", fallback="UNKNOWN")
        if supported_str == "UNKNOWN":
            continue
        try:
            if datetime.date.fromisoformat(supported_str) < today:
                to_remove.append(section)
        except ValueError:
            continue
    for section in to_remove:
        config.remove_section(section)
    return len(to_remove) > 0


def update_general_section(config: configparser.ConfigParser) -> bool:
    """
    Syncs GENERAL.LATEST and GENERAL.OLDEST to the max and min of all
    non-GENERAL stanza names (using semver ordering).
    Returns True if either value changed.
    """
    non_general = [s for s in config.sections() if s != "GENERAL"]
    if not non_general:
        return False
    sorted_versions = sorted(non_general, key=lambda v: version.parse(v))
    new_oldest = sorted_versions[0]
    new_latest = sorted_versions[-1]
    current_oldest = config.get("GENERAL", "OLDEST", fallback=None)
    current_latest = config.get("GENERAL", "LATEST", fallback=None)
    changed = False
    if new_oldest != current_oldest:
        config.set("GENERAL", "OLDEST", new_oldest)
        changed = True
    if new_latest != current_latest:
        config.set("GENERAL", "LATEST", new_latest)
        changed = True
    return changed
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_splunk_matrix_update.py::test_remove_expired_versions_removes_past_eol \
       tests/test_splunk_matrix_update.py::test_remove_expired_versions_keeps_unknown \
       tests/test_splunk_matrix_update.py::test_remove_expired_versions_returns_false_when_nothing_removed \
       tests/test_splunk_matrix_update.py::test_update_general_section_updates_latest_and_oldest \
       tests/test_splunk_matrix_update.py::test_update_general_section_returns_false_when_unchanged \
       -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add splunk_matrix_update.py tests/test_splunk_matrix_update.py
git commit -m "feat: add version expiry pruning and GENERAL section sync"
```

---

### Task 5: Orchestration wiring

**Files:**
- Modify: `splunk_matrix_update.py` (replace body of `update_splunk_version`)
- Modify: `tests/test_splunk_matrix_update.py` (add integration test)

**Interfaces:**
- Consumes all functions from Tasks 1–4.
- Produces: `update_splunk_version() -> str` — returns `"True"` if config changed, `"False"` otherwise. Signature unchanged; only the body changes.

---

- [ ] **Step 1: Write the failing integration test**

Add to `tests/test_splunk_matrix_update.py`:

```python
from splunk_matrix_update import update_splunk_version


def test_update_splunk_version_adds_new_minor_and_updates_general(tmp_path, monkeypatch):
    # Arrange: config with only 9.3, Docker Hub has 9.3.x and 10.4.x
    conf_path = tmp_path / "splunk_matrix.conf"
    conf_path.write_text(
        "[GENERAL]\nLATEST = 9.3\nOLDEST = 9.3\n"
        "[9.3]\nVERSION = 9.3.10\nBUILD = aabbccddee00\nSUPPORTED = 2026-07-24\n"
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
    ]

    with patch("splunk_matrix_update.get_images_details", return_value=docker_images), \
         patch("splunk_matrix_update.get_supported_date", return_value="2028-06-15"):
        result = update_splunk_version()

    assert result == "True"
    config = make_config((tmp_path / "config" / "splunk_matrix.conf").read_text())
    # Patch version bumped
    assert config.get("9.3", "VERSION") == "9.3.11"
    # New stanza added
    assert config.has_section("10.4")
    assert config.get("10.4", "VERSION") == "10.4.0"
    assert config.get("10.4", "SUPPORTED") == "2028-06-15"
    # GENERAL updated
    assert config.get("GENERAL", "LATEST") == "10.4"
    assert config.get("GENERAL", "OLDEST") == "9.3"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_splunk_matrix_update.py::test_update_splunk_version_adds_new_minor_and_updates_general -v
```

Expected: FAIL — the current `update_splunk_version` does not call the new functions.

- [ ] **Step 3: Replace the body of `update_splunk_version`**

In `splunk_matrix_update.py`, replace the entire `update_splunk_version` function with:

```python
def update_splunk_version() -> str:
    """
    Updates config/splunk_matrix.conf:
    - Discovers and adds new Splunk major.minor versions from Docker Hub.
    - Updates patch versions for all existing stanzas.
    - Removes stanzas whose end-of-support date has passed.
    - Syncs GENERAL.LATEST and GENERAL.OLDEST.

    Returns "True" if the config was changed, "False" otherwise.
    """
    config_path = "config/splunk_matrix.conf"

    if not os.path.isfile(config_path):
        return "False"

    config = configparser.ConfigParser()
    config.optionxform = str
    config.read(config_path)
    update_file = False
    all_images_list = get_images_details()

    # Discover and add new major.minor versions
    new_versions = get_new_versions(config, all_images_list)
    for major_minor in new_versions:
        if add_new_version_stanza(config, major_minor, all_images_list):
            update_file = True

    # Update patch versions for all stanzas (including newly added ones)
    for stanza in config.sections():
        if stanza != "GENERAL":
            latest_image_version = get_latest_image(stanza, all_images_list)
            if latest_image_version:
                stanza_image_version = config.get(stanza, "VERSION")
                if is_latest_image(latest_image_version, stanza_image_version):
                    latest_image_digest = get_image_digest(
                        latest_image_version, all_images_list
                    )
                    build_number = get_build_number(
                        latest_image_digest, all_images_list
                    )
                    config.set(stanza, "VERSION", latest_image_version)
                    if build_number:
                        config.set(stanza, "BUILD", build_number)
                    update_file = True

    # Remove stanzas whose support window has closed
    if remove_expired_versions(config):
        update_file = True

    # Keep GENERAL.LATEST and GENERAL.OLDEST in sync
    if update_general_section(config):
        update_file = True

    if update_file:
        with open(config_path, "w") as configfile:
            config.write(configfile)
        return "True"

    return "False"
```

- [ ] **Step 4: Run the full test suite**

```bash
pytest tests/test_splunk_matrix_update.py -v
```

Expected: all tests pass (13+ tests, 0 failures).

- [ ] **Step 5: Run the script locally against the real Docker Hub and lifecycle page**

```bash
cd /Users/mkolasin/workspace/addonfactory-test-matrix-action
cp config/splunk_matrix.conf config/splunk_matrix.conf.bak
python splunk_matrix_update.py
echo "Exit: $?"
diff config/splunk_matrix.conf.bak config/splunk_matrix.conf || echo "(no change)"
```

Review the diff. Check that:
- Any previously missing major.minor versions now have stanzas (or that their SUPPORTED dates explain absence).
- GENERAL.LATEST and GENERAL.OLDEST reflect the actual range.
- No unexpected stanzas were added or removed.

Restore backup if the run was just for validation:

```bash
cp config/splunk_matrix.conf.bak config/splunk_matrix.conf
```

- [ ] **Step 6: Commit**

```bash
git add splunk_matrix_update.py tests/test_splunk_matrix_update.py
git commit -m "feat: wire auto-discovery into update_splunk_version orchestrator"
```

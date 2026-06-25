# Design: Automatic Splunk Version Discovery

**Date:** 2026-06-25
**Status:** Approved

## Problem

`splunk_matrix_update.py` only updates patch versions for stanzas that already exist in
`config/splunk_matrix.conf`. When Splunk releases a new major.minor line (e.g. `10.4`),
no stanza exists, so the automation skips it entirely. A human must manually add the stanza
before the weekly PR job picks it up.

## Goal

Extend `splunk_matrix_update.py` so that:
1. New major.minor Splunk versions appearing on Docker Hub are automatically discovered and
   added to the config.
2. The `SUPPORTED` (end-of-support) date is fetched from Splunk's public lifecycle page;
   falls back to `UNKNOWN` on any failure.
3. Stanzas whose `SUPPORTED` date has passed are automatically removed.
4. `GENERAL.LATEST` and `GENERAL.OLDEST` are kept in sync with the remaining stanzas.

No changes are required to the GitHub Actions workflow or any other file.

## Scope

All changes are confined to `splunk_matrix_update.py` and `requirements.txt`
(if `beautifulsoup4` is needed for HTML parsing).

Out of scope: SC4S updates, action.yml, workflow changes, Docker image publishing steps.

## Architecture

All new logic is added as functions to `splunk_matrix_update.py`. The existing
`update_splunk_version()` function becomes the single orchestrator.

### New functions

| Function | Signature | Purpose |
|---|---|---|
| `get_all_major_minor_versions` | `(images: List[Dict]) -> List[str]` | Extract unique `X.Y` prefixes from Docker Hub tags matching `X.Y.Z` |
| `get_new_versions` | `(config, images) -> List[str]` | Return major.minor strings present on Docker Hub but absent from config |
| `get_supported_date` | `(major_minor: str) -> str` | Scrape Splunk lifecycle page; return `YYYY-MM-DD` or `"UNKNOWN"` |
| `add_new_version_stanza` | `(config, major_minor, images) -> None` | Add a complete new `[X.Y]` stanza to config |
| `remove_expired_versions` | `(config) -> bool` | Drop stanzas where `SUPPORTED < today`; skip `UNKNOWN` |
| `update_general_section` | `(config) -> bool` | Sync `LATEST`/`OLDEST` to current min/max of stanza names |

### Orchestration order in `update_splunk_version()`

```
1. Load config
2. Fetch Docker Hub images (single call, reused throughout)
3. Discover new major.minor versions → add stanzas          [NEW]
4. Update patch versions for all stanzas                    [EXISTING, unchanged]
5. Remove expired stanzas                                   [NEW]
6. Sync GENERAL.LATEST and GENERAL.OLDEST                   [NEW]
7. Write config to disk if anything changed
8. Return "True" / "False"
```

## Component Details

### Version discovery (`get_all_major_minor_versions`, `get_new_versions`)

- Parse Docker Hub tag names using the regex `^\d+\.\d+\.\d+$` to isolate proper release
  tags (excludes build hashes, `latest`, pre-release suffixes).
- Extract the `X.Y` prefix from each match and deduplicate.
- A version is "new" if `X.Y` is not already a section in the config.

### Lifecycle page scraping (`get_supported_date`)

- Target URL: `https://www.splunk.com/en_us/legal/splunk-software-support-policy.html`
- Fetch with `requests.get` (existing dependency).
- Parse with regex to find a table row referencing the target major.minor (e.g. `10.4.x`).
- Extract and normalise the EOL date to `YYYY-MM-DD`.
- Return `"UNKNOWN"` on any exception: network error, HTTP error, version not yet listed,
  parse failure.
- The exact regex must be validated against the live page during implementation; this is the
  most fragile component and the `UNKNOWN` fallback is the primary safety net.

### New stanza defaults (`add_new_version_stanza`)

```ini
[10.4]
VERSION = 10.4.1        ; latest patch for this major.minor from Docker Hub
BUILD = <12-char hash>  ; build hash from Docker Hub
SUPPORTED = 2028-06-15  ; from lifecycle page, or UNKNOWN
PYTHON39 = true         ; consistent with all versions >= 9.3
PYTHON37 = false
```

If the SUPPORTED date resolves to a date already in the past, the stanza is not added
(it would be pruned immediately anyway).

### Expiry pruning (`remove_expired_versions`)

- Iterate all non-`GENERAL` stanzas.
- Parse `SUPPORTED` as `YYYY-MM-DD`; skip if value is `UNKNOWN` or unparseable.
- Remove the section if `supported_date < datetime.date.today()`.
- Return `True` if at least one stanza was removed.

### GENERAL sync (`update_general_section`)

- Collect all non-`GENERAL` section names.
- Compute `max` (LATEST) and `min` (OLDEST) using `packaging.version.Version` for correct
  semver ordering.
- Update the config only if the computed values differ from current values.
- Return `True` if either value changed.

## Dependencies

`requests` and `packaging` are already present in `requirements.txt`. If the lifecycle page
requires HTML parsing beyond what regex can handle cleanly, `beautifulsoup4` will be added.
The decision is deferred to implementation; regex is attempted first.

## Error handling

| Failure | Behaviour |
|---|---|
| Docker Hub API down | Existing `raise_for_status()` propagates; no config change |
| Lifecycle page unreachable | `get_supported_date` returns `"UNKNOWN"`; stanza still added |
| Lifecycle page HTML changed | Regex fails silently; returns `"UNKNOWN"` |
| New version already past EOL at discovery | Stanza not added |
| `SUPPORTED = UNKNOWN` stanza | Never pruned automatically; requires human review |

## Testing considerations

The three new pure functions (`get_all_major_minor_versions`, `get_new_versions`,
`remove_expired_versions`, `update_general_section`) are straightforward to unit test with
mock config and image list fixtures. `get_supported_date` requires HTTP mocking.
Existing tests are not modified.

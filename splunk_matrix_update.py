import configparser
import datetime
import json
import os
import re
from packaging import version
import requests
from typing import List, Dict, Optional


def get_images_details() -> List[Dict]:
    """
    Fetches the details of images from the Docker Hub Splunk repository.

    Returns:
        List[Dict]: A list of dictionaries containing details about each image tag.
    """
    get_images_details_endpoint = "https://hub.docker.com/v2/repositories/splunk/splunk/tags?page_size=1000&ordering=last_updated"
    image_details_response = requests.get(get_images_details_endpoint)
    image_details_response.raise_for_status()
    image_details = image_details_response.json()["results"]
    return image_details


def get_latest_image(stanza: str, images: List[Dict]) -> Optional[str]:
    """
    Finds the latest image version that matches the given stanza version.

    Args:
        stanza (str): The version string from the config file.
        images (List[Dict]): A list of dictionaries containing image details.

    Returns:
        Optional[str]: The latest image version that matches the stanza pattern, or None if no match is found.
    """
    stanza_regex = r"\.".join(re.escape(part) for part in stanza.split("."))
    regex_image = rf"{stanza_regex}\.\d+|{stanza_regex}\.\d+\.\d+"
    versions = [image["name"] for image in images]
    filtered_images = re.findall(regex_image, str(versions))

    if filtered_images:
        filtered_images = [image.replace("'", "") for image in filtered_images]
        filtered_images.sort(key=lambda s: list(map(int, s.split("."))))
        return filtered_images[-1]
    return None


def is_latest_image(latest_image: str, stanza_image: str) -> bool:
    """
    Compares two version strings to determine if the latest image version is newer.

    Args:
        latest_image (str): The latest image version.
        stanza_image (str): The current image version from the config file.

    Returns:
        bool: True if the latest image version is newer, False otherwise.
    """
    return version.parse(latest_image) > version.parse(stanza_image)


def get_build_number(latest_image_digest: str, image_list: List[Dict]) -> Optional[str]:
    """
    Retrieves the build number which is SHA corresponding to the latest image digest.

    Args:
        latest_image_digest (str): The digest of the latest image.
        image_list (List[Dict]): A list of dictionaries containing image details.

    Returns:
        Optional[str]: The build number if found, None otherwise.
    """
    return next(
        (
            d["name"]
            for d in image_list
            for image in d.get("images", [])
            if image["digest"] == latest_image_digest
            and re.match(r"[0-9a-z]{12}", d["name"])
        ),
        None,
    )


def get_image_digest(image: str, image_list: List[Dict]) -> Optional[str]:
    """
    Retrieves the digest for a specific image version.

    Args:
        image (str): The name of the image version.
        image_list (List[Dict]): A list of dictionaries containing image details.

    Returns:
        Optional[str]: The digest of the image if found, None otherwise.
    """
    return next(
        (
            image_data["digest"]
            for d in image_list
            if d["name"] == image
            for image_data in d.get("images", [])
        ),
        None,
    )


def get_all_major_minor_versions(images: List[Dict]) -> List[str]:
    """
    Returns unique major.minor version prefixes found in Docker Hub image tags.
    Only considers tags matching X.Y.Z (excludes build hashes, 'latest', pre-release).
    """
    seen = set()
    for image in images:
        if re.match(r"^\d+\.\d+\.\d+$", image["name"]):
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


def get_supported_date(major_minor: str) -> str:
    """
    Scrapes Splunk's software support policy page for the end-of-support date
    of the given major.minor version (e.g. "10.4").

    Returns a "YYYY-MM-DD" string on success, or "UNKNOWN" on any failure
    (network error, HTTP error, version not yet listed, "Not Released", parse failure).

    Page table structure (one row per version):
      <td>X.Y</td><td>RELEASE_DATE</td><td>EOL_DATE</td><td>...</td>
    Dates are formatted as "Mon DD YYYY" (e.g. "May 18 2028").
    EOL_DATE may be "Not Released" for versions not yet GA → returns "UNKNOWN".
    """
    url = "https://www.splunk.com/en_us/legal/splunk-software-support-policy.html"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        escaped = re.escape(major_minor)
        # Match the version cell, skip the release-date cell, capture the EOL-date cell.
        # (?!\d) prevents "10.4" matching "10.40".
        pattern = rf"<td>{escaped}(?!\d)</td>\s*<td>[^<]*</td>\s*<td>([^<]+)</td>"
        match = re.search(pattern, response.text, re.IGNORECASE)
        if not match:
            return "UNKNOWN"
        date_str = match.group(1).strip()
        if date_str == "Not Released":
            return "UNKNOWN"
        return datetime.datetime.strptime(date_str, "%b %d %Y").strftime("%Y-%m-%d")
    except Exception:
        return "UNKNOWN"


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


if __name__ == "__main__":
    update_file = update_splunk_version()
    print(update_file)

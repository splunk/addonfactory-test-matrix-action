import configparser
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
    versions = [image['name'] for image in images]
    filtered_images = re.findall(regex_image, str(versions))

    if filtered_images:
        filtered_images = [image.replace("'", "") for image in filtered_images]
        filtered_images.sort(key=lambda s: list(map(int, s.split("."))))
        return filtered_images[-1]
    return None


def check_image_version(latest_image: str, stanza_image: str) -> bool:
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
            if image["digest"] == latest_image_digest and re.match(r"[0-9a-z]{12}", d["name"])
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
            image_data['digest']
            for d in image_list
            if d['name'] == image
            for image_data in d.get('images', [])
        ),
        None
    )


def update_splunk_version() -> str:
    """
    Updates the Splunk version in the config file if a newer version is available.

    Returns:
        str: "True" if the config file was updated, "False" otherwise.
    """
    config_path = "config/splunk_matrix.conf"

    if os.path.isfile(config_path):
        config = configparser.ConfigParser()
        config.optionxform = str
        config.read(config_path)
        update_file = False
        all_images_list = get_images_details()

        for stanza in config.sections():
            if stanza != "GENERAL":
                latest_image_version = get_latest_image(stanza, all_images_list)

                if latest_image_version:
                    stanza_image_version = config.get(stanza, "VERSION")

                    if check_image_version(latest_image_version, stanza_image_version):
                        latest_image_digest = get_image_digest(latest_image_version, all_images_list)
                        build_number = get_build_number(latest_image_digest, all_images_list)

                        config.set(stanza, "VERSION", latest_image_version)
                        if build_number:
                            config.set(stanza, "BUILD", build_number)
                        update_file = True

        if update_file:
            with open(config_path, "w") as configfile:
                config.write(configfile)
            return "True"

    return "False"


if __name__ == "__main__":
    update_file = update_splunk_version()
    print(update_file)

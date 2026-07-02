#!/usr/bin/env python3
import argparse
import configparser
import json
import os
import pprint
import re
from datetime import datetime
from pathlib import Path


def has_features(features, section):
    if features is not None:
        for feature in features.split(","):
            value = section.getboolean(feature)
            if not value:
                return False
    return True


_ALLOWED_SERVER_CONF_PYTHON_VERSIONS = {"python3", "force_python3"}


def _load_splunk_config(path):
    if os.path.exists("splunk_matrix.conf"):
        splunk_matrix = "splunk_matrix.conf"
    else:
        splunk_matrix = os.path.join(path, "splunk_matrix.conf")
    config = configparser.ConfigParser()
    config.read(splunk_matrix)
    return config


def _iter_splunk_sections(args, config):
    """Yield (section, props, base_entry) for each non-EOL, feature-matching Splunk version."""
    today = datetime.now().date()
    for section in config.sections():
        if not re.search(r"^\d+", section):
            continue
        eol = datetime.strptime(config[section]["SUPPORTED"], "%Y-%m-%d").date()
        if today >= eol:
            continue
        if not has_features(args.features, config[section]):
            continue
        props = {}
        for k in config[section].keys():
            try:
                value = config[section].getboolean(k)
            except ValueError:
                value = config[section][k]
            props[k] = value
        base_entry = {
            "version": props["version"],
            "build": props["build"],
            "islatest": (config["GENERAL"]["LATEST"] == section),
            "isoldest": (config["GENERAL"]["OLDEST"] == section),
        }
        yield section, props, base_entry


def _generate_supported_splunk(args, path):
    config = _load_splunk_config(path)
    return [base_entry for _, _, base_entry in _iter_splunk_sections(args, config)]


def _generate_supported_splunk_modinput(args, path):
    config = _load_splunk_config(path)
    supported_splunk = []
    for _, props, base_entry in _iter_splunk_sections(args, config):
        raw = props.get("server_conf_python_versions")
        if raw:
            for python_version in raw.split(","):
                python_version = python_version.strip()
                if python_version not in _ALLOWED_SERVER_CONF_PYTHON_VERSIONS:
                    raise ValueError(
                        f"Invalid server_conf_python_versions value: {python_version!r}. "
                        f"Allowed: {sorted(_ALLOWED_SERVER_CONF_PYTHON_VERSIONS)}"
                    )
                variant = dict(base_entry)
                variant["serverConfPythonVersion"] = python_version
                supported_splunk.append(variant)
        else:
            supported_splunk.append(base_entry)
    return supported_splunk


def _generate_supported_sc4s(args, path):
    config = configparser.ConfigParser()
    sc4s_matrix = os.path.join(path, "SC4S_matrix.conf")
    config.read(sc4s_matrix)
    supported_sc4s = []
    for section in config.sections():
        if re.search(r"^\d+", section):
            props = {}
            supported_string = config[section].get("SUPPORTED", "ROLLING")
            if supported_string != "ROLLING":
                eol = datetime.strptime(supported_string, "%Y-%m-%d").date()
                today = datetime.now().date()
                if today >= eol:
                    continue

            for k in config[section].keys():
                try:
                    value = config[section].getboolean(k)
                except:
                    value = config[section][k]
                props[k] = value
            if not props.get("docker_registry"):
                props[
                    "docker_registry"
                ] = "ghcr.io/splunk/splunk-connect-for-syslog/container"
            supported_sc4s.append(
                {
                    "version": props["version"],
                    "docker_registry": props["docker_registry"],
                }
            )
    return supported_sc4s


def _generate_supported_vendors(args, path):
    config = configparser.ConfigParser()
    vendors_matrix = os.path.join(path, "/github/workspace/.vendormatrix")
    config.read(vendors_matrix)

    supported_modinput_functional_vendors = []
    supported_ui_vendors = []
    for section in config.sections():
        if re.search(r"^\d+", section):
            props = {}

            for k in config[section].keys():
                try:
                    value = config[section].getboolean(k)
                except:
                    value = config[section][k]
                props[k] = value
            if props.get("trigger_modinput_functional") is not False:
                supported_modinput_functional_vendors.append(
                    {"version": props["version"], "image": props["docker_image"]}
                )
            if props.get("trigger_ui") is not False:
                supported_ui_vendors.append(
                    {"version": props["version"], "image": props["docker_image"]}
                )

    return supported_modinput_functional_vendors, supported_ui_vendors


def main():
    parser = argparse.ArgumentParser(description="Determine support matrix")
    parser.add_argument(
        "--features",
        type=str,
        default=None,
        help="Comma separated list of features",
    )

    args = parser.parse_args()

    path = os.path.join(Path(__file__).parent.parent, "config")

    supported_splunk = _generate_supported_splunk(args, path)
    pprint.pprint(f"Supported Splunk versions: {json.dumps(supported_splunk)}")
    with open(os.environ["GITHUB_OUTPUT"], "a") as fh:
        print(f"supportedSplunk={json.dumps(supported_splunk)}", file=fh)

    supported_splunk_modinput = _generate_supported_splunk_modinput(args, path)
    pprint.pprint(
        f"Supported Splunk versions (modinput): {json.dumps(supported_splunk_modinput)}"
    )
    with open(os.environ["GITHUB_OUTPUT"], "a") as fh:
        print(
            f"supportedSplunkModinput={json.dumps(supported_splunk_modinput)}", file=fh
        )

    for splunk in supported_splunk:
        if splunk["islatest"]:
            pprint.pprint(f"Latest Splunk version: {json.dumps([splunk])}")
            with open(os.environ["GITHUB_OUTPUT"], "a") as fh:
                print(f"latestSplunk={json.dumps([splunk])}", file=fh)
            break

    supported_sc4s = _generate_supported_sc4s(args, path)
    pprint.pprint(f"Supported SC4S versions: {json.dumps(supported_sc4s)}")
    with open(os.environ["GITHUB_OUTPUT"], "a") as fh:
        print(f"supportedSC4S={json.dumps(supported_sc4s)}", file=fh)
    if os.path.exists("/github/workspace/.vendormatrix"):
        (
            supported_modinput_functional_vendors,
            supported_ui_vendors,
        ) = _generate_supported_vendors(args, path)
    else:
        supported_modinput_functional_vendors, supported_ui_vendors = (
            [{"version": "", "image": ""}],
            [{"version": "", "image": ""}],
        )
    pprint.pprint(
        f"Supported ModInput Functional Vendors {supported_modinput_functional_vendors}"
    )
    pprint.pprint(f"Supported UI Vendors {supported_ui_vendors}")
    with open(os.environ["GITHUB_OUTPUT"], "a") as fh:
        print(
            f"supportedModinputFunctionalVendors={json.dumps(supported_modinput_functional_vendors)}",
            file=fh,
        )
    with open(os.environ["GITHUB_OUTPUT"], "a") as fh:
        print(f"supportedUIVendors={json.dumps(supported_ui_vendors)}", file=fh)


if __name__ == "__main__":
    main()

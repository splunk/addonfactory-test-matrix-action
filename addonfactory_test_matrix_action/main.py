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


def _generate_supported_splunk(args, path):
    if os.path.exists("splunk_matrix.conf"):
        splunk_matrix = "splunk_matrix.conf"
    else:
        splunk_matrix = os.path.join(path, "splunk_matrix.conf")
    config = configparser.ConfigParser()
    config.read(splunk_matrix)
    supported_splunk = []
    for section in config.sections():
        if re.search(r"^\d+", section):
            props = {}
            supported_splunk_string = config[section]["SUPPORTED"]
            eol = datetime.strptime(supported_splunk_string, "%Y-%m-%d").date()
            today = datetime.now().date()
            if not (args.unsupportedSplunk or today <= eol):
                continue

            if not has_features(args.splunkfeatures, config[section]):
                continue
            for k in config[section].keys():
                try:
                    value = config[section].getboolean(k)
                except:
                    value = config[section][k]
                props[k] = value

            supported_splunk.append(
                {
                    "version": props["version"],
                    "build": props["build"],
                    "islatest": (config["GENERAL"]["LATEST"] == section),
                    "isoldest": (config["GENERAL"]["OLDEST"] == section),
                }
            )
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
                if not (args.unsupportedSC4S or today <= eol):
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
        "--unsupportedSplunk",
        action="store_true",
        help="Include unsupported Splunk versions",
    )
    parser.add_argument(
        "--unsupportedSC4S",
        action="store_true",
        help="Include unsupported SC4S versions",
    )
    parser.add_argument(
        "--splunkfeatures",
        type=str,
        default="METRICS_MULTI,PYTHON3",
        help="Required Features",
    )

    args = parser.parse_args()

    path = os.path.join(Path(__file__).parent.parent, "config")

    supported_splunk = _generate_supported_splunk(args, path)
    pprint.pprint(f"Supported Splunk versions: {json.dumps(supported_splunk)}")
    with open(os.environ["GITHUB_OUTPUT"], "a") as fh:
        print(f"supportedSplunk={json.dumps(supported_splunk)}", file=fh)

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

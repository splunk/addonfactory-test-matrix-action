#!/usr/bin/env python3
import argparse
import configparser
import json
import os
import pprint
import re
from datetime import datetime
from pathlib import Path


class LoadFromFile(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        with values as f:
            # parse arguments in the file and store them in the target namespace
            parser.parse_args(f.read().split(), namespace)


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
            if props.get("trigger_modinput_functional"):
                supported_modinput_functional_vendors.append(
                    {"version": props["version"],
                     "image": props["docker_image"]}
                )
            if props.get("trigger_ui"):
                supported_ui_vendors.append(
                    {"version": props["version"],
                     "image": props["docker_image"]}
                )

    return supported_modinput_functional_vendors, supported_ui_vendors


def main():
    parser = argparse.ArgumentParser(description="Determine support matrix")

    parser.add_argument("--file", type=open, action=LoadFromFile)
    parser.add_argument(
        "--unsupportedSplunk",
        action="store_true",
        help="include unsupported Splunk versions",
    )
    parser.add_argument(
        "--unsupportedSC4S",
        action="store_true",
        help="include unsupported SC4S versions",
    )
    parser.add_argument(
        "--splunkfeatures", type=str, default=None, help="Required Features"
    )

    args = parser.parse_args()

    path = os.path.join(Path(__file__).parent.parent, "config")

    supported_splunk = _generate_supported_splunk(args, path)
    pprint.pprint(f"Supported Splunk versions: {json.dumps(supported_splunk)}")
    print(f"::set-output name=supportedSplunk::{json.dumps(supported_splunk)}")

    for splunk in supported_splunk:
        if splunk["islatest"]:
            pprint.pprint(f"Latest Splunk version: {json.dumps([splunk])}")
            print(f"::set-output name=latestSplunk::{json.dumps([splunk])}")
            break

    supported_sc4s = _generate_supported_sc4s(args, path)
    pprint.pprint(f"Supported SC4S versions: {json.dumps(supported_sc4s)}")
    print(f"::set-output name=supportedSC4S::{json.dumps(supported_sc4s)}")

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
    print(
        f"::set-output name=supportedModinputFunctionalVendors::{json.dumps(supported_modinput_functional_vendors)}"
    )
    print(
        f"::set-output name=supportedUIVendors::{json.dumps(supported_ui_vendors)}")

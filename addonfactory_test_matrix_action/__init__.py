#!/usr/bin/env python3
import configparser
import argparse
from datetime import datetime
import json
from pathlib import Path
import os
import re
import pprint
import glob


class LoadFromFile(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        with values as f:
            # parse arguments in the file and store them in the target namespace
            parser.parse_args(f.read().split(), namespace)


def hasfeatures(features, section):
    if not features is None:
        for feature in features.split(","):
            value = section.getboolean(feature)
            if not value:
                return False
    return True


def _generateSupportedSplunk(args, path):
    if os.path.exists("splunk_matrix.conf"):
        splunk_matrix = "splunk_matrix.conf"
    else:
        splunk_matrix = os.path.join(path, "splunk_matrix.conf")
    config = configparser.ConfigParser()
    config.read(splunk_matrix)
    supportedSplunk = []
    for section in config.sections():
        if re.search("^\d+", section):
            props = {}
            supportedSplunk_string = config[section]["SUPPORTED"]
            eol = datetime.strptime(supportedSplunk_string, "%Y-%m-%d").date()
            today = datetime.now().date()
            if not (args.unsupportedSplunk or today <= eol):
                continue

            if not hasfeatures(args.splunkfeatures, config[section]):
                continue
            for k in config[section].keys():
                try:
                    value = config[section].getboolean(k)
                except:
                    value = config[section][k]
                props[k] = value

            supportedSplunk.append(
                {
                    "version": props["version"],
                    "build": props["build"],
                    "islatest": (config["GENERAL"]["LATEST"] == section),
                    "isoldest": (config["GENERAL"]["OLDEST"] == section),
                }
            )
    return supportedSplunk


def _generateSupportedSC4S(args, path):
    config = configparser.ConfigParser()
    sc4s_matrix = os.path.join(path, "SC4S_matrix.conf")
    config.read(sc4s_matrix)
    supportedSC4S = []
    for section in config.sections():
        if re.search("^\d+", section):
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
            supportedSC4S.append(
                {
                    "version": props["version"],
                    "docker_registry": props["docker_registry"],
                }
            )
    return supportedSC4S


def _generateSupportedVendors(args, path):
    config = configparser.ConfigParser()
    Vendors_matrix = os.path.join(path, "/github/workspace/.vendormatrix")
    config.read(Vendors_matrix)

    supportedModinputFunctionalVendors = []
    supportedUIVendors = []
    for section in config.sections():
        if re.search("^\d+", section):
            props = {}

            for k in config[section].keys():
                try:
                    value = config[section].getboolean(k)
                except:
                    value = config[section][k]
                props[k] = value
            if props.get("trigger_modinput_functional") != False:
                supportedModinputFunctionalVendors.append(
                    {"version": props["version"], "image": props["docker_image"]}
                )
            if props.get("trigger_ui") != False:
                supportedUIVendors.append(
                    {"version": props["version"], "image": props["docker_image"]}
                )

    return (supportedModinputFunctionalVendors, supportedUIVendors)


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

    supportedSplunk = _generateSupportedSplunk(args, path)
    print(f"::set-output name=supportedSplunk::{json.dumps(supportedSplunk)}")

    for splunk in supportedSplunk:
        if splunk["islatest"] == "true":
            print(f"::set-output name=latestSplunk::{json.dumps([splunk])}")
            break

    supportedSC4S = _generateSupportedSC4S(args, path)
    print(f"::set-output name=supportedSC4S::{json.dumps(supportedSC4S)}")

    if os.path.exists("/github/workspace/.vendormatrix"):
        (
            supportedModinputFunctionalVendors,
            supportedUIVendors,
        ) = _generateSupportedVendors(args, path)
    else:
        supportedModinputFunctionalVendors, supportedUIVendors = (
            [{"version": "", "image": ""}],
            [{"version": "", "image": ""}],
        )
    pprint.pprint(supportedModinputFunctionalVendors)
    pprint.pprint(supportedUIVendors)
    print(
        f"::set-output name=supportedModinputFunctionalVendors::{json.dumps(supportedModinputFunctionalVendors)}"
    )
    print(f"::set-output name=supportedUIVendors::{json.dumps(supportedUIVendors)}")

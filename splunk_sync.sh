#!/bin/bash
# echo all the commands
set -x

REPOORG=splunk

pip install pip --upgrade
pip install poetry
poetry export --without-hashes --dev -o requirements_dev.txt
pip install -r requirements_dev.txt
splunk_version=$(python splunk_matrix_update.py)
echo $splunk_version

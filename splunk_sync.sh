#!/bin/bash
# echo all the commands
set -x

pip install -r requirements.txt
splunk_version=$(python splunk_matrix_update.py)
echo $splunk_version

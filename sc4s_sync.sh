#!/bin/bash
# echo all the commands
set -x

REPOORG=splunk
current_tag=$(cat config/SC4S_matrix.conf | grep -oP 'VERSION\s*=\s*([0-9\.]+)')
echo $current_tag
re='VERSION\s*=\s*([0-9.]+)'
if [[ $current_tag =~ $re ]]
then
    current_tag_value=${BASH_REMATCH[1]}
fi
echo $current_tag_value

latest_tag=$(curl -s https://api.github.com/repos/splunk/splunk-connect-for-syslog/releases/latest | grep "tag_name" | cut -d : -f 2)
new_value=$(echo $latest_tag | rev | cut -c3- | rev)
new_value=$(echo $new_value | cut -c3-)
echo $new_value

pip install pip --upgrade
python -m pip install packaging

var=`python -c "from packaging import version; print('True' if(version.parse(str('$new_value')) > version.parse(str('$current_tag'))) else 'False')"`
echo $var
sed -i "s/$current_tag_value/$new_value/g" config/SC4S_matrix.conf
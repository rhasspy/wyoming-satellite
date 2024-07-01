#!/usr/bin/env bash

# Installs drivers for the ReSpeaker 2mic and 4mic HATs on Raspberry Pi OS.
# Must be run with sudo.
# Requires: curl raspberrypi-kernel-headers dkms i2c-tools libasound2-plugins alsa-utils

set -eo pipefail

kernel_formatted="$(uname -r | cut -f1,2 -d.)"
driver_url_status="$(curl -ILs https://github.com/HinTak/seeed-voicecard/archive/refs/heads/v$kernel_formatted.tar.gz | tac | grep -o "^HTTP.*" | cut -f 2 -d' ' | head -1)"

if  [ ! "$driver_url_status" = 200 ]; then
echo "Could not find driver for kernel $kernel_formatted"
exit 1
fi

apt-get update
apt-get install --no-install-recommends --yes \
    curl raspberrypi-kernel-headers dkms i2c-tools libasound2-plugins alsa-utils

temp_dir="$(mktemp -d)"

function finish {
   rm -rf "${temp_dir}"
}

trap finish EXIT

pushd "${temp_dir}"

# Download source code to temporary directory
# NOTE: There are different branches in the repo for different kernel versions.
echo 'Downloading source code'
curl -L -o - "https://github.com/HinTak/seeed-voicecard/archive/refs/heads/v$kernel_formatted.tar.gz" | \
    tar -xzf -

cd seeed-voicecard-"$kernel_formatted"/

# 1. Build kernel module
echo 'Building kernel module'
ver='0.3'
mod='seeed-voicecard'
src='./'
kernel="$(uname -r)"
marker='0.0.0'
threads="$(getconf _NPROCESSORS_ONLN)"
memory="$(LANG=C free -m|awk '/^Mem:/{print $2}')"

if  [ "${memory}" -le 512 ] && [ "${threads}" -gt 2 ]; then
threads=2
fi

mkdir -p "/usr/src/${mod}-${ver}"
cp -a "${src}"/* "/usr/src/${mod}-${ver}/"

dkms add -m "${mod}" -v "${ver}"
dkms build -k "${kernel}" -m "${mod}" -v "${ver}" -j "${threads}" && {
    dkms install --force -k "${kernel}" -m "${mod}" -v "${ver}"
}

mkdir -p "/var/lib/dkms/${mod}/${ver}/${marker}"

# 2. Install kernel module and configure
echo 'Updating boot configuration'
config='/boot/config.txt'

cp seeed-*-voicecard.dtbo /boot/overlays
grep -q "^snd-soc-ac108$" /etc/modules || echo "snd-soc-ac108" >> /etc/modules
sed -i -e 's:#dtparam=i2c_arm=on:dtparam=i2c_arm=on:g' "${config}"
echo "dtoverlay=i2s-mmap" >> "${config}"
echo "dtparam=i2s=on" >> "${config}"
mkdir -p /etc/voicecard
cp *.conf *.state /etc/voicecard
cp seeed-voicecard /usr/bin/
cp seeed-voicecard.service /lib/systemd/system/
systemctl enable --now seeed-voicecard.service

echo 'Done. Please reboot the system.'
popd

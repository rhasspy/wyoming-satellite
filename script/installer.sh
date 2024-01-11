#!/usr/bin/env bash
set -eu

title='Wyoming Satellite'

# Directory of *this* script
this_dir="$( cd "$( dirname "$0" )" && pwd )"
program_dir="$(realpath "${this_dir}/..")"

# Directory to store stuff that won't interfere with git
local_dir="${program_dir}/local"
mkdir -p "${local_dir}"

debug_enabled=''
system_deps=''

satellite_name=''
satellite_type=''

wake_word_system=''
wake_word=''
custom_wake_word_dir="${local_dir}/custom-wake-words"
mkdir -p "${custom_wake_word_dir}"

noise_suppression=''

microphone_command='arecord -q -r 16000 -c 1 -f S16_LE -t raw'
speaker_command='aplay -q -r 22050 -c 1 -f S16_LE -t raw'
speaker_sounds=()

pushd () {
    command pushd "$@" > /dev/null
}

popd () {
    command popd "$@" > /dev/null
}

# Args
for arg in "$@"; do
    if [ "${arg}" = '--debug' ]; then
        debug_enabled='1'
    fi
done

if [ -n "${debug_enabled}" ]; then
    whiptail --title "${title}" --msgbox \
        'Debug mode is enabled. This will cause all services to log verbosely, and audio to be recorded in local/debug-recording. Make sure to re-run the installer without debug mode before deploying the satellite.' \
        10 75
fi

# -----------------------------------------------------------------------------
# System dependencies
# -----------------------------------------------------------------------------

commands=('whiptail' 'git' 'python3' 'pip3')
for command in "${commands[@]}";
do
    if ! command -v "${command}" &> /dev/null; then
        system_deps='1'
        break
    fi
done

if command -v python3 &> /dev/null; then
    if ! python3 -c 'import venv'; then
        system_deps='1'
    fi
fi

if [ -n "${system_deps}" ]; then
    echo 'Installing system dependencies'
    sudo apt-get update
    sudo apt-get install --yes --no-install-recommends \
        whiptail python3-venv python3-pip git
fi

# -----------------------------------------------------------------------------
# Microphone
# -----------------------------------------------------------------------------

function get_microphone {
    microphones=()
    while read -r microphone; do
        microphones+=("${microphone}" "${microphone}" 0)
    done < <(arecord -L | grep 'plughw:')

    whiptail --title "${title}" --notags \
        --radiolist 'Select Microphone:' 20 70 \
        12 "${microphones[@]}" \
        'custom' 'Custom ALSA Device' 0 \
        'respeaker' 'Install ReSpeaker Drivers' 0
}

function get_custom_microphone {
    whiptail --title "${title}" --inputbox \
        'ALSA Input Device Name:' \
        8 75
}

microphone=''
while [ -z "${microphone}" ]; do
    microphone="$(get_microphone 3>&1 1>&2 2>&3)"
done

if [ "${microphone}" = 'custom' ]; then
    # Custom ALSA device name from "arecord -L"
    microphone=''
    while [ -z "${microphone}" ]; do
        microphone="$(get_custom_microphone 3>&1 1>&2 2>&3)"
    done
elif [ "${microphone}" = 'respeaker' ]; then
    # ReSpeaker driver installation (requires reboot)
    whiptail --title "${title}" --yesno \
        'ReSpeaker drivers for the Raspberry Pi will now be compiled and installed. This will take a while and require a reboot. Continue?' \
        8 75

    echo 'Installing ReSpeaker drivers'
    "${program_dir}/etc/install-respeaker-drivers.sh"

    whiptail --title "${title}" --msgbox \
        'Driver installation complete. The system will now reboot. Re-run the installer and select the "seeed" microphone.' \
        8 75

    sudo reboot
fi

# Add device
microphone_command="${microphone_command} -D ${microphone}"

# -----------------------------------------------------------------------------
# Speaker
# -----------------------------------------------------------------------------

function get_speaker {
    speakers=()
    while read -r speaker; do
        speakers+=("${speaker}" "${speaker}" 0)
    done < <(aplay -L | grep 'plughw:')

    whiptail --title "${title}" --notags \
        --radiolist 'Select Speaker:' 20 70 \
        12 "${speakers[@]}" \
        'custom' 'Custom ALSA Device' 0 \
        'no_speaker' 'No Audio Output' 0
}

function get_custom_speaker {
    whiptail --title "${title}" --inputbox \
        'ALSA Output Device Name:' \
        8 75
}

function get_speaker_sounds {
    whiptail --title "${title}" --checklist \
        'Play Sounds?' \
        10 50 2 \
        'awake' 'On wake-up' 0 \
        'done' 'After voice command' 0
}

speaker=''
while [ -z "${speaker}" ]; do
    speaker="$(get_speaker 3>&1 1>&2 2>&3)"
done

if [ "${speaker}" = 'custom' ]; then
    # Custom ALSA device name from "aplay -L"
    speaker=''
    while [ -z "${speaker}" ]; do
        speaker="$(get_custom_speaker 3>&1 1>&2 2>&3)"
    done
fi

if [ "${speaker}" = 'no_speaker' ]; then
    # No audio output
    speaker_command=''
else
    # Add device
    speaker_command="${speaker_command} -D ${speaker}"

    # awake/done sounds
    speaker_sounds="$(get_speaker_sounds 3>&1 1>&2 2>&3)"
fi

# -----------------------------------------------------------------------------
# wyoming-satellite
# -----------------------------------------------------------------------------

if [ ! -d "${program_dir}/wyoming_satellite" ]; then
    if [ ! -d "${this_dir}/wyoming-satellite" ]; then
        # Download source here
        git clone 'https://github.com/rhasspy/wyoming-satellite.git'
    fi

    program_dir="${this_dir}/wyoming-satellite"
fi

# Virtual environment
venv="${program_dir}/.venv"
pip="${venv}/bin/pip3"
if [ ! -d "${venv}" ]; then
    echo 'Creating virtual environment'
    "${program_dir}/script/setup"
fi

# Satellite name
function get_satellite_name {
    whiptail --title "${title}" --inputbox \
        'Satellite Name:' \
        8 75 \
        'Wyoming Satellite'
}

while [ -z "${satellite_name}" ]; do
    satellite_name="$(get_satellite_name 3>&1 1>&2 2>&3)"
done

# -----------------------------------------------------------------------------
# Satellite type
# -----------------------------------------------------------------------------

function get_satellite_type {
    whiptail --title "${title}" --notags \
        --radiolist 'Select Satellite Type:' 10 50 \
        3 \
        always 'Always streaming' 1 \
        vad 'Voice activity detection' 0 \
        wake 'Local wake word detection' 0
}

function get_wake_word_system {
    # TODO: Support porcupine1 and snowboy
    echo 'openWakeWord'
    # whiptail --title "${title}" --notags \
    #     --radiolist 'Select Wake Word System:' 10 50 \
    #     3 \
    #     openWakeWord 'openWakeWord' 1 \
    #     porcupine1 'porcupine1' 0 \
    #     snowboy 'snowboy' 0
}

function install_openWakeWord {
    if [ ! -d '/usr/share/doc/libopenblas-dev' ]; then
        echo 'Installing system dependencies'
        sudo apt-get install --yes --no-install-recommends \
            libopenblas-dev
    fi

    oww_dir="${local_dir}/wyoming-openwakeword"
    if [ ! -d "${oww_dir}" ]; then
        echo 'Installing openWakeWord'

        # Download
        pushd "${local_dir}"
        git clone 'https://github.com/rhasspy/wyoming-openwakeword.git'
        popd

        # Install
        "${oww_dir}/script/setup"
    fi
}

function list_openWakeWord {
    whiptail --title "${title}" --notags \
        --radiolist 'Select Wake Word:' 15 50 \
        6 \
        ok_nabu 'ok nabu' 1 \
        hey_jarvis 'hey jarvis' 0 \
        alexa 'alexa' 0 \
        hey_rhasspy 'hey rhasspy' 0 \
        hey_mycroft 'hey mycroft' 0 \
        community 'Community Wake Words' 0
}

satellite_type="$(get_satellite_type 3>&1 1>&2 2>&3)"

if [ "${satellite_type}" = 'vad' ]; then
    # Install vad requirements
    "${pip}" install \
        --extra-index-url 'https://www.piwheels.org/simple' \
        -f 'https://synesthesiam.github.io/prebuilt-apps/' \
        -r "${program_dir}/requirements_vad.txt"
elif [ "${satellite_type}" = 'wake' ]; then
    # Install openWakeWord
    wake_word_system="$(get_wake_word_system 3>&1 1>&2 2>&3)"

    if [ "${wake_word_system}" = 'openWakeWord' ]; then
        install_openWakeWord
        mkdir -p "${custom_wake_word_dir}/openWakeWord"

        # Choose wake word
        wake_word="$(list_openWakeWord 3>&1 1>&2 2>&3)"

        if [ "${wake_word}" = 'community' ]; then
            # Download community wake words
            community_wake_word_dir="${local_dir}/home-assistant-wakewords-collection"
            if [ ! -d "${community_wake_word_dir}" ]; then
                echo 'Downloading community wake words'
                pushd "${local_dir}"
                git clone 'https://github.com/fwartner/home-assistant-wakewords-collection.git'
                popd
            fi

            # Select community wake word
            community_wake_words=()

            pushd "${community_wake_word_dir}"
            while read -r wake_word_model; do
                wake_word_name="$(basename "${wake_word_model}" .tflite)"
                community_wake_words+=("${wake_word_model}" "${wake_word_name}" 0)
            done < <(find . -name '*.tflite' -type f | sort)
            popd

            function list_community_wake_words {
                whiptail --title "${title}" --notags \
                    --radiolist 'Select Wake Word:' 25 80 \
                    20 ${community_wake_words[@]}
            }

            wake_word="$(list_community_wake_words 3>&1 1>&2 2>&3)"
            cp "${community_wake_word_dir}/${wake_word}" \
                "${custom_wake_word_dir}/openWakeWord/"

            wake_word="$(basename "${wake_word}" .tflite)"
        fi  # community wake word
    fi  # openWakeWord

fi  # local wake word detection

# -----------------------------------------------------------------------------
# Audio enhancements
# -----------------------------------------------------------------------------

function get_noise_suppression {
    whiptail --title "${title}" --notags --radiolist \
        'Noise Suppression Level:' \
        15 75 6 \
        '' 'Off' 1 \
        '1' 'Low' 0 \
        '2' 'Medium' 0 \
        '3' 'High' 0 \
        '4' 'Max' 0
}

noise_suppression="$(get_noise_suppression 3>&1 1>&2 2>&3)"

if [ -n "${noise_suppression}" ]; then
    # Install audio enhancement requirements
    "${pip}" install \
        --extra-index-url 'https://www.piwheels.org/simple' \
        -f 'https://synesthesiam.github.io/prebuilt-apps/' \
        -r "${program_dir}/requirements_audio_enhancement.txt"
fi

# -----------------------------------------------------------------------------
# Services
# -----------------------------------------------------------------------------

services_dir="${local_dir}/services"
mkdir -p "${services_dir}"

wake_service_requires=''
event_service_requires=''

# Disable any previous services
echo 'Stopping previous services'
for service in 'wyoming-satellite' 'wyoming-openwakeword'; do
    sudo systemctl disable --now "${service}.service" 2>/dev/null || true
done

echo 'Creating systemd unit files'
new_services=('wyoming-satellite.service')

# openWakeWord
if [ "${wake_word_system}" = 'openWakeWord' ]; then
    new_services+=('wyoming-openwakeword.service')
    wake_service_requires='Requires=wyoming-openwakeword.service'

    wake_word_command=("${local_dir}/wyoming-openwakeword/script/run")
    wake_word_command+=('--uri' 'tcp://127.0.0.1:10400')
    wake_word_command+=('--custom-model-dir' "'${custom_wake_word_dir}/openWakeWord'")

    if [ -n "${debug_enabled}" ]; then
        wake_word_command+=('--debug')
    fi

    cat > "${services_dir}/wyoming-openwakeword.service" <<EOF
[Unit]
Description=Wyoming openWakeWord

[Service]
Type=simple
User=$(id --name -u)
Group=$(id --name -g)
ExecStart=${wake_word_command[@]}
WorkingDirectory=${local_dir}/wyoming-openwakeword
Restart=always
RestartSec=1

[Install]
WantedBy=default.target
EOF
fi

# wyoming-satellite
satellite_command=("${program_dir}/script/run")
satellite_command+=('--name' "'${satellite_name}'")
satellite_command+=('--uri' 'tcp://0.0.0.0:10700')
satellite_command+=('--mic-command' "'${microphone_command}'")

if [ -n "${speaker_command}" ]; then
    satellite_command+=('--snd-command' "'${speaker_command}'")

    for sound in ${speaker_sounds[@]}; do
        if [ "${sound}" = '"awake"' ]; then
            awake_wav="${local_dir}/sounds/awake.wav"
            if [ ! -f "${awake_wav}" ]; then
                awake_wav="${program_dir}/sounds/awake.wav"
            fi

            satellite_command+=('--awake-wav' "'${awake_wav}'")
        elif [ "${sound}" = '"done"' ]; then
            done_wav="${local_dir}/sounds/done.wav"
            if [ ! -f "${done_wav}" ]; then
                done_wav="${program_dir}/sounds/done.wav"
            fi

            satellite_command+=('--done-wav' "'${done_wav}'")
        fi
    done
fi

if [ "${satellite_type}" = 'vad' ]; then
    satellite_command+=('--vad')
elif [ "${satellite_type}" = 'wake' ]; then
    satellite_command+=('--wake-uri' 'tcp://127.0.0.1:10400')
    satellite_command+=('--wake-word-name' "'${wake_word}'")
fi

if [ -n "${noise_suppression}" ]; then
    satellite_command+=('--mic-noise-suppression' "${noise_suppression}")
fi

if [ -n "${debug_enabled}" ]; then
    satellite_command+=('--debug')
    satellite_command+=('--debug-recording-dir' "${local_dir}/debug-recording")
fi

cat > "${services_dir}/wyoming-satellite.service" <<EOF
[Unit]
Description=Wyoming Satellite
Wants=network-online.target
After=network-online.target
${wake_service_requires}
${event_service_requires}

[Service]
Type=simple
User=$(id --name -u)
Group=$(id --name -g)
ExecStart=${satellite_command[@]}
WorkingDirectory=${program_dir}
Restart=always
RestartSec=1

[Install]
WantedBy=default.target
EOF

pushd "${services_dir}"
sudo cp ${new_services[@]} /etc/systemd/system/
popd

sudo systemctl daemon-reload
sudo systemctl enable --now ${new_services[@]}

# -----------------------------------------------------------------------------

whiptail --title "${title}" --msgbox \
    'Installation Successful!' \
    8 35

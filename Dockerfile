FROM python:3.11-slim-bookworm

ENV LANG C.UTF-8
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install --yes --no-install-recommends avahi-utils alsa-utils pulseaudio-utils pipewire-bin build-essential

# set workdir
WORKDIR /app

# copy content for voice
COPY sounds/ ./sounds/
COPY script/setup ./script/
COPY script/run ./script/
COPY script/run_2mic ./script/
COPY script/run_4mic ./script/
COPY setup.py requirements.txt requirements_audio_enhancement.txt requirements_vad.txt MANIFEST.in ./
COPY wyoming_satellite/ ./wyoming_satellite/
COPY docker/run ./

# copy content for led
COPY examples/ ./examples/

# run installation
RUN python3 -m venv .venv
RUN .venv/bin/pip3 install --upgrade pip
RUN .venv/bin/pip3 install --upgrade wheel setuptools
RUN .venv/bin/pip3 install --extra-index-url 'https://www.piwheels.org/simple' -f 'https://synesthesiam.github.io/prebuilt-apps/' -r requirements.txt -r requirements_audio_enhancement.txt -r requirements_vad.txt -r examples/requirements.txt
#RUN .venv/bin/pip3 install 'pixel-ring'

# set port for voice and led
EXPOSE 10700 10500

# set start script
# add parameters in docker
ENTRYPOINT ["/app/run"]
#ENTRYPOINT ["/app/script/run_2mic" "--uri" "tcp://0.0.0.0:10500"] for led

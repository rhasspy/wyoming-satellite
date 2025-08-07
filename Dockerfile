FROM python:3.11-slim-bookworm

ENV LANG C.UTF-8
ENV DEBIAN_FRONTEND=noninteractive

# Install packages
RUN apt-get update && \
apt-get install --yes --no-install-recommends \
    avahi-utils \
    alsa-utils \
    pulseaudio-utils \
    pipewire-bin \
    build-essential \
    libasound2-plugins \
    pipewire-alsa \
    ca-certificates

# Set workdir
WORKDIR /app

# Copy all application files
COPY script/ ./script/
COPY pyproject.toml ./
COPY sounds/ ./sounds/
COPY wyoming_satellite/ ./wyoming_satellite/
COPY docker/run ./
COPY examples/ ./examples/

# run installation
RUN ./script/setup
RUN ./script/setup --vad
RUN ./script/setup --noisegain
RUN ./script/setup --respeaker
#RUN .venv/bin/pip3 install 'pixel-ring'

# Set ports for voice and led
EXPOSE 10700 10500

# Set start script
ENTRYPOINT ["/app/run"]

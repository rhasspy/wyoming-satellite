# Tutorial with 2mic HAT

Create a voice satellite using a [Raspberry Pi Zero 2 W](https://www.raspberrypi.com/products/raspberry-pi-zero-2-w/) and a [ReSpeaker 2Mic HAT](https://wiki.keyestudio.com/Ks0314_keyestudio_ReSpeaker_2-Mic_Pi_HAT_V1.0).

This tutorial should work for almost any Raspberry Pi and USB microphone. Audio enhancements and local wake word detection may require a 64-bit operating system, however.

## Install OS

Follow instructions to [install Raspberry Pi OS](https://www.raspberrypi.com/software/). Under "Choose OS", pick "Raspberry Pi OS (other)" and "Raspberry Pi OS (**64-bit**) Lite".

When asking if you'd like to apply customization settings, choose "Edit Settings" and:

* Set a username/password
* Configure the wireless LAN
* Under the Services tab, enable SSH and use password authentication

## Install Software

After flashing and booting the satellite, connect to it over SSH using the username/password you configured during flashing.

**On the satellite**, make sure system dependencies are installed:

```sh
sudo apt-get update
sudo apt-get install --no-install-recommends  \
  git \
  python3-venv
```

Clone the `wyoming-satellite` repository:

```sh
git clone https://github.com/rhasspy/wyoming-satellite.git
```

If you have the ReSpeaker 2Mic or 4Mic HAT, recompile and install the drivers (this will take really long time):

```sh
cd wyoming-satellite/
sudo bash etc/install-respeaker-drivers.sh
```

After install the drivers, you must reboot the satellite:

```sh
sudo reboot
```

Once the satellite has rebooted, reconnect over SSH and continue the installation:

```sh
cd wyoming-satellite/
python3 -m venv .venv
.venv/bin/pip3 install --upgrade pip
.venv/bin/pip3 install --upgrade wheel setuptools
.venv/bin/pip3 install \
  -f 'https://synesthesiam.github.io/prebuilt-apps/' \
  -r requirements.txt \
  -r requirements_audio_enhancement.txt \
  -r requirements_vad.txt
```

If the installation was successful, you should be able to run:

```sh
script/run --help
```

## Determine Audio Devices

Picking the correct microphone/speaker devices is critical for the satellite to work. We'll do a test recording and playback in this section.

List your available microphones with:

```sh
arecord -L
```

If you have the ReSpeaker 2Mic HAT, you should see:

```
plughw:CARD=seeed2micvoicec,DEV=0
    seeed-2mic-voicecard, bcm2835-i2s-wm8960-hifi wm8960-hifi-0
    Hardware device with all software conversions
```

For other microphones, prefer ones that start with `plughw:` or just use `default` if you don't know what to use.

Record a 5 second sample from your chosen microphone:

```sh
arecord -D plughw:CARD=seeed2micvoicec,DEV=0 -r 16000 -c 1 -f S16_LE -t wav -d 5 test.wav
```

Say something while `arecord` is running. If you get errors, try a different microphone device by changing `-D <device>`.

List your available speakers with:

```sh
aplay -L
```

If you have the ReSpeaker 2Mic HAT, you should see:

```
plughw:CARD=seeed2micvoicec,DEV=0
    seeed-2mic-voicecard, bcm2835-i2s-wm8960-hifi wm8960-hifi-0
    Hardware device with all software conversions
```

For other speakers, prefer ones that start with `plughw:` or just use `default` if you don't know what to use.

Play back your recorded sample WAV:

```sh
aplay -D plughw:CARD=seeed2micvoicec,DEV=0 test.wav
```

You should hear your recorded sample. If there are problems, try a different speaker device by changing `-D <device>`.

Make note of your microphone and speaker devices for the next step.

## Running the Satellite

In the `wyoming-satellite` directory, run:

```sh
script/run \
  --debug \
  --name 'my satellite' \
  --uri 'tcp://0.0.0.0:10700' \
  --mic-command 'arecord -D plughw:CARD=seeed2micvoicec,DEV=0 -r 16000 -c 1 -f S16_LE -t raw' \
  --snd-command 'aplay -D plughw:CARD=seeed2micvoicec,DEV=0 -r 22050 -c 1 -f S16_LE -t raw'
```

Change the `-D <device>` for `arecord` and `aplay` to match the audio devices from the previous section.
You can set `--name <NAME>` to whatever you want, but it should stay the same every time you run the satellite.

In Home Assistant, check the "Devices & services" section in Settings. After some time, you should see your satellite show up as "Discovered" (Wyoming Protocol). Click the "Configure" button and "Submit". Choose the area that your satellite is located, and click "Finish".

Your satellite should say "Streaming audio", and you can use the wake word of your preferred pipeline.

## Create Services

You can run wyoming-satellite as a systemd service by first creating a service file:

``` sh
sudo systemctl edit --force --full wyoming-satellite.service
```

Paste in the following template, and change both `/home/pi` and the `script/run` arguments to match your set up:

```text
[Unit]
Description=Wyoming Satellite
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
ExecStart=/home/pi/wyoming-satellite/script/run --name 'my satellite' --uri 'tcp://0.0.0.0:10700' --mic-command 'arecord -D plughw:CARD=seeed2micvoicec,DEV=0 -r 16000 -c 1 -f S16_LE -t raw' --snd-command 'aplay -D plughw:CARD=seeed2micvoicec,DEV=0 -r 22050 -c 1 -f S16_LE -t raw'
WorkingDirectory=/home/pi/wyoming-satellite
Restart=always
RestartSec=1

[Install]
WantedBy=default.target
```

Save the file and exit your editor. Next, enable the service to start at boot and run it:

``` sh
sudo systemctl enable --now wyoming-satellite.service
```

(you may need to hit CTRL+C to get back to a shell prompt)

With the service running, you can view logs in real-time with:

``` sh
journalctl -u wyoming-satellite.service -f
```

If needed, disable and stop the service with:

``` sh
sudo systemctl disable --now wyoming-satellite.service
```

## Audio Enhancements

You can run the satellite with automatic gain control and noise suppression:

``` sh
script/run \
  ... \
  --mic-auto-gain 5 \
  --mic-noise-suppression 2
```

Automatic gain control is between 0-31 dbFS, which 31 being the loudest.
Noise suppression is from 0-4, with 4 being maximum suppression (may cause audio distortion).

You can also use `--mic-volume-multiplier X` to multiply all audio samples by `X`. For example, using 2 for `X` will double the microphone volume (but may cause audio distortion). The corresponding `--snd-volume-multiplier` does the same for audio playback.

## Local Wake Word Detection

Install the necessary system dependencies:

```sh
sudo apt-get update
sudo apt-get install --no-install-recommends  \
  libopenblas-dev
```

From your home directory, install the openWakeWord Wyoming service:

```sh
git clone https://github.com/rhasspy/wyoming-openwakeword.git
cd wyoming-openwakeword
script/setup
```

Create a systemd service for it:

``` sh
sudo systemctl edit --force --full wyoming-openwakeword.service
```

Paste in the following template, and change both `/home/pi` and the `script/run` arguments to match your set up:

```text
[Unit]
Description=Wyoming openWakeWord

[Service]
Type=simple
ExecStart=/home/pi/wyoming-openwakeword/script/run --uri 'tcp://127.0.0.1:10400'
WorkingDirectory=/home/pi/wyoming-openwakeword
Restart=always
RestartSec=1

[Install]
WantedBy=default.target
```

Save the file and exit your editor.

You can now update your satellite service:

``` sh
sudo systemctl edit --force --full wyoming-satellite.service
```

Update just the parts below:

```text
[Unit]
...
Requires=wyoming-openwakeword.service

[Service]
...
ExecStart=/home/pi/wyoming-satellite/script/run ... --wake-uri 'tcp://127.0.0.1:10400' --wake-word-name 'ok_nabu'
...

[Install]
...
```

Reload and restart the satellite service:

``` sh
sudo systemctl daemon-reload
sudo systemctl restart wyoming-satellite.service
```

You should see the wake service get automatically loaded:

``` sh
sudo systemctl status wyoming-satellite.service wyoming-openwakeword.service
```

They should all be "active (running)" and green.

Test out your satellite by saying "ok, nabu" and a voice command. Use `journalctl` to check the logs of services for errors:

``` sh
journalctl -u wyoming-openwakeword.service -f
```

Make sure to run `sudo systemctl daemon-reload` every time you make changes to the service.

## LED Service

Example event services for the ReSpeaker 2Mic and 4Mic HATs are included in `wyoming-satellite/examples` that will change the LED color depending on the satellite state. The example below is for the 2Mic HAT, using `2mic_service.py`.  If you're using the 4Mic HAT, use `4mic_service.py` instead as the LEDs and GPIO pins are slightly different.

Install it from your home directory:

```sh
cd wyoming-satellite/examples
python3 -m venv --system-site-packages .venv
.venv/bin/pip3 install --upgrade pip
.venv/bin/pip3 install --upgrade wheel setuptools
.venv/bin/pip3 install 'wyoming==1.5.2'
```

In case you use a ReSpeaker USB 4mic array v2.0, additionally install pixel-ring:

```sh
.venv/bin/pip3 install 'pixel-ring'
```


The `--system-site-packages` argument is used to access the pre-installed `gpiozero` and `spidev` Python packages. If these are **not already installed** in your system, run:

```sh
sudo apt-get install python3-spidev python3-gpiozero
```

Test the service with:

```sh
.venv/bin/python3 2mic_service.py --help
```

Create a systemd service for it:

``` sh
sudo systemctl edit --force --full 2mic_leds.service
```

Paste in the following template, and change both `/home/pi` and the `script/run` arguments to match your set up:

```text
[Unit]
Description=2Mic LEDs

[Service]
Type=simple
ExecStart=/home/pi/wyoming-satellite/examples/.venv/bin/python3 2mic_service.py --uri 'tcp://127.0.0.1:10500'
WorkingDirectory=/home/pi/wyoming-satellite/examples
Restart=always
RestartSec=1

[Install]
WantedBy=default.target
```

Save the file and exit your editor.

You can now update your satellite service:

``` sh
sudo systemctl edit --force --full wyoming-satellite.service
```

Update just the parts below:

```text
[Unit]
...
Requires=2mic_leds.service

[Service]
...
ExecStart=/home/pi/wyoming-satellite/script/run ... --event-uri 'tcp://127.0.0.1:10500'
...

[Install]
...
```

Reload and restart the satellite service:

``` sh
sudo systemctl daemon-reload
sudo systemctl restart wyoming-satellite.service
```

You should see the service get automatically loaded:

``` sh
sudo systemctl status wyoming-satellite.service 2mic_leds.service
```

They should all be "active (running)" and green.

Try a voice command and see if the LEDs change. Use `journalctl` to check the logs of services for errors:

``` sh
journalctl -u 2mic_leds.service -f
```

If you encounter any issues, you can add the `--debug` argument to the command line to increase the log level.
To control the brightness of the LEDS, use the `--led-brightness ` argument, which accepts integer numbers from 1 to 31.

Make sure to run `sudo systemctl daemon-reload` every time you make changes to the service.

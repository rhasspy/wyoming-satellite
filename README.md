# Wyoming Satellite

Remote voice satellite using the [Wyoming protocol](https://github.com/rhasspy/wyoming).

* Works with [Home Assistant](https://www.home-assistant.io/integrations/wyoming)
* Local wake word detection using [Wyoming services](https://github.com/rhasspy/wyoming#wyoming-projects)
* Audio enhancements using [webrtc](https://github.com/rhasspy/webrtc-noise-gain/)

See [the tutorial](docs/tutorial_2mic.md) to build a satellite using a [Raspberry Pi Zero 2 W](https://www.raspberrypi.com/products/raspberry-pi-zero-2-w/) and a [ReSpeaker 2Mic HAT](https://wiki.keyestudio.com/Ks0314_keyestudio_ReSpeaker_2-Mic_Pi_HAT_V1.0).

Video tutorials:

* [Wyoming Voice Satellite with ChatGPT](https://www.youtube.com/watch?v=eTKgc0YDCwE)
* [Local ChatGPT Voice Assistant](https://www.youtube.com/watch?v=pAKqKTkx5X4)

---

Requires:

* Python 3.7+ (tested on 3.9+)
* A microphone

## Installation

Install the necessary system dependencies:

``` sh
sudo apt-get install python3-venv python3-pip
```

Then run the install script:

``` sh
script/setup
```

The examples below uses `alsa-utils` to record and play audio:

``` sh
sudo apt-get install alsa-utils
```


## Remote Wake Word Detection

Run the satellite with remote wake word detection:

``` sh
cd wyoming-satellite/
script/run \
  --name 'my satellite' \
  --uri 'tcp://0.0.0.0:10700' \
  --mic-command 'arecord -r 16000 -c 1 -f S16_LE -t raw' \
  --snd-command 'aplay -r 22050 -c 1 -f S16_LE -t raw'
```

This will use the default microphone and playback devices.

Use `arecord -D <DEVICE> ...` if you need to use a different microphone (list them with `arecord -L` and prefer `plughw:` devices).
Use `aplay -D <DEVICE> ...` if you need to use a different playback device (list them with `aplay -L` and prefer `plughw:` devices).

Add `--debug` to print additional logs.

In the [Home Assistant](https://www.home-assistant.io/) settings "Devices & services" page, you should see the satellite discovered automatically. If not, click "Add Integration", choose "Wyoming Protocol", and enter the IP address of the satellite (port 10700).

Audio will be continuously streamed to the server, where wake word detection, etc. will occur.

### Voice Activity Detection

Rather than always streaming audio to Home Assistant, the satellite can wait until speech is detected.

**NOTE:** This will not work on the 32-bit version of Raspberry Pi OS.

Install the dependencies for silero VAD:

``` sh
.venv/bin/pip3 install 'pysilero-vad==1.0.0'
```

Run the satellite with VAD enabled:

``` sh
script/run \
  ... \
  --vad
```

Now, audio will only start streaming once speech has been detected.

## Local Wake Word Detection

Install a wake word detection service, such as [wyoming-openwakeword](https://github.com/rhasspy/wyoming-openwakeword/) and start it:

``` sh
cd wyoming-openwakeword/
script/run \
  --uri 'tcp://0.0.0.0:10400' \
  --preload-model 'ok_nabu'
```

Add `--debug` to print additional logs. See `--help` for more information.

Included wake words are:

* `ok_nabu`
* `hey_jarvis`
* `alexa`
* `hey_mycroft`
* `hey_rhasspy`

[Community trained wake words](https://github.com/fwartner/home-assistant-wakewords-collection) are also available and can be included with `--custom-model-dir <DIR>` where `<DIR>` contains `.tflite` file(s).

Next, start the satellite with some additional arguments:

``` sh
cd wyoming-satellite/
script/run \
  --name 'my satellite' \
  --uri 'tcp://0.0.0.0:10700' \
  --mic-command 'arecord -r 16000 -c 1 -f S16_LE -t raw' \
  --snd-command 'aplay -r 22050 -c 1 -f S16_LE -t raw' \
  --wake-uri 'tcp://127.0.0.1:10400' \
  --wake-word-name 'ok_nabu'
```

Audio will only be streamed to the server after the wake word has been detected.

Once a wake word has been detected, it can not be detected again for several seconds (called the "refractory period"). You can change this with `--wake-refractory-seconds <SECONDS>`.

Note that `--vad` is unnecessary when connecting to a local instance of openwakeword.

## Sounds

You can play a WAV file when the wake word is detected (locally or remotely), and when speech-to-text has completed:

* `--awake-wav <WAV>` - played when the wake word is detected
* `--done-wav <WAV>` - played when the voice command is finished
* `--timer-finished-wav <WAV>` - played when a timer is finished

If you want to play audio files other than WAV, use [event commands](#event-commands). Specifically, the `--detection-command` to replace `--awake-wav` and `--transcript-command` to replace `--done-wav`.

The timer finished sound can be repeated with `--timer-finished-wav-repeat <repeats> <delay>` where `<repeats>` is the number of times to repeat the WAV, and `<delay>` is the number of seconds to wait between repeats.

## Audio Enhancements

Install the dependencies for webrtc:

``` sh
.venv/bin/pip3 install 'webrtc-noise-gain==1.2.3'
```

Run the satellite with automatic gain control and noise suppression:

``` sh
script/run \
  ... \
  --mic-auto-gain 5 \
  --mic-noise-suppression 2
```

Automatic gain control is between 0-31 dbFS, which 31 being the loudest.
Noise suppression is from 0-4, with 4 being maximum suppression (may cause audio distortion).

You can also use `--mic-volume-multiplier X` to multiply all audio samples by `X`. For example, using 2 for `X` will double the microphone volume (but may cause audio distortion). The corresponding `--snd-volume-multiplier` does the same for audio playback.

## Event Commands

Satellites can respond to events from the server by running commands:

* `--startup-command` - run when satellite starts (no stdin)
* `--detect-command` - wake word detection has started, but not detected yet (no stdin)
* `--streaming-start-command` - audio has started streaming to server (no stdin)
* `--streaming-stop-command` - audio has stopped streaming to server (no stdin)
* `--detection-command` - wake word is detected (wake word name on stdin)
* `--transcript-command` - speech-to-text transcript is returned (text on stdin)
* `--stt-start-command` - user started speaking (no stdin)
* `--stt-stop-command` - user stopped speaking (no stdin)
* `--synthesize-command` - text-to-speech text is returned (text on stdin)
* `--tts-start-command` - text-to-speech response started streaming from server (no stdin)
* `--tts-stop-command` - text-to-speech response stopped streaming from server. Can still being played by snd service (no stdin)
* `--tts-played-command` - text-to-speech audio finished playing (no stdin)
* `--error-command` - an error was sent from the server (text on stdin)
* `--connected-command` - satellite connected to server
* `--disconnected-command` - satellite disconnected from server
* `--timer-started-command` - new timer has started (json on stdin)
* `--timer-updated-command` - timer has been paused/unpaused or has time added/removed (json on stdin)
* `--timer-cancelled-command` - timer has been cancelled (timer id on stdin)
* `--timer-finished-command` - timer has finished (timer id on stdin)

For more advanced scenarios, use an event service (`--event-uri`). See `wyoming_satellite/example_event_client.py` for a basic client that just logs events.

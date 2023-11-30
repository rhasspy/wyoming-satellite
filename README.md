# Wyoming Satellite

Remote satellite using the [Wyoming protocol](https://github.com/rhasspy/wyoming).

## Installation

``` sh
script/setup
```

You will need a Wyoming microphone and (optionally) a Wyoming sound service:

* [wyoming-mic-external](https://github.com/rhasspy/wyoming-mic-external)
    * Record audio with an external program like `arecord`
* [wyoming-snd-external](https://github.com/rhasspy/wyoming-snd-external)
    * Play audio with an external program like `aplay`


## Example

Start your microphone service and (optionally) your sound service. In this example, we will run the microphone service on port `10600` and the sound service on port `10601`.

Start microphone service:

``` sh
script/run \
  --program 'arecord -r 16000 -c 1 -f S16_LE -t raw' \
  --rate 16000 \
  --width 2 \
  --channels 1 \
  --uri 'tcp://127.0.0.1:10600'
```

Use `arecord -D <DEVICE> ...` if you need to use a different recording device (list them with `arecord -L` and prefer `plughw:` devices). Add `--debug` to print additional logs.

In a separate terminal, start the sound service:

``` sh
script/run \
  --uri 'tcp://127.0.0.1:10601' \
  --program 'aplay -r 22050 -c 1 -f S16_LE -t raw' \
  --rate 22050 \
  --width 2 \
  --channels 1
```

Use `aplay -D <DEVICE> ...` if you need to use a different playback device (list them with `aplay -L` and prefer `plughw:` devices). Add `--debug` to print additional logs.

Lastly, start the satellite in a separate terminal:

``` sh
script/run \
  --name 'test satellite' \
  --uri 'tcp://0.0.0.0:10700' \
  --mic-uri 'tcp://127.0.0.1:10600' \
  --snd-uri 'tcp://127.0.0.1:10601'
```

This will run the satellite on port `10700` and use the local microphone/sound services. Add `--debug` to print additional logs.

Audio will be continuously streamed to the server, where wake word detection, etc. will occur.

### Local Wake Word Detection

Install a wake word detection service, such as [wyoming-openwakeword](https://github.com/rhasspy/wyoming-openwakeword/) and start it:

``` sh
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
script/run \
  --name 'test satellite' \
  --uri 'tcp://0.0.0.0:10700' \
  --mic-uri 'tcp://127.0.0.1:10600' \
  --snd-uri 'tcp://127.0.0.1:10601' \
  --wake-uri 'tcp://127.0.0.1:10400' \
  --wake-word 'ok_nabu'
```

Audio will only be streamed to the server after the wake word has been detected.

### Event Service

Satellites can respond to events from the server using an event service (`--event-uri`). See `wyoming_satellite/example_event_client.py` for a basic client that just logs events.

Available events are:

* `Detect` - start of wake word detection
* `Detection` - wake word is detected
* `VoiceStarted` - user has started speaking
* `VoiceStopped` - user has stopped speaking
* `Transcript` - text spoken by user
* `Synthesize` - text response that will be spoken
* `AudioStart` - response audio started
* `AudioStop` - response audio stopped

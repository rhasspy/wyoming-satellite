# wyoming-satellite - General configuration

## Sounds

You can play a WAV file when the wake word is detected (locally or remotely), and when speech-to-text has completed:

* `--awake-wav <WAV>` - played when the wake word is detected
* `--done-wav <WAV>` - played when the voice command is finished
* `--timer-finished-wav <WAV>` - played when a timer is finished

If you want to play audio files other than WAV, use [event commands](#event-commands). Specifically, the `--detection-command` to replace `--awake-wav` and `--transcript-command` to replace `--done-wav`.

The timer finished sound can be repeated with `--timer-finished-wav-repeat <repeats> <delay>` where `<repeats>` is the number of times to repeat the WAV, and `<delay>` is the number of seconds to wait between repeats.

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

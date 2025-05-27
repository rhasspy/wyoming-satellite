```markdown
# Wyoming Satellite Command-Line Arguments

This document lists the command-line arguments for the Wyoming Satellite, grouped by functionality.

## Microphone Input

Arguments related to microphone configuration and input processing.

- **--mic-uri**
  - URI of Wyoming microphone service
- **--mic-command**
  - Program to run for microphone input
- **--mic-command-rate**
  - Sample rate of mic-command (hertz, default: 16000)
  - (type: int)
  - (default: 16000)
- **--mic-command-width**
  - Sample width of mic-command (bytes, default: 2)
  - (type: int)
  - (default: 2)
- **--mic-command-channels**
  - Sample channels of mic-command (default: 1)
  - (type: int)
  - (default: 1)
- **--mic-command-samples-per-chunk**
  - Sample per chunk for mic-command (default: 1024)
  - (type: int)
  - (default: 1024)
- **--mic-volume-multiplier**
  - (type: float)
  - (default: 1.0)
- **--mic-noise-suppression**
  - (type: int)
  - (default: 0)
  - (choices: 0, 1, 2, 3, 4)
- **--mic-auto-gain**
  - (type: int)
  - (default: 0)
  - (choices: 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31)
- **--mic-seconds-to-mute-after-awake-wav**
  - Seconds to mute microphone after awake wav is finished playing (default: 0.5)
  - (type: float)
  - (default: 0.5)
- **--mic-no-mute-during-awake-wav**
  - Don't mute the microphone while awake wav is being played
  - (action: store_true)
- **--mic-channel-index**
  - Take microphone input from a specific channel (first channel is 0)
  - (type: int)

## Sound Output

Arguments related to sound output configuration.

- **--snd-uri**
  - URI of Wyoming sound service
- **--snd-command**
  - Program to run for sound output
- **--snd-command-rate**
  - Sample rate of snd-command (hertz, default: 22050)
  - (type: int)
  - (default: 22050)
- **--snd-command-width**
  - Sample width of snd-command (bytes, default: 2)
  - (type: int)
  - (default: 2)
- **--snd-command-channels**
  - Sample channels of snd-command (default: 1)
  - (type: int)
  - (default: 1)
- **--snd-volume-multiplier**
  - (type: float)
  - (default: 1.0)

## Local Wake Word Detection

Arguments for configuring local wake word detection.

- **--wake-uri**
  - URI of Wyoming wake word detection service
- **--wake-word-name**
  - Name of wake word to listen for and optional pipeline name to run (requires --wake-uri)
  - (action: append)
  - (default: [])
  - (nargs: +)
  - (metavar: ['name', 'pipeline'])
- **--wake-command**
  - Program to run for wake word detection
- **--wake-command-rate**
  - Sample rate of wake-command (hertz, default: 16000)
  - (type: int)
  - (default: 16000)
- **--wake-command-width**
  - Sample width of wake-command (bytes, default: 2)
  - (type: int)
  - (default: 2)
- **--wake-command-channels**
  - Sample channels of wake-command (default: 1)
  - (type: int)
  - (default: 1)
- **--wake-refractory-seconds**
  - Seconds after a wake word detection before another detection is handled (default: 5)
  - (type: float)
  - (default: 5.0)

## Voice Activity Detector (VAD)

Arguments for configuring voice activity detection.

- **--vad**
  - Wait for speech before streaming audio
  - (action: store_true)
- **--vad-threshold**
  - (type: float)
  - (default: 0.5)
- **--vad-trigger-level**
  - (type: int)
  - (default: 1)
- **--vad-buffer-seconds**
  - (type: float)
  - (default: 2)
- **--vad-wake-word-timeout**
  - Seconds before going back to waiting for speech when wake word isn't detected
  - (type: float)
  - (default: 5.0)

## External Event Handlers

Arguments for specifying commands to run on various events.

- **--event-uri**
  - URI of Wyoming service to forward events to
- **--startup-command**
  - Command run when the satellite starts
- **--detect-command**
  - Command to run when wake word detection starts
- **--detection-command**
  - Command to run when wake word is detected
- **--transcript-command**
  - Command to run when speech to text transcript is returned
- **--stt-start-command**
  - Command to run when the user starts speaking
- **--stt-stop-command**
  - Command to run when the user stops speaking
- **--synthesize-command**
  - Command to run when text to speech text is returned
- **--tts-start-command**
  - Command to run when text to speech response starts
- **--tts-stop-command**
  - Command to run when text to speech response stops
- **--tts-played-command**
  - Command to run when text-to-speech audio stopped playing
- **--streaming-start-command**
  - Command to run when audio streaming starts
- **--streaming-stop-command**
  - Command to run when audio streaming stops
- **--error-command**
  - Command to run when an error occurs
- **--connected-command**
  - Command to run when connected to the server
- **--disconnected-command**
  - Command to run when disconnected from the server
- **--timer-started-command**
  - Command to run when a timer starts
- **--timer-updated-command**
  - Command to run when a timer is paused, resumed, or has time added or removed
- **--timer-cancelled-command, --timer-canceled-command**
  - Command to run when a timer is cancelled
- **--timer-finished-command**
  - Command to run when a timer finishes

## Sounds

Arguments for configuring sounds played by the satellite.

- **--awake-wav**
  - WAV file to play when wake word is detected
- **--done-wav**
  - WAV file to play when voice command is done
- **--timer-finished-wav**
  - WAV file to play when a timer finishes
- **--timer-finished-wav-repeat**
  - Number of times to play timer finished WAV and delay between repeats in seconds
  - (type: float)
  - (default: [1, 0])
  - (nargs: 2)
  - (metavar: ['repeat', 'delay'])

## Satellite Details

Core arguments for defining the satellite's identity and connection.

- **--uri**
  - unix:// or tcp://
  - (required: True)
- **--name**
  - Name of the satellite
  - (default: "Wyoming Satellite")
- **--area**
  - Area name of the satellite

## Zeroconf

Arguments for configuring Zeroconf discovery.

- **--no-zeroconf**
  - Disable discovery over zeroconf
  - (action: store_true)
- **--zeroconf-name**
  - Name used for zeroconf discovery (default: MAC from uuid.getnode)
- **--zeroconf-host**
  - Host address for zeroconf discovery (default: detect)

## Miscellaneous

Other arguments for debugging, logging, and version information.

- **--debug-recording-dir**
  - Directory to store audio for debugging
- **--debug**
  - Log DEBUG messages
  - (action: store_true)
- **--log-format**
  - Format for log messages
  - (default: "logging.BASIC_FORMAT")
- **--version**
  - Print version and exit
  - (action: version)
```

# wyoming-satellite - Installation - Docker

## Features

- Pre-built Docker image for Wyoming Satellite
- Supports multiple architectures (linux/amd64 and linux/aarch64)
- Automated builds with artifact attestation for security
- Integrated wake word detection with OpenWakeWord
- LED control support for Seeed Studio 2-mic HAT

For Raspberry Pi users: Check out [PiCompose](https://github.com/florian-asche/PiCompose) for a Pi-Ready image with pipewire-server (audio-server).

## Available Docker Tags

- `latest`: Latest stable release
- `nightly`: Builds from the main branch (may be unstable)
- Version-specific tags (e.g., `1.5.0`)

## Parameter Overview

**Note:** The most important parameters to configure are `--name` (unique identifier for your satellite instance) and `--wake-word-name` (name of the wake word to detect).


| Parameter                                            | Description                                          |
| ------------------------------------------------------ | ------------------------------------------------------ |
| `--network host`                                     | Uses the host's network stack for better performance |
| `--device /dev/snd:/dev/snd`                         | Gives access to the host's sound devices             |
| `--device /dev/bus/usb`                              | Enables access to USB audio devices                  |
| `--group-add audio`                                  | Adds the container to the host's audio group         |
| `-e PIPEWIRE_RUNTIME_DIR=/run`                       | Sets the Pipewire runtime directory                  |
| `-e XDG_RUNTIME_DIR=/run`                            | Sets the XDG runtime directory for Pipewire          |
| `--volume /run/user/1000/pipewire-0:/run/pipewire-0` | Mounts the Pipewire socket                           |
| **`--name`**                                         | Unique identifier for this satellite instance        |
| `--vad`                                              | Enables Voice Activity Detection                     |
| `--mic-auto-gain`                                    | Sets microphone auto gain level (0-10)               |
| `--mic-noise-suppression`                            | Sets noise suppression level (0-3)                   |
| `--mic-command`                                      | Command to capture audio input                       |
| `--snd-command`                                      | Command to play audio output                         |
| `--wake-uri`                                         | URI for wake word detection service                  |
| **`--wake-word-name`**                               | Name of the wake word to detect                      |
| `--event-uri`                                        | URI for event handling                               |

## Getting Started

You have two options to set up the Wyoming Satellite:

### Option 1: Using the Ready-to-Use Image

You can download the ready-to-use image which comes with all necessary system configurations.

Check out [PiCompose](https://github.com/florian-asche/PiCompose)

You just have to copy the docker-compose from here. More information in the PiCompose project.

After the first boot the board will automatically reboot one more time. Then you can copy your compose files if you already havent. Then you need to reboot the board one more time in order to activate the 2MicHat drivers if you use that hardware.

### Option 2: Manual Installation

Or you can install the Docker, driver and sofrware setup yourself by following the steps below:

##### 1. Manual Installation - Install Docker base

First, update the package database and install prerequisites:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg lsb-release
```

Add Docker's official GPG key:

```bash
# Create directory for Docker GPG key
mkdir -p /etc/apt/keyrings

# Download and add Docker's official GPG key
curl -fsSL https://download.docker.com/linux/debian/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# Set proper permissions for the GPG key
sudo chmod a+r /etc/apt/keyrings/docker.gpg
```

Set up the Docker repository:

```bash
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/debian \
  $(lsb_release -cs) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
```

Update package lists and install Docker:

```bash
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin git jq curl wget vim htop python3 python3-pip dfu-util
```

##### 2. Manual Installation - Install Pipewire Audio System

Update Package Database:

```bash
sudo apt update
```

Install PipeWire and related packages:

```bash
sudo apt install -y pipewire wireplumber pipewire-audio-client-libraries libspa-0.2-bluetooth pipewire-audio pipewire-pulse
```

Create /etc/pipewire directory:

```bash
mkdir -p "/etc/pipewire"
```

Create the file /etc/pipewire/pipewire.conf with the following content:

```
# Daemon config file for PipeWire version "1.2.7" #
#
# Copy and edit this file in /etc/pipewire for system-wide changes
# or in ~/.config/pipewire for local changes.
#
# It is also possible to place a file with an updated section in
# /etc/pipewire/pipewire.conf.d/ for system-wide changes or in
# ~/.config/pipewire/pipewire.conf.d/ for local changes.
#

context.properties = {
    ## Configure properties in the system.
    #library.name.system                   = support/libspa-support
    #context.data-loop.library.name.system = support/libspa-support
    #support.dbus                          = true
    #link.max-buffers                      = 64
    link.max-buffers                       = 16                       # version < 3 clients can't handle more
    mem.warn-mlock                        = true
    #mem.allow-mlock                       = true
    #mem.mlock-all                         = false
    #clock.power-of-two-quantum            = true
    log.level                             = 3
    #cpu.zero.denormals                    = false

    #loop.rt-prio = -1            # -1 = use module-rt prio, 0 disable rt
    #loop.class = data.rt
    #thread.affinity = [ 0 1 ]    # optional array of CPUs
    context.num-data-loops = 1   # -1 = num-cpus, 0 = no data loops
    #
    #context.data-loops = [
    #    {   loop.rt-prio = -1
    #        loop.class = [ data.rt audio.rt ]
    #        #library.name.system = support/libspa-support
    #        thread.name = data-loop.0
    #        #thread.affinity = [ 0 1 ]    # optional array of CPUs
    #    }
    #]

    core.daemon = true              # listening for socket connections
    core.name   = pipewire-0        # core name and socket name

    ## Properties for the DSP configuration.
    default.clock.rate          = 16000
    #default.clock.allowed-rates = [ 48000 ]
    #default.clock.quantum       = 1024
    #default.clock.min-quantum   = 32
    #default.clock.max-quantum   = 2048
    #default.clock.quantum-limit = 8192
    #default.clock.quantum-floor = 4
    #default.video.width         = 640
    #default.video.height        = 480
    #default.video.rate.num      = 25
    #default.video.rate.denom    = 1
    #
    #settings.check-quantum      = false
    #settings.check-rate         = false

    # keys checked below to disable module loading
    module.x11.bell = true
    # enables autoloading of access module, when disabled an alternative
    # access module needs to be loaded.
    module.access = true
    # enables autoloading of module-jackdbus-detect
    module.jackdbus-detect = true
}

context.properties.rules = [
    {   matches = [ { cpu.vm.name = !null } ]
        actions = {
            update-props = {
                # These overrides are only applied when running in a vm.
                default.clock.min-quantum = 1024
            }
        }
    }
]

context.spa-libs = {
    #<factory-name regex> = <library-name>
    #
    # Used to find spa factory names. It maps an spa factory name
    # regular expression to a library name that should contain
    # that factory.
    #
    audio.convert.* = audioconvert/libspa-audioconvert
    avb.*           = avb/libspa-avb
    api.alsa.*      = alsa/libspa-alsa
    #api.v4l2.*      = v4l2/libspa-v4l2
    #api.libcamera.* = libcamera/libspa-libcamera
    api.bluez5.*    = bluez5/libspa-bluez5
    api.vulkan.*    = vulkan/libspa-vulkan
    api.jack.*      = jack/libspa-jack
    support.*       = support/libspa-support
    #video.convert.* = videoconvert/libspa-videoconvert
    #videotestsrc   = videotestsrc/libspa-videotestsrc
    #audiotestsrc   = audiotestsrc/libspa-audiotestsrc
}

context.modules = [
    #{ name = <module-name>
    #    ( args  = { <key> = <value> ... } )
    #    ( flags = [ ( ifexists ) ( nofail ) ] )
    #    ( condition = [ { <key> = <value> ... } ... ] )
    #}
    #
    # Loads a module with the given parameters.
    # If ifexists is given, the module is ignored when it is not found.
    # If nofail is given, module initialization failures are ignored.
    # If condition is given, the module is loaded only when the context
    # properties all match the match rules.
    #

    # Uses realtime scheduling to boost the audio thread priorities. This uses
    # RTKit if the user doesn't have permission to use regular realtime
    # scheduling. You can also clamp utilisation values to improve scheduling
    # on embedded and heterogeneous systems, e.g. Arm big.LITTLE devices.
    { name = libpipewire-module-rt
        args = {
            nice.level    = -11
            rt.prio       = 88
            #rt.time.soft = -1
            #rt.time.hard = -1
            #uclamp.min = 0
            #uclamp.max = 1024
        }
        flags = [ ifexists nofail ]
    }

    # The native communication protocol.
    { name = libpipewire-module-protocol-native
        args = {
            # List of server Unix sockets, and optionally permissions
            #sockets = [ { name = "pipewire-0" }, { name = "pipewire-0-manager" } ]
        }
    }

    # The profile module. Allows application to access profiler
    # and performance data. It provides an interface that is used
    # by pw-top and pw-profiler.
    { name = libpipewire-module-profiler }

    # Allows applications to create metadata objects. It creates
    # a factory for Metadata objects.
    { name = libpipewire-module-metadata }

    # Creates a factory for making devices that run in the
    # context of the PipeWire server.
    { name = libpipewire-module-spa-device-factory }

    # Creates a factory for making nodes that run in the
    # context of the PipeWire server.
    { name = libpipewire-module-spa-node-factory }

    # Allows creating nodes that run in the context of the
    # client. Is used by all clients that want to provide
    # data to PipeWire.
    { name = libpipewire-module-client-node }

    # Allows creating devices that run in the context of the
    # client. Is used by the session manager.
    { name = libpipewire-module-client-device }

    # The portal module monitors the PID of the portal process
    # and tags connections with the same PID as portal
    # connections.
    { name = libpipewire-module-portal
        flags = [ ifexists nofail ]
    }

    # The access module can perform access checks and block
    # new clients.
    { name = libpipewire-module-access
        args = {
            # Socket-specific access permissions
            #access.socket = { pipewire-0 = "default", pipewire-0-manager = "unrestricted" }

            # Deprecated legacy mode (not socket-based),
            # for now enabled by default if access.socket is not specified
            #access.legacy = true
        }
        condition = [ { module.access = true } ]
    }

    # Makes a factory for wrapping nodes in an adapter with a
    # converter and resampler.
    { name = libpipewire-module-adapter }

    # Makes a factory for creating links between ports.
    { name = libpipewire-module-link-factory }

    # Provides factories to make session manager objects.
    { name = libpipewire-module-session-manager }

    # Use libcanberra to play X11 Bell
    { name = libpipewire-module-x11-bell
        args = {
            #sink.name = "@DEFAULT_SINK@"
            #sample.name = "bell-window-system"
            #x11.display = null
            #x11.xauthority = null
        }
        flags = [ ifexists nofail ]
        condition = [ { module.x11.bell = true } ]
    }
    { name = libpipewire-module-jackdbus-detect
        args = {
            #jack.library     = libjack.so.0
            #jack.server      = null
            #jack.client-name = PipeWire
            #jack.connect     = true
            #tunnel.mode      = duplex  # source|sink|duplex
            source.props = {
                #audio.channels = 2
		#midi.ports = 1
                #audio.position = [ FL FR ]
                # extra sink properties
            }
            sink.props = {
                #audio.channels = 2
		#midi.ports = 1
                #audio.position = [ FL FR ]
                # extra sink properties
            }
        }
        flags = [ ifexists nofail ]
        condition = [ { module.jackdbus-detect = true } ]
    }
]

context.objects = [
    #{ factory = <factory-name>
    #    ( args  = { <key> = <value> ... } )
    #    ( flags = [ ( nofail ) ] )
    #    ( condition = [ { <key> = <value> ... } ... ] )
    #}
    #
    # Creates an object from a PipeWire factory with the given parameters.
    # If nofail is given, errors are ignored (and no object is created).
    # If condition is given, the object is created only when the context properties
    # all match the match rules.
    #
    #{ factory = spa-node-factory   args = { factory.name = videotestsrc node.name = videotestsrc node.description = videotestsrc "Spa:Pod:Object:Param:Props:patternType" = 1 } }
    #{ factory = spa-device-factory args = { factory.name = api.jack.device foo=bar } flags = [ nofail ] }
    #{ factory = spa-device-factory args = { factory.name = api.alsa.enum.udev } }
    #{ factory = spa-node-factory   args = { factory.name = api.alsa.seq.bridge node.name = Internal-MIDI-Bridge } }
    #{ factory = adapter            args = { factory.name = audiotestsrc node.name = my-test node.description = audiotestsrc } }
    #{ factory = spa-node-factory   args = { factory.name = api.vulkan.compute.source node.name = my-compute-source } }

    # A default dummy driver. This handles nodes marked with the "node.always-process"
    # property when no other driver is currently active. JACK clients need this.
    { factory = spa-node-factory
        args = {
            factory.name    = support.node.driver
            node.name       = Dummy-Driver
            node.group      = pipewire.dummy
            node.sync-group  = sync.dummy
            priority.driver = 200000
            #clock.id       = monotonic # realtime | tai | monotonic-raw | boottime
            #clock.name     = "clock.system.monotonic"
        }
    }
    { factory = spa-node-factory
        args = {
            factory.name    = support.node.driver
            node.name       = Freewheel-Driver
            priority.driver = 190000
            node.group      = pipewire.freewheel
            node.sync-group  = sync.dummy
            node.freewheel  = true
            #freewheel.wait = 10
        }
    }

    # This creates a new Source node. It will have input ports
    # that you can link, to provide audio for this source.
    #{ factory = adapter
    #    args = {
    #        factory.name     = support.null-audio-sink
    #        node.name        = "my-mic"
    #        node.description = "Microphone"
    #        media.class      = "Audio/Source/Virtual"
    #        audio.position   = "FL,FR"
    #        monitor.passthrough = true
    #    }
    #}

    # This creates a single PCM source device for the given
    # alsa device path hw:0. You can change source to sink
    # to make a sink in the same way.
    #{ factory = adapter
    #    args = {
    #        factory.name           = api.alsa.pcm.source
    #        node.name              = "alsa-source"
    #        node.description       = "PCM Source"
    #        media.class            = "Audio/Source"
    #        api.alsa.path          = "hw:0"
    #        api.alsa.period-size   = 1024
    #        api.alsa.headroom      = 0
    #        api.alsa.disable-mmap  = false
    #        api.alsa.disable-batch = false
    #        audio.format           = "S16LE"
    #        audio.rate             = 48000
    #        audio.channels         = 2
    #        audio.position         = "FL,FR"
    #    }
    #}

    # Use the metadata factory to create metadata and some default values.
    #{ factory = metadata
    #    args = {
    #        metadata.name = my-metadata
    #        metadata.values = [
    #            { key = default.audio.sink   value = { name = somesink } }
    #            { key = default.audio.source value = { name = somesource } }
    #        ]
    #    }
    #}
]

context.exec = [
    #{   path = <program-name>
    #    ( args = "<arguments>" | [ <arg1> <arg2> ... ] )
    #    ( condition = [ { <key> = <value> ... } ... ] )
    #}
    #
    # Execute the given program with arguments.
    # If condition is given, the program is executed only when the context
    # properties all match the match rules.
    #
    # You can optionally start the session manager here,
    # but it is better to start it as a systemd service.
    # Run the session manager with -h for options.
    #
    #{ path = "/usr/bin/pipewire-media-session" args = ""
    #  condition = [ { exec.session-manager = null } { exec.session-manager = true } ] }
    #
    # You can optionally start the pulseaudio-server here as well
    # but it is better to start it as a systemd service.
    # It can be interesting to start another daemon here that listens
    # on another address with the -a option (eg. -a tcp:4713).
    #
    #{ path = "/usr/bin/pipewire" args = [ "-c" "pipewire-pulse.conf" ]
    #  condition = [ { exec.pipewire-pulse = null } { exec.pipewire-pulse = true } ] }
]

```

Link the PipeWire configuration to enable ALSA applications to use PipeWire:

```bash
sudo ln -sf /usr/share/alsa/alsa.conf.d/50-pipewire.conf /etc/alsa/conf.d/
```

Allow services to run without an active user session:

```bash
sudo mkdir -p /var/lib/systemd/linger
sudo touch /var/lib/systemd/linger/pi
```

##### 3. Manual Installation - Install 2mic_hat driver (Optional)

If you are using the Seeed Studio 2mic_hat, 4mic_hat, or 6mic_hat hardware, you need to install the corresponding drivers.

First, install the required system dependencies:

```bash
sudo apt-get update
sudo apt-get install -y git build-essential dkms curl raspberrypi-kernel-headers i2c-tools libasound2-plugins alsa-utils
```

Download and run the installation script:

```bash
curl -o install_driver.sh https://raw.githubusercontent.com/florian-asche/PiCompose/refs/heads/feature/initial-base/stage-picompose/02-seedstudio_2michat_driver/02-run-chroot.sh
chmod +x install_driver.sh
sudo ./install_driver.sh
```

Install the systemd service:

```bash
sudo curl -o /etc/systemd/system/seeed-voicecard.service https://raw.githubusercontent.com/florian-asche/PiCompose/feature/initial-base/stage-picompose/02-seedstudio_2michat_driver/files/seeed-voicecard.service
sudo curl -o /usr/bin/seeed-voicecard-v2 https://raw.githubusercontent.com/florian-asche/PiCompose/feature/initial-base/stage-picompose/02-seedstudio_2michat_driver/files/seeed-voicecard-v2
sudo chmod +x /usr/bin/seeed-voicecard-v2
```

Enable the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable seeed-voicecard.service
```

After installing the drivers, you need to reboot the satellite:

```bash
sudo reboot
```

##### 4. Manual Installation - Set audio volume

If your driver is loaded and you can see the device with aplay -L then
set the audio volume from 0 to 100:

```bash
export XDG_RUNTIME_DIR=/run/user/1000
sudo amixer -c seeed2micvoicec set Headphone 100%
sudo amixer -c seeed2micvoicec set Speaker 100%
sudo amixer -c Lite set Headphone 100%
sudo amixer -c Lite set Speaker 100%
sudo alsactl store
```

##### 5. Manual Installation - Add the keep_audio_running workaround (Optional) (Only needed for Respeaker Lite Hardware)

Install sox for audio processing:
```
sudo apt-get update
sudo apt-get install -y sox
```

Create script file /usr/bin/keep-audio-alive.sh with the following content:
```
#!/bin/bash

# set custom pipewire path
export XDG_RUNTIME_DIR=/run/user/1000

# run silent output
sox -n -r 16000 -c 1 -b 16 -e signed-integer -t alsa default synth 0 sine 0 vol 0.0
```

Set executable permissions:
```
sudo chmod +x /usr/bin/keep-audio-alive.sh
```

Create Systemd Service /etc/systemd/system/keep-audio-alive.service with the following content:
```
[Unit]
Description=Keep soundcard alive (play silence)
After=user@1000.service sound.target alsa-restore.service user@1000.service:pipewire.service

[Service]
Type=simple
ExecStart=/usr/bin/keep-audio-alive.sh
Restart=always
User=root

[Install]
WantedBy=multi-user.target
```

Reload systemd:
```
sudo systemctl daemon-reload
```

Enable service:
```
sudo systemctl enable keep-audio-alive.service
```

Start service:
```
sudo systemctl start keep-audio-alive.service
```

##### 6. Pipewire runtime directory (Optional)

If you work with the root user, you need to:
```bash
export XDG_RUNTIME_DIR=/run/user/1000
```

##### 7. Manual Installation - Use Docker

For a complete example configuration, check out the `docker-compose_2michat.yml` or `docker-compose_respeaker-lite.yml` file in this repository. The setup includes three main services:

- `satellite`: Main service for voice command processing
- `openwakeword`: Wake word detection service
- `ledcontrol`: LED control for Seeed Studio 2-mic HAT (optional)

To get started with the docker-compose setup:

1. Clone the repository and navigate to the project directory or download the compose file:

```bash
git clone https://github.com/florian-asche/wyoming-satellite.git
cd wyoming-satellite
```

3. Edit the docker-compose.yml file to customize your settings:

```bash
vi docker-compose.yml
```

4. Start the services using docker-compose:

```bash
docker-compose up -d
```

5. Check the status of your services:

```bash
docker-compose ps
```

6. View the logs of all services:

```bash
docker-compose logs -f
```

To stop the services:

```bash
docker-compose down
```

To run the satellite service manually:

```bash
docker run --rm -it \
  --network host \
  --device /dev/snd:/dev/snd \
  --device /dev/bus/usb \
  --group-add audio \
  -e PIPEWIRE_RUNTIME_DIR=/run \
  -e XDG_RUNTIME_DIR=/run \
  --volume /etc/localtime:/etc/localtime:ro \
  --volume /etc/timezone:/etc/timezone:ro \
  --volume /run/user/1000/pipewire-0:/run/pipewire-0 \
  ghcr.io/florian-asche/wyoming-satellite:latest \
  --debug \
  --name "satellite-wohnzimmer" \
  --vad \
  --mic-auto-gain 5 \
  --mic-noise-suppression 2 \
  --mic-command "arecord -D pipewire -r 16000 -c 1 -f S16_LE -t raw" \
  --snd-command "aplay -D pipewire -r 22050 -c 1 -f S16_LE -t raw" \
  --wake-uri "tcp://127.0.0.1:10400" \
  --wake-word-name "hey_jarvis" \
  --event-uri "tcp://127.0.0.1:10500"
```

## Build Information

Image builds can be tracked in this repository's `Actions` tab, and utilize [artifact attestation](https://docs.github.com/en/actions/security-guides/using-artifact-attestations-to-establish-provenance-for-builds) to certify provenance.

The Docker images are built using GitHub Actions, which provides:

- Automated builds for different architectures
- Artifact attestation for build provenance verification
- Regular updates and maintenance

### Build Process

The build process includes:

- Multi-architecture support (linux/amd64 and linux/aarch64)
- Security verification through artifact attestation
- Automated testing and validation
- Regular updates to maintain compatibility

For more information about the build process and available architectures, please refer to the Actions tab in this repository.

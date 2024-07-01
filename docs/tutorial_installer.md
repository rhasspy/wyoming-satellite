# Tutorial with Installer

Create a voice satellite using a Raspberry Pi 3+ and USB microphone and speakers.

## Install OS

Follow instructions to [install Raspberry Pi OS](https://www.raspberrypi.com/software/). Under "Choose OS", pick "Raspberry Pi OS (other)" and "Raspberry Pi OS (**64-bit**) Lite".

When asking if you'd like to apply customization settings, choose "Edit Settings" and:

* Set a username/password
* Configure the wireless LAN
* Under the Services tab, enable SSH and use password authentication

## Install Dependencies

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

Now you can run the installer:

```sh
cd wyoming-satellite/
python3 -m installer
```

## Satellite

Under the "Satellite" menu, select "Satellite Type" and choose "Local wake word detection" (with the space bar).

## Microphone

Make sure you USB microphone is plugged in.

Under the "Microphone" menu, select "Autodetect", and speak loudly into the microphone for a few seconds.

In "Audio Settings", set "Noise Suppression" to "Medium" and "Auto Gain" to 15.

## Speakers

Make sure your USB speakers are plugged in.

Under the "Speakers" menu, choose "Test All Speakers". For each device, choose "Play Sound" and listen. If you hear the sound, select "Choose This Device"; otherwise, select "Next Device".

In "Toggle Feedback Sounds", enable "On wake-up" and "After voice command" (with the space bar).

## Wake Word

Under the "Wake Word" menu, select "Wake Word System" and choose "openWakeWord" (with the space bar). When prompted, install openWakeWord.

In the "openWakeWord" menu, choose "Download Community Wake Words". Back in the "Wake Word" menu, select "Choose Wake Word" and select one (with the space bar).

## Apply Settings

From the main menu, select "Apply Settings" and enter your password.

Check logs with:

```sh
sudo journalctl -f -u wyoming-satellite.service
```

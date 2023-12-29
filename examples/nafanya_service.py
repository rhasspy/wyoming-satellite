#!/usr/bin/env python3
"""Controls the LEDs on the MTS Marvin Speaker."""
import argparse
import asyncio
import logging
import time
from functools import partial
from math import ceil
from typing import Tuple

#import gpiozero
#import spidev
from wyoming.asr import Transcript
from wyoming.event import Event
from wyoming.satellite import RunSatellite, StreamingStarted, StreamingStopped, VolumeAdjusted, MicMuted, MuteMic, SetVolume
from wyoming.server import AsyncEventHandler, AsyncServer
from wyoming.vad import VoiceStarted
from wyoming.wake import Detection

_LOGGER = logging.getLogger()

NUM_LEDS = 16
#LEDS_GPIO = 5
RGB_MAP = {
    "rgb": [3, 2, 1],
    "rbg": [3, 1, 2],
    "grb": [2, 3, 1],
    "gbr": [2, 1, 3],
    "brg": [1, 3, 2],
    "bgr": [1, 2, 3],
}

_BLACK = (0, 0, 0)
_WHITE = (255, 255, 255)
_RED = (255, 0, 0)
_YELLOW = (255, 255, 0)
_BLUE = (0, 0, 255)
_GREEN = (0, 255, 0)
_ORANGE = (255, 102, 0)


async def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--uri", required=True, help="unix:// or tcp://")
    #
    parser.add_argument("--debug", action="store_true", help="Log DEBUG messages")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)
    _LOGGER.debug(args)

    _LOGGER.info("Ready")

    # Turn on power to LEDs
    leds = ISSI(num_led=NUM_LEDS)

    # Start server
    server = AsyncServer.from_uri(args.uri)

    try:
        await server.run(partial(LEDsEventHandler, args, leds))
    except KeyboardInterrupt:
        pass
    finally:
        for i in range(NUM_LEDS):
            leds.set_pixel(i, 0, 0, 0)

        leds.show()

# -----------------------------------------------------------------------------



class LEDsEventHandler(AsyncEventHandler):
    """Event handler for clients."""

    def __init__(
        self,
        cli_args: argparse.Namespace,
        leds: "ISSI",
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)

        self.cli_args = cli_args
        self.client_id = str(time.monotonic_ns())
        self.leds = leds

        _LOGGER.debug("Client connected: %s", self.client_id)

    async def handle_event(self, event: Event) -> bool:
        _LOGGER.debug(event)

        if StreamingStarted.is_type(event.type):
            self.color(_YELLOW)
        elif Detection.is_type(event.type):
            self.color(_ORANGE)
            await asyncio.sleep(1.0)  # show for 1 sec
        elif VoiceStarted.is_type(event.type):
            self.color(_YELLOW)
        elif Transcript.is_type(event.type):
            self.color(_GREEN)
            await asyncio.sleep(1.0)  # show for 1 sec
        elif StreamingStopped.is_type(event.type):
            self.color(_WHITE)
        elif RunSatellite.is_type(event.type):
            self.color(_WHITE)

        return True

    def color(self, rgb: Tuple[int, int, int]) -> None:
        for i in range(NUM_LEDS):
            self.leds.set_pixel(i, rgb[0], rgb[1], rgb[2])

        self.leds.show()



# -----------------------------------------------------------------------------


class ISSI:
    """
    Driver for ISSI LEDS .
    """

    # Constants
    MAX_BRIGHTNESS = 255  # Safeguard: Set to a value appropriate for your setup
    LED_START = 0b11100000  # Three "1" bits, followed by 5 brightness bits

    def __init__(
        self,
        num_led,
        global_brightness=MAX_BRIGHTNESS,
        order="rgb",
    ):
        self.num_led = num_led  # The number of LEDs in the Strip
        order = order.lower()
        self.rgb = RGB_MAP.get(order, RGB_MAP["rgb"])
        # Limit the brightness to the maximum if it's set higher
        if global_brightness > self.MAX_BRIGHTNESS:
            self.global_brightness = self.MAX_BRIGHTNESS
        else:
            self.global_brightness = global_brightness

        self.leds = [self.LED_START, 0, 0, 0] * self.num_led  # Pixel buffer

    def set_pixel(self, led_num, red, green, blue, bright_percent=100):
        """Sets the color of one pixel in the LED stripe.

        The changed pixel is not shown yet on the Stripe, it is only
        written to the pixel buffer. Colors are passed individually.
        If brightness is not set the global brightness setting is used.
        """
        if led_num < 0:
            return  # Pixel is invisible, so ignore
        if led_num >= self.num_led:
            return  # again, invisible

        # Calculate pixel brightness as a percentage of the
        # defined global_brightness. Round up to nearest integer
        # as we expect some brightness unless set to 0
        brightness = int(ceil(bright_percent * self.global_brightness / 100.0))
        start_index = 4 * led_num
        self.leds[start_index] = self.LED_START
        self.leds[start_index + self.rgb[0]] = red
        self.leds[start_index + self.rgb[1]] = green
        self.leds[start_index + self.rgb[2]] = blue


    def set_pixel_rgb(self, led_num, rgb_color, bright_percent=100):
        """Sets the color of one pixel in the LED stripe.

        The changed pixel is not shown yet on the Stripe, it is only
        written to the pixel buffer.
        Colors are passed combined (3 bytes concatenated)
        If brightness is not set the global brightness setting is used.
        """
        self.set_pixel(
            led_num,
            (rgb_color & 0xFF0000) >> 16,
            (rgb_color & 0x00FF00) >> 8,
            rgb_color & 0x0000FF,
            bright_percent,
        )

    def rotate(self, positions=1):
        """Rotate the LEDs by the specified number of positions.

        Treating the internal LED array as a circular buffer, rotate it by
        the specified number of positions. The number could be negative,
        which means rotating in the opposite direction.
        """
        cutoff = 4 * (positions % self.num_led)
        self.leds = self.leds[cutoff:] + self.leds[:cutoff]

    def show(self):
        """Sends the content of the pixel buffer to the strip."""

        for led_num in range(self.num_led):
          start_index = 4 * led_num
          f = open(f'/sys/class/leds/rgb{led_num:02}_red/brightness', "w")
          f.write(str(self.leds[start_index + self.rgb[0]]))
          f.close()
          f = open(f'/sys/class/leds/rgb{led_num:02}_green/brightness', "w")
          f.write(str(self.leds[start_index + self.rgb[1]]))
          f.close()
          f = open(f'/sys/class/leds/rgb{led_num:02}_blue/brightness', "w")
          f.write(str(self.leds[start_index + self.rgb[2]]))
          f.close()



# -----------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

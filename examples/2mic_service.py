#!/usr/bin/env python3
"""Controls the LEDs on the ReSpeaker 2mic HAT."""
import argparse
import asyncio
import logging
import time
from functools import partial
from math import ceil
from typing import Tuple

import gpiozero
import spidev
from wyoming.asr import Transcript
from wyoming.event import Event
from wyoming.satellite import (
    RunSatellite,
    SatelliteConnected,
    SatelliteDisconnected,
    StreamingStarted,
    StreamingStopped,
)
from wyoming.server import AsyncEventHandler, AsyncServer
from wyoming.vad import VoiceStarted
from wyoming.wake import Detection

_LOGGER = logging.getLogger()

NUM_LEDS = 3
LEDS_GPIO = 12
RGB_MAP = {
    "rgb": [3, 2, 1],
    "rbg": [3, 1, 2],
    "grb": [2, 3, 1],
    "gbr": [2, 1, 3],
    "brg": [1, 3, 2],
    "bgr": [1, 2, 3],
}


async def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--uri", required=True, help="unix:// or tcp://")
    parser.add_argument("--debug", action="store_true", help="Log DEBUG messages")
    parser.add_argument(
        "--led-brightness",
        type=int,
        choices=range(1, 32),
        default=31,
        help="LED brightness (integer from 1 to 31)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)
    _LOGGER.debug(args)

    _LOGGER.info("Ready")

    # Turn on power to LEDs
    led_power = gpiozero.LED(LEDS_GPIO, active_high=False)
    led_power.on()

    leds = APA102(num_led=NUM_LEDS, global_brightness=args.led_brightness)

    # Start server
    server = AsyncServer.from_uri(args.uri)

    try:
        await server.run(partial(LEDsEventHandler, args, leds))
    except KeyboardInterrupt:
        pass
    finally:
        leds.cleanup()
        led_power.off()


# -----------------------------------------------------------------------------

_BLACK = (0, 0, 0)
_WHITE = (255, 255, 255)
_RED = (255, 0, 0)
_YELLOW = (255, 255, 0)
_BLUE = (0, 0, 255)
_GREEN = (0, 255, 0)


class LEDsEventHandler(AsyncEventHandler):
    """Event handler for clients."""

    def __init__(
        self,
        cli_args: argparse.Namespace,
        leds: "APA102",
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
            self.color(_BLUE)
            await asyncio.sleep(1.0)  # show for 1 sec
        elif VoiceStarted.is_type(event.type):
            self.color(_YELLOW)
        elif Transcript.is_type(event.type):
            self.color(_GREEN)
            await asyncio.sleep(1.0)  # show for 1 sec
        elif StreamingStopped.is_type(event.type):
            self.color(_BLACK)
        elif RunSatellite.is_type(event.type):
            self.color(_BLACK)
        elif SatelliteConnected.is_type(event.type):
            # Flash
            for _ in range(3):
                self.color(_GREEN)
                await asyncio.sleep(0.3)
                self.color(_BLACK)
                await asyncio.sleep(0.3)
        elif SatelliteDisconnected.is_type(event.type):
            self.color(_RED)

        return True

    def color(self, rgb: Tuple[int, int, int]) -> None:
        for i in range(NUM_LEDS):
            self.leds.set_pixel(i, rgb[0], rgb[1], rgb[2])

        self.leds.show()


# -----------------------------------------------------------------------------


class APA102:
    """
    Driver for APA102 LEDS (aka "DotStar").
    (c) Martin Erzberger 2016-2017
    """

    # Constants
    MAX_BRIGHTNESS = 0b11111  # Safeguard: Set to a value appropriate for your setup
    LED_START = 0b11100000  # Three "1" bits, followed by 5 brightness bits

    def __init__(
        self,
        num_led,
        global_brightness,
        order="rgb",
        bus=0,
        device=1,
        max_speed_hz=8000000,
    ):
        self.num_led = num_led  # The number of LEDs in the Strip
        order = order.lower()
        self.rgb = RGB_MAP.get(order, RGB_MAP["rgb"])
        # Limit the brightness to the maximum if it's set higher
        if global_brightness > self.MAX_BRIGHTNESS:
            self.global_brightness = self.MAX_BRIGHTNESS
        else:
            self.global_brightness = global_brightness
        _LOGGER.debug("LED brightness: %d", self.global_brightness)

        self.leds = [self.LED_START, 0, 0, 0] * self.num_led  # Pixel buffer
        self.spi = spidev.SpiDev()  # Init the SPI device
        self.spi.open(bus, device)  # Open SPI port 0, slave device (CS) 1
        # Up the speed a bit, so that the LEDs are painted faster
        if max_speed_hz:
            self.spi.max_speed_hz = max_speed_hz

    def clock_start_frame(self):
        """Sends a start frame to the LED strip.

        This method clocks out a start frame, telling the receiving LED
        that it must update its own color now.
        """
        self.spi.xfer2([0] * 4)  # Start frame, 32 zero bits

    def clock_end_frame(self):
        """Sends an end frame to the LED strip.

        As explained above, dummy data must be sent after the last real colour
        information so that all of the data can reach its destination down the line.
        The delay is not as bad as with the human example above.
        It is only 1/2 bit per LED. This is because the SPI clock line
        needs to be inverted.

        Say a bit is ready on the SPI data line. The sender communicates
        this by toggling the clock line. The bit is read by the LED
        and immediately forwarded to the output data line. When the clock goes
        down again on the input side, the LED will toggle the clock up
        on the output to tell the next LED that the bit is ready.

        After one LED the clock is inverted, and after two LEDs it is in sync
        again, but one cycle behind. Therefore, for every two LEDs, one bit
        of delay gets accumulated. For 300 LEDs, 150 additional bits must be fed to
        the input of LED one so that the data can reach the last LED.

        Ultimately, we need to send additional numLEDs/2 arbitrary data bits,
        in order to trigger numLEDs/2 additional clock changes. This driver
        sends zeroes, which has the benefit of getting LED one partially or
        fully ready for the next update to the strip. An optimized version
        of the driver could omit the "clockStartFrame" method if enough zeroes have
        been sent as part of "clockEndFrame".
        """

        self.spi.xfer2([0xFF] * 4)

        # Round up num_led/2 bits (or num_led/16 bytes)
        # for _ in range((self.num_led + 15) // 16):
        #    self.spi.xfer2([0x00])

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

        # LED startframe is three "1" bits, followed by 5 brightness bits
        ledstart = (brightness & 0b00011111) | self.LED_START

        start_index = 4 * led_num
        self.leds[start_index] = ledstart
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
        """Sends the content of the pixel buffer to the strip.

        Todo: More than 1024 LEDs requires more than one xfer operation.
        """
        self.clock_start_frame()
        # xfer2 kills the list, unfortunately. So it must be copied first
        # SPI takes up to 4096 Integers. So we are fine for up to 1024 LEDs.
        data = list(self.leds)
        while data:
            self.spi.xfer2(data[:32])
            data = data[32:]
        self.clock_end_frame()

    def cleanup(self):
        """Release the SPI device; Call this method at the end"""

        self.spi.close()  # Close SPI port


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

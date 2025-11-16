#!/usr/bin/env python3
"""
Sphero RVR Driver
Wrapper around sphero_sdk for drive and servo control
Optimized for Raspberry Pi Zero W
"""

import asyncio
import logging
import time
import traceback
from typing import Optional

import nest_asyncio

from sphero_sdk import SpheroRvrAsync
from sphero_sdk import SerialAsyncDal
from sphero_sdk import RvrLedGroups

# Enable nested event loops (required for Sphero SDK in Python 3.7)
nest_asyncio.apply()

logger = logging.getLogger(__name__)


class RVRDriver:
    """Driver for controlling Sphero RVR robot."""

    def __init__(self, config: dict):
        """
        Initialize RVR driver.

        Args:
            config: Configuration dictionary with RVR settings
        """
        self.config = config

        # RVR will be initialized in connect() method to avoid event loop issues
        self.rvr = None
        self.connected = False

        # Drive settings
        self.max_speed = config['drive']['max_speed']
        self.min_speed = config['drive']['min_speed']
        self.speed_scale = config['drive']['speed_scale']
        self.steering_sensitivity = config['drive']['steering_sensitivity']
        self.heading_speed = config['drive']['heading_speed']

        # Servo settings
        self.servo_enabled = config['servo']['enabled']
        self.servo_configs = {s['channel']: s for s in config['servo']['servos']}

        # Current state
        self.current_speed = 0
        self.current_heading = 0  # Accumulated heading (0-359)
        self.last_update_time = time.time()
        self.servo_positions = {}

        # Initialize servo positions to neutral
        for channel, servo_config in self.servo_configs.items():
            self.servo_positions[channel] = servo_config['positions']['neutral']

    async def connect(self) -> bool:
        """
        Connect to RVR via UART.

        Returns:
            True if connection successful, False otherwise
        """
        print("RVRDriver.connect() called")
        try:
            # Initialize RVR with SerialAsyncDal (must be done in async context)
            if self.rvr is None:
                print("Creating SerialAsyncDal...")
                logger.debug("Creating SerialAsyncDal...")
                loop = asyncio.get_running_loop()
                print(f"Got running loop: {loop}")
                self.rvr = SpheroRvrAsync(dal=SerialAsyncDal(loop))
                print("SpheroRvrAsync instance created")
                logger.info("RVR instance created with SerialAsyncDal")

            logger.info("Waking RVR via UART...")
            await self.rvr.wake()
            logger.debug("Wake command sent, waiting 2 seconds...")
            await asyncio.sleep(2)  # Give RVR time to wake up

            logger.debug("Requesting battery percentage...")
            # Test connection with battery percentage request
            battery = await self.rvr.get_battery_percentage()
            logger.info(f"Connected to RVR. Battery: {battery['percentage']}%")

            logger.debug("Setting LED colors to green...")
            # Set LEDs to indicate ready state (green)
            await self.rvr.set_all_leds(
                led_group=RvrLedGroups.all_lights.value,
                led_brightness_values=[0, 255, 0] * 10  # Green
            )
            logger.debug("LEDs set successfully")

            self.connected = True
            print("=" * 60)
            print("RVR CONNECTED SUCCESSFULLY - CODE VERSION: 2025-11-16-v2")
            print("=" * 60)
            logger.info("=" * 60)
            logger.info("RVR CONNECTED SUCCESSFULLY - CODE VERSION: 2025-11-16-v2")
            logger.info("=" * 60)
            return True

        except Exception as e:
            print(f"EXCEPTION in RVRDriver.connect(): {e}")
            print(f"Exception type: {type(e).__name__}")
            print(f"Traceback:\n{traceback.format_exc()}")
            logger.error(f"Failed to connect to RVR: {e}")
            logger.error(f"Exception type: {type(e).__name__}")
            logger.error(f"Traceback:\n{traceback.format_exc()}")
            self.connected = False
            return False

    async def disconnect(self):
        """Disconnect from RVR."""
        if self.connected:
            try:
                # Stop movement
                await self.stop()

                # Reset servos to neutral
                if self.servo_enabled:
                    await self.reset_servos()

                # Set LEDs to indicate shutdown (red)
                await self.rvr.set_all_leds(
                    led_group=RvrLedGroups.all_lights.value,
                    led_brightness_values=[255, 0, 0] * 10  # Red
                )

                await asyncio.sleep(0.5)
                await self.rvr.close()
                logger.info("Disconnected from RVR")
            except Exception as e:
                logger.error(f"Error during disconnect: {e}")
            finally:
                self.connected = False

    def calculate_speed(self, throttle: int, reverse: int) -> int:
        """
        Calculate speed from throttle and reverse triggers.

        Args:
            throttle: Right trigger value (0-255)
            reverse: Left trigger value (0-255)

        Returns:
            Signed speed value (-255 to 255), negative for reverse
        """
        # Both triggers cancel out
        if throttle > 0 and reverse > 0:
            return 0

        # Calculate raw speed
        if throttle > 0:
            raw_speed = throttle
        elif reverse > 0:
            raw_speed = -reverse
        else:
            return 0

        # Apply speed scaling
        scaled_speed = int(raw_speed * self.speed_scale)

        # Apply minimum speed threshold to overcome static friction
        if abs(scaled_speed) > 0 and abs(scaled_speed) < self.min_speed:
            scaled_speed = self.min_speed if scaled_speed > 0 else -self.min_speed

        # Clamp to max speed
        if abs(scaled_speed) > self.max_speed:
            scaled_speed = self.max_speed if scaled_speed > 0 else -self.max_speed

        return scaled_speed

    def calculate_heading_delta(self, steering: int, delta_time: float) -> int:
        """
        Calculate heading change from steering input over time.

        Args:
            steering: Left stick X value (-255 to 255)
            delta_time: Time elapsed since last update in seconds

        Returns:
            Heading change in degrees
        """
        if steering == 0:
            # No steering input, no heading change
            return 0

        # Apply steering sensitivity
        adjusted_steering = steering * self.steering_sensitivity

        # Calculate rotation rate based on steering input
        # Max rotation rate is heading_speed degrees per second
        # Steering range: -255 (left) to 255 (right)
        rotation_rate = (adjusted_steering / 255) * self.heading_speed

        # Calculate heading change over the time delta
        heading_delta = int(rotation_rate * delta_time)

        return heading_delta

    async def drive(self, throttle: int, reverse: int, steering: int):
        """
        Drive the RVR based on controller input.
        SIMPLIFIED: Only steering for now, throttle/reverse ignored.
        VERSION: 2025-11-16-v2

        Args:
            throttle: Right trigger value (0-255) - IGNORED
            reverse: Left trigger value (0-255) - IGNORED
            steering: Left stick X value (-255 to 255)
        """
        if not self.connected:
            logger.warning("Cannot drive: RVR not connected")
            return

        try:
            print(f"[DRIVE] Steering input: {steering}")
            logger.info(f"Steering input: {steering}")

            # Only handle steering
            if abs(steering) > 0:
                # Turn in place using raw motors
                # Positive steering (right) = left forward, right backward
                # Negative steering (left) = left backward, right forward

                turn_speed = int(abs(steering) * 0.3)
                turn_speed = max(40, min(turn_speed, 100))  # Clamp between 40-100

                if steering > 0:
                    # Turn right
                    left_speed = turn_speed
                    right_speed = -turn_speed
                else:
                    # Turn left
                    left_speed = -turn_speed
                    right_speed = turn_speed

                logger.info(f"Turning: left_speed={left_speed}, right_speed={right_speed}")

                await self.rvr.raw_motors(
                    left_mode=1 if left_speed >= 0 else 2,
                    left_speed=abs(left_speed),
                    right_mode=1 if right_speed >= 0 else 2,
                    right_speed=abs(right_speed)
                )
            else:
                # Steering released - stop motors
                logger.info("Stopping motors")
                await self.rvr.raw_motors(
                    left_mode=1,
                    left_speed=0,
                    right_mode=1,
                    right_speed=0
                )

        except Exception as e:
            logger.error(f"Error in drive command: {e}")
            import traceback
            logger.error(traceback.format_exc())

    async def stop(self):
        """Stop the RVR."""
        if not self.connected:
            return

        try:
            # Stop but maintain current heading
            await self.rvr.drive_with_heading(speed=0, heading=self.current_heading, flags=0)
            self.current_speed = 0
            logger.info(f"RVR stopped at heading {self.current_heading}")
        except Exception as e:
            logger.error(f"Error stopping RVR: {e}")

    async def set_servo(self, channel: int, position: int):
        """
        Set servo position.

        Args:
            channel: Servo channel (0-3)
            position: Servo position (0-255)
        """
        if not self.connected or not self.servo_enabled:
            return

        try:
            # Clamp position to valid range
            position = max(0, min(255, position))

            # RVR servo control using PWM commands
            # The RVR SDK uses set_all_pwms or individual PWM control
            # Servo channel maps to PWM channel on the RVR
            # Duty cycle: 0-255 (0 = 0%, 255 = 100%)

            # Create PWM duty array (4 channels, set only the specified one)
            pwm_duties = [0, 0, 0, 0]
            if 0 <= channel < 4:
                pwm_duties[channel] = position

                # Note: If set_all_pwms doesn't work, you may need to configure
                # the RVR's IO pins for servo output using set_io_pin_configuration
                # and then use set_io_pin_pwm_output
                try:
                    await self.rvr.set_all_pwms(pwm_duties)
                except AttributeError:
                    # Fallback: log warning if method doesn't exist
                    logger.warning(f"Servo control not available in this SDK version. "
                                 f"Channel {channel} position {position} requested but not set.")
                    return

                self.servo_positions[channel] = position
                logger.info(f"Servo {channel} set to position {position}")
            else:
                logger.warning(f"Invalid servo channel {channel}. Must be 0-3.")

        except Exception as e:
            logger.error(f"Error setting servo {channel}: {e}")

    async def set_servo_preset(self, button: str):
        """
        Set servo to preset position based on button press.

        Args:
            button: Button identifier ('a', 'b', 'x', 'y')
        """
        if not self.servo_enabled:
            return

        # Map buttons to servo channels and positions
        button_map = {
            'a': (0, 'position1'),  # Servo 0, position 1
            'b': (0, 'position2'),  # Servo 0, position 2
            'x': (1, 'position1'),  # Servo 1, position 1
            'y': (1, 'position2'),  # Servo 1, position 2
        }

        if button not in button_map:
            return

        channel, position_key = button_map[button]

        if channel not in self.servo_configs:
            logger.warning(f"Servo channel {channel} not configured")
            return

        position = self.servo_configs[channel]['positions'][position_key]
        await self.set_servo(channel, position)

    async def reset_servos(self):
        """Reset all servos to neutral position."""
        if not self.servo_enabled:
            return

        for channel, servo_config in self.servo_configs.items():
            neutral = servo_config['positions']['neutral']
            await self.set_servo(channel, neutral)

        logger.info("All servos reset to neutral")

    async def emergency_stop(self):
        """Emergency stop - immediately halt all motion."""
        logger.warning("EMERGENCY STOP")

        try:
            await self.stop()
            await self.rvr.reset_yaw()

            # Flash LEDs red to indicate emergency stop
            for _ in range(3):
                await self.rvr.set_all_leds(
                    led_group=RvrLedGroups.all_lights.value,
                    led_brightness_values=[255, 0, 0] * 10
                )
                await asyncio.sleep(0.2)
                await self.rvr.set_all_leds(
                    led_group=RvrLedGroups.all_lights.value,
                    led_brightness_values=[0, 0, 0] * 10
                )
                await asyncio.sleep(0.2)

        except Exception as e:
            logger.error(f"Error during emergency stop: {e}")

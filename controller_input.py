#!/usr/bin/env python3
"""
Controller Input Handler for Sphero RVR
Uses evdev to read input from Victrix BFG Pro controller
Optimized for Raspberry Pi Zero W
"""

import asyncio
import logging
from typing import Optional, Dict, Callable
from evdev import InputDevice, categorize, ecodes, list_devices

logger = logging.getLogger(__name__)


class ControllerInput:
    """Handles controller input using evdev."""

    def __init__(self, config: dict):
        """
        Initialize controller input handler.

        Args:
            config: Configuration dictionary with controller settings
        """
        self.config = config
        self.device: Optional[InputDevice] = None
        self.running = False

        # Event code mappings from config
        self.event_codes = {
            'right_trigger': getattr(ecodes, config['event_codes']['right_trigger']),
            'left_trigger': getattr(ecodes, config['event_codes']['left_trigger']),
            'left_stick_x': getattr(ecodes, config['event_codes']['left_stick_x']),
            'left_stick_y': getattr(ecodes, config['event_codes']['left_stick_y']),
            'button_a': getattr(ecodes, config['event_codes']['button_a']),
            'button_b': getattr(ecodes, config['event_codes']['button_b']),
            'button_x': getattr(ecodes, config['event_codes']['button_x']),
            'button_y': getattr(ecodes, config['event_codes']['button_y']),
        }

        # Current controller state
        self.state = {
            'right_trigger': 0,    # 0-255
            'left_trigger': 0,     # 0-255
            'left_stick_x': 0,     # -255 to 255
            'button_a': False,
            'button_b': False,
            'button_x': False,
            'button_y': False,
        }

        # Deadzone and threshold from config
        self.deadzone = config.get('deadzone', 5) / 100.0
        self.trigger_threshold = config.get('trigger_threshold', 10)

        # Callbacks
        self.on_drive_update: Optional[Callable] = None
        self.on_button_press: Optional[Callable] = None

    def find_controller(self) -> Optional[str]:
        """
        Find controller device automatically.

        Returns:
            Device path if found, None otherwise
        """
        device_name = self.config.get('device_name', 'Victrix')
        devices = [InputDevice(path) for path in list_devices()]

        for device in devices:
            if device_name.lower() in device.name.lower():
                logger.info(f"Found controller: {device.name} at {device.path}")
                return device.path

        logger.error(f"Controller with name pattern '{device_name}' not found")
        logger.info(f"Available devices: {[d.name for d in devices]}")
        return None

    async def connect(self) -> bool:
        """
        Connect to controller device.

        Returns:
            True if connection successful, False otherwise
        """
        device_path = self.config.get('device_path', 'auto')

        if device_path == 'auto':
            device_path = self.find_controller()
            if not device_path:
                return False

        try:
            self.device = InputDevice(device_path)
            logger.info(f"Connected to controller: {self.device.name}")
            logger.info(f"Device capabilities: {self.device.capabilities(verbose=True)}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to controller at {device_path}: {e}")
            return False

    def normalize_trigger(self, raw_value: int, max_raw: int = 255) -> int:
        """
        Normalize trigger value to 0-255 range with threshold.

        Args:
            raw_value: Raw trigger value from controller
            max_raw: Maximum raw value

        Returns:
            Normalized value 0-255
        """
        # Normalize to 0-255
        normalized = int((raw_value / max_raw) * 255)

        # Apply threshold
        if normalized < self.trigger_threshold:
            return 0

        return normalized

    def normalize_stick(self, raw_value: int, min_raw: int = -32768, max_raw: int = 32767) -> int:
        """
        Normalize stick value to -255 to 255 range with deadzone.

        Args:
            raw_value: Raw stick value from controller
            min_raw: Minimum raw value
            max_raw: Maximum raw value

        Returns:
            Normalized value -255 to 255
        """
        # Normalize to -1.0 to 1.0
        if raw_value >= 0:
            normalized = raw_value / max_raw
        else:
            normalized = raw_value / abs(min_raw)

        # Apply deadzone
        if abs(normalized) < self.deadzone:
            return 0

        # Scale to -255 to 255
        return int(normalized * 255)

    async def process_event(self, event):
        """
        Process a single controller event.

        Args:
            event: evdev InputEvent
        """
        if event.type != ecodes.EV_ABS and event.type != ecodes.EV_KEY:
            return

        updated = False

        # Process trigger events
        if event.code == self.event_codes['right_trigger']:
            old_value = self.state['right_trigger']
            self.state['right_trigger'] = self.normalize_trigger(event.value)
            updated = old_value != self.state['right_trigger']

        elif event.code == self.event_codes['left_trigger']:
            old_value = self.state['left_trigger']
            self.state['left_trigger'] = self.normalize_trigger(event.value)
            updated = old_value != self.state['left_trigger']

        # Process stick events
        elif event.code == self.event_codes['left_stick_x']:
            old_value = self.state['left_stick_x']
            self.state['left_stick_x'] = self.normalize_stick(event.value)
            updated = old_value != self.state['left_stick_x']

        # Process button events
        elif event.code == self.event_codes['button_a']:
            if event.value == 1 and not self.state['button_a']:  # Button pressed
                self.state['button_a'] = True
                if self.on_button_press:
                    await self.on_button_press('a', True)
            elif event.value == 0:
                self.state['button_a'] = False

        elif event.code == self.event_codes['button_b']:
            if event.value == 1 and not self.state['button_b']:
                self.state['button_b'] = True
                if self.on_button_press:
                    await self.on_button_press('b', True)
            elif event.value == 0:
                self.state['button_b'] = False

        elif event.code == self.event_codes['button_x']:
            if event.value == 1 and not self.state['button_x']:
                self.state['button_x'] = True
                if self.on_button_press:
                    await self.on_button_press('x', True)
            elif event.value == 0:
                self.state['button_x'] = False

        elif event.code == self.event_codes['button_y']:
            if event.value == 1 and not self.state['button_y']:
                self.state['button_y'] = True
                if self.on_button_press:
                    await self.on_button_press('y', True)
            elif event.value == 0:
                self.state['button_y'] = False

        # Notify drive update callback if triggers or steering changed
        if updated and self.on_drive_update:
            await self.on_drive_update(
                self.state['right_trigger'],
                self.state['left_trigger'],
                self.state['left_stick_x']
            )

    async def run(self):
        """Main event loop for reading controller input."""
        if not self.device:
            logger.error("Controller not connected")
            return

        self.running = True
        logger.info("Controller input loop started")

        try:
            async for event in self.device.async_read_loop():
                if not self.running:
                    break
                await self.process_event(event)
        except Exception as e:
            logger.error(f"Error in controller input loop: {e}")
        finally:
            self.running = False
            logger.info("Controller input loop stopped")

    def stop(self):
        """Stop the controller input loop."""
        self.running = False

    def get_state(self) -> Dict:
        """
        Get current controller state.

        Returns:
            Dictionary with current state values
        """
        return self.state.copy()

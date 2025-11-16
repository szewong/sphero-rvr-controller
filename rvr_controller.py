#!/usr/bin/env python3
"""
Sphero RVR Controller - Main Application
Controls Sphero RVR with Victrix BFG Pro controller via evdev
Optimized for Raspberry Pi Zero W headless operation
"""

import asyncio
import logging
import signal
import sys
import time
from pathlib import Path

import yaml

from controller_input import ControllerInput
from rvr_driver import RVRDriver


class RVRController:
    """Main application controller."""

    def __init__(self, config_path: str = 'config.yaml'):
        """
        Initialize RVR controller application.

        Args:
            config_path: Path to configuration file
        """
        print(f"RVRController.__init__() called with config_path: {config_path}")

        # Load configuration
        print("Loading configuration...")
        self.config = self.load_config(config_path)
        print("Configuration loaded successfully")

        # Setup logging
        print("Setting up logging...")
        self.setup_logging()
        print("Logging configured")

        # Initialize components
        print("Creating ControllerInput...")
        self.controller = ControllerInput(self.config['controller'])
        print("Creating RVRDriver...")
        self.rvr = RVRDriver(self.config)  # Pass full config (needs rvr, drive, servo sections)
        print("RVRDriver created")

        # Safety settings
        self.input_timeout = self.config['safety']['input_timeout']
        self.stop_on_disconnect = self.config['safety']['stop_on_disconnect']
        self.last_input_time = time.time()

        # Runtime state
        self.running = False
        self.reconnect_task = None

        # Register callbacks
        self.controller.on_drive_update = self.on_drive_update
        self.controller.on_button_press = self.on_button_press

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

        logger.info("RVR Controller initialized")

    def load_config(self, config_path: str) -> dict:
        """
        Load configuration from YAML file.

        Args:
            config_path: Path to config file

        Returns:
            Configuration dictionary
        """
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            print(f"Configuration loaded from {config_path}")
            return config
        except Exception as e:
            print(f"Error loading configuration: {e}")
            sys.exit(1)

    def setup_logging(self):
        """Setup logging based on configuration."""
        log_level = getattr(logging, self.config['logging']['level'])
        log_file = self.config['logging'].get('file')

        # Configure logging format
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        handlers = []

        # Console handler (always enabled for headless monitoring)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter(log_format))
        handlers.append(console_handler)

        # File handler (if specified)
        if log_file:
            try:
                file_handler = logging.FileHandler(log_file)
                file_handler.setFormatter(logging.Formatter(log_format))
                handlers.append(file_handler)
            except Exception as e:
                print(f"Warning: Could not create log file {log_file}: {e}")

        # Configure root logger
        logging.basicConfig(
            level=log_level,
            format=log_format,
            handlers=handlers
        )

        global logger
        logger = logging.getLogger(__name__)

    def signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, initiating shutdown...")
        self.running = False

    async def on_drive_update(self, throttle: int, reverse: int, steering: int):
        """
        Callback for drive input updates.

        Args:
            throttle: Right trigger value (0-255)
            reverse: Left trigger value (0-255)
            steering: Left stick X value (-255 to 255)
        """
        self.last_input_time = time.time()

        # Always log for debugging
        logger.info(f"Drive input received: throttle={throttle}, reverse={reverse}, steering={steering}")

        await self.rvr.drive(throttle, reverse, steering)

    async def on_button_press(self, button: str, pressed: bool):
        """
        Callback for button press events.

        Args:
            button: Button identifier ('a', 'b', 'x', 'y')
            pressed: True if pressed, False if released
        """
        if not pressed:
            return

        self.last_input_time = time.time()

        if self.config['logging'].get('log_inputs', False):
            logger.debug(f"Button pressed: {button}")

        # Handle servo control
        await self.rvr.set_servo_preset(button)

    async def safety_monitor(self):
        """Monitor for safety conditions (timeout, disconnection)."""
        while self.running:
            # Check input timeout
            if self.input_timeout > 0:
                time_since_input = time.time() - self.last_input_time
                if time_since_input > self.input_timeout:
                    logger.warning(f"Input timeout ({self.input_timeout}s) - stopping RVR")
                    await self.rvr.emergency_stop()
                    self.last_input_time = time.time()  # Reset to avoid repeated stops

            # Check RVR connection
            if self.stop_on_disconnect and not self.rvr.connected:
                logger.warning("RVR disconnected - attempting reconnect")
                if not self.reconnect_task or self.reconnect_task.done():
                    self.reconnect_task = asyncio.create_task(self.reconnect_rvr())

            await asyncio.sleep(0.5)

    async def reconnect_rvr(self):
        """Attempt to reconnect to RVR."""
        reconnect_delay = self.config['rvr'].get('reconnect_delay', 2)

        while self.running and not self.rvr.connected:
            logger.info("Attempting to reconnect to RVR...")
            if await self.rvr.connect():
                logger.info("RVR reconnected successfully")
                return
            else:
                logger.error(f"Reconnection failed, retrying in {reconnect_delay}s")
                await asyncio.sleep(reconnect_delay)

    async def run(self):
        """Main application loop."""
        self.running = True
        logger.info("Starting RVR Controller...")

        # Connect to controller
        logger.info("Connecting to controller...")
        if not await self.controller.connect():
            logger.error("Failed to connect to controller")
            return 1

        # Connect to RVR
        logger.info("Connecting to RVR...")
        if not await self.rvr.connect():
            logger.error("Failed to connect to RVR")
            return 1

        logger.info("RVR Controller ready!")
        logger.info("Controls:")
        logger.info("  Right Trigger: Forward throttle")
        logger.info("  Left Trigger: Reverse throttle")
        logger.info("  Left Stick: Steering")
        logger.info("  A/B/X/Y Buttons: Servo control")
        logger.info("Press Ctrl+C to stop")

        try:
            # Start all tasks concurrently
            await asyncio.gather(
                self.controller.run(),
                self.safety_monitor(),
            )
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
        finally:
            await self.shutdown()

        return 0

    async def shutdown(self):
        """Graceful shutdown."""
        logger.info("Shutting down...")

        # Stop controller input
        self.controller.stop()

        # Stop RVR and disconnect
        if self.rvr.connected:
            await self.rvr.emergency_stop()
            await self.rvr.disconnect()

        logger.info("Shutdown complete")


async def main():
    """Entry point."""
    print("In main() function...")

    # Determine config path
    config_path = 'config.yaml'
    if len(sys.argv) > 1:
        config_path = sys.argv[1]

    print(f"Using config file: {config_path}")

    # Create and run controller
    print("Creating RVRController instance...")
    controller = RVRController(config_path)
    print("RVRController created, calling run()...")
    return await controller.run()


if __name__ == '__main__':
    print("Starting Sphero RVR Controller...")
    print(f"Python version: {sys.version}")

    try:
        print("Calling asyncio.run(main())...")
        exit_code = asyncio.run(main())
        print(f"Main returned exit code: {exit_code}")
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"Fatal error: {e}")
        print(f"Exception type: {type(e).__name__}")
        import traceback
        print(f"Traceback:\n{traceback.format_exc()}")
        sys.exit(1)

"""
Raspberry Pi server script to communicate with a central AI computer for an
autonomous car.  This script opens a TCP server socket to receive control
commands and status requests from the central computer and uses a UDP
socket to stream compressed camera frames back to the central computer.

Design notes:

* The server listens for a single TCP connection from a client.  All control
  messages are sent over this reliable connection.  The Python socket
  HOWTO notes that TCP (stream) sockets provide better behaviour and
  performance for most applications than alternatives【331489574117605†L71-L77】.  Using
  TCP for control ensures that commands arrive in order and without loss.
* A simple JSON‑based protocol is used for control messages.  Each message
  must contain at least a ``cmd`` key.  Supported commands include::

    {"cmd": "register_video", "video_port": 6000}
        Register the client’s IP address and UDP port for receiving video
        frames.  Only one client can be registered at a time.  Once
        registered, the server will begin streaming camera frames via
        UDP to ``(client_ip, video_port)``.

    {"cmd": "move", "direction": "forward", "speed": 0.6, "steering": -0.2}
        Move the car.  ``direction`` should be ``"forward"`` or
        ``"backward"``.  ``speed`` is a float in the range [0, 1].  ``steering``
        is a float in the range [-1, 1], where negative values steer left
        and positive values steer right.  Implementation of motor control
        is left as a stub and should be adapted to your hardware.

    {"cmd": "stop"}
        Stop the car.  This resets speed and steering to zero.

    {"cmd": "quit"}
        Cleanly shut down the server.

* Once a client has registered a video port, a dedicated thread will
  capture frames from the Raspberry Pi camera using OpenCV (``cv2``) and
  transmit them over UDP.  The Keyestudio Smart Car documentation
  recommends using UDP for video streaming while using TCP for control
  because UDP has lower overhead【170506542320415†L50-L55】.  Frames are resized
  to 320×240 and JPEG‑encoded to reduce the datagram size.  JPEG quality
  and frame size can be adjusted to balance latency and bandwidth.

To run this script on your Raspberry Pi, first install the required
dependencies::

    sudo apt update
    sudo apt install python3-opencv python3-pygame

Then invoke the script.  By default it binds the TCP server to all
interfaces on port 5051.  You can override the host and port with
command‑line arguments (see ``--help``)::

    python3 raspi_server.py --host 0.0.0.0 --port 5051

"""

import argparse
import json
import socket
import threading
import time
from typing import Optional, Tuple

try:
    import cv2  # type: ignore
except ImportError:
    cv2 = None  # OpenCV is optional; images will not be streamed if unavailable


class CarController:
    """Control two DC motors via an L298N driver connected to a Raspberry Pi.

    Motor A (locomoção) is wired to pins IN1, IN2, ENA; Motor B (direção)
    is wired to pins IN3, IN4, ENB.  Both motors are driven via PWM on the
    ENA/ENB pins, allowing speed control.  When steering, Motor B is
    driven at a duty cycle proportional to the steering magnitude, with
    direction controlled by IN3/IN4.  When not steering, Motor B is
    stopped to avoid unnecessary current draw.

    Because the code runs on a Raspberry Pi, it depends on the
    ``RPi.GPIO`` package.  If running off‑hardware (for example, in a
    development environment), GPIO operations are skipped and log
    messages are printed instead.
    """

    def __init__(self,
                 in1: int = 17,
                 in2: int = 27,
                 ena: int = 22,
                 in3: int = 23,
                 in4: int = 24,
                 enb: int = 25,
                 freq: int = 1000) -> None:
        self.pins = {
            'IN1': in1, 'IN2': in2, 'ENA': ena,
            'IN3': in3, 'IN4': in4, 'ENB': enb,
        }
        self.freq = freq
        self.speed = 0.0
        self.steering = 0.0
        # Attempt to import RPi.GPIO; if unavailable, use a mock
        try:
            import RPi.GPIO as GPIO  # type: ignore
            self.GPIO = GPIO
            self.gpio_available = True
            self.GPIO.setmode(self.GPIO.BCM)
            # Setup motor control pins
            for pin_name, pin in self.pins.items():
                # ENA and ENB will be set up for PWM later
                if 'EN' not in pin_name:
                    self.GPIO.setup(pin, self.GPIO.OUT)
            # Setup PWM on enable pins
            self.GPIO.setup(ena, self.GPIO.OUT)
            self.GPIO.setup(enb, self.GPIO.OUT)
            self.pwm_a = self.GPIO.PWM(ena, self.freq)
            self.pwm_b = self.GPIO.PWM(enb, self.freq)
            self.pwm_a.start(0)
            self.pwm_b.start(0)
            print(f"[Motor] GPIO initialised using pins: {self.pins}")
        except Exception as e:
            # When GPIO isn't available (e.g. during development), log actions
            self.GPIO = None  # type: ignore
            self.gpio_available = False
            self.pwm_a = None  # type: ignore
            self.pwm_b = None  # type: ignore
            print(f"[Motor] RPi.GPIO not available: {e}; running in simulation mode")

    def set_speed_and_steering(self, speed: float, steering: float) -> None:
        """Update the locomotion and steering motors.

        ``speed`` may be positive (forward) or negative (backward).  The absolute
        value (0–1) defines the duty cycle for the locomotion motor.  ``steering``
        remains in the range [-1, 1].  Negative steering turns left; positive
        steering turns right; 0 means no steering.
        """
        # Clamp inputs
        speed = max(-1.0, min(1.0, speed))
        steering = max(-1.0, min(1.0, steering))
        self.speed = abs(speed)
        self.steering = steering
        # Determine direction for locomotion
        locomotion_forward = speed >= 0
        duty_loco = abs(speed)
        if duty_loco < 1e-2:
            # Stop locomotion motor
            self._set_motor(self.pins['IN1'], self.pins['IN2'], 0.0, forward=True)
        else:
            self._set_motor(self.pins['IN1'], self.pins['IN2'], duty_loco, forward=locomotion_forward)
        # Steering control
        if abs(steering) < 1e-2:
            self._set_motor(self.pins['IN3'], self.pins['IN4'], 0.0, forward=True)
        else:
            steering_forward = steering > 0
            duty_steer = abs(steering)
            self._set_motor(self.pins['IN3'], self.pins['IN4'], duty_steer, forward=steering_forward)
        print(f"[Motor] speed={speed:.2f} steering={steering:.2f}")

    def _set_motor(self, in_pin1: int, in_pin2: int, duty: float, forward: bool) -> None:
        """Low‑level helper to set a motor's direction and PWM duty cycle.

        Parameters
        ----------
        in_pin1, in_pin2 : int
            GPIO pins controlling the H‑bridge inputs for this motor.
        duty : float
            Duty cycle between 0.0 and 1.0.
        forward : bool
            If True, sets IN1 high and IN2 low; else reversed.
        """
        duty = max(0.0, min(1.0, duty))
        if not self.gpio_available:
            print(f"[Motor] (sim) {'forward' if forward else 'reverse'} duty {duty:.2f} on pins {in_pin1},{in_pin2}")
            return
        # Set direction
        if forward:
            self.GPIO.output(in_pin1, self.GPIO.HIGH)
            self.GPIO.output(in_pin2, self.GPIO.LOW)
        else:
            self.GPIO.output(in_pin1, self.GPIO.LOW)
            self.GPIO.output(in_pin2, self.GPIO.HIGH)
        # Determine which PWM to use based on IN pins
        if in_pin1 in (self.pins['IN1'], self.pins['IN2']):
            # Locomotion PWM
            self.pwm_a.ChangeDutyCycle(duty * 100)
        else:
            # Steering PWM
            self.pwm_b.ChangeDutyCycle(duty * 100)

    def stop(self) -> None:
        """Stop both motors."""
        self.set_speed_and_steering(0.0, 0.0)
        print("[Motor] stop() called")


class VideoStreamer(threading.Thread):
    """Thread that captures frames and sends them via UDP."""

    def __init__(self, udp_socket: socket.socket, get_client_addr, frame_rate: float = 20.0) -> None:
        super().__init__(daemon=True)
        self.udp_socket = udp_socket
        self.get_client_addr = get_client_addr  # Callable returning (ip, port)
        self.frame_interval = 1.0 / frame_rate
        self.running = True
        self.cap: Optional[cv2.VideoCapture] = None

    def run(self) -> None:
        if cv2 is None:
            print("[Video] OpenCV not available; video streaming disabled")
            return
        # Open default camera
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            print("[Video] Failed to open camera; video streaming disabled")
            return
        print("[Video] Camera opened; starting streaming loop")
        while self.running:
            client_addr = self.get_client_addr()
            if client_addr is None:
                # No client registered; wait and retry
                time.sleep(0.5)
                continue
            ret, frame = self.cap.read()
            if not ret:
                continue
            # Resize and compress
            frame_small = cv2.resize(frame, (320, 240))
            # Encode as JPEG; quality can be adjusted (0-100)
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 50]
            ret, buffer = cv2.imencode('.jpg', frame_small, encode_param)
            if not ret:
                continue
            data = buffer.tobytes()
            try:
                # Send frame via UDP
                self.udp_socket.sendto(data, client_addr)
            except Exception as e:
                print(f"[Video] Error sending frame: {e}")
            time.sleep(self.frame_interval)
        # Cleanup
        if self.cap is not None:
            self.cap.release()
        print("[Video] Streaming thread stopped")

    def stop(self) -> None:
        self.running = False


class CommandServer:
    """TCP server to handle incoming commands from the central computer."""

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Allow immediate reuse of the address after the server exits
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(1)
        print(f"[Server] Listening for control connection on {self.host}:{self.port}")

        # UDP socket for video streaming
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.client_video_addr: Optional[Tuple[str, int]] = None
        self.video_streamer = VideoStreamer(self.udp_socket, self.get_client_video_addr)
        self.video_streamer.start()

        # Car controller stub
        self.controller = CarController()

    def get_client_video_addr(self) -> Optional[Tuple[str, int]]:
        return self.client_video_addr

    def handle_client(self, client_socket: socket.socket, addr: Tuple[str, int]) -> None:
        print(f"[Server] Accepted connection from {addr}")
        try:
            # We will accumulate data until a newline is found.  Messages are
            # separated by newlines to make parsing easier.
            buffer = b""
            while True:
                data = client_socket.recv(4096)
                if not data:
                    print("[Server] Client disconnected")
                    break
                buffer += data
                # Process each complete line (message)
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    if not line:
                        continue
                    try:
                        msg = json.loads(line.decode('utf-8'))
                    except json.JSONDecodeError as e:
                        print(f"[Server] Failed to decode message: {e}")
                        continue
                    self.process_message(msg, client_socket, addr)
        except Exception as e:
            print(f"[Server] Error during client handling: {e}")
        finally:
            client_socket.close()
            # Reset video address on client disconnect
            if self.client_video_addr and self.client_video_addr[0] == addr[0]:
                print("[Server] Clearing registered video client")
                self.client_video_addr = None

    def process_message(self, msg: dict, client_socket: socket.socket, addr: Tuple[str, int]) -> None:
        cmd = msg.get("cmd")
        if cmd == "register_video":
            port = int(msg.get("video_port", 0))
            if port <= 0 or port > 65535:
                print(f"[Server] Invalid video port received: {port}")
                return
            # Save the client's IP address and port for video streaming
            self.client_video_addr = (addr[0], port)
            print(f"[Server] Registered video client at {self.client_video_addr}")
        elif cmd == "move":
            # Extract desired motion values
            direction = msg.get("direction", "stop")
            speed = float(msg.get("speed", 0.0))
            steering = float(msg.get("steering", 0.0))
            if direction == "forward":
                # positive speed means forward
                self.controller.set_speed_and_steering(speed, steering)
            elif direction == "backward":
                # negative speed means backward
                self.controller.set_speed_and_steering(-speed, steering)
            else:
                # unknown or "stop" -> stop motors
                self.controller.set_speed_and_steering(0.0, 0.0)
        elif cmd == "stop":
            self.controller.stop()
        elif cmd == "quit":
            print("[Server] Quit command received; shutting down")
            # Stop video and exit the main loop
            self.video_streamer.stop()
            self.server_socket.close()
        elif cmd == "status":
            # Send a status response back to the client
            status = {
                "battery": 100,  # placeholder for battery level
                "speed": self.controller.speed,
                "steering": self.controller.steering,
            }
            resp = json.dumps(status).encode('utf-8') + b"\n"
            client_socket.sendall(resp)
        else:
            print(f"[Server] Unknown command: {cmd}")

    def serve_forever(self) -> None:
        try:
            while True:
                client_socket, addr = self.server_socket.accept()
                # Spawn a thread to handle the client
                client_thread = threading.Thread(
                    target=self.handle_client, args=(client_socket, addr), daemon=True
                )
                client_thread.start()
        except OSError:
            # Server socket closed due to quit command
            pass
        finally:
            # Clean up
            print("[Server] Closing server and stopping video thread")
            self.video_streamer.stop()
            self.video_streamer.join()
            self.server_socket.close()
            self.udp_socket.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Raspberry Pi remote control server")
    parser.add_argument('--host', default='0.0.0.0', help='IP address to bind the TCP server')
    parser.add_argument('--port', type=int, default=5051, help='TCP port to listen on')
    parser.add_argument('--fps', type=float, default=20.0, help='Frame rate for video streaming')
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server = CommandServer(args.host, args.port)
    # Adjust frame rate if provided
    server.video_streamer.frame_interval = 1.0 / args.fps
    server.serve_forever()


if __name__ == '__main__':
    main()
"""
Central AI client for controlling the Raspberry Pi autonomous car.

This script runs on the central computer (for example, a laptop or desktop
running an AI model).  It establishes a TCP connection to the Raspberry Pi
server, registers a UDP port for receiving video, and reads input from a
PlayStation 5 DualSense controller (or any other joystick recognised by
pygame).  Joystick values are translated into car control commands and
sent as JSON messages over the TCP connection.  A background thread
receives JPEG‑encoded video frames via UDP, decodes them with OpenCV
and displays them in a simple window.

The Keyestudio Smart Car documentation suggests using TCP for control
commands and UDP for video streaming【170506542320415†L50-L55】.  Control commands
must be reliable and ordered, whereas video frames are tolerant of
occasional loss and benefit from lower latency.

Usage example::

    python3 central_client.py --server_ip 192.168.1.100 --server_port 5051 --video_port 6000

Dependencies:
    * pygame (for joystick input)
    * opencv-python (for video decoding and display)

Install these on your machine via pip if necessary::

    pip install pygame opencv-python

"""

import argparse
import json
import socket
import threading
import time
from typing import Optional, Tuple

try:
    import numpy as np  # type: ignore
    import cv2  # type: ignore
except ImportError:
    np = None  # type: ignore
    cv2 = None  # type: ignore

try:
    import pygame  # type: ignore
except ImportError:
    pygame = None  # type: ignore


class VideoReceiver(threading.Thread):
    """Thread that receives JPEG frames over UDP and displays them."""

    def __init__(self, udp_port: int) -> None:
        super().__init__(daemon=True)
        self.udp_port = udp_port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Bind to all interfaces on the given port
        self.sock.bind(("", udp_port))
        self.running = True
        # Frame display toggle; disable GUI on headless systems where DISPLAY is not set.
        import os
        self.display = (cv2 is not None) and bool(os.environ.get('DISPLAY'))
        if self.display:
            try:
                cv2.namedWindow("Car Camera", cv2.WINDOW_AUTOSIZE)
            except Exception:
                # Failed to create a window; disable display
                self.display = False

    def run(self) -> None:
        if np is None or cv2 is None:
            print("[VideoReceiver] numpy/cv2 not available; cannot decode frames")
            return
        print(f"[VideoReceiver] Listening for video on UDP port {self.udp_port}")
        while self.running:
            try:
                data, _ = self.sock.recvfrom(65536)
                if not data:
                    continue
                np_data = np.frombuffer(data, dtype=np.uint8)
                frame = cv2.imdecode(np_data, cv2.IMREAD_COLOR)
                if frame is None:
                    continue
                # Display the frame
                if self.display:
                    cv2.imshow("Car Camera", frame)
                    cv2.waitKey(1)
            except Exception as e:
                print(f"[VideoReceiver] Error receiving frame: {e}")
                time.sleep(0.01)
        if self.display:
            cv2.destroyWindow("Car Camera")
        self.sock.close()
        print("[VideoReceiver] Video thread terminated")

    def stop(self) -> None:
        self.running = False


class JoystickController(threading.Thread):
    """Thread that reads joystick events and sends control commands."""

    def __init__(self, client_socket: socket.socket, send_lock: threading.Lock) -> None:
        super().__init__(daemon=True)
        self.client_socket = client_socket
        self.send_lock = send_lock
        self.running = True
        self.prev_speed = 0.0
        self.prev_steering = 0.0
        self.axis_deadzone = 0.1  # ignore small movements
        self.send_interval = 0.05  # seconds between command transmissions

    def run(self) -> None:
        if pygame is None:
            print("[Joystick] pygame not available; joystick control disabled")
            return
        pygame.init()
        pygame.joystick.init()
        num_joysticks = pygame.joystick.get_count()
        if num_joysticks == 0:
            print("[Joystick] No joystick detected; please connect a controller")
            return
        joystick = pygame.joystick.Joystick(0)
        joystick.init()
        print(f"[Joystick] Using controller: {joystick.get_name()}")
        last_sent = time.time()
        try:
            while self.running:
                # Pump events to get latest state
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.running = False
                        break
                # Read axis values
                # The PS5 DualSense controller typically uses axis 1 (left stick Y)
                # for throttle and axis 0 (left stick X) for steering.
                axis_y = joystick.get_axis(1)
                axis_x = joystick.get_axis(0)
                # In pygame, up on the joystick returns -1, down returns +1.
                # We map forward movement to positive speed.
                speed = 0.0
                direction = "stop"
                # Apply deadzone
                if abs(axis_y) > self.axis_deadzone:
                    if axis_y < 0:
                        direction = "forward"
                        speed = min(1.0, -axis_y)  # invert sign; range 0-1
                    else:
                        direction = "backward"
                        speed = min(1.0, axis_y)
                steering = 0.0
                if abs(axis_x) > self.axis_deadzone:
                    steering = max(-1.0, min(1.0, axis_x))
                # Send command if changed significantly or at interval
                now = time.time()
                if (
                    abs(speed - self.prev_speed) > 0.05
                    or abs(steering - self.prev_steering) > 0.05
                    or now - last_sent >= self.send_interval
                ):
                    self.prev_speed = speed
                    self.prev_steering = steering
                    last_sent = now
                    self.send_move_command(direction, speed, steering)
                time.sleep(0.01)
        finally:
            # On exit, send stop command
            self.send_move_command("stop", 0.0, 0.0)
            pygame.joystick.quit()
            pygame.quit()
            print("[Joystick] Controller thread exiting")

    def send_move_command(self, direction: str, speed: float, steering: float) -> None:
        cmd = {
            "cmd": "move" if direction != "stop" else "stop",
            "direction": direction,
            "speed": speed,
            "steering": steering,
        }
        self.send_message(cmd)

    def send_message(self, msg: dict) -> None:
        # Send JSON message followed by newline
        data = json.dumps(msg).encode('utf-8') + b"\n"
        with self.send_lock:
            try:
                self.client_socket.sendall(data)
            except Exception as e:
                print(f"[Joystick] Failed to send command: {e}")

    def stop(self) -> None:
        self.running = False


class StatusReceiver(threading.Thread):
    """Thread that listens for status messages from the server over TCP."""

    def __init__(self, client_socket: socket.socket, send_lock: threading.Lock) -> None:
        super().__init__(daemon=True)
        self.client_socket = client_socket
        self.send_lock = send_lock
        self.running = True

    def run(self) -> None:
        buffer = b""
        while self.running:
            try:
                data = self.client_socket.recv(4096)
                if not data:
                    break
                buffer += data
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    if not line:
                        continue
                    try:
                        msg = json.loads(line.decode('utf-8'))
                        self.handle_status(msg)
                    except json.JSONDecodeError:
                        continue
            except Exception:
                time.sleep(0.01)
        print("[StatusReceiver] Exiting status thread")

    def handle_status(self, msg: dict) -> None:
        # Simple handler for status messages; extend as needed
        print(f"[Status] {msg}")

    def stop(self) -> None:
        self.running = False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Central client for Raspberry Pi car")
    parser.add_argument('--server_ip', required=True, help='IP address of the Raspberry Pi server')
    parser.add_argument('--server_port', type=int, default=5051, help='TCP port of the Raspberry Pi server')
    parser.add_argument('--video_port', type=int, default=6000, help='Local UDP port to receive video')
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    # Create a TCP connection to the server
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    print(f"[Client] Connecting to {args.server_ip}:{args.server_port} ...")
    client_socket.connect((args.server_ip, args.server_port))
    print("[Client] Connected to server")
    send_lock = threading.Lock()
    # Register for video streaming
    register_msg = {"cmd": "register_video", "video_port": args.video_port}
    client_socket.sendall(json.dumps(register_msg).encode('utf-8') + b"\n")
    print(f"[Client] Requested video stream on UDP port {args.video_port}")
    # Start video receiver
    video_receiver = VideoReceiver(args.video_port)
    video_receiver.start()
    # Start status receiver
    status_receiver = StatusReceiver(client_socket, send_lock)
    status_receiver.start()
    # Start joystick controller
    joystick_controller = JoystickController(client_socket, send_lock)
    joystick_controller.start()
    try:
        # Wait for threads to finish (they run until program exit)
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[Client] Keyboard interrupt received; shutting down")
    finally:
        # Stop all threads
        joystick_controller.stop()
        status_receiver.stop()
        video_receiver.stop()
        # Send quit command to server
        try:
            quit_msg = {"cmd": "quit"}
            with send_lock:
                client_socket.sendall(json.dumps(quit_msg).encode('utf-8') + b"\n")
        except Exception:
            pass
        # Close socket
        client_socket.close()
        # Wait for threads to finish
        joystick_controller.join(timeout=1.0)
        status_receiver.join(timeout=1.0)
        video_receiver.join(timeout=1.0)
        print("[Client] Closed connection and cleaned up")


if __name__ == '__main__':
    main()
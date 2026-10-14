#!/usr/bin/env python3
"""Validate launch-time Wolf negotiation against its actual Wayland output.

Only core wl_registry/wl_output requests are sent: no surface, rendering, GPU,
subprocess, home write or third-party Python dependency is needed.
"""
import socket
import struct
import time


def negotiated_refresh(env):
    value = env.get('GAMESCOPE_REFRESH', '60')
    try:
        rate = int(value)
    except ValueError as exc:
        raise RuntimeError('Invalid Wolf client refresh: expected integer Hz') from exc
    if not 1 <= rate <= 144:
        raise RuntimeError('Invalid Wolf client refresh: expected 1..144 Hz')
    return rate


def require_parent_mode(modes, width, height, rate):
    # Wolf provides one output per lobby. Do not guess an output on a multi-head
    # compositor, or confuse a preferred-but-not-current mode with negotiation.
    if len(modes) != 1:
        raise RuntimeError(f'Expected one current Wolf parent mode, got {modes!r}')
    mode = modes[0]
    if (mode['width'], mode['height']) != (width, height) or abs(mode['refresh_mHz'] - rate * 1000) > 500:
        raise RuntimeError(f'Wolf parent/request mismatch: parent={mode!r}, requested={width}x{height}@{rate}; recreate the lobby at the desired rate')


def parent_modes(path):
    """Read current modes with two bounded core Wayland roundtrips."""
    with socket.socket(socket.AF_UNIX) as client:
        deadline = time.monotonic() + 5
        client.settimeout(5)
        client.connect(path)
        def send(obj, opcode, payload):
            client.sendall(struct.pack('II', obj, ((8 + len(payload)) << 16) | opcode) + payload)
        def read(size):
            result = b''
            while len(result) < size:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError('Wolf parent output probe timed out')
                client.settimeout(remaining)
                chunk = client.recv(size - len(result))
                if not chunk:
                    raise RuntimeError('Wolf parent disconnected during output probe')
                result += chunk
            return result
        def events(sync):
            while True:
                obj, word = struct.unpack('II', read(8))
                size, opcode = word >> 16, word & 65535
                if size < 8 or size % 4:
                    raise RuntimeError('Malformed Wolf Wayland message')
                payload = read(size - 8)
                if obj == 1 and opcode == 0:
                    raise RuntimeError(f'Wolf parent Wayland protocol error: {payload!r}')
                if obj == sync and opcode == 0:
                    return
                yield obj, opcode, payload
        send(1, 1, struct.pack('I', 2))  # wl_display.get_registry
        send(1, 0, struct.pack('I', 3))  # wl_display.sync
        outputs = []
        for obj, opcode, payload in events(3):
            if obj == 2 and opcode == 0:
                name, length = struct.unpack('II', payload[:8])
                interface = payload[8:8 + length]
                version = struct.unpack('I', payload[8 + ((length + 3) // 4) * 4:][:4])[0]
                if interface == b'wl_output\0' and version >= 1:
                    outputs.append((name, min(version, 2)))
        current = {}
        for output, (name, version) in enumerate(outputs, 4):
            interface = b'wl_output\0'
            send(2, 0, struct.pack('II', name, len(interface)) + interface + b'\0' * 2 + struct.pack('II', version, output))
        sync = 4 + len(outputs)
        send(1, 0, struct.pack('I', sync))
        for obj, opcode, payload in events(sync):
            if 4 <= obj < sync and opcode == 1:
                flags, width, height, refresh = struct.unpack('Iiii', payload)
                if flags & 1:  # WL_OUTPUT_MODE_CURRENT, not just preferred
                    current[obj] = {'width': width, 'height': height, 'refresh_mHz': refresh}
        return list(current.values())

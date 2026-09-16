"""Small, side-effect-free builders for the Ultra Skelly BLE protocol."""

SERVICE_UUID = "0000ae00-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "0000ae01-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "0000ae02-0000-1000-8000-00805f9b34fb"


def crc8(data: bytes) -> int:
    """Return the Dallas/Maxim CRC-8 used by the prop controller."""
    result = 0
    for value in data:
        result ^= value
        for _ in range(8):
            result = ((result >> 1) ^ 0x8C) if result & 1 else result >> 1
    return result


def build_command(tag: str, payload_hex: str = "", minimum_payload_bytes: int = 8) -> bytes:
    clean_tag = tag.replace(" ", "").upper()
    clean_payload = payload_hex.replace(" ", "").upper()
    if len(clean_tag) != 4 or not clean_tag.startswith("AA"):
        raise ValueError("A Skelly command tag must be four hex characters beginning with AA")
    if len(clean_payload) % 2:
        raise ValueError("Command payload must contain complete bytes")
    clean_payload = clean_payload.ljust(minimum_payload_bytes * 2, "0")
    command = bytes.fromhex(clean_tag + clean_payload)
    return command + bytes((crc8(command),))


def set_eye_icon(index: int) -> bytes:
    if not 1 <= index <= 18:
        raise ValueError("Ultra Skelly eye index must be between 1 and 18")
    # icon, reserved byte, live cluster (zero), empty filename
    return build_command("AAF9", f"{index:02X}00" + "00000000" + "00")


def set_movement(action: int) -> bytes:
    if action not in {0, 1, 2, 4, 5, 6, 7, 255}:
        raise ValueError("Unsupported Ultra Skelly movement bitfield")
    # action bitfield, reserved byte, live cluster (zero), empty filename
    return build_command("AACA", f"{action:02X}00" + "00000000" + "00")


def probe_movement_value(action: int) -> bytes:
    """Build a tightly restricted diagnostic movement frame.

    Only values whose verified head/arm/torso bits are all clear are allowed.
    Keeping this separate from ``set_movement`` prevents an experimental value
    from leaking into normal operation or media presets.
    """
    if not 8 <= action <= 248 or action % 8:
        raise ValueError(
            "Diagnostic movement value must be 0x08-0xF8 in steps of 0x08"
        )
    return build_command("AACA", f"{action:02X}00" + "00000000" + "00")


def probe_movement_bit(action: int) -> bytes:
    """Backward-compatible name for the diagnostic movement builder."""
    return probe_movement_value(action)


def set_classic_audio(enabled: bool) -> bytes:
    return build_command("AAFD", "01" if enabled else "00")


def query_media_files() -> bytes:
    return build_command("AAD0")


def query_media_order() -> bytes:
    return build_command("AAD1")


def play_media_file(serial: int, enabled: bool = True) -> bytes:
    if not 0 <= serial <= 0xFFFF:
        raise ValueError("Media serial must fit in two bytes")
    return build_command("AAC6", f"{serial:04X}{1 if enabled else 0:02X}")


def set_volume(volume: int) -> bytes:
    if not 0 <= volume <= 100:
        raise ValueError("Skelly volume must be between 0 and 100")
    return build_command("AAFA", f"{volume:02X}")


def query_volume() -> bytes:
    return build_command("AAE5")


def query_version() -> bytes:
    """Ask the stock controller for its firmware revision."""
    return build_command("AAEE")


def filename_payload(name: str) -> str:
    clean = name.strip()
    return "5C55" + clean.encode("utf-16-le").hex().upper() if clean else "00"


def media_target_payload(data_hex: str, cluster: int, name: str) -> str:
    if not 0 <= cluster <= 0xFFFFFFFF:
        raise ValueError("Media cluster must fit in four bytes")
    return data_hex + f"{cluster:08X}" + filename_payload(name)


def set_light_brightness(channel: int, brightness: int, *, cluster: int = 0, name: str = "") -> bytes:
    if channel not in {0, 1} or not 0 <= brightness <= 255:
        raise ValueError("Light channel must be 0 or 1 and brightness 0-255")
    return build_command("AAF3", media_target_payload(f"{channel:02X}{brightness:02X}", cluster, name))


def set_light_rgb(
    channel: int,
    red: int,
    green: int,
    blue: int,
    cycle: bool = False,
    *,
    cluster: int = 0,
    name: str = "",
) -> bytes:
    if channel not in {0, 1} or any(not 0 <= value <= 255 for value in (red, green, blue)):
        raise ValueError("Light channel must be 0 or 1 and RGB values 0-255")
    data = f"{channel:02X}{red:02X}{green:02X}{blue:02X}{int(cycle):02X}"
    return build_command("AAF4", media_target_payload(data, cluster, name))


def set_light_mode(channel: int, mode: int, *, cluster: int = 0, name: str = "") -> bytes:
    if channel not in {0, 1} or mode not in {1, 2, 3}:
        raise ValueError("Light mode must be static, strobe, or pulsing")
    return build_command("AAF2", media_target_payload(f"{channel:02X}{mode:02X}", cluster, name))


def set_media_eye(index: int, cluster: int, name: str) -> bytes:
    if not 1 <= index <= 18:
        raise ValueError("Ultra Skelly eye index must be between 1 and 18")
    return build_command("AAF9", media_target_payload(f"{index:02X}00", cluster, name))


def set_media_movement(action: int, cluster: int, name: str) -> bytes:
    if action not in {0, 1, 2, 4, 5, 6, 7, 255}:
        raise ValueError("Unsupported Ultra Skelly movement bitfield")
    return build_command("AACA", media_target_payload(f"{action:02X}00", cluster, name))


def set_media_order(enabled_count: int, position: int, serial: int, name: str) -> bytes:
    if not 1 <= enabled_count <= 255 or not 1 <= position <= enabled_count:
        raise ValueError("Media order position is invalid")
    return build_command(
        "AAC9",
        f"{enabled_count:02X}{position:02X}{serial:04X}" + filename_payload(name),
    )


def start_media_transfer(size: int, packet_count: int, name: str) -> bytes:
    return build_command("AAC0", f"{size:08X}{packet_count:04X}" + filename_payload(name))


def media_transfer_chunk(index: int, data: bytes) -> bytes:
    return build_command("AAC1", f"{index:04X}" + data.hex().upper(), 0)


def end_media_transfer() -> bytes:
    return build_command("AAC2")


def confirm_media_transfer(name: str) -> bytes:
    return build_command("AAC3", filename_payload(name))

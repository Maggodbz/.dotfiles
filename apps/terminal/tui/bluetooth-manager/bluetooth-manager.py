#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["rich>=13.7"]
# ///
"""Bluetooth Manager -- full-featured interactive Rich TUI overlay."""

import re
import select
import subprocess
import sys
import termios
import threading
import time
import tty
from dataclasses import dataclass, field

from rich.align import Align
from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# Nord palette, matching eww's dark.scss.
NORD = {
    "accent": "#88C0D0",
    "green": "#A3BE8C",
    "red": "#BF616A",
    "yellow": "#EBCB8B",
    "dim": "#4C566A",
    "fg": "#ECEFF4",
    "fg_dim": "#D8DEE9",
}


def run(cmd: str, timeout: int = 5) -> tuple[int, str]:
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return r.returncode, r.stdout.strip()
    except Exception:
        return 1, ""


def overlay_panel(content: RenderableType, title: str) -> Panel:
    return Panel(
        Align.center(content),
        title=Text(title, style=f"bold {NORD['fg']}"),
        border_style=NORD["accent"],
        padding=(1, 2),
        expand=True,
    )


# ── Data Models ──────────────────────────────────────────────────────────────


@dataclass
class BluetoothDevice:
    mac: str
    name: str
    paired: bool = False
    connected: bool = False
    trusted: bool = False
    icon: str = ""  # bluetoothctl icon type (audio-card, input-keyboard, etc.)
    battery: int | None = None
    nearby: bool = False  # True if discovered during scan but not paired


@dataclass
class AdapterState:
    powered: bool = False
    discoverable: bool = False
    pairable: bool = False
    name: str = "hci0"


# ── Pairing (agent-backed session) ───────────────────────────────────────────


def pair_connect(mac: str, connect: bool = True) -> tuple[bool, str]:
    """Pair (and optionally connect) within a single bluetoothctl session that
    registers a default agent. A bare `bluetoothctl pair` run with captured
    stdin has no agent, so the bond is not authenticated and collapses after a
    few seconds. Keeping one session alive with `agent on`/`default-agent` and
    waiting through the handshake makes the bond persist.
    """
    import subprocess

    proc = subprocess.Popen(
        ["bluetoothctl"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, bufsize=1,
    )

    def send(cmd: str) -> None:
        try:
            proc.stdin.write(cmd + "\n")
            proc.stdin.flush()
        except (BrokenPipeError, ValueError):
            pass

    send("agent NoInputNoOutput")
    send("default-agent")
    send(f"pair {mac}")
    time.sleep(6)            # allow the pairing/bonding handshake to complete
    send(f"trust {mac}")
    if connect:
        send(f"connect {mac}")
        time.sleep(5)        # allow the audio profile to connect
    send("quit")

    try:
        out, _ = proc.communicate(timeout=25)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, _ = proc.communicate()

    ok = "Pairing successful" in out or "Connection successful" in out
    return ok, out


# ── Data Collection ──────────────────────────────────────────────────────────


def get_adapter() -> AdapterState:
    """Get the Bluetooth adapter status."""
    code, out = run("bluetoothctl show", timeout=3)
    if code != 0:
        return AdapterState()

    state = AdapterState()
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("Name:"):
            state.name = line.split(":", 1)[1].strip()
        elif line.startswith("Powered:"):
            state.powered = "yes" in line.lower()
        elif line.startswith("Discoverable:"):
            state.discoverable = "yes" in line.lower()
        elif line.startswith("Pairable:"):
            state.pairable = "yes" in line.lower()
    return state


def get_device_info(mac: str) -> dict[str, str]:
    """Get detailed info for a single device."""
    code, out = run(f"bluetoothctl info {mac}", timeout=3)
    if code != 0:
        return {}
    info = {}
    for line in out.splitlines():
        line = line.strip()
        if ":" in line:
            key, _, val = line.partition(":")
            info[key.strip()] = val.strip()
    return info


def get_devices() -> list[BluetoothDevice]:
    """Get all known (paired/bonded) Bluetooth devices with details."""
    _, out = run("bluetoothctl devices", timeout=3)
    devices: list[BluetoothDevice] = []

    for line in out.splitlines():
        match = re.match(r"Device\s+([0-9A-Fa-f:]{17})\s+(.*)", line.strip())
        if not match:
            continue
        mac, name = match.group(1), match.group(2)
        info = get_device_info(mac)

        battery = None
        bat_str = info.get("Battery Percentage", "")
        bat_match = re.search(r"(\d+)", bat_str)
        if bat_match:
            battery = int(bat_match.group(1))

        dev = BluetoothDevice(
            mac=mac,
            name=name or mac,
            paired="yes" in info.get("Paired", "").lower(),
            connected="yes" in info.get("Connected", "").lower(),
            trusted="yes" in info.get("Trusted", "").lower(),
            icon=info.get("Icon", ""),
            battery=battery,
        )
        devices.append(dev)

    return devices


def get_nearby_devices(known_macs: set[str]) -> list[BluetoothDevice]:
    """Get recently discovered devices that aren't already known/paired.

    bluetoothctl caches discovered devices, so this works even between scans.
    """
    _, out = run("bluetoothctl devices", timeout=3)
    nearby: list[BluetoothDevice] = []

    for line in out.splitlines():
        match = re.match(r"Device\s+([0-9A-Fa-f:]{17})\s+(.*)", line.strip())
        if not match:
            continue
        mac, name = match.group(1), match.group(2)
        if mac in known_macs:
            continue
        info = get_device_info(mac)
        if "yes" in info.get("Paired", "").lower():
            continue
        nearby.append(
            BluetoothDevice(
                mac=mac,
                name=name or mac,
                icon=info.get("Icon", ""),
                nearby=True,
            )
        )

    return nearby


# ── Device Type Labels ───────────────────────────────────────────────────────


def device_type_label(icon: str) -> str:
    """Map bluetoothctl icon string to a short readable label."""
    mapping = {
        "audio-card": "Audio",
        "audio-headphones": "Audio",
        "audio-headset": "Audio",
        "input-keyboard": "Input",
        "input-mouse": "Input",
        "input-gaming": "Input",
        "input-tablet": "Input",
        "phone": "Phone",
        "computer": "PC",
        "network-wireless": "Network",
    }
    return mapping.get(icon, icon.split("-")[0].title() if icon else "---")


# ── Battery Bar ──────────────────────────────────────────────────────────────


def battery_text(level: int | None) -> Text:
    """Render a compact battery indicator."""
    if level is None:
        return Text("")
    if level >= 60:
        color = NORD["green"]
    elif level >= 25:
        color = NORD["yellow"]
    else:
        color = NORD["red"]
    filled = level // 10
    empty = 10 - filled
    bar = "\u2588" * filled + "\u2591" * empty
    return Text(f" {bar} {level}%", style=color)


# ── Rendering ────────────────────────────────────────────────────────────────


def render_device_table(
    devices: list[BluetoothDevice],
    title: str,
    cursor_idx: int,
    offset: int,
) -> Table:
    """Render a section of devices as a Rich Table."""
    table = Table(
        show_header=True,
        header_style=f"bold {NORD['accent']}",
        box=None,
        padding=(0, 1),
        expand=True,
    )
    table.add_column("", width=2, justify="center")
    table.add_column("Device", ratio=3, no_wrap=True)
    table.add_column("MAC", ratio=3, style=NORD["fg_dim"])
    table.add_column("Type", ratio=1, justify="center")
    table.add_column("Status", ratio=2, justify="right")
    table.add_column("Battery", ratio=2, justify="right")

    for i, dev in enumerate(devices):
        global_idx = offset + i
        is_selected = global_idx == cursor_idx

        if dev.connected:
            dot = Text("\u25cf", style=NORD["green"])
            status = Text("Connected", style=f"bold {NORD['green']}")
        elif dev.paired:
            dot = Text("\u25cb", style=NORD["yellow"])
            status = Text("Paired", style=NORD["yellow"])
        elif dev.nearby:
            dot = Text("\u25cc", style=NORD["fg_dim"])
            status = Text("New", style=NORD["fg_dim"])
        else:
            dot = Text("\u25cb", style=NORD["dim"])
            status = Text("Known", style=NORD["dim"])

        name_style = f"bold {NORD['fg']}" if is_selected else NORD["fg"]
        prefix = Text("\u25b8 ", style=f"bold {NORD['accent']}") if is_selected else Text("  ")

        name_text = Text()
        name_text.append_text(prefix)
        name_text.append(dev.name, style=name_style)

        table.add_row(
            dot,
            name_text,
            Text(dev.mac, style=NORD["fg_dim"]),
            Text(device_type_label(dev.icon), style=NORD["fg_dim"]),
            status,
            battery_text(dev.battery),
        )

    return table


def build_ui(
    adapter: AdapterState,
    paired_devices: list[BluetoothDevice],
    nearby_devices: list[BluetoothDevice],
    cursor_idx: int,
    scanning: bool,
    status_msg: str,
) -> Panel:
    """Build the full Bluetooth manager UI."""

    # Header: adapter state
    if adapter.powered:
        power_text = Text("ON", style=f"bold {NORD['green']}")
    else:
        power_text = Text("OFF", style=f"bold {NORD['red']}")

    header = Text()
    header.append("Adapter: ", style=NORD["fg_dim"])
    header.append_text(power_text)
    if scanning:
        header.append("  \u00b7  ", style=NORD["dim"])
        header.append("Scanning\u2026", style=f"italic {NORD['yellow']}")

    parts: list = [Align.right(header), ""]

    if not adapter.powered:
        parts.append(
            Text(
                "  Adapter is off. Press Enter to power on.",
                style=f"italic {NORD['yellow']}",
            )
        )
        parts.append("")

    # Paired devices section
    if paired_devices:
        parts.append(
            Text("  PAIRED DEVICES", style=f"bold {NORD['accent']}")
        )
        parts.append(
            render_device_table(paired_devices, "Paired", cursor_idx, offset=0)
        )
        parts.append("")

    # Nearby devices section
    if nearby_devices:
        parts.append(
            Text("  NEARBY DEVICES", style=f"bold {NORD['accent']}")
        )
        parts.append(
            render_device_table(
                nearby_devices, "Nearby", cursor_idx, offset=len(paired_devices)
            )
        )
        parts.append("")

    if not paired_devices and not nearby_devices:
        parts.append(
            Text(
                "  No devices found. Press [s] to scan.",
                style=f"italic {NORD['fg_dim']}",
            )
        )
        parts.append("")

    # Status message (action feedback)
    if status_msg:
        parts.append(Text(f"  {status_msg}", style=f"italic {NORD['yellow']}"))
        parts.append("")

    # Footer: keybindings
    footer = Text()
    footer.append("  j/k", style=f"bold {NORD['yellow']}")
    footer.append(" Navigate  ", style=NORD["fg_dim"])
    footer.append("Enter", style=f"bold {NORD['yellow']}")
    footer.append(" Connect/Disconnect  ", style=NORD["fg_dim"])
    footer.append("s", style=f"bold {NORD['yellow']}")
    footer.append(" Scan  ", style=NORD["fg_dim"])
    footer.append("p", style=f"bold {NORD['yellow']}")
    footer.append(" Pair  ", style=NORD["fg_dim"])
    footer.append("t", style=f"bold {NORD['yellow']}")
    footer.append(" Trust  ", style=NORD["fg_dim"])
    footer.append("r", style=f"bold {NORD['yellow']}")
    footer.append(" Remove  ", style=NORD["fg_dim"])
    footer.append("q", style=f"bold {NORD['yellow']}")
    footer.append(" Quit", style=NORD["fg_dim"])

    parts.append(footer)

    return overlay_panel(Group(*parts), title="Bluetooth Manager")


# ── App State & Actions ──────────────────────────────────────────────────────


class BluetoothApp:
    """Manages state and actions for the Bluetooth manager TUI."""

    def __init__(self):
        self.adapter = AdapterState()
        self.paired: list[BluetoothDevice] = []
        self.nearby: list[BluetoothDevice] = []
        self.cursor = 0
        self.scanning = False
        self.status_msg = ""
        self.quit_event = threading.Event()
        self.lock = threading.Lock()
        self._status_timer: threading.Timer | None = None

    @property
    def all_devices(self) -> list[BluetoothDevice]:
        return self.paired + self.nearby

    @property
    def selected(self) -> BluetoothDevice | None:
        devices = self.all_devices
        if 0 <= self.cursor < len(devices):
            return devices[self.cursor]
        return None

    def set_status(self, msg: str, duration: float = 3.0):
        """Set a temporary status message that auto-clears."""
        with self.lock:
            self.status_msg = msg
            if self._status_timer:
                self._status_timer.cancel()
            self._status_timer = threading.Timer(
                duration, self._clear_status
            )
            self._status_timer.daemon = True
            self._status_timer.start()

    def _clear_status(self):
        with self.lock:
            self.status_msg = ""

    def refresh(self):
        """Refresh all device data."""
        self.adapter = get_adapter()
        self.paired = [d for d in get_devices() if d.paired]
        known_macs = {d.mac for d in self.paired}
        if self.scanning:
            self.nearby = get_nearby_devices(known_macs)
        total = len(self.all_devices)
        if total > 0:
            self.cursor = min(self.cursor, total - 1)

    def move_cursor(self, delta: int):
        total = len(self.all_devices)
        if total == 0:
            return
        self.cursor = max(0, min(self.cursor + delta, total - 1))

    def _stop_scan(self):
        """Stop scanning. Required before pair/connect: the controller cannot
        reliably establish an A2DP connection while it is busy scanning."""
        if self.scanning:
            run("bluetoothctl scan off", timeout=3)
            self.scanning = False

    def _run_action(self, cmd: str, success_msg: str, fail_msg: str, stop_scan: bool = False):
        """Run a bluetoothctl command in a background thread."""

        def _do():
            if stop_scan:
                self._stop_scan()
            self.set_status(f"Working\u2026")
            code, out = run(cmd, timeout=20)
            if code == 0:
                self.set_status(success_msg)
            else:
                self.set_status(fail_msg)
            self.refresh()

        threading.Thread(target=_do, daemon=True).start()

    def toggle_connect(self):
        if not self.adapter.powered:
            self._run_action(
                "bluetoothctl power on",
                "Adapter powered on",
                "Failed to power on adapter",
            )
            return

        dev = self.selected
        if not dev:
            return

        if dev.connected:
            self._run_action(
                f"bluetoothctl disconnect {dev.mac}",
                f"Disconnected {dev.name}",
                f"Failed to disconnect {dev.name}",
            )
        elif not dev.paired:
            # Pair + connect in one agent-backed session so the bond persists.
            def _do():
                self._stop_scan()
                self.set_status("Pairing & connecting…")
                ok, _ = pair_connect(dev.mac, connect=True)
                self.set_status(
                    f"Connected to {dev.name}" if ok
                    else f"Failed to connect to {dev.name}"
                )
                self.refresh()

            threading.Thread(target=_do, daemon=True).start()
        else:
            # Already paired/bonded — a plain connect is reliable.
            self._run_action(
                f"bluetoothctl connect {dev.mac}",
                f"Connected to {dev.name}",
                f"Failed to connect to {dev.name}",
                stop_scan=True,
            )

    def toggle_scan(self):
        if self.scanning:
            run("bluetoothctl scan off", timeout=3)
            self.scanning = False
            self.set_status("Scan stopped")
        else:
            self.scanning = True
            self.set_status("Scanning for devices\u2026")
            threading.Thread(
                target=lambda: run("bluetoothctl --timeout 15 scan on", timeout=20),
                daemon=True,
            ).start()

    def pair_selected(self):
        dev = self.selected
        if not dev:
            return
        if dev.paired:
            self.set_status(f"{dev.name} is already paired")
            return
        def _do():
            self._stop_scan()
            self.set_status("Pairing…")
            ok, _ = pair_connect(dev.mac, connect=False)
            self.set_status(
                f"Paired & trusted {dev.name}" if ok
                else f"Failed to pair with {dev.name}"
            )
            self.refresh()

        threading.Thread(target=_do, daemon=True).start()

    def trust_selected(self):
        dev = self.selected
        if not dev:
            return
        if dev.trusted:
            self._run_action(
                f"bluetoothctl untrust {dev.mac}",
                f"Untrusted {dev.name}",
                f"Failed to untrust {dev.name}",
            )
        else:
            self._run_action(
                f"bluetoothctl trust {dev.mac}",
                f"Trusted {dev.name}",
                f"Failed to trust {dev.name}",
            )

    def remove_selected(self):
        dev = self.selected
        if not dev:
            return
        self._run_action(
            f"bluetoothctl remove {dev.mac}",
            f"Removed {dev.name}",
            f"Failed to remove {dev.name}",
        )

    def render(self) -> Panel:
        with self.lock:
            return build_ui(
                self.adapter,
                self.paired,
                self.nearby,
                self.cursor,
                self.scanning,
                self.status_msg,
            )


# ── Main ─────────────────────────────────────────────────────────────────────


def _read_key(fd: int, timeout: float = 0.05) -> str | None:
    """Non-blocking single keypress read using select."""
    ready, _, _ = select.select([fd], [], [], timeout)
    if ready:
        return sys.stdin.read(1)
    return None


def main() -> None:
    console = Console()
    app = BluetoothApp()
    app.refresh()

    handlers = {
        "j": lambda: app.move_cursor(1),
        "k": lambda: app.move_cursor(-1),
        "\r": app.toggle_connect,
        "\n": app.toggle_connect,
        "s": app.toggle_scan,
        "p": app.pair_selected,
        "t": app.trust_selected,
        "r": app.remove_selected,
    }

    def background_refresh():
        while not app.quit_event.is_set():
            app.refresh()
            for _ in range(8):
                if app.quit_event.is_set():
                    return
                time.sleep(0.25)

    refresh_thread = threading.Thread(target=background_refresh, daemon=True)
    refresh_thread.start()

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        with Live(
            app.render(),
            console=console,
            refresh_per_second=30,
            screen=True,
        ) as live:
            while not app.quit_event.is_set():
                ch = _read_key(fd)
                if ch:
                    if ch.lower() == "q":
                        break
                    handler = handlers.get(ch.lower()) or handlers.get(ch)
                    if handler:
                        handler()
                live.update(app.render())
    except KeyboardInterrupt:
        pass
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        if app.scanning:
            run("bluetoothctl scan off", timeout=3)


if __name__ == "__main__":
    main()

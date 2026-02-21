#!/usr/bin/env python3
"""Network Live Metrics Dashboard — Rich TUI"""

import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from rich.align import Align
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


# ── Data Models ──────────────────────────────────────────────────────────────


@dataclass
class VPN:
    name: str
    kind: str  # "WireGuard" or "OpenVPN"
    connected: bool


@dataclass
class SSHHost:
    alias: str
    host: str
    port: int
    user: str
    reachable: bool | None = None  # None = checking


@dataclass
class K8sContext:
    name: str
    cluster: str
    active: bool
    accessible: bool | None = None  # None = checking


# ── Data Collection ──────────────────────────────────────────────────────────


def run(cmd: str, timeout: int = 5) -> tuple[int, str]:
    """Run a shell command and return (exit_code, stdout)."""
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return r.returncode, r.stdout.strip()
    except subprocess.TimeoutExpired:
        return 1, ""
    except Exception:
        return 1, ""


def get_vpns() -> list[VPN]:
    """Query NetworkManager for VPN and WireGuard connections."""
    _, out = run("nmcli -t -f NAME,TYPE,DEVICE connection show")
    vpns = []
    for line in out.splitlines():
        parts = line.split(":")
        if len(parts) < 3:
            continue
        name, kind, device = parts[0], parts[1], parts[2]
        if kind == "wireguard":
            vpns.append(VPN(name, "WireGuard", bool(device)))
        elif kind == "vpn":
            vpns.append(VPN(name, "OpenVPN", bool(device)))
    return vpns


def get_ssh_hosts() -> list[SSHHost]:
    """Parse ~/.ssh/config for Host entries."""
    from pathlib import Path

    config = Path.home() / ".ssh" / "config"
    if not config.exists():
        return []

    hosts: list[SSHHost] = []
    current: dict[str, str] = {}

    def flush():
        if current.get("alias") and current.get("host"):
            hosts.append(
                SSHHost(
                    alias=current["alias"],
                    host=current["host"],
                    port=int(current.get("port", "22")),
                    user=current.get("user", ""),
                )
            )

    for line in config.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            if current:
                flush()
                current = {}
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        key = parts[0].lower()
        val = parts[1]
        if key == "host" and "*" not in val:
            if current:
                flush()
            current = {"alias": val}
        elif key == "hostname":
            current["host"] = val
        elif key == "port":
            current["port"] = val
        elif key == "user":
            current["user"] = val

    flush()
    return hosts


def get_k8s_contexts() -> list[K8sContext]:
    """Get kubectl contexts and identify the active one."""
    _, current = run("kubectl config current-context")
    _, out = run("kubectl config get-contexts --no-headers")
    contexts = []
    for line in out.splitlines():
        cols = line.split()
        if not cols:
            continue
        if cols[0] == "*":
            name, cluster = cols[1], cols[2] if len(cols) > 2 else cols[1]
        else:
            name, cluster = cols[0], cols[1] if len(cols) > 1 else cols[0]
        contexts.append(K8sContext(name, cluster, name == current))
    return contexts


def check_ssh(host: SSHHost) -> bool:
    """Check if an SSH host is reachable via port check."""
    code, _ = run(f"nc -z -w 2 {host.host} {host.port}", timeout=4)
    return code == 0


def check_k8s(ctx: K8sContext) -> bool:
    """Check if a Kubernetes context has API access."""
    code, _ = run(
        f'kubectl --context="{ctx.name}" auth can-i get ns --request-timeout=3s',
        timeout=5,
    )
    return code == 0


# ── Rendering ────────────────────────────────────────────────────────────────

THEME = {
    "accent": "#88C0D0",
    "green": "#A3BE8C",
    "red": "#BF616A",
    "yellow": "#EBCB8B",
    "dim": "#4C566A",
    "fg": "#ECEFF4",
    "fg_dim": "#D8DEE9",
}


def make_vpn_table(vpns: list[VPN]) -> Table:
    table = Table(
        show_header=True,
        header_style=f"bold {THEME['accent']}",
        box=None,
        padding=(0, 2),
        expand=True,
    )
    table.add_column("", width=3, justify="center")
    table.add_column("Connection", ratio=3)
    table.add_column("Type", ratio=2)
    table.add_column("Status", ratio=2, justify="right")

    for vpn in vpns:
        if vpn.connected:
            dot = Text("●", style=THEME["green"])
            status = Text("Connected", style=f"bold {THEME['green']}")
        else:
            dot = Text("○", style=THEME["red"])
            status = Text("Disconnected", style=f"bold {THEME['red']}")

        table.add_row(
            dot,
            Text(vpn.name, style=THEME["fg"]),
            Text(vpn.kind, style=THEME["fg_dim"]),
            status,
        )

    return table


def make_ssh_table(hosts: list[SSHHost]) -> Table:
    table = Table(
        show_header=True,
        header_style=f"bold {THEME['accent']}",
        box=None,
        padding=(0, 2),
        expand=True,
    )
    table.add_column("", width=3, justify="center")
    table.add_column("Host", ratio=2)
    table.add_column("Target", ratio=3)
    table.add_column("Status", ratio=2, justify="right")

    for h in hosts:
        target = f"{h.host}:{h.port}" if h.port != 22 else h.host

        if h.reachable is None:
            dot = Text("◌", style=THEME["yellow"])
            status = Text("Checking…", style=f"italic {THEME['yellow']}")
        elif h.reachable:
            dot = Text("●", style=THEME["green"])
            status = Text("Reachable", style=f"bold {THEME['green']}")
        else:
            dot = Text("○", style=THEME["red"])
            status = Text("Unreachable", style=f"bold {THEME['red']}")

        table.add_row(
            dot,
            Text(h.alias, style=THEME["fg"]),
            Text(target, style=THEME["fg_dim"]),
            status,
        )

    return table


def make_k8s_table(contexts: list[K8sContext]) -> Table:
    table = Table(
        show_header=True,
        header_style=f"bold {THEME['accent']}",
        box=None,
        padding=(0, 2),
        expand=True,
    )
    table.add_column("", width=3, justify="center")
    table.add_column("Context", ratio=2)
    table.add_column("Cluster", ratio=3)
    table.add_column("Access", ratio=2, justify="right")

    for ctx in contexts:
        indicator = Text("▸", style=f"bold {THEME['accent']}") if ctx.active else Text(" ")

        if ctx.accessible is None:
            access = Text("Checking…", style=f"italic {THEME['yellow']}")
        elif ctx.accessible:
            access = Text("✓ Access OK", style=f"bold {THEME['green']}")
        else:
            access = Text("✗ Unreachable", style=f"bold {THEME['red']}")

        name_style = f"bold {THEME['fg']}" if ctx.active else THEME["fg"]

        table.add_row(
            indicator,
            Text(ctx.name, style=name_style),
            Text(ctx.cluster, style=THEME["fg_dim"]),
            access,
        )

    return table


def build_dashboard(
    vpns: list[VPN],
    ssh_hosts: list[SSHHost],
    k8s_contexts: list[K8sContext],
    refresh_time: str,
) -> Panel:
    """Compose the full dashboard layout."""

    vpn_panel = Panel(
        make_vpn_table(vpns),
        title="[bold]VPNs[/bold]",
        title_align="left",
        border_style=THEME["dim"],
        padding=(1, 2),
    )

    ssh_panel = Panel(
        make_ssh_table(ssh_hosts),
        title="[bold]SSH Hosts[/bold]",
        title_align="left",
        border_style=THEME["dim"],
        padding=(1, 2),
    )

    k8s_panel = Panel(
        make_k8s_table(k8s_contexts),
        title="[bold]Kubernetes Contexts[/bold]",
        title_align="left",
        border_style=THEME["dim"],
        padding=(1, 2),
    )

    footer = Text(
        f"  Last refresh: {refresh_time}  ·  Refreshing every 5s  ·  q to quit",
        style=THEME["fg_dim"],
    )

    content = Group(vpn_panel, "", ssh_panel, "", k8s_panel, "", footer)

    return Panel(
        Align.center(content, width=72),
        title=f"[bold {THEME['accent']}]  Network Live Metrics [/bold {THEME['accent']}]",
        border_style=THEME["accent"],
        padding=(1, 3),
        expand=True,
    )


# ── Main Loop ────────────────────────────────────────────────────────────────


def main() -> None:
    console = Console()

    # Initial data (fast, synchronous)
    vpns = get_vpns()
    ssh_hosts = get_ssh_hosts()
    k8s_contexts = get_k8s_contexts()

    # Quit flag
    quit_event = threading.Event()

    def listen_for_quit():
        """Listen for 'q' keypress in a thread."""
        try:
            import termios
            import tty

            fd = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
            try:
                tty.setcbreak(fd)
                while not quit_event.is_set():
                    ch = sys.stdin.read(1)
                    if ch.lower() == "q":
                        quit_event.set()
                        return
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
        except (termios.error, OSError, ValueError):
            # No TTY available (e.g. piped input) — just wait for SIGINT
            quit_event.wait()

    quit_thread = threading.Thread(target=listen_for_quit, daemon=True)
    quit_thread.start()

    try:
        with Live(
            build_dashboard(vpns, ssh_hosts, k8s_contexts, time.strftime("%H:%M:%S")),
            console=console,
            refresh_per_second=2,
            screen=True,
        ) as live:
            while not quit_event.is_set():
                # Refresh base data
                vpns = get_vpns()
                ssh_hosts = get_ssh_hosts()
                k8s_contexts = get_k8s_contexts()

                # Show dashboard with "checking" states
                live.update(
                    build_dashboard(
                        vpns, ssh_hosts, k8s_contexts, time.strftime("%H:%M:%S")
                    )
                )

                # Run async checks
                with ThreadPoolExecutor(max_workers=8) as pool:
                    ssh_futures = {
                        pool.submit(check_ssh, h): h for h in ssh_hosts
                    }
                    k8s_futures = {
                        pool.submit(check_k8s, c): c for c in k8s_contexts
                    }

                    for future in as_completed(
                        {**ssh_futures, **k8s_futures}, timeout=10
                    ):
                        if quit_event.is_set():
                            break

                        if future in ssh_futures:
                            host = ssh_futures[future]
                            host.reachable = future.result()
                        else:
                            ctx = k8s_futures[future]
                            ctx.accessible = future.result()

                        # Live update as each check completes
                        live.update(
                            build_dashboard(
                                vpns,
                                ssh_hosts,
                                k8s_contexts,
                                time.strftime("%H:%M:%S"),
                            )
                        )

                # Final render with all results
                live.update(
                    build_dashboard(
                        vpns, ssh_hosts, k8s_contexts, time.strftime("%H:%M:%S")
                    )
                )

                # Wait 5s but check quit every 250ms
                for _ in range(20):
                    if quit_event.is_set():
                        break
                    time.sleep(0.25)

    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()


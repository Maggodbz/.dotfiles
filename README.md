# dotfiles

A Hyprland desktop on Fedora, managed with GNU stow. Wayland compositor, an
eww top bar, wezterm + yazi, zsh, Neovim, and **Kaya** — a local‑LLM console
that lives in a terminal overlay.

Everything is designed to move to a new machine cleanly: no hardcoded usernames,
monitor names, or repo paths. Clone it anywhere and run the installer.

---

## Quick start

On a **fresh Fedora** laptop, one line:

```bash
git clone <this-repo> ~/.dotfiles && cd ~/.dotfiles && ./install.sh
```

That installs packages, uv, the JetBrainsMono Nerd Font, symlinks everything
with stow, and builds the Kaya Python env (with the voice extras). Re-runnable.
To only re-link the configs: `./install.sh stow`.

Fedora 44 does not ship the Hyprland compositor. The installer enables
`cesusieh/Hyprland` on F44 (`hyprland hyprpaper hyprshot hyprland-guiutils`)
and `solopasha/hyprland` on older releases, plus `varlad/eww` and
`lihaohong/yazi`. Configs target Hyprland **0.56** (window-rule rewrite from
0.53, hyprpaper 0.8 wallpaper blocks).

Then pick **Hyprland** (or **start-hyprland**, if the greeter lists it) at the
login screen. The top bar starts itself.

`./install.sh` does **not** install these — they are separate programs, not
dotfiles:

| Still manual | Why |
| --- | --- |
| [Ollama](https://ollama.com) + `ollama pull gemma4:e2b` | the LLM daemon Kaya talks to over HTTP |
| NVIDIA drivers | without them Kaya falls back to CPU |
| Kokoro files in `~/.local/share/kaya/kokoro/` | only if you want TTS (`kokoro-v1.0.onnx`, `voices-v1.0.bin`) |

---

## Manual install

If you'd rather do it by hand, or you're not on Fedora:

1. **Packages** — install the equivalents of:
   `git stow zsh tmux neovim jq fd-find fzf bat ripgrep wl-clipboard
   brightnessctl playerctl bluez NetworkManager nmap-ncat bc
   socat pipewire wireplumber pipewire-pulseaudio xdg-utils wofi wlogout`,
   `uv`, a JetBrainsMono Nerd Font, and the `Numix-Circle` + `breeze` icon
   themes. The Hyprland stack is spread over COPRs — `cesusieh/Hyprland` on
   Fedora 44 (`hyprland hyprpaper hyprshot hyprland-guiutils`; older Fedora
   uses `solopasha/hyprland`), `varlad/eww` (`eww`), and `lihaohong/yazi`
   (`yazi`). `wezterm` is in neither Fedora nor a COPR: install its rpm from
   [the upstream release](https://github.com/wez/wezterm/releases).
2. **Symlink** — `./install.sh stow` (`window-manager/hypr` → `~/.config/hypr`;
   `desktop-shell/` for topbar, wallpaper, overlays; apps from `apps/`).
3. **Kaya env** — `~/.config/kaya/setup-env.sh` (add `--voice` for speech).

`eww` must end up on your `PATH` (ideally `~/.local/bin`); the top‑bar daemon
adds `~/.local/bin` itself, but a login shell should too.

---

## Kaya — the local AI console

Launch with **SUPER → SPACE**. It's a Textual TUI: a waveform in the centre, an
activity ledger on the left, the conversation on the right, and an input line.

- **Ollama** is a separate program. uv only installs Kaya's Python libraries
  (Textual, numpy, optional speech). The LLM itself is served by
  [Ollama](https://ollama.com) over HTTP. Install Ollama, then:
  ```bash
  ollama pull gemma4:e2b        # the default; override with $KAYA_MODEL
  ```
- **Environment** is a uv‑managed virtualenv at `~/.local/share/kaya/venv`.
  If it's missing, Kaya prints how to build it instead of crashing. Rebuild any
  time with `~/.config/kaya/setup-env.sh [--voice]`.
- **GPU** — on start Kaya reports whether an NVIDIA GPU is available. Without
  one the model falls back to CPU and will be slow.
- **Voice** (optional) needs the `--voice` extra **and** the Kokoro model files
  in `~/.local/share/kaya/kokoro/` (`kokoro-v1.0.onnx`, `voices-v1.0.bin`).
  Speech‑to‑text downloads a Whisper model on first use.

Slash commands: `/model [name]`, `/voice on|off|list|<name>`, `/ctx <N>`,
`/viz wave|plate`, `/talk`, `/clear`, `/status`, `/help`.
Keys: `Ctrl+R` talk (press again to send / barge in), `Esc` cancel/quit,
`Ctrl+B`/`Ctrl+T` toggle the side panels, `Ctrl+L` clear.

Useful env vars: `KAYA_MODEL`, `OLLAMA_URL`, `KAYA_VENV`, `KAYA_VOICE`,
`KAYA_STT_MODEL`.

---

## Hyprland usage

The **SUPER** key toggles *hyper mode* (shown in the top bar). While it's on,
single keys act as commands:

| Key | Action |
|-----|--------|
| `t` | terminal overlay (wezterm) |
| `a` | app launcher (wofi) |
| `f` | file manager overlay (yazi) |
| `space` | Kaya AI |
| `m` | network metrics dashboard |
| `b` | bluetooth manager |
| `i` | keybindings cheat‑sheet |
| `d` | toggle monitor mirroring |
| `h/j/k/l` | focus window · `ALT`+ moves it |
| `1‑9,0` | switch workspace · `SHIFT`+ moves window there |
| `Tab` | focus next monitor |
| `Esc` | logout menu |
| `F1/F2/F3` | screenshot: output / window / region |

Overlays live on a hidden workspace and toggle in and out, so the same key both
opens and hides them.

---

## Top bar

`~/.config/desktop-shell/topbar-daemon.sh` (autostarted from the desktop-shell
Hyprland fragment) keeps an eww bar on **every** monitor and rebuilds it after
monitor hotplug or **suspend/hibernate**. Each bar highlights the workspace
active on *its own* monitor. Logs: `~/.cache/eww/open-topbar.log`.

The bar is implemented with eww; the repo package is named `topbar` because
that is what it *is*. eww still reads `~/.config/eww/` (its hardcoded config
dir), so stow maps `desktop-shell/topbar/` → `~/.config/eww/`.

The bar itself is transparent so the wallpaper shows through. Capsules (workspaces,
indicators, hyper mode) sit on top. Focus — hovered capsule, active workspace,
hyper mode, and the Hyprland window border — is the same white edge plus glow.

### Theming

A theme is one directory under `topbar/theme/`, and `theme/current` is a symlink
naming the active one. Two files per theme:

| File | Owns | Read by |
| --- | --- | --- |
| `colors.scss` | colours, fonts, shape | `eww.scss`, via `@import "./theme/current/colors.scss"` |
| `icons.sh` | icon paths and sizes | shell widgets `source` it; eww reads `icons.sh --json` into the `ICONS` variable |

Nothing outside `theme/` may name a colour or an icon file. Widgets report a
*state* — `muted`, `critical`, a window class — and the theme decides which file
that is; icon sets disagree about file names as much as they do about
directories, so a theme that only remapped directories would swap to a bar full
of missing icons.

To swap: add `theme/<name>/`, then `ln -sfn <name> theme/current && eww reload`.

---

## Per‑machine notes

These adapt automatically — nothing to edit when moving machines:

- **Monitors** — `monitor=,preferred,auto,auto`; the lid bind auto‑detects the
  internal panel (eDP/LVDS/DSI), so there's no hardcoded output name.
- **Wallpaper** — `hyprpaper` (a separate hyprwm daemon, not the compositor)
  plus images in `~/.config/hyprpaper/wallpapers/`.
- **Homebrew** — sourced only if present; harmless if you don't use it.

---

## Repo layout

GNU stow packages. Hyprland must load `~/.config/hypr/hyprland.conf`; that file
stays compositor-only and `source`s the desktop-shell fragment. Packages under
`window-manager/`, `desktop-shell/`, and `apps/` are **flat**.

```
window-manager/
  hypr/                       → ~/.config/hypr/  (compositor + lid/mirror)
desktop-shell/
  topbar/                     → ~/.config/eww/  (eww implementation of the bar)
  hyprpaper/                  → ~/.config/hyprpaper/  (wallpaper daemon + images)
  session/                    → ~/.config/desktop-shell/  (hypr fragment, overlays, topbar daemon)
apps/
  gui/
    wezterm/                  → ~/.wezterm.lua
    wofi/                     → ~/.config/wofi/
  terminal/
    cli/
      zsh/                    → ~/.zshrc
      tmux/                   → ~/.tmux.conf
    tui/
      nvim/                   → ~/.config/nvim/
      yazi/                   yazi config
      kaya/                   Kaya TUI + setup-env / venv tooling
      bluetooth-manager/      single-file Rich TUI (PEP 723 deps)
      netmetrics/             single-file Rich TUI (PEP 723 deps)
      keybindings/            single-file Rich TUI (PEP 723 deps)
install.sh                    Fedora bootstrap (`./install.sh stow` re-links)
```

### Python dependencies

Only **Kaya** has a managed environment: `pyproject.toml` + `setup-env.sh` build
a uv venv at `~/.local/share/kaya/venv` (it needs textual, numpy, and the
optional voice stack).

The three small Rich TUIs declare their own dependencies inline with
[PEP 723](https://peps.python.org/pep-0723/) and run via `uv run --script`, so
each gets its own cached environment with **no setup step** — `run.sh` just
hands the script to uv. Adding a dependency means editing the header comment at
the top of the script, nothing else.

## Troubleshooting

- **No top bar after login/resume** — check `~/.cache/eww/open-topbar.log`, make
  sure `eww` is on `PATH`, and that `topbar-daemon.sh` is running
  (`pgrep -af topbar-daemon`). The daemon lives at `~/.config/desktop-shell/`.
- **Kaya says the env isn't ready** — run `~/.config/kaya/setup-env.sh`.
- **Kaya is slow / "No GPU"** — install NVIDIA drivers, or accept CPU inference.
- **Model VRAM stays used after quit** — Kaya unloads on exit and on
  `SIGHUP`/`SIGTERM`/`SIGINT`; if Ollama was started elsewhere it manages its
  own `keep_alive`.
- **Reload config live** — `hyprctl reload`, `eww reload`.
- **Bar looks unthemed / missing icons** — `theme/current` must point at a
  theme directory (`ln -sfn nord ~/.config/eww/theme/current`) and the
  `numix-icon-theme-circle` + `breeze-icon-theme` packages must be installed.

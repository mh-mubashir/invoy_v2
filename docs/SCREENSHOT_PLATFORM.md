# Screenshot Capture – Platform Compatibility

This document records which screenshot methodology works on each tested Linux configuration.

---

## Verified Working Configuration

### Methodology (GNOME Wayland)

| Method | Status | Notes |
|--------|--------|-------|
| **gnome-screenshot** | ✅ Working | Produces accurate screenshots with content. |
| **mss** | ❌ Fails | `XGetImage()` error – requires X11, not available on Wayland |
| **grim** | ❌ Fails | `compositor doesn't support wlr-screencopy-unstable-v1` – grim requires wlroots (Sway, etc.), not GNOME |
| **scrot** | ❌ Produces BLACK images | Do not use on Wayland. Creates PNG files but they are empty/black. |

On **GNOME Wayland**, **gnome-screenshot** is the correct tool. grim and scrot do not work on this setup.

### Tested Machine

| Property | Value |
|----------|-------|
| **Hardware** | Lenovo V14 G3 IAP (LENOVO_MT_82TS) |
| **OS** | Ubuntu 24.04.2 LTS (Noble Numbat) |
| **Kernel** | Linux 6.17.0-14-generic |
| **Architecture** | x86_64 |
| **Display** | Wayland (`XDG_SESSION_TYPE=wayland`) |
| **Desktop** | GNOME |
| **Working tool** | gnome-screenshot |

### Verification

- Single capture: OK (1.5 MB PNG, 3840×1080)
- Periodic capture: OK (multiple screenshots at ~2s interval)
- Image content: verified non-black (avg RGB ~54, 57, 60)

### Capture Flow

1. SDK tries **mss** (X11) first.
2. If mss fails (e.g. on Wayland), SDK tries **gnome-screenshot** (GNOME).
3. If gnome-screenshot fails, SDK tries **grim** (Sway/wlroots).
4. scrot is **not** used – it produces black screenshots on Wayland.

### Dependencies for This Setup (GNOME Wayland, Ubuntu 24.04)

```bash
sudo apt install gnome-screenshot
```

---

## Other Platforms (Reference)

| Compositor | Recommended tool |
|------------|------------------|
| GNOME Wayland | gnome-screenshot |
| Sway / wlroots | grim |
| X11 | mss |

---

## Adding New Platforms

When testing on a new machine, add an entry to this document with:

- Methodology that worked (mss, grim, gnome-screenshot, etc.)
- Hardware make/model
- OS and kernel version
- Display type (X11 vs Wayland)
- Desktop/compositor (GNOME, Sway, etc.)

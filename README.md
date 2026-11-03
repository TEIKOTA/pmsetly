# pmsetly

A tiny macOS menu bar app that toggles `pmset disablesleep`, so your Mac keeps running
(e.g. AI agents, long builds) even with the lid closed.

The whole app is about 140 lines. Please read it before you install — that is the point.

| File | What it does |
| --- | --- |
| `Sources/pmsetly/Pmset.swift` | Reads `pmset -g` and runs `sudo -n pmset -a disablesleep 0/1` |
| `Sources/pmsetly/PmsetlyApp.swift` | Menu bar UI: state, toggle, quit |
| `build.sh` | Builds `build/pmsetly.app` with SwiftPM |
| `install.sh` | Copies the app to `/Applications` and adds a sudoers rule |

## Install

Requires macOS 13+ and Xcode or the Command Line Tools.

```sh
git clone https://github.com/TEIKOTA/pmsetly.git
cd pmsetly
./build.sh
sudo ./install.sh
open /Applications/pmsetly.app
```

`install.sh` writes `/etc/sudoers.d/pmsetly`, which lets **only your user** run exactly
`/usr/bin/pmset -a disablesleep 0` and `/usr/bin/pmset -a disablesleep 1` without a password.
Note: any process running as your user can then toggle sleep prevention (nothing else).

## Behavior

- The icon shows the real system state (`SleepDisabled` in `pmset -g`), even if another tool changed it.
- **Quit turns sleep prevention OFF.**
- If the app crashes while ON, sleep stays disabled. Reopen the app and turn it OFF, or run:
  `sudo pmset -a disablesleep 0`

With the lid closed, the Mac keeps running hot in your bag. Watch heat and battery.

## Uninstall

```sh
sudo rm /etc/sudoers.d/pmsetly
sudo rm -rf /Applications/pmsetly.app
```

## License

[MIT](./LICENSE)

# getapp

**One fuzzy search for everything you can install on Debian.** Type a few letters and see matches from **apt**,
**Flatpak** (Flathub), the **Snap Store** and **web apps** in one ranked list, with a details pane and a ✓ on what is
already installed. Press Enter to install. Inspired by Omarchy's package picker, built for any Debian-based system.

```
 install> vlc                                                            112/112   ╭─ details ─────────────────────────
 ▌ flatpak  VLC                       VLC media player, the open-source …          │ org.videolan.VLC
   snap     VLC                       The ultimate media player                    │ VLC media player, the open-source …
   apt      vlc                       multimedia player and streamer               │ Installs with: flatpak install flathub …
   apt      vlc-bin                   binaries from VLC                            │ Flatpak apps are sandboxed and come …
   apt      vlc-plugin-qt             multimedia player and streamer (Qt plugin)   │
```

## Install

On any Debian, Ubuntu, Mint, Pop!_OS … machine, from a checkout of this repository:

```
./install.sh --dry-run        # see what it would do
./install.sh                  # installs getapp for your user into ~/.local (apt-installs fzf and python3 if missing)
```

Options: `--with-flatpak` (also install Flatpak and add Flathub), `--with-snap` (also install snapd),
`--with-chromium` (for web apps), `--system` (for all users, into `/usr/local`), `--prefix DIR`,
`--no-desktop-entry`, `--uninstall`. It also adds **getapp** to your application launcher.

## Use

```
getapp                 # the search screen
getapp vlc             # ... starting with a query
getapp --dry-run       # the same, but nothing is ever installed: it only shows what it would run
getapp remove          # pick something installed to remove
getapp doctor          # what works on this machine
```

| In the search screen | |
|---|---|
| type | words are all required; order does not matter; small typos are tolerated (`frefox` finds Firefox) |
| `apt:` `flatpak:` `snap:` `web:` | limit the list to one source, e.g. `flatpak: slack` |
| type a web address, e.g. `github.com/foo` | offers to install it as a **web app** |
| `Enter` | shows exactly what will run, asks, then does it, then returns to the search |
| `Ctrl-/` | show or hide the details pane |
| `Esc` | quit |

Other commands: `getapp install KEY...` (for example `getapp install flatpak:com.slack.Slack`), `getapp remove KEY...`,
`getapp refresh` (rebuild the package lists), `getapp setup flatpak|snap|chromium` (install the tools a source needs).
`--yes` skips the confirmation question.

## Sources

| Source | Searched | Installs with | Notes |
|---|---|---|---|
| **apt** | local index of about 70 000 packages | `apt-get install` | Libraries and `-dev`/`-dbg` packages rank low unless you ask for them |
| **flatpak** | Flathub's app list, refreshed daily | `flatpak install flathub` | Sandboxed apps; set `GETAPP_FLATPAK_SCOPE=user` to install without sudo |
| **snap** | the Snap Store, live (1 h cache) | `snap install` | Works without snapd installed; installing offers to install snapd first |
| **web** | a catalog of about 90 sites, plus any address you type | a launcher that runs `chromium --app=URL` | No software is added: you get an app-launcher entry with the site's icon |

There is no AUR on Debian (it is Arch's repository); these four sources cover the same ground.

Add your own web apps in `~/.config/getapp/webapps.tsv` (`name`, `url`, `description`, separated by tabs).

## How it works

A small Python program ranks the results (exact name, prefix, word start, substring, description, then loose
subsequence matches) and [`fzf`](https://github.com/junegunn/fzf) draws the screen: every keystroke re-runs
`getapp search`, so the list is always the live, merged ranking. Package lists are cached in `~/.cache/getapp` and
refreshed when apt or Flathub change. Installing never happens without showing the commands first; `sudo` is only
used for the steps that need root.

Environment variables: `GETAPP_DRY_RUN=1`, `GETAPP_FLATPAK_SCOPE=user`, `GETAPP_OFFLINE=1` (no network; the Snap Store
and icons are skipped), `GETAPP_CACHE_DIR`, `GETAPP_CONFIG_DIR`, `GETAPP_DATA_HOME`.

## Tests

```
tests/run.sh      # unit tests, the installer in a throwaway prefix, the real screen driven through tmux, privacy scan
```

Nothing in the tests installs software or touches your configuration.

## Limits

* Debian and derivatives only (it uses `apt`). The search screen needs `fzf` and a terminal.
* Snap results need the network; apt and Flatpak search works offline from the cached lists.
* Removing an apt package uses `apt-get remove` (it keeps configuration files) and tells you which other packages
  would go with it; it does not run `autoremove`.
* The list is rebuilt for every keystroke in about a fifth of a second; a long-running search service would make it
  faster still.

## License

MIT, see [LICENSE](LICENSE).

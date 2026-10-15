# iOS installs

Open <https://apps.christiantanul.com/> on a registered iPhone.

## Install from Linux

Keep the iPhone awake. On the same local network:

```sh
uv run scripts/iphone.py --pairing-record ~/.local/share/ios-installs/iphone.plist app.ipa
```

Over Tailscale, connect the iPhone to **Tailscale**, not LocalDevVPN:

```sh
uv run scripts/iphone.py --pairing-record ~/.local/share/ios-installs/iphone.plist --host 100.116.148.84 app.ipa
```

`--host` skips local discovery. `--port` overrides the default pairing port, 49152.
Omit `app.ipa` to check connectivity. The command needs passwordless `sudo`
for a temporary developer tunnel. It verifies the installed bundle and build.
The IPA must already be signed for this phone; this command does not build or sign apps.

Restore the pairing file from the `record` field of **Christian iPhone pairing**
in 1Password, with mode `0600`. It contains the remote pairing keys,
`host_identifier`, `remote_identifier`, and Bonjour `hostname`.

## Switch VPNs

Add [SideStore VPN](shortcuts/sidestore-vpn.shortcut) and
[Tailscale VPN](shortcuts/tailscale-vpn.shortcut) in Shortcuts on the iPhone.

In **Automation → App → SideStore**, run **SideStore VPN** when opened.
Set **Run Immediately**. Run **Tailscale VPN** after installs finish.
An **Is Closed** automation can restore Tailscale too, but switching away
during an install or self-refresh may interrupt it.

Generate the unsigned files with `uv run scripts/make-vpn-shortcuts.py`.
Sign each on macOS with `shortcuts sign --mode anyone --input NAME.unsigned.shortcut --output NAME.shortcut`.

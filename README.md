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
The IPA must already be signed for this phone. Updates use the same bundle ID;
the installer does not uninstall the app or clear its data.

Restore the pairing file from the `record` field of **Christian iPhone pairing**
in 1Password, with mode `0600`. It contains the remote pairing keys,
`host_identifier`, `remote_identifier`, and Bonjour `hostname`.

## Sign on Linux

Download an IPA from a trusted HTTPS source, then sign it:

```sh
curl --fail --location --proto '=https' --proto-redir '=https' --output app.ipa 'HTTPS_URL'
uv run scripts/apple.py zsign -m app.mobileprovision -o signed.ipa app.ipa
uv run scripts/iphone.py --pairing-record ~/.local/share/ios-installs/iphone.plist --host 100.116.148.84 signed.ipa
```

`apple.py` supplies credentials to the existing `zsign` and `asc` tools.
It uses the ThinkCentre's locked Nix packages when they are not on `PATH`.
The signer receives its key through an anonymous memory file, without password
arguments or saved key files.
The Mac and SideStore are not involved.

Credentials come from **Training Sensors Apple signing** and
**Training Sensors App Store Connect** in 1Password, through the shared
`~/.local/share/pyskills` secret helper. The host needs its existing 1Password Connect access.

Each app needs an explicit profile matching its bundle ID, signing certificate,
capabilities and registered devices. Download Finance's profile:

```sh
uv run scripts/apple.py asc profiles download --id ZLKWRD99GC --output app.mobileprovision
```

For other apps, use `asc bundle-ids` and `asc profiles` through the same wrapper.
Extensions need their own profiles; pass a separate `-m` for each profile.
Re-signing does not remove App Store encryption or grant another developer's capabilities.
Certificates and profiles expire; renew them before signing further updates.

Run the installer and signing tests:

```sh
uv run --with cryptography==50.0.2 --with onepasswordconnectsdk==2.1.0 --with pymobiledevice3==11.31.0 --with asn1crypto==1.5.1 python -m unittest discover -s scripts
```

## Update Spotify without losing Siri or data

Use a **patched EeveeSpotify IPA containing `IntentsExtension.appex`**.
A filename mentioning Siri or a Siri-enabled profile alone is insufficient.
The working source is the patched 6.6.7 / Spotify 9.1.68 build linked from the
[maintainer's release](https://github.com/SideloadLabs/EeveeSpotifyReincarnated/releases/tag/v6.6.7).

Keep the installed bundle ID and existing keychain/app groups.
Back up Documents, Library/Preferences, Library/Application Support and
Library/Cookies with `pymobiledevice3` House Arrest before each update.
Store backups privately outside this repository. Update in place; never uninstall.
Compare the saved files after installation; iOS may change the container path.

Sign the main app, Siri extension and Safari extension with their own profiles:

```sh
cd ~/Downloads/ios
uv run ~/Projects/ios-installs/scripts/apple.py zsign \
  -m Spotify-Siri.mobileprovision \
  -m Spotify-Intents.mobileprovision \
  -m OpenSpotifyExtension.mobileprovision \
  -b com.spotify.client.94F2Q36UHT -z 6 -o EeveeSpotify-Siri.ipa SOURCE.ipa
```

The local profiles correspond to Apple profile IDs `Z5VL5K2KLA`, `5ZSJLHJ92C`
and `ZUZN68R9YP`. Renew expired profiles with the same bundle IDs and capabilities.
Keep the prefix compatibility patch included in the patched build.
Additional extensions require their own profiles; do not remove the Siri extension.

`iphone.py` rejects Spotify packages with a changed bundle ID, missing playback
extension, or missing Siri permission in either profile, before connecting.
Open Spotify after updating, then test Siri playback. These preflight checks cannot
prove that future Spotify or iOS releases still work with Siri.

## Switch VPNs

Add [SideStore VPN](shortcuts/sidestore-vpn.shortcut) and
[Tailscale VPN](shortcuts/tailscale-vpn.shortcut) in Shortcuts on the iPhone.

In **Automation → App → SideStore**, run **SideStore VPN** when opened.
Set **Run Immediately**. Run **Tailscale VPN** after installs finish.
An **Is Closed** automation can restore Tailscale too, but switching away
during an install or self-refresh may interrupt it.

Generate the unsigned files with `uv run scripts/make-vpn-shortcuts.py`.
Sign each on macOS with `shortcuts sign --mode anyone --input NAME.unsigned.shortcut --output NAME.shortcut`.

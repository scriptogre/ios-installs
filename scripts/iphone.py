# /// script
# requires-python = ">=3.13"
# dependencies = ["pymobiledevice3==11.31.0", "asn1crypto==1.5.1"]
# ///
"""Inspect or install a signed IPA on a paired iPhone over Wi-Fi or Tailscale."""

import argparse
import asyncio
import datetime
import os
import pathlib
import plistlib
import re
import subprocess
import sys
import zipfile
from typing import Any

from asn1crypto import cms
from pymobiledevice3.bonjour import browse_remotepairing
from pymobiledevice3.exceptions import PyMobileDevice3Exception
from pymobiledevice3.remote.remote_service_discovery import (
    RemoteServiceDiscoveryService,
)
from pymobiledevice3.remote.tunnel_service import RemotePairingTunnelService
from pymobiledevice3.services.installation_proxy import InstallationProxyService


class PairedTunnel(RemotePairingTunnelService):
    def __init__(self, record: dict[str, Any], address: str, port: int) -> None:
        super().__init__(record["remote_identifier"], address, port)
        self.record = record

    @property
    def pair_record(self) -> dict[str, Any]:
        return self.record


def inspect_profile(archive: zipfile.ZipFile, path: str, udid: str) -> dict[str, Any]:
    signed = cms.ContentInfo.load(archive.read(path))
    profile = plistlib.loads(signed["content"]["encap_content_info"]["content"].native)
    if udid not in profile.get("ProvisionedDevices", []):
        raise ValueError("This IPA is not signed for this iPhone.")
    expiration = profile["ExpirationDate"].replace(tzinfo=datetime.UTC)
    if expiration <= datetime.datetime.now(datetime.UTC):
        raise ValueError("This IPA's provisioning profile has expired.")
    return profile


def inspect_package(path: pathlib.Path, udid: str) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        entries = [
            name
            for name in archive.namelist()
            if re.fullmatch(r"Payload/[^/]+\.app/Info\.plist", name)
        ]
        if len(entries) != 1:
            raise ValueError("Expected one iOS app in the IPA.")
        info = plistlib.loads(archive.read(entries[0]))
        profile_path = (
            entries[0].removesuffix("Info.plist") + "embedded.mobileprovision"
        )
        profile = inspect_profile(archive, profile_path, udid)
        if "SpotifyVersionShort" in info or info["CFBundleIdentifier"].startswith(
            "com.spotify.client"
        ):
            bundle = "com.spotify.client.94F2Q36UHT"
            if info["CFBundleIdentifier"] != bundle:
                raise ValueError(f"Keep Spotify's installed bundle ID: {bundle}")
            extension_path = (
                entries[0].removesuffix("Info.plist")
                + "PlugIns/IntentsExtension.appex/"
            )
            try:
                extension = plistlib.loads(archive.read(extension_path + "Info.plist"))
                extension_profile = inspect_profile(
                    archive, extension_path + "embedded.mobileprovision", udid
                )
                archive.getinfo(extension_path + extension["CFBundleExecutable"])
            except KeyError:
                raise ValueError(
                    "Spotify needs its signed Siri extension, not just Siri permission."
                ) from None
            if extension["CFBundleIdentifier"] != bundle + ".intents":
                raise ValueError("Keep Spotify's Siri extension bundle ID.")
            service = extension.get("NSExtension", {})
            intents = service.get("NSExtensionAttributes", {}).get(
                "IntentsSupported", []
            )
            if (
                service.get("NSExtensionPointIdentifier") != "com.apple.intents-service"
                or "INPlayMediaIntent" not in intents
            ):
                raise ValueError(
                    "Spotify's Siri extension must declare its playback intent."
                )
            if any(
                p["Entitlements"].get("com.apple.developer.siri") is not True
                for p in (profile, extension_profile)
            ):
                raise ValueError(
                    "Spotify and its extension both need Siri permission in their profiles."
                )
        return info


async def run(args: argparse.Namespace) -> None:
    record = plistlib.loads(args.pairing_record.read_bytes())
    info = inspect_package(args.ipa, record["remote_identifier"]) if args.ipa else None
    host, port = args.host, args.port
    if host is None:
        answers = await browse_remotepairing(timeout=3)
        answer = next(
            (
                answer
                for answer in answers
                if answer.host.rstrip(".").casefold()
                == record["hostname"].rstrip(".").casefold()
            ),
            None,
        )
        if answer is None or not answer.addresses:
            raise RuntimeError("iPhone not found. Keep it awake on the same Wi-Fi.")
        address = next(
            (a for a in answer.addresses if ":" not in a.ip), answer.addresses[0]
        )
        host, port = address.full_ip, answer.port
    service = PairedTunnel(record, host, port)
    try:
        await service.connect(autopair=False)
        async with (
            service.start_tcp_tunnel() as tunnel,
            RemoteServiceDiscoveryService((tunnel.address, tunnel.port)) as device,
            InstallationProxyService(device) as installer,
        ):
            if info is not None:
                bundle = info["CFBundleIdentifier"]
                print(f"Installing {bundle}…", flush=True)
                await installer.install_from_local(str(args.ipa))
                apps = await installer.get_apps()
                installed = apps.get(bundle)
                if installed is None or any(
                    installed.get(key) != info.get(key)
                    for key in ("CFBundleVersion", "CFBundleShortVersionString")
                ):
                    raise RuntimeError("Installed build could not be verified.")
                print(f"Installed {bundle}, build {info['CFBundleVersion']}.")
            else:
                apps = await installer.get_apps()
                print(f"Connected to {record['hostname']}. {len(apps)} apps visible.")
    finally:
        await service.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairing-record", type=pathlib.Path, required=True)
    parser.add_argument(
        "ipa", type=pathlib.Path, nargs="?", help="Omit to check connectivity."
    )
    parser.add_argument("--host", help="iPhone IP or hostname; skips local discovery.")
    parser.add_argument("--port", type=int, default=49152, help="Remote pairing port.")
    args = parser.parse_args()
    if os.geteuid() != 0:
        return subprocess.run(
            [
                "sudo",
                "-n",
                sys.executable,
                str(pathlib.Path(__file__).resolve()),
                *sys.argv[1:],
            ],
            check=False,
        ).returncode
    try:
        asyncio.run(asyncio.wait_for(run(args), timeout=180))
    except (
        PyMobileDevice3Exception,
        OSError,
        ValueError,
        KeyError,
        RuntimeError,
        zipfile.BadZipFile,
    ) as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

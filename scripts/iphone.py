# /// script
# requires-python = ">=3.13"
# dependencies = ["pymobiledevice3==11.31.0", "asn1crypto==1.5.1"]
# ///
"""Inspect or install a signed IPA on a paired iPhone over local Wi-Fi."""

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
        signed = cms.ContentInfo.load(archive.read(profile_path))
        profile = plistlib.loads(
            signed["content"]["encap_content_info"]["content"].native
        )
        if udid not in profile.get("ProvisionedDevices", []):
            raise ValueError("This IPA is not signed for this iPhone.")
        expiration = profile["ExpirationDate"].replace(tzinfo=datetime.UTC)
        if expiration <= datetime.datetime.now(datetime.UTC):
            raise ValueError("This IPA's provisioning profile has expired.")
        return info


async def run(args: argparse.Namespace) -> None:
    record = plistlib.loads(args.pairing_record.read_bytes())
    info = inspect_package(args.ipa, record["remote_identifier"]) if args.ipa else None
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
    service = PairedTunnel(record, address.full_ip, answer.port)
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
                if (
                    installed is None
                    or installed.get("CFBundleVersion") != info["CFBundleVersion"]
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

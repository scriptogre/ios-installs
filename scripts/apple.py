# /// script
# requires-python = ">=3.13"
# dependencies = ["cryptography==50.0.2", "onepasswordconnectsdk==2.1.0"]
# ///
"""Run asc or zsign on Linux with signing credentials from 1Password."""

import argparse
import base64
import ctypes
import os
import pathlib
import shutil
import subprocess
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12

sys.path.insert(0, str(pathlib.Path.home() / ".local/share/pyskills"))
from managing_secrets.skill import get_secret

VAULT = "wntgzcyr5x3bxict6nnuroeigu"
API_ITEM = "ff2skavbinjrazel6m6ojktxhm"
SIGNING_ITEM = "7lsltr7m3hpuwl3z22ip63445i"


def run(tool: str, arguments: list[str]) -> int:
    os.umask(0o077)
    executable = shutil.which(tool)
    if executable is None:
        flake = pathlib.Path.home() / "Projects/dotfiles/hosts/thinkcentre"
        package = "asccli" if tool == "asc" else "zsign"
        output = subprocess.check_output(
            [
                "nix",
                "build",
                f"{flake}#nixosConfigurations.thinkcentre.pkgs.{package}",
                "--no-link",
                "--print-out-paths",
            ],
            text=True,
        ).strip()
        executable = f"{output}/bin/{tool}"
    if tool == "asc":
        environment = os.environ.copy()
        for field in ("ASC_KEY_ID", "ASC_ISSUER_ID", "ASC_PRIVATE_KEY"):
            environment[field] = get_secret(API_ITEM, field, VAULT)
        environment.update(ASC_BYPASS_KEYCHAIN="1", ASC_TELEMETRY_DISABLED="1")
        return subprocess.run(
            [executable, *arguments], env=environment, check=False
        ).returncode

    identity = base64.b64decode(
        get_secret(SIGNING_ITEM, "APPLE_SIGNING_P12_BASE64", VAULT), validate=True
    )
    password = get_secret(SIGNING_ITEM, "APPLE_SIGNING_PASSWORD", VAULT).encode()
    key, certificate, chain = pkcs12.load_key_and_certificates(identity, password)
    if key is None or certificate is None:
        raise ValueError("The signing identity needs a private key and certificate.")
    # zsign accepts passwords only in argv. A memory-only P12 avoids exposing one.
    # Some uv Python builds omit os.memfd_create even though Linux provides it.
    descriptor_number = ctypes.CDLL(None, use_errno=True).memfd_create(
        b"apple-signing", 1
    )
    if descriptor_number < 0:
        raise OSError(ctypes.get_errno(), "Cannot create signing memory file")
    with os.fdopen(descriptor_number, "wb") as descriptor:
        descriptor.write(
            pkcs12.serialize_key_and_certificates(
                b"Signing", key, certificate, chain, serialization.NoEncryption()
            )
        )
        descriptor.flush()
        return subprocess.run(
            [executable, "-k", f"/proc/self/fd/{descriptor.fileno()}", *arguments],
            pass_fds=(descriptor.fileno(),),
            check=False,
        ).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tool", choices=("asc", "zsign"))
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    return run(args.tool, args.arguments)


if __name__ == "__main__":
    raise SystemExit(main())

"""Generate unsigned VPN shortcuts. Sign with `shortcuts sign` on macOS."""

import pathlib
import plistlib
from typing import Any


def make_intent(
    bundle: str, team: str, name: str, intent: str, **parameters: str
) -> dict[str, Any]:
    return {
        "WFWorkflowActionIdentifier": f"{bundle}.{intent}",
        "WFWorkflowActionParameters": {
            "AppIntentDescriptor": {
                "BundleIdentifier": bundle,
                "TeamIdentifier": team,
                "Name": name,
                "AppIntentIdentifier": intent,
            },
            **parameters,
        },
    }


output = pathlib.Path(__file__).resolve().parents[1] / "shortcuts"
output.mkdir(exist_ok=True)
for stem, name, operation, tailscale_intent in [
    ("sidestore-vpn", "SideStore VPN", "enable", "DisconnectIntent"),
    ("tailscale-vpn", "Tailscale VPN", "disable", "ConnectIntent"),
]:
    local = make_intent(
        "com.jkcoxson.LocalDevVPN",
        "42Q7QX86GV",
        "LocalDevVPN",
        "ControlLocalDevVPNIntent",
        operation=operation,
        intermediateAddressPolicy="appSetting",
    )
    tailscale = make_intent(
        "io.tailscale.ipn.ios", "W5364U7YZB", "Tailscale", tailscale_intent
    )
    actions = [tailscale, local] if operation == "enable" else [local, tailscale]
    shortcut = {
        "WFWorkflowName": name,
        "WFWorkflowClientVersion": "3036.0.4",
        "WFWorkflowMinimumClientVersion": 900,
        "WFWorkflowMinimumClientVersionString": "900",
        "WFWorkflowIcon": {
            "WFWorkflowIconStartColor": 4282601983,
            "WFWorkflowIconGlyphNumber": 59511,
        },
        "WFWorkflowTypes": [],
        "WFWorkflowInputContentItemClasses": [],
        "WFWorkflowActions": actions,
    }
    (output / f"{stem}.unsigned.shortcut").write_bytes(
        plistlib.dumps(shortcut, fmt=plistlib.FMT_BINARY)
    )

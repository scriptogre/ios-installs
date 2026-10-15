import copy
import datetime
import pathlib
import plistlib
import tempfile
import unittest
import zipfile

import iphone
from asn1crypto import cms


class SpotifyUpdateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = pathlib.Path(self.directory.name) / "app.ipa"
        self.bundle = "com.spotify.client.94F2Q36UHT"
        self.root = "Payload/Spotify.app/"
        self.extension = self.root + "PlugIns/IntentsExtension.appex/"
        self.profile = {
            "ProvisionedDevices": ["phone"],
            "ExpirationDate": datetime.datetime.now() + datetime.timedelta(days=1),
            "Entitlements": {"com.apple.developer.siri": True},
        }
        self.extension_profile = copy.deepcopy(self.profile)
        self.files = {
            self.root + "Info.plist": {
                "CFBundleIdentifier": self.bundle,
                "SpotifyVersionShort": "9.1.68",
            },
            self.extension + "Info.plist": {
                "CFBundleIdentifier": self.bundle + ".intents",
                "CFBundleExecutable": "IntentsExtension",
                "NSExtension": {
                    "NSExtensionPointIdentifier": "com.apple.intents-service",
                    "NSExtensionAttributes": {
                        "IntentsSupported": ["INPlayMediaIntent"]
                    },
                },
            },
        }

    def write_package(self, *, include_extension: bool = True) -> None:
        with zipfile.ZipFile(self.path, "w") as archive:
            for name, value in self.files.items():
                if include_extension or not name.startswith(self.extension):
                    archive.writestr(name, plistlib.dumps(value))
            for root in (
                [self.root, self.extension] if include_extension else [self.root]
            ):
                profile = cms.ContentInfo(
                    {
                        "content_type": "signed_data",
                        "content": {
                            "version": "v1",
                            "digest_algorithms": [],
                            "encap_content_info": {
                                "content_type": "data",
                                "content": plistlib.dumps(
                                    self.profile
                                    if root == self.root
                                    else self.extension_profile
                                ),
                            },
                            "signer_infos": [],
                        },
                    }
                )
                archive.writestr(root + "embedded.mobileprovision", profile.dump())
            if include_extension:
                archive.writestr(
                    self.extension + "IntentsExtension", b"test executable"
                )

    def test_accept_siri_build(self) -> None:
        self.write_package()
        self.assertEqual(
            iphone.inspect_package(self.path, "phone")["CFBundleIdentifier"],
            self.bundle,
        )

    def test_reject_missing_siri_extension(self) -> None:
        self.write_package(include_extension=False)
        with self.assertRaisesRegex(ValueError, "Siri extension"):
            iphone.inspect_package(self.path, "phone")

    def test_reject_changed_app_identity(self) -> None:
        self.files[self.root + "Info.plist"]["CFBundleIdentifier"] = (
            "com.spotify.client"
        )
        self.write_package()
        with self.assertRaisesRegex(ValueError, "bundle ID"):
            iphone.inspect_package(self.path, "phone")

    def test_reject_missing_siri_permission(self) -> None:
        self.profile["Entitlements"] = {}
        self.write_package()
        with self.assertRaisesRegex(ValueError, "Siri permission"):
            iphone.inspect_package(self.path, "phone")

    def test_reject_missing_playback_intent(self) -> None:
        self.files[self.extension + "Info.plist"]["NSExtension"][
            "NSExtensionAttributes"
        ]["IntentsSupported"] = []
        self.write_package()
        with self.assertRaisesRegex(ValueError, "playback intent"):
            iphone.inspect_package(self.path, "phone")

    def test_reject_extension_profile_without_siri(self) -> None:
        self.extension_profile["Entitlements"] = {}
        self.write_package()
        with self.assertRaisesRegex(ValueError, "Siri permission"):
            iphone.inspect_package(self.path, "phone")

    def test_reject_expired_extension_profile(self) -> None:
        self.extension_profile["ExpirationDate"] = (
            datetime.datetime.now() - datetime.timedelta(days=1)
        )
        self.write_package()
        with self.assertRaisesRegex(ValueError, "expired"):
            iphone.inspect_package(self.path, "phone")

    def test_reject_extension_for_another_phone(self) -> None:
        self.extension_profile["ProvisionedDevices"] = ["another-phone"]
        self.write_package()
        with self.assertRaisesRegex(ValueError, "not signed for this iPhone"):
            iphone.inspect_package(self.path, "phone")

    def test_reject_renamed_spotify(self) -> None:
        self.files[self.root + "Info.plist"]["CFBundleIdentifier"] = "com.example.music"
        self.write_package()
        with self.assertRaisesRegex(ValueError, "bundle ID"):
            iphone.inspect_package(self.path, "phone")

    def test_allow_other_apps_without_siri(self) -> None:
        self.files[self.root + "Info.plist"] = {
            "CFBundleIdentifier": "com.example.finance"
        }
        self.profile["Entitlements"] = {}
        self.write_package(include_extension=False)
        self.assertEqual(
            iphone.inspect_package(self.path, "phone")["CFBundleIdentifier"],
            "com.example.finance",
        )

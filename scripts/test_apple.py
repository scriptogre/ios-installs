import base64
import datetime
import os
import pathlib
import subprocess
import unittest
from unittest import mock

import apple
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID


class SigningTests(unittest.TestCase):
    @mock.patch("apple.shutil.which", return_value="/bin/asc")
    @mock.patch("apple.get_secret", side_effect=lambda item, field, vault: field)
    @mock.patch("apple.subprocess.run")
    def test_pass_api_credentials_in_environment(
        self, execute: mock.Mock, secret: mock.Mock, which: mock.Mock
    ) -> None:
        execute.return_value.returncode = 7
        self.assertEqual(apple.run("asc", ["profiles", "list"]), 7)
        arguments, keywords = execute.call_args
        self.assertEqual(arguments[0], ["/bin/asc", "profiles", "list"])
        self.assertEqual(keywords["env"]["ASC_PRIVATE_KEY"], "ASC_PRIVATE_KEY")
        self.assertEqual(keywords["env"]["ASC_TELEMETRY_DISABLED"], "1")

    @mock.patch("apple.shutil.which", return_value="/bin/zsign")
    def test_pass_signing_key_only_in_memory(self, which: mock.Mock) -> None:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test")])
        now = datetime.datetime.now(datetime.UTC)
        certificate = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(1)
            .not_valid_before(now)
            .not_valid_after(now + datetime.timedelta(days=1))
            .sign(key, hashes.SHA256())
        )
        identity = pkcs12.serialize_key_and_certificates(
            b"test",
            key,
            certificate,
            None,
            serialization.BestAvailableEncryption(b"test-password"),
        )
        descriptor_paths: list[str] = []

        def inspect_signer(
            arguments: list[str], *, pass_fds: tuple[int, ...], check: bool
        ) -> subprocess.CompletedProcess:
            self.assertEqual(arguments[:2], ["/bin/zsign", "-k"])
            self.assertEqual(arguments[3:], ["-m", "profile", "app.ipa"])
            descriptor_paths.append(arguments[2])
            data = pathlib.Path(arguments[2]).read_bytes()
            restored_key, restored_cert, _ = pkcs12.load_key_and_certificates(
                data, None
            )
            self.assertIsNotNone(restored_key)
            self.assertEqual(restored_cert, certificate)
            self.assertEqual(pass_fds, (int(arguments[2].rsplit("/", 1)[1]),))
            return subprocess.CompletedProcess(arguments, 0)

        with (
            mock.patch(
                "apple.get_secret",
                side_effect=[base64.b64encode(identity).decode(), "test-password"],
            ),
            mock.patch("apple.subprocess.run", side_effect=inspect_signer),
        ):
            self.assertEqual(apple.run("zsign", ["-m", "profile", "app.ipa"]), 0)
        self.assertFalse(os.path.exists(descriptor_paths[0]))


if __name__ == "__main__":
    unittest.main()

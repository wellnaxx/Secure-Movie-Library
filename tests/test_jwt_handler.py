import os
import unittest
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Literal
from unittest.mock import patch

from jose import jwt

from auth.jwt_handler import (
    ALGORITHM,
    JWTPayload,
    UserTokenData,
    create_access_token,
    create_refresh_token,
    create_token,
    decode_token,
)
from config.jwt import JWTConfig, set_jwt_config

if TYPE_CHECKING:
    from collections.abc import Callable


class JWTHandlerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.secret = "test-secret-for-jwt-validation-at-least-32-characters"
        config_patch = patch("auth.jwt_handler.get_jwt_config", return_value=JWTConfig(secret_key=self.secret))
        config_patch.start()
        self.addCleanup(config_patch.stop)
        self.user: UserTokenData = {
            "user_id": 1,
            "username": "testuser",
            "role": "USER",
            "token_version": 0,
        }
        now = datetime.now(UTC)
        self.payload: JWTPayload = {
            "sub": "1",
            "iat": now,
            "exp": now + timedelta(minutes=30),
            "jti": "test-token-id",
            "type": "access",
            "username": "testuser",
            "role": "USER",
            "token_version": 0,
        }

    def test_access_and_refresh_tokens_round_trip(self) -> None:
        access = create_access_token(self.user)
        refresh = create_refresh_token(self.user)
        cases: list[tuple[str, Literal["access", "refresh"]]] = [(access, "access"), (refresh, "refresh")]
        for token, expected_type in cases:
            with self.subTest(expected_type=expected_type):
                payload = decode_token(token, expected_type=expected_type)
                self.assertIsNotNone(payload)
                if payload is None:
                    self.fail("Valid token should decode")
                self.assertEqual(payload["sub"], "1")
                self.assertEqual(payload["token_version"], 0)
                self.assertEqual(payload["type"], expected_type)
                self.assertIsInstance(payload["iat"], int)
                self.assertIsInstance(payload["exp"], int)
        self.assertIsNone(decode_token(refresh))
        self.assertIsNone(decode_token(access, expected_type="refresh"))

    def test_missing_required_claims_are_rejected(self) -> None:
        for missing in self.payload:
            incomplete: dict[str, object] = {
                key: value for key, value in self.payload.items() if key != missing
            }
            token = jwt.encode(incomplete, self.secret, algorithm=ALGORITHM)
            with self.subTest(missing=missing):
                self.assertIsNone(decode_token(token))

    def test_incorrect_claim_types_are_rejected_without_coercion(self) -> None:
        cases: list[dict[str, object]] = [
            {**self.payload, "token_version": "0"},
            {**self.payload, "role": "SUPERUSER"},
            {**self.payload, "username": 123},
        ]
        for malformed in cases:
            with self.subTest(malformed=malformed):
                token = jwt.encode(malformed, self.secret, algorithm=ALGORITHM)
                self.assertIsNone(decode_token(token))

    def test_expired_invalid_signature_and_malformed_tokens_are_rejected(self) -> None:
        expired: JWTPayload = {**self.payload, "exp": datetime.now(UTC) - timedelta(minutes=1)}
        tokens = [
            jwt.encode(dict(expired), self.secret, algorithm=ALGORITHM),
            jwt.encode(dict(self.payload), "a-different-secret", algorithm=ALGORITHM),
            "invalid-token",
        ]
        for token in tokens:
            with self.subTest(token=token):
                self.assertIsNone(decode_token(token))

    def test_admin_claims_and_unique_token_ids(self) -> None:
        admin: UserTokenData = {**self.user, "role": "ADMIN", "token_version": 4}
        first = decode_token(create_access_token(admin))
        second = decode_token(create_access_token(admin))
        if first is None or second is None:
            self.fail("Valid ADMIN tokens should decode")
        self.assertEqual(first["role"], "ADMIN")
        self.assertEqual(first["username"], admin["username"])
        self.assertEqual(first["token_version"], 4)
        self.assertNotEqual(first["jti"], second["jti"])

    def test_creation_rejects_missing_and_empty_identity_fields(self) -> None:
        # Deliberately bypass the static input contract to test runtime guards.
        create_unchecked: Callable[..., str] = create_token
        for field, empty in (("user_id", 0), ("username", ""), ("role", "")):
            cases: list[dict[str, object]] = [
                {key: value for key, value in self.user.items() if key != field},
                {**self.user, field: empty},
            ]
            for data in cases:
                with self.subTest(field=field, data=data), self.assertRaisesRegex(ValueError, field):
                    create_unchecked(data)

    def test_creation_rejects_missing_token_version(self) -> None:
        create_unchecked: Callable[..., str] = create_token
        incomplete = {key: value for key, value in self.user.items() if key != "token_version"}
        with self.assertRaisesRegex(KeyError, "token_version"):
            create_unchecked(incomplete)

    def test_unexpected_signing_algorithm_is_rejected(self) -> None:
        token = jwt.encode(dict(self.payload), self.secret, algorithm="HS384")
        self.assertIsNone(decode_token(token))

    def test_expiration_boundary_at_second_precision(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=UTC)
        for offset, accepted in ((1, True), (0, True), (-1, False)):
            payload: JWTPayload = {**self.payload, "exp": now + timedelta(seconds=offset)}
            token = jwt.encode(dict(payload), self.secret, algorithm=ALGORITHM)
            with self.subTest(offset=offset), patch("jose.jwt.datetime") as clock:
                clock.now.return_value = now
                # python-jose accepts equality; a token expires the following second.
                self.assertEqual(decode_token(token) is not None, accepted)


class JWTConfigurationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.secret = "s" * 32
        self.user: UserTokenData = {
            "user_id": 1,
            "username": "testuser",
            "role": "USER",
            "token_version": 0,
        }
        patches = [
            patch.dict(os.environ, {"JWT_SECRET_KEY": self.secret}, clear=True),
            patch("config.jwt.load_dotenv"),
        ]
        set_jwt_config(None)
        self.addCleanup(set_jwt_config, None)
        for context in patches:
            context.start()
            self.addCleanup(context.stop)

    def test_minimum_length_secret_and_default_lifetimes(self) -> None:
        access = jwt.decode(create_access_token(self.user), self.secret, algorithms=[ALGORITHM])
        refresh = jwt.decode(create_refresh_token(self.user), self.secret, algorithms=[ALGORITHM])
        self.assertEqual(access["exp"] - access["iat"], 30 * 60)
        self.assertEqual(refresh["exp"] - refresh["iat"], 7 * 24 * 60 * 60)

    def test_custom_lifetimes_and_settings_are_cached(self) -> None:
        with patch.dict(os.environ, {"JWT_EXPIRATION_MINUTES": "12", "JWT_REFRESH_EXPIRATION_DAYS": "2"}):
            first_access = create_access_token(self.user)
            first_refresh = create_refresh_token(self.user)
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": "changed-secret-that-must-not-replace-cache",
                "JWT_EXPIRATION_MINUTES": "99",
                "JWT_REFRESH_EXPIRATION_DAYS": "99",
            },
        ):
            second_access = create_access_token(self.user)
            second_refresh = create_refresh_token(self.user)
        for token in (first_access, second_access):
            payload = jwt.decode(token, self.secret, algorithms=[ALGORITHM])
            self.assertEqual(payload["exp"] - payload["iat"], 12 * 60)
        for token in (first_refresh, second_refresh):
            payload = jwt.decode(token, self.secret, algorithms=[ALGORITHM])
            self.assertEqual(payload["exp"] - payload["iat"], 2 * 24 * 60 * 60)

    def test_short_secret_is_rejected_without_caching(self) -> None:
        for length in (0, 31):
            with (
                self.subTest(length=length),
                patch.dict(os.environ, {"JWT_SECRET_KEY": "s" * length}),
                self.assertRaisesRegex(RuntimeError, "at least 32"),
            ):
                create_access_token(self.user)
        self.assertIsNotNone(decode_token(create_access_token(self.user)))

    def test_missing_secret_is_reported(self) -> None:
        with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(OSError, "JWT_SECRET_KEY"):
            create_access_token(self.user)

    def test_nonnumeric_expiration_settings_are_rejected(self) -> None:
        cases: list[tuple[str, Callable[[UserTokenData], str]]] = [
            ("JWT_EXPIRATION_MINUTES", create_access_token),
            ("JWT_REFRESH_EXPIRATION_DAYS", create_refresh_token),
        ]
        for setting, create in cases:
            set_jwt_config(None)
            for value in ("", "invalid", "1.5"):
                with (
                    self.subTest(setting=setting, value=value),
                    patch.dict(os.environ, {setting: value}),
                    self.assertRaises(ValueError),
                ):
                    create(self.user)
            self.assertIsInstance(create(self.user), str)

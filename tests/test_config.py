"""Configuration validation, environment loading, and cache lifecycle tests."""

import os
import unittest
from dataclasses import FrozenInstanceError, replace
from typing import TYPE_CHECKING
from unittest.mock import patch

from config.database import DBConfig, get_db_config, load_db_config, set_db_config
from config.jwt import JWTConfig, get_jwt_config, load_jwt_config, set_jwt_config
from config.omdb import OMDbConfig, get_omdb_config, load_omdb_config, set_omdb_config

if TYPE_CHECKING:
    from collections.abc import Callable


class ConfigurationTests(unittest.TestCase):
    """Validate immutable settings and independent environment-backed cache lifecycles."""

    def setUp(self) -> None:
        """Isolate required environment values, disable dotenv reads, and reset caches."""
        environment = patch.dict(
            os.environ,
            {
                "DB_HOST": "localhost",
                "DB_NAME": "movies",
                "DB_USER": "user",
                "DB_PASSWORD": "db-secret",
                "JWT_SECRET_KEY": "j" * 32,
                "OMDB_API_KEY": "omdb-secret",
            },
            clear=True,
        )
        environment.start()
        self.addCleanup(environment.stop)
        for module in ("database", "jwt", "omdb"):
            dotenv_patch = patch(f"config.{module}.load_dotenv")
            dotenv_patch.start()
            self.addCleanup(dotenv_patch.stop)
        set_db_config(None)
        set_jwt_config(None)
        set_omdb_config(None)
        self.addCleanup(set_db_config, None)
        self.addCleanup(set_jwt_config, None)
        self.addCleanup(set_omdb_config, None)

    def test_defaults_preserve_existing_environment_contract(self) -> None:
        db = load_db_config()
        self.assertEqual((db.host, db.name, db.user, db.password), ("localhost", "movies", "user", "db-secret"))
        self.assertEqual((db.port, db.connect_timeout), (3306, 5))
        jwt = load_jwt_config()
        self.assertEqual(jwt.secret_key, "j" * 32)
        self.assertEqual((jwt.access_token_expire_minutes, jwt.refresh_token_expire_days), (30, 7))
        omdb = load_omdb_config()
        self.assertEqual(omdb.api_key, "omdb-secret")
        self.assertEqual((omdb.base_url, omdb.timeout_seconds), ("https://www.omdbapi.com/", 10.0))

    def test_custom_environment_values_are_parsed(self) -> None:
        with patch.dict(
            os.environ,
            {
                "DB_PORT": "3307",
                "DB_CONNECT_TIMEOUT": "12",
                "JWT_EXPIRATION_MINUTES": "15",
                "JWT_REFRESH_EXPIRATION_DAYS": "2",
                "OMDB_BASE_URL": "http://localhost:8080/api",
                "OMDB_TIMEOUT_SECONDS": "2.5",
            },
        ):
            db, jwt, omdb = load_db_config(), load_jwt_config(), load_omdb_config()
        self.assertEqual((db.port, db.connect_timeout), (3307, 12))
        self.assertEqual((jwt.access_token_expire_minutes, jwt.refresh_token_expire_days), (15, 2))
        self.assertEqual((omdb.base_url, omdb.timeout_seconds), ("http://localhost:8080/api", 2.5))

    def test_required_environment_values_are_reported_by_name(self) -> None:
        cases: list[tuple[str, Callable[[], object]]] = [
            ("DB_HOST", load_db_config),
            ("DB_NAME", load_db_config),
            ("DB_USER", load_db_config),
            ("DB_PASSWORD", load_db_config),
            ("JWT_SECRET_KEY", load_jwt_config),
            ("OMDB_API_KEY", load_omdb_config),
        ]
        for setting, load in cases:
            with self.subTest(setting=setting), patch.dict(os.environ):
                del os.environ[setting]
                with self.assertRaisesRegex(OSError, setting):
                    load()

    def test_blank_required_text_is_rejected(self) -> None:
        cases: list[tuple[str, Callable[[], object]]] = [
            ("DB_HOST", load_db_config),
            ("DB_NAME", load_db_config),
            ("DB_USER", load_db_config),
            ("OMDB_API_KEY", load_omdb_config),
        ]
        for setting, load in cases:
            for value in ("", "   "):
                with (
                    self.subTest(setting=setting, value=value),
                    patch.dict(os.environ, {setting: value}),
                    self.assertRaisesRegex(ValueError, setting),
                ):
                    load()

    def test_empty_database_password_remains_supported(self) -> None:
        with patch.dict(os.environ, {"DB_PASSWORD": ""}):
            self.assertEqual(load_db_config().password, "")

    def test_database_port_boundaries(self) -> None:
        for port in (1, 65535):
            with self.subTest(port=port), patch.dict(os.environ, {"DB_PORT": str(port)}):
                self.assertEqual(load_db_config().port, port)
        for port in (0, -1, 65536):
            with (
                self.subTest(port=port),
                patch.dict(os.environ, {"DB_PORT": str(port)}),
                self.assertRaisesRegex(ValueError, "DB_PORT"),
            ):
                load_db_config()

    def test_integer_settings_reject_nonnumeric_values(self) -> None:
        cases: list[tuple[str, Callable[[], object]]] = [
            ("DB_PORT", load_db_config),
            ("DB_CONNECT_TIMEOUT", load_db_config),
            ("JWT_EXPIRATION_MINUTES", load_jwt_config),
            ("JWT_REFRESH_EXPIRATION_DAYS", load_jwt_config),
        ]
        for setting, load in cases:
            for value in ("", "invalid", "1.5"):
                with (
                    self.subTest(setting=setting, value=value),
                    patch.dict(os.environ, {setting: value}),
                    self.assertRaisesRegex(ValueError, setting),
                ):
                    load()

    def test_durations_must_be_positive(self) -> None:
        cases: list[tuple[str, Callable[[], object]]] = [
            ("DB_CONNECT_TIMEOUT", load_db_config),
            ("JWT_EXPIRATION_MINUTES", load_jwt_config),
            ("JWT_REFRESH_EXPIRATION_DAYS", load_jwt_config),
            ("OMDB_TIMEOUT_SECONDS", load_omdb_config),
        ]
        for setting, load in cases:
            for value in ("0", "-1"):
                with (
                    self.subTest(setting=setting, value=value),
                    patch.dict(os.environ, {setting: value}),
                    self.assertRaisesRegex(ValueError, setting),
                ):
                    load()

    def test_short_and_whitespace_signing_secrets_are_rejected(self) -> None:
        for secret in ("", "j" * 31, " " * 32, " " + "j" * 30 + " "):
            with (
                self.subTest(length=len(secret)),
                patch.dict(os.environ, {"JWT_SECRET_KEY": secret}),
                self.assertRaisesRegex(RuntimeError, "JWT_SECRET_KEY"),
            ):
                load_jwt_config()
        self.assertEqual(load_jwt_config().secret_key, "j" * 32)

    def test_omdb_timeout_rejects_invalid_and_nonfinite_values(self) -> None:
        for value in ("", "invalid", "nan", "inf", "-inf"):
            with (
                self.subTest(value=value),
                patch.dict(os.environ, {"OMDB_TIMEOUT_SECONDS": value}),
                self.assertRaisesRegex(ValueError, "OMDB_TIMEOUT_SECONDS"),
            ):
                load_omdb_config()

    def test_omdb_url_requires_absolute_http_or_https(self) -> None:
        for value in ("", "/relative", "ftp://example.com", "https://", "not-a-url"):
            with (
                self.subTest(value=value),
                patch.dict(os.environ, {"OMDB_BASE_URL": value}),
                self.assertRaisesRegex(ValueError, "OMDB_BASE_URL"),
            ):
                load_omdb_config()

    def test_configuration_objects_are_immutable_and_hide_secrets(self) -> None:
        for config, attribute, secret in (
            (load_db_config(), "password", "db-secret"),
            (load_jwt_config(), "secret_key", "j" * 32),
            (load_omdb_config(), "api_key", "omdb-secret"),
        ):
            with self.subTest(config=type(config).__name__):
                self.assertNotIn(secret, repr(config))
                with self.assertRaises(FrozenInstanceError):
                    setattr(config, attribute, "replacement")

    def test_direct_construction_is_validated(self) -> None:
        constructors: list[Callable[[], object]] = [
            lambda: DBConfig("", "movies", "user", "secret"),
            lambda: DBConfig("localhost", "movies", "user", "secret", port=65536),
            lambda: JWTConfig(secret_key="short"),
            lambda: JWTConfig(secret_key="j" * 32, access_token_expire_minutes=0),
            lambda: OMDbConfig(api_key=""),
            lambda: OMDbConfig(api_key="key", timeout_seconds=float("nan")),
        ]
        for construct in constructors:
            with self.subTest(construct=construct), self.assertRaises((ValueError, RuntimeError)):
                construct()

    def test_database_cache_override_and_reset(self) -> None:
        first = get_db_config()
        with patch.dict(os.environ, {"DB_HOST": "changed"}):
            self.assertIs(get_db_config(), first)
            self.assertEqual(load_db_config().host, "changed")
            override = replace(first, host="override")
            set_db_config(override)
            self.assertIs(get_db_config(), override)
            set_db_config(None)
            self.assertEqual(get_db_config().host, "changed")

    def test_jwt_cache_override_and_reset(self) -> None:
        first = get_jwt_config()
        with patch.dict(os.environ, {"JWT_EXPIRATION_MINUTES": "12"}):
            self.assertIs(get_jwt_config(), first)
            self.assertEqual(load_jwt_config().access_token_expire_minutes, 12)
            override = replace(first, access_token_expire_minutes=15)
            set_jwt_config(override)
            self.assertIs(get_jwt_config(), override)
            set_jwt_config(None)
            self.assertEqual(get_jwt_config().access_token_expire_minutes, 12)

    def test_omdb_cache_override_and_reset(self) -> None:
        first = get_omdb_config()
        with patch.dict(os.environ, {"OMDB_TIMEOUT_SECONDS": "2.5"}):
            self.assertIs(get_omdb_config(), first)
            self.assertEqual(load_omdb_config().timeout_seconds, 2.5)
            override = replace(first, timeout_seconds=5.0)
            set_omdb_config(override)
            self.assertIs(get_omdb_config(), override)
            set_omdb_config(None)
            self.assertEqual(get_omdb_config().timeout_seconds, 2.5)

    def test_failed_loads_are_not_cached(self) -> None:
        cases: list[tuple[str, str, Callable[[], object]]] = [
            ("DB_PORT", "invalid", get_db_config),
            ("JWT_SECRET_KEY", "short", get_jwt_config),
            ("OMDB_API_KEY", "", get_omdb_config),
        ]
        for setting, invalid, get in cases:
            with self.subTest(setting=setting):
                with patch.dict(os.environ, {setting: invalid}), self.assertRaises((ValueError, RuntimeError)):
                    get()
                self.assertIsNotNone(get())

    def test_each_component_loads_without_unrelated_settings(self) -> None:
        with patch.dict(os.environ, {"JWT_SECRET_KEY": "j" * 32}, clear=True):
            self.assertEqual(load_jwt_config().access_token_expire_minutes, 30)
        with patch.dict(os.environ, {"OMDB_API_KEY": "key"}, clear=True):
            self.assertEqual(load_omdb_config().timeout_seconds, 10.0)
        with patch.dict(
            os.environ,
            {
                "DB_HOST": "localhost",
                "DB_NAME": "movies",
                "DB_USER": "user",
                "DB_PASSWORD": "",
            },
            clear=True,
        ):
            self.assertEqual(load_db_config().port, 3306)

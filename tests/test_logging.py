"""Logging configuration validation, output handlers, and cache behavior."""

import io
import logging
import os
import unittest
from dataclasses import FrozenInstanceError
from logging.handlers import RotatingFileHandler
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from config.logging import LoggingConfig, get_logging_config, load_logging_config, set_logging_config
from utils.logging_config import configure_logging


class LoggingConfigurationTests(unittest.TestCase):
    """Validate logging settings without reading the developer environment."""

    def setUp(self) -> None:
        """Disable dotenv reads, clear environment settings, and reset the logging cache."""
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        dotenv = patch("config.logging.load_dotenv")
        dotenv.start()
        self.addCleanup(dotenv.stop)
        set_logging_config(None)
        self.addCleanup(set_logging_config, None)

    def test_default_configuration(self) -> None:
        self.assertEqual(load_logging_config(), LoggingConfig(level=logging.INFO, log_file=None))

    def test_level_names_are_case_insensitive_and_whitespace_is_trimmed(self) -> None:
        for name, level in (
            ("critical", logging.CRITICAL),
            ("error", logging.ERROR),
            ("warning", logging.WARNING),
            (" info ", logging.INFO),
            (" DeBuG ", logging.DEBUG),
            ("notset", logging.NOTSET),
        ):
            with self.subTest(name=name), patch.dict(os.environ, {"LOG_LEVEL": name}):
                self.assertEqual(load_logging_config().level, level)

    def test_invalid_level_names_are_reported(self) -> None:
        for name in ("", "invalid", "10"):
            with (
                self.subTest(name=name),
                patch.dict(os.environ, {"LOG_LEVEL": name}),
                self.assertRaisesRegex(ValueError, "LOG_LEVEL"),
            ):
                load_logging_config()

    def test_empty_or_blank_file_path_disables_file_logging(self) -> None:
        for path in ("", "  "):
            with self.subTest(path=path), patch.dict(os.environ, {"LOG_FILE": path}):
                self.assertIsNone(load_logging_config().log_file)

    def test_file_path_is_loaded(self) -> None:
        with patch.dict(os.environ, {"LOG_FILE": " logs/application.log "}):
            self.assertEqual(load_logging_config().log_file, Path("logs/application.log"))

    def test_direct_construction_is_validated_and_immutable(self) -> None:
        with self.assertRaisesRegex(ValueError, "LOG_LEVEL"):
            LoggingConfig(level=123)
        config = LoggingConfig()
        attribute = "level"
        with self.assertRaises(FrozenInstanceError):
            setattr(config, attribute, logging.DEBUG)

    def test_cache_can_be_overridden_and_reset(self) -> None:
        first = get_logging_config()
        with patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}):
            self.assertIs(get_logging_config(), first)
            self.assertEqual(load_logging_config().level, logging.DEBUG)
            override = LoggingConfig(level=logging.ERROR)
            set_logging_config(override)
            self.assertIs(get_logging_config(), override)
            set_logging_config(None)
            self.assertEqual(get_logging_config().level, logging.DEBUG)

    def test_failed_load_is_not_cached(self) -> None:
        with patch.dict(os.environ, {"LOG_LEVEL": "invalid"}), self.assertRaises(ValueError):
            get_logging_config()
        self.assertEqual(get_logging_config().level, logging.INFO)


class LoggingOutputTests(unittest.TestCase):
    """Capture configured handlers and restore global logging after each scenario."""

    def setUp(self) -> None:
        """Capture stdout while preserving root handlers and library logger levels for cleanup."""
        self.root = logging.getLogger()
        self.original_handlers = self.root.handlers[:]
        self.original_level = self.root.level
        self.root.handlers = []
        self.logger_levels = {
            name: logging.getLogger(name).level
            for name in (
                "uvicorn.access",
                "uvicorn.error",
                "httpx",
                "httpcore",
                "multipart",
                "python_multipart",
            )
        }
        self.addCleanup(self.restore_logging)
        self.output = io.StringIO()
        stdout = patch("utils.logging_config.sys.stdout", self.output)
        stdout.start()
        self.addCleanup(stdout.stop)

    def restore_logging(self) -> None:
        """Close test handlers and restore saved root handlers, severity, and library levels."""
        for handler in self.root.handlers:
            handler.close()
        self.root.handlers = self.original_handlers
        self.root.setLevel(self.original_level)
        for name, level in self.logger_levels.items():
            logging.getLogger(name).setLevel(level)

    def test_stdout_formatting_and_level_filtering(self) -> None:
        configure_logging(LoggingConfig(level=logging.INFO))
        logger = logging.getLogger("application-test")
        logger.debug("filtered debug")
        logger.info("Application ready")
        output = self.output.getvalue()
        self.assertRegex(output, r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \| INFO")
        self.assertIn("application-test | Application ready", output)
        self.assertNotIn("filtered debug", output)

    def test_configuration_is_loaded_when_not_supplied(self) -> None:
        with patch(
            "utils.logging_config.get_logging_config", return_value=LoggingConfig(level=logging.DEBUG)
        ) as get:
            configure_logging()
        self.assertEqual(self.root.level, logging.DEBUG)
        get.assert_called_once_with()

    def test_reconfiguration_closes_old_handlers_and_avoids_duplicate_records(self) -> None:
        configure_logging(LoggingConfig())
        previous = self.root.handlers[0]
        with patch.object(previous, "close", wraps=previous.close) as close:
            configure_logging(LoggingConfig())
        close.assert_called_once_with()
        self.assertEqual(len(self.root.handlers), 1)
        logging.getLogger("application-test").info("One record")
        self.assertEqual(self.output.getvalue().count("One record"), 1)

    def test_access_and_http_client_noise_is_suppressed_without_hiding_server_errors(self) -> None:
        logging.getLogger("uvicorn.error").setLevel(logging.INFO)
        configure_logging(LoggingConfig(level=logging.DEBUG))
        for name in ("uvicorn.access", "httpx", "httpcore", "multipart", "python_multipart"):
            self.assertEqual(logging.getLogger(name).level, logging.WARNING)
        self.assertEqual(logging.getLogger("uvicorn.error").level, logging.INFO)
        logging.getLogger("httpx").info("https://example.com/?apikey=secret")
        self.assertNotIn("apikey", self.output.getvalue())

    def test_rotating_file_output_creates_parent_directories_and_writes_utf8(self) -> None:
        with TemporaryDirectory(prefix="movie_logging_") as directory:
            path = Path(directory) / "nested" / "application.log"
            try:
                configure_logging(LoggingConfig(log_file=path))
                file_handlers = [
                    handler for handler in self.root.handlers if isinstance(handler, RotatingFileHandler)
                ]
                self.assertEqual(len(file_handlers), 1)
                handler = file_handlers[0]
                self.assertEqual(handler.maxBytes, 10 * 1024 * 1024)
                self.assertEqual(handler.backupCount, 5)
                logging.getLogger("application-test").info("caf\u00e9")
                self.assertIn("caf\u00e9", path.read_text(encoding="utf-8"))
                # Exercise real rollover using a small limit rather than a 10 MiB fixture.
                handler.maxBytes = 1
                logging.getLogger("application-test").info("After rollover")
                self.assertTrue(Path(str(path) + ".1").exists())
                self.assertIn("After rollover", path.read_text(encoding="utf-8"))
            finally:
                for handler in self.root.handlers:
                    handler.close()
                self.root.handlers = []

    def test_unwritable_file_destination_fails_before_replacing_handlers(self) -> None:
        configure_logging(LoggingConfig())
        handlers = self.root.handlers[:]
        with (
            patch("pathlib.Path.mkdir", side_effect=PermissionError("unwritable directory")),
            self.assertRaises(PermissionError),
        ):
            configure_logging(LoggingConfig(log_file=Path("unwritable/application.log")))
        self.assertEqual(self.root.handlers, handlers)

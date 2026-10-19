import unittest
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, patch

from data.models import UserInternal
from services.user_service import (
    authenticate_user,
    change_password,
    refresh_token_pair,
    register_user,
    update_user_role,
)
from utils.errors import (
    DatabaseError,
    DuplicateKeyError,
    IncorrectOldPasswordError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    UserCreationError,
    UsernameAlreadyExistsError,
    UserNotFoundError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _user_dict(**overrides: Any) -> dict[str, Any]:
    base = {
        "id": 1,
        "username": "johndoe",
        "password_hash": "hashed_secret",
        "role": "USER",
        "token_version": 0,
        "created_at": datetime(2024, 1, 1),
    }
    base.update(overrides)
    return base


def _internal_user(**overrides: Any) -> UserInternal:
    from data.models import UserInternal

    return UserInternal(**_user_dict(**overrides))


def _refresh_payload(**overrides: Any) -> dict[str, Any]:
    base = {
        "sub": "1",
        "type": "refresh",
        "token_version": 0,
        "username": "johndoe",
        "role": "USER",
    }
    base.update(overrides)
    return base


class TestRegisterUser(unittest.TestCase):
    def test_concurrent_duplicate_insert_is_translated_to_username_conflict(self) -> None:
        from data.models import UserCreate

        error = DuplicateKeyError("unique key conflict")
        with (
            patch("services.user_service.get_user_by_username", return_value=None),
            patch("services.user_service.hash_password", return_value="stored-hash"),
            patch("services.user_service.create_user", side_effect=error),
            patch("services.user_service.get_user_by_id") as reload_user,
            self.assertRaises(UsernameAlreadyExistsError) as caught,
        ):
            register_user(UserCreate(username="testuser", password="SecurePass1!"))
        self.assertEqual(str(caught.exception), "Username is already taken.")
        self.assertIs(caught.exception.__cause__, error)
        reload_user.assert_not_called()

    def test_non_conflict_database_errors_remain_distinct(self) -> None:
        from data.models import UserCreate

        error = DatabaseError("Database unavailable")
        with (
            patch("services.user_service.get_user_by_username", return_value=None),
            patch("services.user_service.hash_password", return_value="stored-hash"),
            patch("services.user_service.create_user", side_effect=error),
            patch("services.user_service.get_user_by_id") as reload_user,
            self.assertRaises(DatabaseError) as caught,
        ):
            register_user(UserCreate(username="testuser", password="SecurePass1!"))
        self.assertIs(caught.exception, error)
        reload_user.assert_not_called()

    @patch("services.user_service.get_user_by_id")
    @patch("services.user_service.create_user")
    @patch("services.user_service.hash_password")
    @patch("services.user_service.get_user_by_username")
    def test_registers_new_user_successfully(
        self,
        mock_get_by_name: MagicMock,
        mock_hash: MagicMock,
        mock_create: MagicMock,
        mock_get_by_id: MagicMock,
    ) -> None:
        mock_get_by_name.return_value = None
        mock_hash.return_value = "hashed_secret"
        mock_create.return_value = 1
        mock_get_by_id.return_value = _user_dict()

        from data.models import UserCreate

        result = register_user(UserCreate(username="johndoe", password="SecurePass1!"))

        mock_create.assert_called_once_with(username="johndoe", password_hash="hashed_secret", role="USER")
        self.assertEqual(result.username, "johndoe")
        self.assertEqual(result.role, "USER")

    @patch("services.user_service.get_user_by_username")
    def test_raises_username_already_exists_when_taken(self, mock_get_by_name: MagicMock) -> None:
        mock_get_by_name.return_value = _user_dict()

        from data.models import UserCreate

        with self.assertRaises(UsernameAlreadyExistsError):
            register_user(UserCreate(username="johndoe", password="SecurePass1!"))

    @patch("services.user_service.get_user_by_id")
    @patch("services.user_service.create_user")
    @patch("services.user_service.hash_password")
    @patch("services.user_service.get_user_by_username")
    def test_raises_user_creation_error_when_load_after_create_fails(
        self,
        mock_get_by_name: MagicMock,
        mock_hash: MagicMock,
        mock_create: MagicMock,
        mock_get_by_id: MagicMock,
    ) -> None:
        mock_get_by_name.return_value = None
        mock_hash.return_value = "hashed_secret"
        mock_create.return_value = 99
        mock_get_by_id.return_value = None

        from data.models import UserCreate

        with self.assertRaises(UserCreationError):
            register_user(UserCreate(username="johndoe", password="SecurePass1!"))


class TestAuthenticateUser(unittest.TestCase):
    @patch("services.user_service.create_refresh_token")
    @patch("services.user_service.create_access_token")
    @patch("services.user_service.verify_password")
    @patch("services.user_service.get_user_by_username")
    def test_returns_token_pair_on_valid_credentials(
        self, mock_get: MagicMock, mock_verify: MagicMock, mock_access: MagicMock, mock_refresh: MagicMock
    ) -> None:
        mock_get.return_value = _user_dict()
        mock_verify.return_value = True
        mock_access.return_value = "access.token"
        mock_refresh.return_value = "refresh.token"

        result = authenticate_user("johndoe", "SecurePass1!")

        self.assertEqual(result.access_token, "access.token")
        self.assertEqual(result.refresh_token, "refresh.token")
        self.assertEqual(result.token_type, "bearer")

    @patch("services.user_service.get_user_by_username")
    def test_raises_invalid_credentials_when_user_not_found(self, mock_get: MagicMock) -> None:
        mock_get.return_value = None
        with self.assertRaises(InvalidCredentialsError):
            authenticate_user("unknown", "anything")

    @patch("services.user_service.verify_password")
    @patch("services.user_service.get_user_by_username")
    def test_raises_invalid_credentials_when_password_wrong(
        self, mock_get: MagicMock, mock_verify: MagicMock
    ) -> None:
        mock_get.return_value = _user_dict()
        mock_verify.return_value = False
        with self.assertRaises(InvalidCredentialsError):
            authenticate_user("johndoe", "WrongPass1!")


class TestRefreshTokenPair(unittest.TestCase):
    @patch("services.user_service.create_refresh_token")
    @patch("services.user_service.create_access_token")
    @patch("services.user_service.get_user_by_id")
    @patch("services.user_service.decode_token")
    def test_returns_new_token_pair_on_valid_refresh(
        self, mock_decode: MagicMock, mock_get: MagicMock, mock_access: MagicMock, mock_refresh: MagicMock
    ) -> None:
        mock_decode.return_value = _refresh_payload()
        mock_get.return_value = _user_dict(token_version=0)
        mock_access.return_value = "new.access"
        mock_refresh.return_value = "new.refresh"

        from data.models import RefreshRequest

        result = refresh_token_pair(RefreshRequest(refresh_token="valid.refresh.token"))

        self.assertEqual(result.access_token, "new.access")
        self.assertEqual(result.refresh_token, "new.refresh")

    @patch("services.user_service.decode_token")
    def test_raises_invalid_refresh_token_when_decode_fails(self, mock_decode: MagicMock) -> None:
        mock_decode.return_value = None
        from data.models import RefreshRequest

        with self.assertRaises(InvalidRefreshTokenError):
            refresh_token_pair(RefreshRequest(refresh_token="bad.token"))

    @patch("services.user_service.get_user_by_id")
    @patch("services.user_service.decode_token")
    def test_raises_invalid_refresh_token_when_user_deleted(
        self, mock_decode: MagicMock, mock_get: MagicMock
    ) -> None:
        mock_decode.return_value = _refresh_payload()
        mock_get.return_value = None
        from data.models import RefreshRequest

        with self.assertRaises(InvalidRefreshTokenError):
            refresh_token_pair(RefreshRequest(refresh_token="orphaned.token"))

    @patch("services.user_service.get_user_by_id")
    @patch("services.user_service.decode_token")
    def test_raises_invalid_refresh_token_when_version_mismatch(
        self, mock_decode: MagicMock, mock_get: MagicMock
    ) -> None:
        mock_decode.return_value = _refresh_payload(token_version=0)
        mock_get.return_value = _user_dict(token_version=1)  # bumped after password change
        from data.models import RefreshRequest

        with self.assertRaises(InvalidRefreshTokenError):
            refresh_token_pair(RefreshRequest(refresh_token="revoked.token"))

    @patch("services.user_service.decode_token")
    def test_raises_invalid_refresh_token_when_sub_missing(self, mock_decode: MagicMock) -> None:
        mock_decode.return_value = {"token_version": 0}  # no 'sub'
        from data.models import RefreshRequest

        with self.assertRaises(InvalidRefreshTokenError):
            refresh_token_pair(RefreshRequest(refresh_token="no.sub.token"))


class TestChangePassword(unittest.TestCase):
    @patch("services.user_service.bump_token_version")
    @patch("services.user_service.update_password")
    @patch("services.user_service.hash_password")
    @patch("services.user_service.verify_password")
    def test_changes_password_and_bumps_token_version(
        self, mock_verify: MagicMock, mock_hash: MagicMock, mock_update: MagicMock, mock_bump: MagicMock
    ) -> None:
        mock_verify.return_value = True
        mock_hash.return_value = "new_hash"
        mock_update.return_value = 1

        from data.models import UserUpdate

        change_password(_internal_user(), UserUpdate(old_password="OldPass1!", new_password="NewPass1@"))

        mock_update.assert_called_once_with(1, "new_hash")
        mock_bump.assert_called_once_with(1)

    @patch("services.user_service.verify_password")
    def test_raises_incorrect_old_password_when_verify_fails(self, mock_verify: MagicMock) -> None:
        mock_verify.return_value = False
        from data.models import UserUpdate

        with self.assertRaises(IncorrectOldPasswordError):
            change_password(_internal_user(), UserUpdate(old_password="WrongOld1!", new_password="NewPass1@"))


class TestUpdateUserRole(unittest.TestCase):
    @patch("services.user_service.get_user_by_id")
    @patch("services.user_service.update_role")
    def test_promotes_user_to_admin(self, mock_update_role: MagicMock, mock_get: MagicMock) -> None:
        mock_get.side_effect = [_user_dict(), _user_dict(role="ADMIN")]
        mock_update_role.return_value = 1

        result = update_user_role(1, "ADMIN")

        mock_update_role.assert_called_once_with(1, "ADMIN")
        self.assertEqual(result.role, "ADMIN")

    @patch("services.user_service.get_user_by_id")
    def test_raises_user_not_found_when_user_missing(self, mock_get: MagicMock) -> None:
        mock_get.return_value = None
        with self.assertRaises(UserNotFoundError):
            update_user_role(999, "ADMIN")

    @patch("services.user_service.get_user_by_id")
    @patch("services.user_service.update_role")
    def test_raises_user_not_found_if_record_vanishes_after_update(
        self, mock_update_role: MagicMock, mock_get: MagicMock
    ) -> None:
        mock_get.side_effect = [_user_dict(), None]
        mock_update_role.return_value = 1
        with self.assertRaises(UserNotFoundError):
            update_user_role(1, "ADMIN")


if __name__ == "__main__":
    unittest.main()

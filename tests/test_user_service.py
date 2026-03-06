"""
Unit tests for services/user_service.py

All repository and auth calls are mocked so no database or JWT signing is required.
"""

import unittest
from datetime import datetime
from unittest.mock import patch, call

from services.user_service import (
    authenticate_user,
    change_password,
    get_current_user_public_profile,
    refresh_token_pair,
    register_user,
    update_user_role,
)
from utils.errors import (
    IncorrectOldPasswordError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    PasswordUpdateError,
    RoleUpdateError,
    UsernameAlreadyExistsError,
    UserNotFoundError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _user_dict(**overrides) -> dict:
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


def _internal_user(**overrides):
    from data.models import UserInternal
    return UserInternal(**_user_dict(**overrides))


def _refresh_payload(**overrides) -> dict:
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

    @patch("services.user_service.get_user_by_id")
    @patch("services.user_service.create_user")
    @patch("services.user_service.hash_password")
    @patch("services.user_service.get_user_by_username")
    def test_registers_new_user_successfully(self, mock_get_by_name, mock_hash, mock_create, mock_get_by_id):
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
    def test_raises_username_already_exists_when_taken(self, mock_get_by_name):
        mock_get_by_name.return_value = _user_dict()

        from data.models import UserCreate
        with self.assertRaises(UsernameAlreadyExistsError):
            register_user(UserCreate(username="johndoe", password="SecurePass1!"))

    @patch("services.user_service.get_user_by_id")
    @patch("services.user_service.create_user")
    @patch("services.user_service.hash_password")
    @patch("services.user_service.get_user_by_username")
    def test_raises_user_not_found_when_load_after_create_fails(self, mock_get_by_name, mock_hash, mock_create, mock_get_by_id):
        mock_get_by_name.return_value = None
        mock_hash.return_value = "hashed_secret"
        mock_create.return_value = 99
        mock_get_by_id.return_value = None

        from data.models import UserCreate
        with self.assertRaises(UserNotFoundError):
            register_user(UserCreate(username="johndoe", password="SecurePass1!"))



class TestAuthenticateUser(unittest.TestCase):

    @patch("services.user_service.create_refresh_token")
    @patch("services.user_service.create_access_token")
    @patch("services.user_service.verify_password")
    @patch("services.user_service.get_user_by_username")
    def test_returns_token_pair_on_valid_credentials(self, mock_get, mock_verify, mock_access, mock_refresh):
        mock_get.return_value = _user_dict()
        mock_verify.return_value = True
        mock_access.return_value = "access.token"
        mock_refresh.return_value = "refresh.token"

        result = authenticate_user("johndoe", "SecurePass1!")

        self.assertEqual(result.access_token, "access.token")
        self.assertEqual(result.refresh_token, "refresh.token")
        self.assertEqual(result.token_type, "bearer")

    @patch("services.user_service.get_user_by_username")
    def test_raises_invalid_credentials_when_user_not_found(self, mock_get):
        mock_get.return_value = None
        with self.assertRaises(InvalidCredentialsError):
            authenticate_user("unknown", "anything")

    @patch("services.user_service.verify_password")
    @patch("services.user_service.get_user_by_username")
    def test_raises_invalid_credentials_when_password_wrong(self, mock_get, mock_verify):
        mock_get.return_value = _user_dict()
        mock_verify.return_value = False
        with self.assertRaises(InvalidCredentialsError):
            authenticate_user("johndoe", "WrongPass1!")



class TestRefreshTokenPair(unittest.TestCase):

    @patch("services.user_service.create_refresh_token")
    @patch("services.user_service.create_access_token")
    @patch("services.user_service.get_user_by_id")
    @patch("services.user_service.decode_token")
    def test_returns_new_token_pair_on_valid_refresh(self, mock_decode, mock_get, mock_access, mock_refresh):
        mock_decode.return_value = _refresh_payload()
        mock_get.return_value = _user_dict(token_version=0)
        mock_access.return_value = "new.access"
        mock_refresh.return_value = "new.refresh"

        from data.models import RefreshRequest
        result = refresh_token_pair(RefreshRequest(refresh_token="valid.refresh.token"))

        self.assertEqual(result.access_token, "new.access")
        self.assertEqual(result.refresh_token, "new.refresh")

    @patch("services.user_service.decode_token")
    def test_raises_invalid_refresh_token_when_decode_fails(self, mock_decode):
        mock_decode.return_value = None
        from data.models import RefreshRequest
        with self.assertRaises(InvalidRefreshTokenError):
            refresh_token_pair(RefreshRequest(refresh_token="bad.token"))

    @patch("services.user_service.get_user_by_id")
    @patch("services.user_service.decode_token")
    def test_raises_user_not_found_when_user_deleted(self, mock_decode, mock_get):
        mock_decode.return_value = _refresh_payload()
        mock_get.return_value = None
        from data.models import RefreshRequest
        with self.assertRaises(UserNotFoundError):
            refresh_token_pair(RefreshRequest(refresh_token="orphaned.token"))

    @patch("services.user_service.get_user_by_id")
    @patch("services.user_service.decode_token")
    def test_raises_invalid_refresh_token_when_version_mismatch(self, mock_decode, mock_get):
        mock_decode.return_value = _refresh_payload(token_version=0)
        mock_get.return_value = _user_dict(token_version=1)  # bumped after password change
        from data.models import RefreshRequest
        with self.assertRaises(InvalidRefreshTokenError):
            refresh_token_pair(RefreshRequest(refresh_token="revoked.token"))

    @patch("services.user_service.decode_token")
    def test_raises_invalid_refresh_token_when_sub_missing(self, mock_decode):
        mock_decode.return_value = {"token_version": 0}  # no 'sub'
        from data.models import RefreshRequest
        with self.assertRaises(InvalidRefreshTokenError):
            refresh_token_pair(RefreshRequest(refresh_token="no.sub.token"))



class TestChangePassword(unittest.TestCase):

    @patch("services.user_service.bump_token_version")
    @patch("services.user_service.update_password")
    @patch("services.user_service.hash_password")
    @patch("services.user_service.verify_password")
    def test_changes_password_and_bumps_token_version(self, mock_verify, mock_hash, mock_update, mock_bump):
        mock_verify.return_value = True
        mock_hash.return_value = "new_hash"
        mock_update.return_value = 1

        from data.models import UserUpdate
        change_password(_internal_user(), UserUpdate(old_password="OldPass1!", new_password="NewPass1@"))

        mock_update.assert_called_once_with(1, "new_hash")
        mock_bump.assert_called_once_with(1)

    @patch("services.user_service.verify_password")
    def test_raises_incorrect_old_password_when_verify_fails(self, mock_verify):
        mock_verify.return_value = False
        from data.models import UserUpdate
        with self.assertRaises(IncorrectOldPasswordError):
            change_password(_internal_user(), UserUpdate(old_password="WrongOld1!", new_password="NewPass1@"))

    @patch("services.user_service.update_password")
    @patch("services.user_service.hash_password")
    @patch("services.user_service.verify_password")
    def test_raises_password_update_error_when_db_returns_zero_rows(self, mock_verify, mock_hash, mock_update):
        mock_verify.return_value = True
        mock_hash.return_value = "new_hash"
        mock_update.return_value = 0
        from data.models import UserUpdate
        with self.assertRaises(PasswordUpdateError):
            change_password(_internal_user(), UserUpdate(old_password="OldPass1!", new_password="NewPass1@"))

    @patch("services.user_service.bump_token_version")
    @patch("services.user_service.update_password")
    @patch("services.user_service.hash_password")
    @patch("services.user_service.verify_password")
    def test_token_version_not_bumped_when_update_fails(self, mock_verify, mock_hash, mock_update, mock_bump):
        mock_verify.return_value = True
        mock_hash.return_value = "new_hash"
        mock_update.return_value = 0
        from data.models import UserUpdate
        with self.assertRaises(PasswordUpdateError):
            change_password(_internal_user(), UserUpdate(old_password="OldPass1!", new_password="NewPass1@"))
        mock_bump.assert_not_called()



class TestGetCurrentUserPublicProfile(unittest.TestCase):

    @patch("services.user_service.get_user_by_id")
    def test_returns_public_profile(self, mock_get):
        mock_get.return_value = _user_dict()
        result = get_current_user_public_profile(_internal_user())
        self.assertEqual(result.username, "johndoe")
        self.assertEqual(result.id, 1)

    @patch("services.user_service.get_user_by_id")
    def test_raises_user_not_found_when_missing(self, mock_get):
        mock_get.return_value = None
        with self.assertRaises(UserNotFoundError):
            get_current_user_public_profile(_internal_user())



class TestUpdateUserRole(unittest.TestCase):

    @patch("services.user_service.get_user_by_id")
    @patch("services.user_service.update_role")
    def test_promotes_user_to_admin(self, mock_update_role, mock_get):
        mock_get.side_effect = [_user_dict(), _user_dict(role="ADMIN")]
        mock_update_role.return_value = 1

        result = update_user_role(1, "ADMIN")

        mock_update_role.assert_called_once_with(1, "ADMIN")
        self.assertEqual(result.role, "ADMIN")

    @patch("services.user_service.get_user_by_id")
    def test_raises_user_not_found_when_user_missing(self, mock_get):
        mock_get.return_value = None
        with self.assertRaises(UserNotFoundError):
            update_user_role(999, "ADMIN")

    @patch("services.user_service.get_user_by_id")
    @patch("services.user_service.update_role")
    def test_raises_role_update_error_when_db_returns_zero_rows(self, mock_update_role, mock_get):
        mock_get.return_value = _user_dict()
        mock_update_role.return_value = 0
        with self.assertRaises(RoleUpdateError):
            update_user_role(1, "ADMIN")

    @patch("services.user_service.get_user_by_id")
    @patch("services.user_service.update_role")
    def test_raises_user_not_found_if_record_vanishes_after_update(self, mock_update_role, mock_get):
        mock_get.side_effect = [_user_dict(), None]
        mock_update_role.return_value = 1
        with self.assertRaises(UserNotFoundError):
            update_user_role(1, "ADMIN")


if __name__ == "__main__":
    unittest.main()

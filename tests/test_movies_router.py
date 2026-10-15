import unittest
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Literal
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from jose import jwt

from auth.jwt_handler import ALGORITHM, JWTPayload, UserTokenData, create_access_token, create_refresh_token
from config.jwt import JWTConfig
from data.models import MovieOut, UserInternal
from dependencies.auth import get_current_admin, get_current_user
from routers.movies import movies_router
from utils.errors import EmptyMovieUpdateError, MovieCreationError, MovieDeleteError, MovieNotFoundError

if TYPE_CHECKING:
    from repositories.user_repository import UserRow


class MoviesRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = FastAPI()
        self.app.include_router(movies_router)
        self.app.dependency_overrides[get_current_user] = self.authorized_user
        self.app.dependency_overrides[get_current_admin] = self.authorized_user
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        self.movie = MovieOut(
            id=1,
            title="Example",
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
        )

    @staticmethod
    def authorized_user() -> UserInternal:
        return UserInternal(
            id=1,
            username="admin",
            password_hash="hash",
            role="ADMIN",
            created_at=datetime(2026, 1, 1),
        )

    @staticmethod
    def forbidden() -> UserInternal:
        raise HTTPException(status_code=403, detail="Admin required")

    @staticmethod
    def unauthorized() -> UserInternal:
        raise HTTPException(status_code=401, detail="Authentication required")

    def test_create_returns_201_and_runs_background_enrichment(self) -> None:
        with (
            patch("routers.movies.create_movie_record", return_value=self.movie),
            patch("routers.movies.enrich_movie_rating", new_callable=AsyncMock) as enrich,
        ):
            response = self.client.post("/movies", json={"title": "Example"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["id"], 1)
        self.assertNotIn("enrichment_error", response.json())
        enrich.assert_awaited_once_with(1, "Example")

    def test_list_passes_default_and_custom_query_options(self) -> None:
        for url, expected in (
            ("/movies", {"q": None, "sort_by": "rating", "order": "desc"}),
            ("/movies?q=Example&sort_by=title&order=asc", {"q": "Example", "sort_by": "title", "order": "asc"}),
        ):
            with (
                self.subTest(url=url),
                patch("routers.movies.list_movie_records", return_value=[self.movie]) as service,
            ):
                response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.json()), 1)
            service.assert_called_once_with(**expected)

    def test_get_and_update_return_movie(self) -> None:
        with patch("routers.movies.get_movie_record", return_value=self.movie) as service:
            self.assertEqual(self.client.get("/movies/1").status_code, 200)
        service.assert_called_once_with(1)
        with patch("routers.movies.update_movie_record", return_value=self.movie) as update:
            response = self.client.put("/movies/1", json={"director": None})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(update.call_args.args[0], 1)
        self.assertEqual(update.call_args.args[1].fields_to_update(), {"director": None})

    def test_delete_returns_empty_204(self) -> None:
        with patch("routers.movies.delete_movie_record") as service:
            response = self.client.delete("/movies/1")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        service.assert_called_once_with(1)

    def test_domain_errors_map_to_http_statuses(self) -> None:
        cases = [
            ("post", "/movies", "create_movie_record", MovieCreationError("creation failed"), 500),
            ("get", "/movies/1", "get_movie_record", MovieNotFoundError("missing"), 404),
            ("put", "/movies/1", "update_movie_record", EmptyMovieUpdateError("empty"), 400),
            ("put", "/movies/1", "update_movie_record", MovieNotFoundError("missing"), 404),
            ("delete", "/movies/1", "delete_movie_record", MovieNotFoundError("missing"), 404),
            ("delete", "/movies/1", "delete_movie_record", MovieDeleteError("delete failed"), 500),
        ]
        for method, url, target, error, expected in cases:
            with (
                self.subTest(method=method, error=error),
                patch(f"routers.movies.{target}", side_effect=error),
                patch("routers.movies.enrich_movie_rating", new_callable=AsyncMock) as enrich,
            ):
                response = self.client.request(method, url, json={"title": "Example"})
            self.assertEqual(response.status_code, expected)
            self.assertEqual(response.json()["detail"], str(error))
            enrich.assert_not_awaited()

    def test_invalid_sort_options_are_rejected_before_service(self) -> None:
        for query in ("sort_by=invalid", "order=invalid", "sort_by=title%0A", "order=asc%0A"):
            with self.subTest(query=query), patch("routers.movies.list_movie_records") as service:
                self.assertEqual(self.client.get(f"/movies?{query}").status_code, 422)
            service.assert_not_called()

    def test_reads_require_authentication(self) -> None:
        self.app.dependency_overrides[get_current_user] = self.unauthorized
        for url, target in (("/movies", "list_movie_records"), ("/movies/1", "get_movie_record")):
            with self.subTest(url=url), patch(f"routers.movies.{target}") as service:
                self.assertEqual(self.client.get(url).status_code, 401)
            service.assert_not_called()

    def test_writes_require_admin_permission(self) -> None:
        self.app.dependency_overrides[get_current_admin] = self.forbidden
        for method, url, target in (
            ("post", "/movies", "create_movie_record"),
            ("put", "/movies/1", "update_movie_record"),
            ("delete", "/movies/1", "delete_movie_record"),
        ):
            with self.subTest(method=method), patch(f"routers.movies.{target}") as service:
                response = self.client.request(method, url, json={"title": "Example"})
            self.assertEqual(response.status_code, 403)
            service.assert_not_called()

    def test_invalid_bodies_are_rejected_before_services(self) -> None:
        future_year = datetime.now(UTC).year + 3
        cases: list[tuple[str, str, dict[str, object]]] = [
            ("post", "create_movie_record", {}),
            ("post", "create_movie_record", {"title": None}),
            ("post", "create_movie_record", {"title": ""}),
            ("post", "create_movie_record", {"title": "   "}),
            ("post", "create_movie_record", {"title": "x" * 256}),
            ("post", "create_movie_record", {"title": 123}),
            ("post", "create_movie_record", {"title": "Example", "release_year": 1887}),
            ("post", "create_movie_record", {"title": "Example", "release_year": future_year}),
            ("post", "create_movie_record", {"title": "Example", "director": "x" * 256}),
            ("put", "update_movie_record", {"title": None}),
            ("put", "update_movie_record", {"title": "   "}),
            ("put", "update_movie_record", {"release_year": 1887}),
            ("put", "update_movie_record", {"release_year": future_year}),
        ]
        for method, target, body in cases:
            url = "/movies" if method == "post" else "/movies/1"
            with self.subTest(body=body), patch(f"routers.movies.{target}") as service:
                self.assertEqual(self.client.request(method, url, json=body).status_code, 422)
            service.assert_not_called()

    def test_missing_and_malformed_request_bodies(self) -> None:
        for method, url, target in (
            ("post", "/movies", "create_movie_record"),
            ("put", "/movies/1", "update_movie_record"),
        ):
            for content in (b"", b"{invalid json", b"[]"):
                with self.subTest(method=method, content=content), patch(f"routers.movies.{target}") as service:
                    response = self.client.request(
                        method,
                        url,
                        content=content,
                        headers={"Content-Type": "application/json"},
                    )
                self.assertEqual(response.status_code, 422)
                service.assert_not_called()

    def test_invalid_path_ids_are_rejected(self) -> None:
        for method, target in (
            ("get", "get_movie_record"),
            ("put", "update_movie_record"),
            ("delete", "delete_movie_record"),
        ):
            for invalid in ("not-an-id", "1.5"):
                with self.subTest(method=method, invalid=invalid), patch(f"routers.movies.{target}") as service:
                    response = self.client.request(method, f"/movies/{invalid}", json={"title": "Example"})
                self.assertEqual(response.status_code, 422)
                service.assert_not_called()

    def test_empty_list_and_all_valid_sort_combinations(self) -> None:
        for sort_by in ("rating", "title", "release_year", "created_at"):
            for order in ("asc", "desc"):
                with (
                    self.subTest(sort_by=sort_by, order=order),
                    patch("routers.movies.list_movie_records", return_value=[]) as service,
                ):
                    response = self.client.get("/movies", params={"sort_by": sort_by, "order": order})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), [])
                service.assert_called_once_with(q=None, sort_by=sort_by, order=order)

    def test_empty_update_returns_400_without_database_access(self) -> None:
        with patch("services.movies_service.get_movie") as lookup:
            response = self.client.put("/movies/1", json={})
        self.assertEqual(response.status_code, 400)
        lookup.assert_not_called()

    def test_updates_distinguish_omitted_fields_and_explicit_nulls(self) -> None:
        cases: list[dict[str, object]] = [
            {"title": "Updated"},
            {"director": None},
            {"release_year": None},
            {"director": None, "release_year": None},
            {"title": "Updated", "director": "Director", "release_year": 2000},
        ]
        for body in cases:
            with (
                self.subTest(body=body),
                patch("routers.movies.update_movie_record", return_value=self.movie) as update,
            ):
                response = self.client.put("/movies/1", json=body)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(update.call_args.args[1].fields_to_update(), body)

    def test_writes_require_authentication(self) -> None:
        self.app.dependency_overrides[get_current_admin] = self.unauthorized
        for method, url, target in (
            ("post", "/movies", "create_movie_record"),
            ("put", "/movies/1", "update_movie_record"),
            ("delete", "/movies/1", "delete_movie_record"),
        ):
            with self.subTest(method=method), patch(f"routers.movies.{target}") as service:
                response = self.client.request(method, url, json={"title": "Example"})
            self.assertEqual(response.status_code, 401)
            service.assert_not_called()

    def test_response_serialization_for_each_enrichment_state(self) -> None:
        cases: list[tuple[dict[str, object], str]] = [
            ({}, "pending"),
            ({"rating": 8.5, "enrichment_error": "internal detail"}, "success"),
            ({"enrichment_error": "Movie not found in OMDb."}, "not_found"),
            ({"enrichment_error": "internal detail"}, "failed"),
            ({"rating_updated_at": datetime(2026, 1, 1)}, "failed"),
        ]
        for changes, expected in cases:
            movie = MovieOut.model_validate({**self.movie.model_dump(), **changes})
            with self.subTest(expected=expected), patch("routers.movies.get_movie_record", return_value=movie):
                response = self.client.get("/movies/1")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["enrichment_status"], expected)
            self.assertNotIn("enrichment_error", response.json())
            self.assertEqual(response.json()["created_at"], "2026-01-01T00:00:00")

    def test_unexpected_service_errors_return_500(self) -> None:
        with TestClient(self.app, raise_server_exceptions=False) as client:
            for method, url, target in (
                ("post", "/movies", "create_movie_record"),
                ("get", "/movies", "list_movie_records"),
                ("get", "/movies/1", "get_movie_record"),
                ("put", "/movies/1", "update_movie_record"),
                ("delete", "/movies/1", "delete_movie_record"),
            ):
                with (
                    self.subTest(method=method, url=url),
                    patch(f"routers.movies.{target}", side_effect=RuntimeError("internal details")),
                    patch("routers.movies.enrich_movie_rating", new_callable=AsyncMock) as enrich,
                ):
                    response = client.request(method, url, json={"title": "Example"})
                self.assertEqual(response.status_code, 500)
                self.assertNotIn("internal details", response.text)
                enrich.assert_not_awaited()

    def test_background_fetch_and_persistence_failures_preserve_created_response(self) -> None:
        for fail_persistence in (False, True):
            with (
                self.subTest(fail_persistence=fail_persistence),
                patch("routers.movies.create_movie_record", return_value=self.movie),
                patch("services.rating_service._fetch_rating_from_omdb", new_callable=AsyncMock) as fetch,
                patch("services.rating_service.update_movie_rating") as persist,
                self.assertLogs("services.rating_service", level="ERROR"),
            ):
                fetch.side_effect = RuntimeError("lookup failed")
                if fail_persistence:
                    persist.side_effect = RuntimeError("database unavailable")
                response = self.client.post("/movies", json={"title": "Example"})
            self.assertEqual(response.status_code, 201)
            self.assertEqual(response.json()["id"], 1)
            fetch.assert_awaited_once_with("Example")
            self.assertIn("lookup failed", persist.call_args.kwargs["enrichment_error"])

    def test_real_jwt_authentication_and_roles_on_all_routes(self) -> None:
        self.app.dependency_overrides.clear()
        roles: tuple[Literal["USER", "ADMIN"], ...] = ("USER", "ADMIN")
        for role in roles:
            user: UserTokenData = {"user_id": 1, "username": "testuser", "role": role, "token_version": 0}
            row: UserRow = {
                "id": 1,
                "username": "testuser",
                "password_hash": "hash",
                "role": role,
                "token_version": 0,
                "created_at": datetime(2026, 1, 1),
            }
            with (
                patch(
                    "auth.jwt_handler.get_jwt_config",
                    return_value=JWTConfig(secret_key="test-key-at-least-32-characters-long"),
                ),
                patch("dependencies.auth.get_user_by_id", return_value=row),
            ):
                token = create_access_token(user)
                for method, url, target, result, success in (
                    ("get", "/movies", "list_movie_records", [self.movie], 200),
                    ("get", "/movies/1", "get_movie_record", self.movie, 200),
                    ("post", "/movies", "create_movie_record", self.movie, 201),
                    ("put", "/movies/1", "update_movie_record", self.movie, 200),
                    ("delete", "/movies/1", "delete_movie_record", None, 204),
                ):
                    with (
                        self.subTest(role=role, method=method, url=url),
                        patch(f"routers.movies.{target}", return_value=result) as service,
                        patch("routers.movies.enrich_movie_rating", new_callable=AsyncMock),
                    ):
                        response = self.client.request(
                            method,
                            url,
                            headers={"Authorization": f"Bearer {token}"},
                            json={"title": "Example"},
                        )
                    expected = 403 if role == "USER" and method != "get" else success
                    self.assertEqual(response.status_code, expected)
                    if expected == 403:
                        service.assert_not_called()

    def test_real_auth_rejects_invalid_expired_refresh_deleted_and_revoked_tokens(self) -> None:
        self.app.dependency_overrides.clear()
        secret = "test-key-at-least-32-characters-long"
        user: UserTokenData = {"user_id": 1, "username": "testuser", "role": "USER", "token_version": 0}
        row: UserRow = {
            "id": 1,
            "username": "testuser",
            "password_hash": "hash",
            "role": "USER",
            "token_version": 0,
            "created_at": datetime(2026, 1, 1),
        }
        with (
            patch("auth.jwt_handler.get_jwt_config", return_value=JWTConfig(secret_key=secret)),
        ):
            access = create_access_token(user)
            refresh = create_refresh_token(user)
            expired: JWTPayload = {
                "sub": "1",
                "iat": 1,
                "exp": datetime.now(UTC) - timedelta(minutes=1),
                "jti": "expired",
                "type": "access",
                "username": "testuser",
                "role": "USER",
                "token_version": 0,
            }
            cases: list[tuple[str | None, UserRow | None]] = [
                (None, row),
                ("invalid", row),
                (refresh, row),
                (jwt.encode(dict(expired), secret, algorithm=ALGORITHM), row),
                (access, None),
                (access, {**row, "token_version": 1}),
            ]
            for token, database_row in cases:
                with (
                    self.subTest(token=token, database_row=database_row),
                    patch("dependencies.auth.get_user_by_id", return_value=database_row),
                    patch("routers.movies.list_movie_records") as service,
                ):
                    headers = {"Authorization": f"Bearer {token}"} if token else {}
                    response = self.client.get("/movies", headers=headers)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.headers["www-authenticate"], "Bearer")
                service.assert_not_called()

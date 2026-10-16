"""Typed SQL registry modeled on FleetFlow's database query registry.

Query groups load lazily and are cached on first access. SQL templates interpolate
only trusted structural fragments; repositories bind all data values separately.
"""

from dataclasses import dataclass
from functools import cached_property

from data.loader import load_sql


@dataclass(frozen=True, slots=True)
class MovieQueries:
    """Movie statements and templates stored under data/sql/movies."""

    create: str
    get_by_id: str
    list_all: str
    filter_by_title: str
    order_by: str
    order_by_rating: str
    update: str
    update_assignment: str
    update_rating: str
    delete: str


@dataclass(frozen=True, slots=True)
class UserQueries:
    """User statements stored under data/sql/users."""

    create: str
    get_by_username: str
    get_by_id: str
    update_password: str
    update_role: str
    bump_token_version: str


class QueryRegistry:
    """Load independent immutable query groups only when first requested."""

    @cached_property
    def movies(self) -> MovieQueries:
        """Load movie queries, propagating missing or invalid SQL file errors."""
        return MovieQueries(
            create=load_sql("movies/create.sql"),
            get_by_id=load_sql("movies/get_by_id.sql"),
            list_all=load_sql("movies/list.sql"),
            filter_by_title=load_sql("movies/filter_by_title.sql"),
            order_by=load_sql("movies/order_by.sql"),
            order_by_rating=load_sql("movies/order_by_rating.sql"),
            update=load_sql("movies/update.sql"),
            update_assignment=load_sql("movies/update_assignment.sql"),
            update_rating=load_sql("movies/update_rating.sql"),
            delete=load_sql("movies/delete.sql"),
        )

    @cached_property
    def users(self) -> UserQueries:
        """Load user queries, propagating missing or invalid SQL file errors."""
        return UserQueries(
            create=load_sql("users/create.sql"),
            get_by_username=load_sql("users/get_by_username.sql"),
            get_by_id=load_sql("users/get_by_id.sql"),
            update_password=load_sql("users/update_password.sql"),
            update_role=load_sql("users/update_role.sql"),
            bump_token_version=load_sql("users/bump_token_version.sql"),
        )


QUERIES = QueryRegistry()

SELECT
    id, title, director, release_year,
    rating, rating_source, rating_updated_at,
    enrichment_error, created_at, updated_at
FROM movies
{where_clause}
{order_clause}

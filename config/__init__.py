"""Immutable, validated settings loaded lazily for each application component.

Each module exposes load, get, and set functions. Load reads the environment;
get caches the result; set overrides it or clears the cache when passed None.
"""

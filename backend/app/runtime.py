"""API connection pool and active demo-run helpers."""

from functools import lru_cache

from app.config import get_settings
from app.db import create_client, get_database


@lru_cache
def mongo_client():
    return create_client(get_settings())


def database():
    return get_database(mongo_client(), get_settings())

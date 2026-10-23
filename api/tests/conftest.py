import pytest
from fastapi.testclient import TestClient

from place.app import create_app
from place.config import Settings
from place.store import MemoryStore


@pytest.fixture
def settings(tmp_path):
    return Settings(
        image_size=250,
        rate_limit_seconds=5,
        admin_client_ids=frozenset({"client_admin"}),
        redis_url="redis://unused:6379/0",
        data_dir=tmp_path,
        events_stream="place:events",
        consumer_group="png-writer",
    )


@pytest.fixture
def store():
    return MemoryStore()


@pytest.fixture
def app(settings, store):
    return create_app(settings=settings, store=store)


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client

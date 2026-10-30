"""Offline suite: no provider HTTP and no PostgreSQL except the explicit fixture."""

import os
from urllib.parse import urlsplit

import psycopg
import pytest
import requests


@pytest.fixture(autouse=True)
def offline_boundaries(monkeypatch):
    real_connect = psycopg.connect
    fixture_dsn = os.environ.get("PISRS_OLC85_TEST_DSN")

    def connect(dsn, *args, **kwargs):
        if not fixture_dsn or dsn != fixture_dsn:
            raise AssertionError("offline tests may only connect to their fixture database")
        u = urlsplit(dsn)
        assert u.hostname == "127.0.0.1" and u.port not in (None, 5432, 6333, 6334)
        assert u.path == "/olc85_fixture"
        return real_connect(dsn, *args, **kwargs)

    def no_http(*args, **kwargs):
        raise AssertionError("offline suite forbids real HTTP calls")

    monkeypatch.setattr(psycopg, "connect", connect)
    monkeypatch.setattr(requests.sessions.Session, "request", no_http)

"""Общие фикстуры: приложение на временной БД с демо-данными и вход под пользователем."""
import re
import sqlite3

import pytest

from app import create_app

CSRF_RE = re.compile(r'name="csrf_token" value="([0-9a-f]+)"')


@pytest.fixture()
def app(tmp_path):
    return create_app({"DATABASE": str(tmp_path / "test.db"), "SECRET_KEY": "test", "TESTING": True})


@pytest.fixture()
def db(app):
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


@pytest.fixture()
def ids(db):
    return {row["username"]: row["id"] for row in db.execute("SELECT id, username FROM users")}


class Client:
    """Тестовый клиент, который сам подставляет CSRF-токен в POST-запросы."""

    def __init__(self, flask_client):
        self.raw = flask_client

    def token(self):
        html = self.raw.get("/login").get_data(as_text=True)
        if "csrf_token" not in html:
            html = self.raw.get("/profile").get_data(as_text=True)
        return CSRF_RE.search(html).group(1)

    def get(self, url, **kwargs):
        return self.raw.get(url, **kwargs)

    def post(self, url, data=None, **kwargs):
        payload = {"csrf_token": self.token(), **(data or {})}
        return self.raw.post(url, data=payload, **kwargs)

    def login(self, username, password="123456"):
        return self.post("/login", {"username": username, "password": password})

    def text(self, url):
        return self.get(url).get_data(as_text=True)


@pytest.fixture()
def client(app):
    return Client(app.test_client())


@pytest.fixture()
def manager(app):
    c = Client(app.test_client())
    c.login("manager", "manager123")
    return c


@pytest.fixture()
def make_client(app):
    def factory(username, password="123456"):
        c = Client(app.test_client())
        c.login(username, password)
        return c
    return factory

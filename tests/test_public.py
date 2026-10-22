"""Публичный режим: разбор ссылок, перезапуск туннелей, защита данных."""
import re
import sys
import threading

import pytest

from app import create_app
from public_link import TunnelSupervisor, find_public_url
from run import find_free_port, links_message
from tests.conftest import Client

FAKE_URL_RE = re.compile(r"https://[a-z0-9]+\.lhr\.life")


def test_public_urls_are_found_in_tunnel_logs():
    cloudflare = "2026-10-22T14:00:00Z INF |  https://quiet-river-1234.trycloudflare.com   |"
    lhr = "9a17a398f04baf.lhr.life tunneled with tls termination, https://9a17a398f04baf.lhr.life"
    assert find_public_url(cloudflare) == "https://quiet-river-1234.trycloudflare.com"
    assert find_public_url(lhr) == "https://9a17a398f04baf.lhr.life"
    assert find_public_url("INF Starting tunnel") is None


def test_free_port_is_found():
    assert 5000 <= find_free_port(5000) < 5050


def test_links_message_lists_every_link():
    message = links_message({"Cloudflare": "https://a.trycloudflare.com", "localhost.run": "https://b.lhr.life"})
    assert "https://a.trycloudflare.com" in message and "https://b.lhr.life" in message


def test_supervisor_reports_link_and_restarts_dropped_tunnel():
    events, restarted = [], threading.Event()

    def on_event(name, url, note):
        events.append((name, url, note))
        if "переподключаюсь" in note and sum(1 for e in events if e[1]) >= 1:
            restarted.set()

    fake = [sys.executable, "-c", "print('ready https://abc123.lhr.life', flush=True)"]
    supervisor = TunnelSupervisor(5000, on_event, providers=(("fake", FAKE_URL_RE, lambda port: fake),))
    supervisor.restart_delay = 0.05
    supervisor.start()
    assert restarted.wait(10)
    supervisor.stop()
    assert ("fake", "https://abc123.lhr.life", "") in events


def test_supervisor_gives_up_when_tool_is_missing():
    events = []

    def broken(port):
        raise RuntimeError("нет программы")

    supervisor = TunnelSupervisor(5000, lambda *e: events.append(e), providers=(("broken", FAKE_URL_RE, broken),))
    supervisor.start()
    assert supervisor.wait_for_links(5) == {}
    assert events == [("broken", None, "не запущен: нет программы")]


@pytest.fixture()
def public_manager(tmp_path):
    app = create_app({"DATABASE": str(tmp_path / "public.db"), "SECRET_KEY": "test",
                      "TESTING": True, "PUBLIC_MODE": True})
    client = Client(app.test_client())
    client.login("manager", "manager123")
    return client


def test_public_mode_blocks_reset_and_clear(public_manager):
    public_manager.post("/settings/clear", {"confirm": "УДАЛИТЬ"})
    public_manager.post("/settings/reset-demo")
    assert public_manager.get("/dashboard").status_code == 200, "сброс не должен был разлогинить"
    html = public_manager.text("/profile")
    assert "публичной ссылке" in html
    assert "Очистить данные" not in html
    assert "Иван Петров" in public_manager.text("/employees")


def test_public_mode_blocks_password_changes(public_manager):
    public_manager.post("/profile/password", {"current_password": "manager123", "new_password": "hacked1",
                                              "new_password_confirm": "hacked1"})
    assert "изменение пароля отключено" in public_manager.text("/profile")
    public_manager.post("/logout")
    assert public_manager.login("manager", "manager123").status_code == 302, "старый пароль должен работать"


def test_public_mode_keeps_normal_work(public_manager):
    for url in ("/schedule", "/employees", "/requests", "/shifts/new"):
        assert public_manager.get(url).status_code == 200

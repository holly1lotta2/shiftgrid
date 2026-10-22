"""Публичные ссылки на ShiftGrid для одногруппников.

Поднимаются два независимых туннеля, чтобы хотя бы один открывался в любой сети:
  1. Cloudflare (trycloudflare.com) — программа cloudflared, скачивается в tools/ при первом запуске;
  2. localhost.run (lhr.life) — через ssh, встроенный в Windows 10/11, ничего скачивать не нужно.
Регистрация нигде не нужна. Если туннель обрывается, он перезапускается и сообщает новую ссылку.
"""
import os
import platform
import re
import shutil
import subprocess
import threading
import time
import urllib.request

TOOLS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools")
CLOUDFLARED_EXE = os.path.join(TOOLS_DIR, "cloudflared.exe")
CLOUDFLARED_DOWNLOAD_URL = (
    "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
)
CLOUDFLARED_HELP_URL = "https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
DOWNLOAD_CHUNK = 1024 * 1024
EXTRA_WAIT_AFTER_FIRST_LINK_SECONDS = 8
RESTART_DELAY_SECONDS = 5
MAX_RESTART_DELAY_SECONDS = 60
STABLE_RUN_SECONDS = 60
ERROR_LINE_RE = re.compile(r"\bERR\b|error|denied|refused", re.IGNORECASE)
MAX_REASON_CHARS = 140


# ----------------------------------------------------------------- Cloudflare

def cloudflared_path():
    """cloudflared из PATH или из tools/; на Windows при отсутствии — скачивается."""
    installed = shutil.which("cloudflared")
    if installed:
        return installed
    if os.path.exists(CLOUDFLARED_EXE):
        return CLOUDFLARED_EXE
    if platform.system() != "Windows":
        raise RuntimeError(f"установите cloudflared: {CLOUDFLARED_HELP_URL}")
    download(CLOUDFLARED_DOWNLOAD_URL, CLOUDFLARED_EXE)
    return CLOUDFLARED_EXE


def download(url, target):
    os.makedirs(TOOLS_DIR, exist_ok=True)
    partial = target + ".part"
    print("Первый запуск: скачиваю cloudflared от Cloudflare (около 60 МБ)...")
    try:
        with urllib.request.urlopen(url, timeout=60) as response, open(partial, "wb") as out:
            while chunk := response.read(DOWNLOAD_CHUNK):
                out.write(chunk)
    except OSError as error:
        if os.path.exists(partial):
            os.remove(partial)
        raise RuntimeError(f"не удалось скачать cloudflared ({error})") from error
    os.replace(partial, target)


def cloudflare_command(port):
    # http2 идёт через обычный TCP 443 — проходит там, где VPN или сеть режут QUIC/UDP.
    return [cloudflared_path(), "tunnel", "--no-autoupdate", "--protocol", "http2",
            "--url", f"http://127.0.0.1:{port}"]


# ------------------------------------------------------------- localhost.run

def localhost_run_command(port):
    ssh = shutil.which("ssh")
    if not ssh:
        raise RuntimeError("не найден ssh (в Windows 10/11 он есть по умолчанию)")
    # Ключ хоста не сохраняем, чтобы не трогать ~/.ssh пользователя.
    return [ssh, "-T", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no",
            "-o", f"UserKnownHostsFile={os.devnull}", "-o", "LogLevel=ERROR",
            "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=3",
            "-o", "ExitOnForwardFailure=yes",
            "-R", f"80:127.0.0.1:{port}", "nokey@localhost.run"]


# (название, шаблон ссылки в выводе программы, функция сборки команды)
PROVIDERS = (
    ("Cloudflare", re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com"), cloudflare_command),
    ("localhost.run", re.compile(r"https://[a-z0-9]+\.lhr\.life"), localhost_run_command),
)


def find_public_url(line):
    for _name, pattern, _build in PROVIDERS:
        match = pattern.search(line)
        if match:
            return match.group(0)
    return None


class TunnelSupervisor:
    """Держит туннели запущенными. О событиях сообщает через on_event(название, ссылка, пояснение)."""

    def __init__(self, port, on_event, providers=PROVIDERS):
        self.port = port
        self.on_event = on_event
        self.providers = providers
        self.restart_delay = RESTART_DELAY_SECONDS
        self._links = {}
        self._given_up = set()
        self._processes = set()
        self._lock = threading.Lock()
        self._stopped = threading.Event()

    def start(self):
        for name, pattern, build in self.providers:
            threading.Thread(target=self._keep_alive, args=(name, pattern, build), daemon=True).start()

    def links(self):
        with self._lock:
            return {name: self._links[name] for name, _p, _b in self.providers if name in self._links}

    def wait_for_links(self, timeout):
        """Ждёт ссылки от всех туннелей. Как только есть первая — даёт остальным ещё несколько секунд,
        чтобы сбоящий туннель не задерживал запуск."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                have_links = bool(self._links)
                settled = len(self._links) + len(self._given_up - set(self._links))
            if settled >= len(self.providers):
                break
            if have_links:
                deadline = min(deadline, time.monotonic() + EXTRA_WAIT_AFTER_FIRST_LINK_SECONDS)
            time.sleep(0.3)
        return self.links()

    def stop(self):
        self._stopped.set()
        with self._lock:
            processes = list(self._processes)
        for process in processes:
            if process.poll() is None:
                process.terminate()

    def _keep_alive(self, name, pattern, build):
        delay = self.restart_delay
        while not self._stopped.is_set():
            try:
                command = build(self.port)
            except RuntimeError as error:
                with self._lock:
                    self._given_up.add(name)
                self.on_event(name, None, f"не запущен: {error}")
                return
            started = time.monotonic()
            last_error = self._run_once(name, pattern, command)
            if self._stopped.is_set():
                return
            with self._lock:
                self._links.pop(name, None)
            reason = f" ({last_error})" if last_error else ""
            self.on_event(name, None, f"связь потеряна, переподключаюсь...{reason}")
            # Быстро падающий туннель перезапускаем всё реже, стабильный — сразу.
            ran_long = time.monotonic() - started > STABLE_RUN_SECONDS
            delay = self.restart_delay if ran_long else min(delay * 2, MAX_RESTART_DELAY_SECONDS)
            self._stopped.wait(delay)

    def _run_once(self, name, pattern, command):
        """Запускает туннель и ждёт его завершения. Возвращает последнюю строку с ошибкой."""
        try:
            process = subprocess.Popen(
                command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
            )
        except OSError as error:
            return f"не запустился: {error}"
        with self._lock:
            self._processes.add(process)
        last_error = ""
        # Вывод читаем до конца: если буфер переполнится, программа туннеля зависнет.
        for line in process.stdout:
            if ERROR_LINE_RE.search(line):
                last_error = line.strip()[-MAX_REASON_CHARS:]
            match = pattern.search(line)
            if not match:
                continue
            with self._lock:
                is_new = self._links.get(name) != match.group(0)
                self._links[name] = match.group(0)
            if is_new:
                self.on_event(name, match.group(0), "")
        process.wait()
        with self._lock:
            self._processes.discard(process)
        return last_error

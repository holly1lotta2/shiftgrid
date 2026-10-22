"""Запуск ShiftGrid на своём компьютере.

    python run.py           — только на этом компьютере
    python run.py --public  — плюс ссылки из интернета для одногруппников

Сам находит свободный порт, начиная с 5000, и открывает приложение в браузере.
"""
import argparse
import atexit
import os
import socket
import subprocess
import threading
import webbrowser

from app import create_app

HOST = "127.0.0.1"
FIRST_PORT = 5000
PORTS_TO_TRY = 50
BROWSER_DELAY_SECONDS = 1.0
LINK_WAIT_SECONDS = 60
BANNER_WIDTH = 70

# Консоль Windows: режим выделения мышью (QuickEdit) замораживает программу, пока выделение не снято.
STD_INPUT_HANDLE = -10
ENABLE_QUICK_EDIT_MODE = 0x0040
ENABLE_EXTENDED_FLAGS = 0x0080


def find_free_port(first_port):
    for port in range(first_port, first_port + PORTS_TO_TRY):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((HOST, port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"Не нашлось свободного порта в диапазоне {first_port}–{first_port + PORTS_TO_TRY}.")


def disable_quick_edit():
    """Случайный щелчок мышью в окне консоли больше не останавливает сервер."""
    if os.name != "nt":
        return
    import ctypes

    kernel32 = ctypes.windll.kernel32
    handle = kernel32.GetStdHandle(STD_INPUT_HANDLE)
    mode = ctypes.c_uint32()
    if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
        kernel32.SetConsoleMode(handle, (mode.value & ~ENABLE_QUICK_EDIT_MODE) | ENABLE_EXTENDED_FLAGS)


def copy_to_clipboard(text):
    """Копирует в буфер обмена Windows; на других системах молча пропускает."""
    try:
        subprocess.run(["clip"], input=text, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return False
    return True


def links_message(links):
    return "\n".join(f"ShiftGrid ({name}): {url}" for name, url in links.items())


def start_public_links(port):
    """Поднимает туннели и ждёт первые ссылки. Возвращает {название: ссылка}."""
    from public_link import TunnelSupervisor

    state = {"banner_shown": False}

    def on_event(name, url, note):
        if url and state["banner_shown"]:
            print(f"\n  [{name}] НОВАЯ ССЫЛКА: {url}")
            if copy_to_clipboard(links_message(supervisor.links())):
                print("  Ссылки в буфере обмена обновлены — перешлите их заново.")
        elif url:
            print(f"  [{name}] ссылка получена")
        else:
            print(f"  [{name}] {note}")

    print("Получаю ссылки для одногруппников (Cloudflare и localhost.run), это до минуты...")
    supervisor = TunnelSupervisor(port, on_event)
    supervisor.start()
    atexit.register(supervisor.stop)
    links = supervisor.wait_for_links(LINK_WAIT_SECONDS)
    state["banner_shown"] = True
    return links


def print_banner(local_url, public_links, public_requested):
    print("=" * BANNER_WIDTH)
    print(f"  ShiftGrid на этом компьютере:  {local_url}")
    if public_links:
        copied = copy_to_clipboard(links_message(public_links))
        print()
        print("  ССЫЛКИ ДЛЯ ОДНОГРУППНИКОВ (не открывается одна — пусть пробуют другую):")
        for url in public_links.values():
            print(f"    {url}")
        if copied:
            print("  Обе уже скопированы в буфер обмена — просто вставьте в чат.")
        print("  Работают, пока открыто это окно и компьютер не уснул.")
        print("  Если связь оборвётся, здесь появится новая ссылка.")
    elif public_requested:
        print("  Ссылки получить не удалось — сайт доступен только на этом компьютере.")
        print("  Проверьте интернет и запустите start-public.bat ещё раз.")
    print()
    print("  Демо-вход: manager / manager123, сотрудники ivan, maria, peter, olga / 123456")
    print("  Остановить: Ctrl+C или закрыть это окно")
    print("=" * BANNER_WIDTH)


def main():
    parser = argparse.ArgumentParser(description="Запуск ShiftGrid")
    parser.add_argument("--public", action="store_true", help="открыть доступ по ссылке из интернета")
    args = parser.parse_args()

    disable_quick_edit()
    app = create_app({"PUBLIC_MODE": args.public})
    explicit_port = os.environ.get("PORT")
    port = int(explicit_port) if explicit_port else find_free_port(FIRST_PORT)
    local_url = f"http://{HOST}:{port}"
    public_links = start_public_links(port) if args.public else {}
    print_banner(local_url, public_links, args.public)

    # Если порт задан снаружи (PORT), запуском управляет другая программа — браузер не открываем.
    if not explicit_port and os.environ.get("SHIFTGRID_NO_BROWSER") != "1":
        threading.Timer(BROWSER_DELAY_SECONDS, webbrowser.open, args=(local_url,)).start()

    app.run(host=HOST, port=port, debug=os.environ.get("FLASK_DEBUG") == "1")


if __name__ == "__main__":
    main()

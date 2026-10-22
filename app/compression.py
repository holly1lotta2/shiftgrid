"""Сжатие ответов gzip и долгий кэш статики — сайт быстрее открывается через туннель."""
import gzip
import os

from flask import request, url_for

COMPRESSIBLE_TYPES = ("text/", "application/javascript", "application/json", "image/svg+xml")
MIN_COMPRESS_BYTES = 1024
GZIP_LEVEL = 6
STATIC_CACHE_SECONDS = 365 * 24 * 60 * 60


def static_url(app, filename):
    """Адрес статики с версией по времени изменения файла: кэш вечный, обновления видны сразу."""
    path = os.path.join(app.static_folder, filename)
    try:
        version = int(os.path.getmtime(path))
    except OSError:
        version = 0
    return url_for("static", filename=filename, v=version)


def init_app(app):
    if app.config.get("SEND_FILE_MAX_AGE_DEFAULT") is None:
        app.config["SEND_FILE_MAX_AGE_DEFAULT"] = STATIC_CACHE_SECONDS
    app.add_template_global(lambda filename: static_url(app, filename), "static_url")

    @app.after_request
    def compress(response):
        if (response.status_code != 200
                or "gzip" not in request.headers.get("Accept-Encoding", "")
                or "Content-Encoding" in response.headers
                or not response.mimetype.startswith(COMPRESSIBLE_TYPES)):
            return response
        response.direct_passthrough = False
        data = response.get_data()
        if len(data) < MIN_COMPRESS_BYTES:
            return response
        response.set_data(gzip.compress(data, compresslevel=GZIP_LEVEL))
        response.headers["Content-Encoding"] = "gzip"
        response.vary.add("Accept-Encoding")
        return response

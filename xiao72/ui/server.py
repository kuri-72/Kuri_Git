"""本地 UI 服务：静态页 + SSE 推事件 + 设置读写。

只绑 127.0.0.1，不暴露到局域网（里面有 API Key 的读取入口）。
"""
from __future__ import annotations

import json
import queue

from flask import Flask, Response, jsonify, request, send_from_directory, stream_with_context

from . import settings as st


def _sse(event: dict) -> str:
    return "data: %s\n\n" % json.dumps(event, ensure_ascii=False)


def create_app(bus, runtime) -> Flask:
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    app.config["JSON_AS_ASCII"] = False

    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/events")
    def events():
        def gen():
            q = bus.subscribe()
            try:
                for e in bus.snapshot():
                    yield _sse(e)
                yield _sse({"t": "state", "v": runtime.state})
                while True:
                    try:
                        e = q.get(timeout=15)
                        yield _sse(e)
                    except queue.Empty:
                        yield ": ping\n\n"
            finally:
                bus.unsubscribe(q)

        return Response(
            stream_with_context(gen()),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/settings")
    def get_settings():
        data = st.load()
        return jsonify({
            "settings": data,
            "voices": st.VOICES,
            "rate": st.rate_to_percent(data.get("tts_rate", "+0%")),
            "volume": st.rate_to_percent(data.get("tts_volume", "+0%")),
        })

    @app.post("/api/settings")
    def post_settings():
        patch = request.get_json(force=True, silent=True) or {}
        data = st.save(patch)
        runtime.apply_settings(data)
        return jsonify({
            "ok": True,
            "settings": data,
            "rate": st.rate_to_percent(data.get("tts_rate", "+0%")),
            "volume": st.rate_to_percent(data.get("tts_volume", "+0%")),
        })

    @app.post("/api/cancel")
    def post_cancel():
        runtime.request_cancel()
        return jsonify({"ok": True})

    return app

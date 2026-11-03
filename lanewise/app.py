"""Lanewise web app: one page plus a JSON endpoint."""
import os
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from .analysis import BENCH, build_report
from .riot import PLATFORMS, Riot, RiotError

STATIC = Path(__file__).resolve().parent / "static"


def load_env(path=".env"):
    """Minimal .env reader so the app has no extra dependency for it."""
    p = Path(path)
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


def create_app():
    load_env()
    app = Flask(__name__, static_folder=str(STATIC), static_url_path="/static")
    riot = Riot()

    @app.get("/")
    def index():
        return send_from_directory(STATIC, "index.html")

    @app.get("/api/meta")
    def meta():
        return jsonify({"platforms": {k: v[1] for k, v in PLATFORMS.items()}, "benchmark_games": BENCH["games"]})

    @app.get("/api/report")
    def report():
        riot_id = request.args.get("riot_id", "").strip()
        platform = request.args.get("platform", "euw1")
        count = max(5, min(int(request.args.get("count", 20)), 40))
        if platform not in PLATFORMS:
            return jsonify(error="Unknown region"), 400
        try:
            return jsonify(build_report(riot, platform, riot_id, count))
        except ValueError as e:
            return jsonify(error=str(e)), 400
        except LookupError as e:
            return jsonify(error=str(e)), 404
        except RiotError as e:
            return jsonify(error=str(e)), 502

    return app


def main():
    port = int(os.environ.get("PORT", 5000))
    create_app().run(host="127.0.0.1", port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()

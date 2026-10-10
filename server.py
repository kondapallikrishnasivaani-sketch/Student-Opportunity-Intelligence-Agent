"""Local web server: serves index.html and exposes the existing agent pipeline as an API.

Run with:
    python server.py
"""
from __future__ import annotations

import json
import os
import queue
import sys
import threading

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)



def _load_saved_key() -> None:
    """Load SERPAPI_KEY once from a local file so it never has to be typed again.

    Looks, in order, at: an existing environment variable, `.env`, `.streamlit/secrets.toml`.
    """
    if os.environ.get("SERPAPI_KEY", "").strip():
        return
    env_path = os.path.join(ROOT, ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8-sig") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    if k.strip() == "SERPAPI_KEY" and v.strip().strip("\"'"):
                        os.environ["SERPAPI_KEY"] = v.strip().strip("\"'")
                        return
    toml_path = os.path.join(ROOT, ".streamlit", "secrets.toml")
    if os.path.exists(toml_path):
        try:
            import tomllib
            with open(toml_path, "rb") as fh:
                key = str(tomllib.load(fh).get("SERPAPI_KEY", "")).strip()
            if key:
                os.environ["SERPAPI_KEY"] = key
        except Exception:
            pass


_load_saved_key()

from flask import Flask, Response, abort, jsonify, request, send_file

import serpapi_client
from agent import run_agent
from models import StudentProfile

app = Flask(__name__)


def _list(v) -> list[str]:
    if isinstance(v, str):
        v = v.split(",")
    return [str(s).strip() for s in (v or []) if str(s).strip()]


@app.get("/")
def index():
    return send_file(os.path.join(ROOT, "index.html"))


@app.get("/assets/<name>")
def assets(name):
    if name not in {"dashboard.js", "dashboard.css"}:
        abort(404)
    return send_file(os.path.join(ROOT, name), max_age=0)


@app.get("/api/status")
def status():
    return jsonify(configured=serpapi_client.is_configured())


@app.post("/api/search")
def search():
    body = request.get_json(silent=True) or {}
    p = body.get("profile") or {}
    d = StudentProfile()
    profile = StudentProfile(
        name=str(p.get("name", d.name)), degree=str(p.get("degree", d.degree)),
        branch=str(p.get("branch", d.branch)), year=str(p.get("year", d.year)),
        skills=_list(p.get("skills", d.skills)), interests=_list(p.get("interests", d.interests)),
        location=str(p.get("location", d.location)),
        opportunity_types=_list(p.get("opportunity_types", d.opportunity_types)),
    )
    req = str(body.get("request", ""))
    q: queue.Queue = queue.Queue()

    def work():
        try:
            opps, queries = run_agent(profile, req, progress=lambda m: q.put({"type": "progress", "message": m}))
            out = []
            for o in opps:
                item = o.to_dict()
                item["is_new"] = o.is_new
                out.append(item)
            q.put({"type": "done", "opportunities": out, "queries": queries})
        except serpapi_client.SerpApiError as e:
            q.put({"type": "error", "kind": e.kind, "message": e.message})
        except Exception as e:  # keep the stream well-formed whatever happens
            q.put({"type": "error", "kind": "error", "message": f"Unexpected error: {e}"})
        q.put(None)

    threading.Thread(target=work, daemon=True).start()

    def stream():
        while (item := q.get()) is not None:
            yield json.dumps(item) + "\n"

    return Response(stream(), mimetype="application/x-ndjson",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Open http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
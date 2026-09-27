"""RiskScope single-node HTTP service; run with python -m app.server."""

import argparse
import hmac
import json
import logging
import os
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import __version__
from .model import RAW_FEATURES, load_bundle, predict_many
from .monitoring import summarize
from .store import Store

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "web"
MAX_BODY = 2_000_000
MAX_BATCH = 500
LOGGER = logging.getLogger("riskscope")


def load_local_env():
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line and not line.lstrip().startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


class Handler(BaseHTTPRequestHandler):
    api_key = ""
    admin_key = ""
    store = None
    model_path = ""

    def log_message(self, format, *args):
        # Suppress built-in access log (which includes unsanitized paths).
        pass

    def _headers(self, code, content_type, size):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(size))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers()

    def _send(self, code, payload, content_type="application/json; charset=utf-8"):
        raw = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8") if isinstance(payload, (dict,list)) else payload
        self._headers(code, content_type, len(raw))
        self.wfile.write(raw)

    def _error(self, code, message):
        self._send(code, {"error": message})

    def _auth(self, admin=False):
        supplied = self.headers.get("X-Admin-Key" if admin else "X-API-Key", "")
        secret = self.admin_key if admin else self.api_key
        if not hmac.compare_digest(supplied, secret):
            self._error(401, "Invalid or missing API key")
            return False
        return True

    def _json_body(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Invalid Content-Length") from exc
        if not 0 < length <= MAX_BODY:
            raise ValueError("Request must contain 1 to 2,000,000 bytes")
        if "application/json" not in self.headers.get("Content-Type", ""):
            raise ValueError("Content-Type must be application/json")
        try:
            return json.loads(self.rfile.read(length))
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid JSON") from exc

    def _serve_file(self, filename, content_type):
        raw = (STATIC / filename).read_bytes()
        self._send(200, raw, content_type)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            return self._serve_file("index.html", "text/html; charset=utf-8")
        if path == "/app.css":
            return self._serve_file("app.css", "text/css; charset=utf-8")
        if path == "/app.js":
            return self._serve_file("app.js", "text/javascript; charset=utf-8")
        if path == "/healthz":
            try:
                bundle = load_bundle(self.model_path)
                self.store.counts()
                return self._send(200, {"status":"ok","app_version":__version__,
                                        "model_version":bundle["version"]})
            except Exception:
                return self._error(503, "Model or database unavailable")
        if path == "/api/schema":
            return self._send(200, {"features": RAW_FEATURES, "model_task":
                                     "Next-month credit card payment default probability",
                                     "max_batch":MAX_BATCH})
        if path == "/api/monitor":
            if not self._auth(admin=True): return
            try:
                days = int(parse_qs(urlparse(self.path).query).get("days", ["30"])[0])
                if not 1 <= days <= 365: raise ValueError("days must be 1..365")
                bundle = load_bundle(self.model_path)
                data = summarize(self.store.recent(days), bundle["reference_scores"], days)
                data["model_version"] = bundle["version"]
                return self._send(200, data)
            except ValueError as exc:
                return self._error(400, str(exc))
        if path == "/metrics":
            if not self._auth(admin=True): return
            counts = self.store.counts()
            metrics = ("# HELP riskscope_predictions_total Persisted predictions\n"
                       "# TYPE riskscope_predictions_total gauge\n"
                       f"riskscope_predictions_total {counts['total']}\n"
                       "# HELP riskscope_labeled_total Predictions with observed outcome\n"
                       "# TYPE riskscope_labeled_total gauge\n"
                       f"riskscope_labeled_total {counts['labeled']}\n")
            return self._send(200, metrics.encode("utf-8"),
                              "text/plain; version=0.0.4; charset=utf-8")
        return self._error(404, "Route not found")

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in ("/api/predict", "/api/batch", "/api/outcome"):
            return self._error(404, "Route not found")
        if not self._auth(admin=path=="/api/outcome"): return
        started = time.monotonic()
        status = 200
        try:
            body = self._json_body()
            if path == "/api/outcome":
                if not isinstance(body, dict) or set(body) != {"prediction_id", "actual_default"}:
                    raise ValueError("Expected prediction_id and actual_default")
                if not isinstance(body["prediction_id"], str):
                    raise ValueError("prediction_id must be a string")
                try: uuid.UUID(body["prediction_id"])
                except ValueError as exc: raise ValueError("prediction_id must be a UUID") from exc
                if type(body["actual_default"]) is not int or body["actual_default"] not in (0,1):
                    raise ValueError("actual_default must be 0 or 1")
                self.store.add_outcome(body["prediction_id"], body["actual_default"])
                return self._send(200, {"status":"recorded"})
            if path == "/api/predict":
                scores, version = predict_many([body], self.model_path)
                ids = self.store.add_scores(scores, version)
                return self._send(200, {"prediction_id":ids[0],
                                        "default_probability_next_month":round(scores[0],6),
                                        "model_version":version,
                                        "notice":"Research model; not a collection decision"})
            if not isinstance(body, dict) or set(body) != {"records"} or not isinstance(body["records"],list):
                raise ValueError("Expected JSON object with records array")
            if not 1 <= len(body["records"]) <= MAX_BATCH:
                raise ValueError(f"Batch size must be 1..{MAX_BATCH}")
            scores, version = predict_many(body["records"], self.model_path)
            batch_id = str(uuid.uuid4())
            ids = self.store.add_scores(scores, version, batch_id)
            return self._send(200, {"batch_id":batch_id, "model_version":version,
                                    "results":[{"prediction_id":i,"default_probability_next_month":round(p,6)}
                                               for i,p in zip(ids,scores)]})
        except KeyError as exc:
            status = 404
            return self._error(status, str(exc))
        except ValueError as exc:
            status = 400
            return self._error(status, str(exc))
        except Exception:
            status = 500
            LOGGER.exception("Unhandled server error")
            return self._error(status, "Internal error")
        finally:
            LOGGER.info(json.dumps({"route":path,"status":status,
                                    "duration_ms":round((time.monotonic()-started)*1000,1)}))


def main():
    load_local_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.environ.get("APP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("APP_PORT", "8000")))
    args = parser.parse_args()
    api_key, admin_key = os.environ.get("APP_API_KEY", ""), os.environ.get("APP_ADMIN_KEY", "")
    if min(len(api_key),len(admin_key)) < 16 or api_key == admin_key:
        raise SystemExit("Set distinct APP_API_KEY and APP_ADMIN_KEY (at least 16 characters each)")
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    Handler.api_key, Handler.admin_key = api_key, admin_key
    Handler.model_path = os.environ.get("MODEL_PATH", str(ROOT / "models/credit_default_model.joblib"))
    Handler.store = Store(os.environ.get("DB_PATH", str(ROOT / "state/predictions.sqlite3")))
    load_bundle(Handler.model_path)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"RiskScope listening on http://{args.host}:{server.server_address[1]}",flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()


if __name__ == "__main__":
    main()

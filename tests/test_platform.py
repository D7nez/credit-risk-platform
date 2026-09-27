"""Real model and HTTP integration checks; no network service required."""
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app.model import RAW_FEATURES, feature_frame, load_bundle, predict_many, validate_record
from app.server import Handler, ROOT
from app.store import Store

SAMPLE = {
    "LIMIT_BAL": 20000, "PAY_0": 2, "PAY_2": 2, "PAY_3": -1,
    "PAY_4": -1, "PAY_5": -2, "PAY_6": -2,
    "BILL_AMT1": 3913, "BILL_AMT2": 3102, "BILL_AMT3": 689,
    "BILL_AMT4": 0, "BILL_AMT5": 0, "BILL_AMT6": 0,
    "PAY_AMT1": 0, "PAY_AMT2": 689, "PAY_AMT3": 0,
    "PAY_AMT4": 0, "PAY_AMT5": 0, "PAY_AMT6": 0,
}
MODEL = str(ROOT / "models" / "credit_default_model.joblib")


class PlatformTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        Handler.store = Store(str(Path(cls.temp.name) / "test.sqlite3"))
        Handler.model_path = MODEL
        Handler.api_key = "test-api-key-123456789"
        Handler.admin_key = "test-admin-key-123456789"
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        cls.temp.cleanup()

    def call(self, path, body=None, key=None):
        headers = {}
        if key == "api": headers["X-API-Key"] = Handler.api_key
        if key == "admin": headers["X-Admin-Key"] = Handler.admin_key
        if body is not None: headers["Content-Type"] = "application/json"
        payload = json.dumps(body).encode() if body is not None else None
        request = Request(self.base + path, data=payload, headers=headers)
        try:
            with urlopen(request, timeout=10) as response:
                raw, status = response.read(), response.status
        except HTTPError as error:
            raw, status = error.read(), error.code
        return status, json.loads(raw)

    def test_full_flow(self):
        self.assertEqual(self.call("/healthz")[0], 200)
        self.assertEqual(self.call("/api/predict", SAMPLE)[0], 401)
        status, result = self.call("/api/predict", SAMPLE, "api")
        self.assertEqual(status, 200)
        self.assertAlmostEqual(result["default_probability_next_month"], 0.709864, places=3)
        self.assertEqual(self.call("/api/predict", {**SAMPLE, "PAY_AMT1": -1}, "api")[0], 400)
        self.assertEqual(self.call("/api/predict", {**SAMPLE, "irrelevant": 1}, "api")[0], 400)
        self.assertEqual(self.call("/api/monitor", key="api")[0], 401)
        self.assertEqual(self.call("/api/outcome", {"prediction_id":result["prediction_id"],"actual_default":1}, "api")[0], 401)
        status, batch = self.call("/api/batch", {"records":[SAMPLE]*100}, "api")
        self.assertEqual(status, 200)
        self.assertEqual(len(batch["results"]), 100)
        self.assertEqual(self.call("/api/batch", {"records":[SAMPLE]*501}, "api")[0], 400)
        for index, item in enumerate(batch["results"][:32]):
            outcome = {"prediction_id":item["prediction_id"],"actual_default":index % 2}
            self.assertEqual(self.call("/api/outcome", outcome, "admin")[0], 200)
        self.assertEqual(self.call("/api/outcome", outcome, "admin")[0], 400)
        status, monitor = self.call("/api/monitor", key="admin")
        self.assertEqual(status, 200)
        self.assertEqual(monitor["predictions"], 101)
        self.assertEqual(monitor["labeled"], 32)
        self.assertEqual(monitor["drift"]["status"], "available")
        self.assertEqual(monitor["performance"]["status"], "available")
        self.assertEqual(self.call("/api/monitor?days=0", key="admin")[0], 400)
        self.assertEqual(self.call("/api/schema")[1]["features"], RAW_FEATURES)
        req = Request(self.base + "/metrics", headers={"X-Admin-Key":Handler.admin_key})
        with urlopen(req, timeout=5) as response:
            self.assertIn(b"riskscope_predictions_total 101", response.read())
        with urlopen(self.base + "/", timeout=5) as response:
            self.assertIn("مراقبة النموذج", response.read().decode())

    def test_model_schema(self):
        cleaned = validate_record(SAMPLE)
        features = feature_frame([cleaned])
        self.assertEqual(list(features), load_bundle(MODEL)["feature_names"])
        self.assertAlmostEqual(predict_many([SAMPLE], MODEL)[0][0], 0.709864, places=3)


if __name__ == "__main__":
    unittest.main()

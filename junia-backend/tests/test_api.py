import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import xarray as xr
from fastapi.testclient import TestClient

from app.main import app


class APITests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)

        output_patch = patch(
            "app.services.BACKEND",
            Path(temporary.name),
        )
        output_patch.start()
        self.addCleanup(output_patch.stop)

        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_prepare_status_and_download(self):
        response = self.client.post("/prepare", json={
            "dataset_id": "stancomb-wills-prepared",
            "region_id": "stancomb-wills",
        })
        self.assertEqual(response.status_code, 201, response.text)
        result = response.json()
        self.assertEqual(result["cells"], 250000)

        url = f"/preparations/{result['id']}"
        status = self.client.get(url)
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["status"], "completed")

        download = self.client.get(f"{url}/output")
        self.assertEqual(download.status_code, 200)
        with xr.open_dataset(
            io.BytesIO(download.content), engine="scipy"
        ) as dataset:
            dataset.load()
            self.assertEqual(dict(dataset.sizes), {"y": 500, "x": 500})
            self.assertIn("bed", dataset)

    def test_unsupported_dataset_rejected(self):
        response = self.client.post("/prepare", json={
            "dataset_id": "unsupported",
            "region_id": "stancomb-wills",
        })
        self.assertEqual(response.status_code, 422)

    def test_invalid_bounds_rejected(self):
        response = self.client.post("/prepare", json={
            "dataset_id": "stancomb-wills-prepared",
            "region_id": "stancomb-wills",
            "bbox": [500, 1000, 0, 1500],
        })
        self.assertEqual(response.status_code, 422)

    def test_missing_preparation(self):
        url = f"/preparations/{uuid4()}"
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(
            self.client.get(f"{url}/output").status_code, 404
        )

    def test_invalid_id_rejected(self):
        response = self.client.get("/preparations/not-a-uuid")
        self.assertEqual(response.status_code, 422)
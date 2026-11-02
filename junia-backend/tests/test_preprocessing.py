import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from data_pipeline.preprocessing import REQUIRED, build_grid, export_grid


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / "grid.csv"
        self.frame = pd.DataFrame([{**{n: 1.0 for n in REQUIRED}, "x": x, "y": y,
                                    "bed": np.nan if x == 0 else y + x, "highvel_mask": False}
                                   for y in [1000, 1500] for x in [0, 500]])
        self.frame.sample(frac=1, random_state=4).to_csv(self.source, index=False)

    def test_coordinate_order_and_missing_roundtrip(self):
        output, report_path, report = export_grid(self.source, Path(self.temp.name) / "test.nc")
        self.assertTrue(report_path.exists())
        self.assertTrue(report["roundtrip_verified"])
        with xr.open_dataset(output, engine="scipy") as ds:
            self.assertEqual(ds.bed.dims, ("y", "x"))
            self.assertEqual(float(ds.bed.sel(x=500, y=1000)), 1500)
            self.assertTrue(np.isnan(ds.bed.sel(x=0, y=1000)))
            self.assertEqual(report["missing_by_variable"]["bed"], 2)

    def test_duplicates_rejected(self):
        pd.concat([self.frame, self.frame.iloc[:1]]).to_csv(self.source, index=False)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            build_grid(self.source)

    def test_incomplete_grid_rejected(self):
        self.frame.iloc[:-1].to_csv(self.source, index=False)
        with self.assertRaisesRegex(ValueError, "missing coordinate"):
            build_grid(self.source)

    def test_empty_crop_rejected(self):
        with self.assertRaisesRegex(ValueError, "no cells"):
            build_grid(self.source, [10000, 10000, 11000, 11000])

    def test_bad_spacing_rejected(self):
        self.frame.loc[self.frame.x == 500, "x"] = 501
        self.frame.to_csv(self.source, index=False)
        with self.assertRaisesRegex(ValueError, "spacing"):
            build_grid(self.source)

    def test_missing_column_rejected(self):
        self.frame.drop(columns="bed").to_csv(self.source, index=False)
        with self.assertRaisesRegex(ValueError, "required columns"):
            build_grid(self.source)


if __name__ == "__main__":
    unittest.main()

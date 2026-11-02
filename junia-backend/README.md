# Antarctic data preparation backend

## Prepare the repository's Stancomb-Wills grid

Run from `junia-backend/` with the Python virtual environment activated:

```powershell
python -m pip install -r requirements.txt
python -m data_pipeline.preprocessing
python -m unittest discover -s tests -v
```

The default input is `../MCMC_implementation/data/StancombWillsDataGridded.csv`.
Outputs are `generated/stancomb_wills.nc` and `generated/stancomb_wills.validation.json`.
Generated data and the temporary Bedmap catalog are ignored by Git.

The pipeline checks required columns, numeric values, finite coordinates, unique
coordinate pairs, complete rectangular coverage, and 500 m spacing. It orders
values by their actual `(y,x)` coordinates, preserves all layers and missing
measurements, and reopens NetCDF to verify every value against the prepared grid.
The report includes source SHA-256, bounds, shape, and missing-value counts.

Optional crop, in the source grid's meter coordinates (inclusive cell centers):

```powershell
python -m data_pipeline.preprocessing --bbox -600250 1350250 -350750 1599750
```

No interpolation, zero filling, vertical correction, or coordinate transformation
is applied. CRS and vertical datum remain explicitly unconfirmed in the export.
Only height/thickness column units are labeled as meters. Other variable units
and mask classes require source confirmation. This is a validated export of the
prepared input, not a claim of scientific calibration or MCMC integration.

Source Cooperative exploratory checks established anonymous S3 access and BAS
survey coverage, but those measurements are not merged into the repository grid.
`source_cooperative.py` remains reserved for a future independent ingestion stage.

## API

```powershell
uvicorn app.main:app --reload
```

The existing root endpoint reports application availability. Data preparation is
run explicitly with the CLI above; it does not run during API startup.

## Docker

Build from this directory: `docker build -t junia-backend .`
Run API: `docker run --rm -p 8000:8000 junia-backend`
To run preparation, mount repository input read-only and generated output writable,
then use `python -m data_pipeline.preprocessing --input /input/StancombWillsDataGridded.csv --output /output/stancomb_wills.nc`.


from fastapi import FastAPI
from data_pipeline.preprocessing import load_region
from fastapi import HTTPException
from app.schemas import PreparationRequest
from app.services import prepare_dataset
from app.services import get_preparation
from uuid import UUID
from fastapi.responses import FileResponse
from app.services import get_preparation_output

app = FastAPI(title="Antarctic Data Preparation Platform")

@app.get("/")
def home():
    return {
        "message": "Junia's Antarctic backend is running!",
        "status": "ready"
    }

@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "antarctic-data-backend",
        "scientific_metadata_status": "provisional",
    }

@app.get("/datasets")
def list_datasets():
    return {
        "datasets": [
            {
                "id": "stancomb-wills-prepared",
                "name": "Stancomb-Wills prepared repository grid",
                "region_id": "stancomb-wills",
                "source_type": "repository_csv",
                "resolution_m": 500,
                "scientific_metadata_status": "provisional",
            }
        ]
    }

@app.get("/regions")
def list_regions():
    return {"regions": [load_region()]}

@app.post("/prepare", status_code=201)
def prepare(request: PreparationRequest):
    try:
        return prepare_dataset(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail="Preparation failed while reading or saving files.",
        ) from exc

@app.get("/preparations/{preparation_id}")
def preparation_status(preparation_id: UUID):
    try:
        return get_preparation(preparation_id)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Preparation not found",
        ) from exc

@app.get("/preparations/{preparation_id}/output")
def download_preparation(preparation_id: UUID):
    try:
        output = get_preparation_output(preparation_id)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Preparation or output not found",
        ) from exc

    return FileResponse(
        path=output,
        media_type="application/x-netcdf",
        filename=f"stancomb-wills-{preparation_id}.nc",
    )



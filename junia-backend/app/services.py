import json
from uuid import uuid4
from uuid import UUID

from app.schemas import PreparationRequest
from data_pipeline.preprocessing import BACKEND, export_grid


def prepare_dataset(request: PreparationRequest):
    preparation_id = str(uuid4())
    folder = BACKEND / "generated" / "preparations" / preparation_id

    _, _, report = export_grid(
        output=folder / "dataset.nc",
        bbox=request.bbox,
    )

    result = {
        "id": preparation_id,
        "status": "completed",
        "dataset_id": request.dataset_id,
        "region_id": request.region_id,
        "cells": report["cells"],
        "scientific_metadata_status": "provisional",
    }

    (folder / "status.json").write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )
    return result

def get_preparation(preparation_id: UUID):
    folder = BACKEND / "generated" / "preparations" / str(preparation_id)
    status_file = folder / "status.json"

    if not status_file.is_file():
        raise FileNotFoundError("Preparation not found")

    return json.loads(status_file.read_text(encoding="utf-8"))

def get_preparation_output(preparation_id: UUID):
    get_preparation(preparation_id)
    output = (
        BACKEND / "generated" / "preparations"
        / str(preparation_id) / "dataset.nc"
    )
    if not output.is_file():
        raise FileNotFoundError("Output not found")
    return output

import math
from typing import Literal

from pydantic import BaseModel, model_validator


class PreparationRequest(BaseModel):
    dataset_id: Literal["stancomb-wills-prepared"]
    region_id: Literal["stancomb-wills"]
    bbox: tuple[float, float, float, float] | None = None

    @model_validator(mode="after")
    def validate_bbox(self):
        if self.bbox is not None:
            xmin, ymin, xmax, ymax = self.bbox
            if not all(math.isfinite(v) for v in self.bbox):
                raise ValueError("Bounds must be finite numbers")
            if xmin >= xmax or ymin >= ymax:
                raise ValueError("Bounds must be xmin, ymin, xmax, ymax")
        return self
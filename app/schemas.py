from datetime import datetime
from typing import Annotated

from pydantic import (  # pyright: ignore[reportMissingImports]
    BaseModel,  # pyright: ignore[reportUnknownVariableType]
    Field,  # pyright: ignore[reportUnknownVariableType]
)


class PunchRequest(BaseModel):  # pyright: ignore[reportUntypedBaseClass]
    employee_id: Annotated[str, Field(min_length=1)]


class CorrectionRequest(BaseModel):  # pyright: ignore[reportUntypedBaseClass]
    punch_in: datetime | None = None
    punch_out: datetime | None = None
    reason: Annotated[str, Field(min_length=5, max_length=500)]
    corrected_by: Annotated[str, Field(min_length=1)]

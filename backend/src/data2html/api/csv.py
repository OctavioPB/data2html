"""CSV upload: preview with suggested types → confirmation → Parquet table."""

from __future__ import annotations

from fastapi import APIRouter, UploadFile, status

from data2html.api.deps import CsvDep, MetaDep
from data2html.api.schemas import TableOut
from data2html.sources.csv_source import ConfirmRequest, CsvPreview

router = APIRouter(prefix="/api/csv", tags=["csv"])


@router.post("/preview")
def csv_preview(file: UploadFile, csv: CsvDep) -> CsvPreview:
    upload_id = csv.stage(file.file, file.filename or "data.csv")
    return csv.preview(upload_id)


@router.post("/confirm", status_code=status.HTTP_201_CREATED)
def csv_confirm(req: ConfirmRequest, csv: CsvDep, meta: MetaDep) -> TableOut:
    return TableOut.of(csv.confirm(req), meta.get(csv.id, req.table))


@router.delete("/uploads/{upload_id}", status_code=status.HTTP_204_NO_CONTENT)
def csv_discard(upload_id: str, csv: CsvDep) -> None:
    csv.discard(upload_id)

"""Subida de CSV: vista previa con tipos sugeridos → confirmación → tabla Parquet."""

from __future__ import annotations

from fastapi import APIRouter, UploadFile, status

from data2html.api.deps import CsvDep, MetaDep, http_error
from data2html.api.schemas import TableOut
from data2html.sources.csv_source import ConfirmRequest, CsvError, CsvPreview

router = APIRouter(prefix="/api/csv", tags=["csv"])


@router.post("/preview")
def csv_preview(file: UploadFile, csv: CsvDep) -> CsvPreview:
    try:
        upload_id = csv.stage(file.file, file.filename or "datos.csv")
        return csv.preview(upload_id)
    except CsvError as e:
        raise http_error(e) from e


@router.post("/confirm", status_code=status.HTTP_201_CREATED)
def csv_confirm(req: ConfirmRequest, csv: CsvDep, meta: MetaDep) -> TableOut:
    try:
        return TableOut.of(csv.confirm(req), meta.get(csv.id, req.table))
    except CsvError as e:
        raise http_error(e) from e


@router.delete("/uploads/{upload_id}", status_code=status.HTTP_204_NO_CONTENT)
def csv_discard(upload_id: str, csv: CsvDep) -> None:
    try:
        csv.discard(upload_id)
    except CsvError as e:
        raise http_error(e) from e

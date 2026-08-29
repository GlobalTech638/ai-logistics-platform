from fastapi import APIRouter, File, HTTPException, UploadFile

from app.ingestion.csv_import import parse_fleet_csv

router = APIRouter(prefix="/api/v1/ingestion", tags=["ingestion"])


@router.post("/fleet/csv")
async def import_fleet_csv(file: UploadFile = File(...)) -> dict:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported")

    content = (await file.read()).decode("utf-8-sig")
    try:
        records = parse_fleet_csv(content)
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="CSV must be UTF-8 encoded") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {"records_validated": len(records), "records": records}

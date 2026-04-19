import io
import logging

from fastapi import APIRouter, UploadFile, File, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/parquet", tags=["parquet"])

MAX_PREVIEW_ROWS = 200


@router.post("/read")
async def read_parquet(file: UploadFile = File(...)):
    """Read a Parquet file and return schema + first N rows as JSON."""
    try:
        import pyarrow.parquet as pq
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="pyarrow is not installed. Run: pip install pyarrow",
        )

    if not file.filename or not file.filename.lower().endswith(".parquet"):
        raise HTTPException(status_code=400, detail="Please upload a .parquet file")

    try:
        contents = await file.read()
        buf = io.BytesIO(contents)
        table = pq.read_table(buf)

        schema = [
            {"name": field.name, "type": str(field.type)}
            for field in table.schema
        ]
        columns = [field.name for field in table.schema]
        num_rows = table.num_rows

        # Convert first N rows to list of dicts
        preview = table.slice(0, min(MAX_PREVIEW_ROWS, num_rows))
        rows = preview.to_pydict()
        # Transpose from {col: [values]} to [{col: val}, ...]
        row_list = [
            {col: rows[col][i] for col in columns}
            for i in range(preview.num_rows)
        ]

        return {
            "columns": columns,
            "schema": schema,
            "numRows": num_rows,
            "rows": row_list,
        }
    except Exception as e:
        logger.exception("Error reading parquet file")
        raise HTTPException(status_code=400, detail=f"Error reading parquet file: {e}")

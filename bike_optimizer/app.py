import json
import os
import shutil
import sys
import tempfile
import time

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse

# Allow running from the bike_optimizer directory directly
sys.path.insert(0, os.path.dirname(__file__))

from agent.react_agent import run_agent  # noqa: E402
from tools.csv_sql import set_csv_path  # noqa: E402

app = FastAPI(
    title="Citi Bike Pass Optimizer",
    description="Single-Agent ReAct + MRKL Bike-Share Cost Optimizer (NYC Citi Bike)",
)

# Temp dir for uploaded CSVs
UPLOAD_DIR = tempfile.mkdtemp(prefix="citibike_")


@app.get("/", response_class=HTMLResponse)
def index():
    """Serve the main web UI."""
    html_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
    with open(html_path) as f:
        return HTMLResponse(content=f.read())


@app.post("/upload")
async def upload_csv(file: UploadFile = File(...)):
    """Upload the Citi Bike trip CSV. Returns confirmation and basic stats."""
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are accepted.")

    # Save to temp dir
    dest_path = os.path.join(UPLOAD_DIR, "trips.csv")
    with open(dest_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Register with csv_sql tool
    set_csv_path(dest_path)

    # Quick preview using DuckDB
    from tools.csv_sql import csv_sql

    count_result = csv_sql("SELECT COUNT(*) as total_rows FROM trips")
    cols_result = csv_sql("SELECT * FROM trips LIMIT 1")

    total_rows = 0
    columns = []
    if count_result.get("success"):
        rows = count_result["data"]["rows"]
        if rows:
            total_rows = rows[0].get("total_rows", 0)
    if cols_result.get("success"):
        rows = cols_result["data"]["rows"]
        if rows:
            columns = list(rows[0].keys())

    return {
        "success": True,
        "filename": file.filename,
        "total_rows": total_rows,
        "columns": columns,
        "message": f"CSV uploaded successfully: {total_rows} rows, {len(columns)} columns.",
    }


@app.post("/run-agent")
async def run_agent_endpoint(pricing_url: str = Form(...)):
    """
    Run the ReAct agent and stream each step as Server-Sent Events (SSE).
    The frontend listens to this stream and renders the timeline in real time.
    """
    from tools.csv_sql import get_csv_path

    if get_csv_path() is None:
        raise HTTPException(
            status_code=400,
            detail="No CSV uploaded. Please upload a Citi Bike trip CSV first.",
        )

    def event_stream():
        try:
            for step in run_agent(pricing_url=pricing_url):
                data = json.dumps(step, default=str)
                yield f"data: {data}\n\n"
                time.sleep(0.05)  # small delay for smooth UI rendering
        except Exception as e:
            error_event = json.dumps({"type": "error", "content": str(e)})
            yield f"data: {error_event}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/health")
def health():
    return {"status": "ok", "service": "Citi Bike Pass Optimizer"}

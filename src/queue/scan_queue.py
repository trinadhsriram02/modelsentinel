import asyncio
import json
import uuid
from datetime import datetime

# ─────────────────────────────────────────
# In-memory async queue for background scanning
# Same pattern as AutonomousSOC's alert_queue
# but adapted for model scanning jobs
# ─────────────────────────────────────────

scan_queue = asyncio.Queue()
scan_results = {}


async def queue_scan(file_path: str, file_name: str,
                     num_classes: int = 10,
                     analyst_id: int = None) -> str:
    """
    Add a model scan job to the background queue.
    Returns scan_id immediately — no waiting.
    Scanning happens in the background.
    """
    scan_id = f"q_{str(uuid.uuid4())[:8]}"

    job = {
        "scan_id": scan_id,
        "file_path": file_path,
        "file_name": file_name,
        "num_classes": num_classes,
        "analyst_id": analyst_id,
        "queued_at": datetime.now().isoformat(),
        "status": "queued"
    }

    # Store initial status so clients can poll
    scan_results[scan_id] = {
        "scan_id": scan_id,
        "status": "queued",
        "file_name": file_name,
        "queued_at": job["queued_at"],
        "message": "Scan queued — processing in background"
    }

    await scan_queue.put(job)
    print(f"Scan {scan_id} queued. Queue size: {scan_queue.qsize()}")
    return scan_id


async def consume_scans():
    """
    Background worker — runs forever processing queued scans.
    Started once at API startup via asyncio.create_task().
    Each scan is run in a thread pool to avoid blocking the event loop.
    """
    from src.scanner.scanner_engine import scan_model
    from src.data.memory_store import save_scan

    print("Scan queue consumer started — waiting for jobs...")

    while True:
        try:
            job = await scan_queue.get()
            scan_id = job["scan_id"]

            print(f"Processing queued scan: {scan_id}")

            # Update status to running
            scan_results[scan_id]["status"] = "running"
            scan_results[scan_id]["started_at"] = datetime.now().isoformat()

            # Run in thread pool — scan_model is synchronous/blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: scan_model(
                    job["file_path"],
                    scan_id,
                    job["num_classes"]
                )
            )

            # Save to database
            save_scan(
                result,
                analyst_id=job.get("analyst_id"),
                file_name=job["file_name"]
            )

            # Store full result for polling
            scan_results[scan_id] = {
                **result,
                "status": "completed",
                "file_name": job["file_name"]
            }

            print(f"Queued scan {scan_id} complete: {result.get('verdict')}")
            scan_queue.task_done()

        except Exception as e:
            print(f"Queue processing error: {e}")
            if "scan_id" in locals():
                scan_results[scan_id]["status"] = "failed"
                scan_results[scan_id]["error"] = str(e)
            await asyncio.sleep(1)


def get_scan_result(scan_id: str) -> dict:
    """
    Get the result of a queued scan by ID.
    Returns status, partial results, or full results.
    """
    if scan_id in scan_results:
        return scan_results[scan_id]
    return {
        "scan_id": scan_id,
        "status": "not_found",
        "message": "Scan ID not found — may have expired from memory"
    }


def get_queue_stats() -> dict:
    """Get current queue statistics."""
    statuses = [r.get("status") for r in scan_results.values()]
    return {
        "queue_size": scan_queue.qsize(),
        "total_processed": len(scan_results),
        "completed": statuses.count("completed"),
        "running": statuses.count("running"),
        "queued": statuses.count("queued"),
        "failed": statuses.count("failed")
    }
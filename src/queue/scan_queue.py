import asyncio
import uuid
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# Tier 2 Fix — capped thread pool
# Without cap: 50 simultaneous scan requests = 50 PyTorch instances
# Each PyTorch scan uses ~2GB RAM = 100GB = OOM crash on HuggingFace
# Cap at 2 workers = max 4GB RAM used, leaving 12GB free
_scan_executor = ThreadPoolExecutor(max_workers=2)

scan_queue = asyncio.Queue()
scan_results = {}


async def queue_scan(file_path: str, file_name: str,
                     num_classes: int = 10,
                     analyst_id: int = None) -> str:
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
    from src.scanner.scanner_engine import scan_model
    from src.data.memory_store import save_scan

    print("Scan queue consumer started")

    while True:
        try:
            job = await scan_queue.get()
            scan_id = job["scan_id"]

            scan_results[scan_id]["status"] = "running"
            scan_results[scan_id]["started_at"] = datetime.now().isoformat()

            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                _scan_executor,
                lambda: scan_model(
                    job["file_path"],
                    scan_id,
                    job["num_classes"]
                )
            )

            save_scan(
                result,
                analyst_id=job.get("analyst_id"),
                file_name=job["file_name"]
            )

            scan_results[scan_id] = {
                **result,
                "status": "completed",
                "file_name": job["file_name"]
            }

            print(f"Queue scan {scan_id} done: {result.get('verdict')}")
            scan_queue.task_done()

        except Exception as e:
            print(f"Queue error: {e}")
            if "scan_id" in locals():
                scan_results[scan_id]["status"] = "failed"
                scan_results[scan_id]["error"] = str(e)
            await asyncio.sleep(1)


def get_scan_result(scan_id: str) -> dict:
    if scan_id in scan_results:
        return scan_results[scan_id]
    return {
        "scan_id": scan_id,
        "status": "not_found",
        "message": "Scan ID not found"
    }


def get_queue_stats() -> dict:
    statuses = [r.get("status") for r in scan_results.values()]
    return {
        "queue_size": scan_queue.qsize(),
        "total_processed": len(scan_results),
        "completed": statuses.count("completed"),
        "running": statuses.count("running"),
        "queued": statuses.count("queued"),
        "failed": statuses.count("failed")
    }
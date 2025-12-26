from __future__ import annotations

import os
from datetime import datetime

from graph.builder import CHECKPOINTS_DB
from logger import logger

RUN_IDS_LOG = os.path.join(os.path.dirname(__file__), "run_ids.log")


def record_run_id(run_id: str, user_input: str) -> None:
    """Append run_id to a local log for later listing."""
    try:
        os.makedirs(os.path.dirname(RUN_IDS_LOG), exist_ok=True)
        ts = datetime.utcnow().isoformat()
        with open(RUN_IDS_LOG, "a", encoding="utf-8") as f:
            f.write(f"{ts}\t{run_id}\t{user_input}\n")
    except Exception as e:
        logger.error("Failed to record run_id {}: {}", run_id, e)


def list_run_ids(limit: int = 50) -> list[dict[str, str]]:
    """Return the latest run_ids with timestamps and queries (most recent last)."""
    if not os.path.exists(RUN_IDS_LOG):
        return []
    try:
        with open(RUN_IDS_LOG, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        logger.error("Failed to read run_id log: {}", e)
        return []

    lines = lines[-limit:]
    entries = []
    for line in lines:
        parts = line.rstrip("\n").split("\t", 2)
        if len(parts) == 3:
            ts, rid, query = parts
            entries.append({"timestamp": ts, "run_id": rid, "query": query})
    return entries


def clear_run_ids() -> None:
    """Clear the run_ids log file and sqlite checkpoints."""
    try:
        if os.path.exists(RUN_IDS_LOG):
            os.remove(RUN_IDS_LOG)
            logger.info("Cleared run_ids log")

        db_path = str(CHECKPOINTS_DB)
        for path in [db_path, f"{db_path}-wal", f"{db_path}-shm"]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                    logger.info(f"Removed checkpoint file: {path}")
                except OSError as e:
                    logger.warning(f"Could not remove {path}: {e}")

    except Exception as e:
        logger.error("Failed to clear run data: {}", e)


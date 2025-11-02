from redis_client import redis_client
from datetime import datetime
import json

STREAMS = {
    "simulate": "stream:simulate",
    "c_qir_convert": "stream:c_qir",
    "backend_run": "stream:backend",
}

async def enqueue_task(task_id: str, task_type: str, payload: dict):
    stream_name = STREAMS.get(task_type)
    if not stream_name:
        raise ValueError(f"Unknown task_type {task_type}")

    await redis_client.xadd(
        stream_name,
        {
            "task_id": task_id,
            "task_type": task_type,
            "payload": json.dumps(payload),
            "created_at": datetime.utcnow().isoformat(),
        },
    )

import asyncio
import json
import uuid
from datetime import datetime
from redis import asyncio as aioredis

# Stream names 
STREAMS = {
    "simulate": "stream:simulate",
    "backend": "stream:backend",
}

# Example QASM circuits
BELL_STATE_QASM = """OPENQASM 2.0;
include "qelib1.inc";
qreg q[2];
creg c[2];
h q[0];
cx q[0],q[1];
measure q[0] -> c[0];
measure q[1] -> c[1];
"""

GHZ_STATE_QASM = """OPENQASM 2.0;
include "qelib1.inc";
qreg q[3];
creg c[3];
h q[0];
cx q[0],q[1];
cx q[0],q[2];
measure q[0] -> c[0];
measure q[1] -> c[1];
measure q[2] -> c[2];
"""


class TestClient:
    """Test client for enqueueing tasks"""
    
    def __init__(self):
        self.redis_client = None
    
    async def initialize(self):
        """Initialize connections"""
        self.redis_client = await aioredis.from_url(
            "redis://localhost:6379/0",
            encoding="utf-8",
            decode_responses=True
        )
    
    async def close(self):
        """Close connections"""
        if self.redis_client:
            await self.redis_client.close()
    
    async def enqueue_task(self, task_type: str, payload: dict):
        """Enqueue a task to the appropriate stream"""
        stream_name = STREAMS.get(task_type)
        if not stream_name:
            raise ValueError(f"Unknown task_type: {task_type}")
        
        task_id = str(uuid.uuid4())
        
        message = {
            "task_id": task_id,
            "task_type": task_type,
            "payload": json.dumps(payload),
            "created_at": datetime.utcnow().isoformat(),
        }
        
        # Add to Redis Stream
        stream_id = await self.redis_client.xadd(stream_name, message)
        
        print(f"✓ Enqueued task {task_id} to {stream_name}")
        print(f"  Stream ID: {stream_id}")
        
        return task_id
    
    async def check_stream_length(self, task_type: str):
        """Check how many messages are in the stream"""
        stream_name = STREAMS.get(task_type)
        if stream_name:
            length = await self.redis_client.xlen(stream_name)
            print(f"Stream {stream_name} has {length} messages")
            return length
        return 0


async def test_simulator_jobs():
    """Test simulator job submission"""
    print("\n" + "="*60)
    print("Testing Simulator Jobs")
    print("="*60)
    
    client = TestClient()
    await client.initialize()
    
    try:
        # Test 1: QASM Bell State
        print("\n1. Testing QASM Bell State on Simulator")
        payload1 = {
            "circuit_type": "qasm",
            "circuit_data": BELL_STATE_QASM,
            "shots": 100,
            "simulator_id": "qbraid_qir_simulator"
        }
        task_id1 = await client.enqueue_task("simulate", payload1)
        
        await asyncio.sleep(1)
        
        # Test 2: QASM GHZ State
        print("\n2. Testing QASM GHZ State on Simulator")
        payload2 = {
            "circuit_type": "qasm",
            "circuit_data": GHZ_STATE_QASM,
            "shots": 200,
            "simulator_id": "qbraid_qir_simulator"
        }
        task_id2 = await client.enqueue_task("simulate", payload2)
        
        await asyncio.sleep(1)
        
        # Check stream length
        print("\n")
        await client.check_stream_length("simulate")
        
        return [task_id1, task_id2]
        
    finally:
        await client.close()


async def test_backend_jobs():
    """Test backend job submission"""
    print("\n" + "="*60)
    print("Testing Backend Jobs")
    print("="*60)
    
    client = TestClient()
    await client.initialize()
    
    try:
        # Test 1: Submit to backend (not waiting for completion)
        print("\n1. Testing Bell State on Backend (async)")
        payload1 = {
            "circuit_type": "qasm",
            "circuit_data": BELL_STATE_QASM,
            "backend_name": "aws_braket_simulator",
            "shots": 1024,
            "wait_for_completion": False
        }
        task_id1 = await client.enqueue_task("backend", payload1)
        
        await asyncio.sleep(1)
        
        # Check stream length
        print("\n")
        await client.check_stream_length("backend")
        
        return [task_id1]
        
    finally:
        await client.close()


async def monitor_streams():
    """Monitor both streams"""
    print("\n" + "="*60)
    print("Stream Status")
    print("="*60)
    
    client = TestClient()
    await client.initialize()
    
    try:
        print("\nCurrent stream lengths:")
        await client.check_stream_length("simulate")
        await client.check_stream_length("backend")
        
    finally:
        await client.close()


async def main():
    """Main test runner"""
    print("\n" + "="*60)
    print("Quantum Circuit Processor - Test Client")
    print("="*60)
    
    while True:
        print("\nSelect test to run:")
        print("1. Test Simulator Jobs")
        print("2. Test Backend Jobs")
        print("3. Monitor Streams")
        print("0. Exit")
        
        choice = input("\nEnter choice: ").strip()
        
        if choice == "1":
            await test_simulator_jobs()
        elif choice == "2":
            await test_backend_jobs()
        elif choice == "3":
            await monitor_streams()
        elif choice == "0":
            print("\nExiting...")
            break
        else:
            print("Invalid choice!")
        
        print("\n" + "-"*60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nTest client stopped.")
import os
import asyncio
from typing import Dict, Any
from dotenv import load_dotenv
from qbraid import QbraidProvider
from circuit_processor import QueueProcessor, STREAMS

# Import circuit converter from simulator worker
import sys
sys.path.append(os.path.dirname(__file__))
from simulator_worker import CircuitConverter

load_dotenv()

QBRAID_API_KEY = os.getenv("QBRAID_API_KEY")


class BackendWorker:
    """Worker for processing backend (real quantum hardware) jobs"""
    
    def __init__(self):
        self.provider = QbraidProvider()
    
    async def process_backend_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Process a backend execution task"""
        try:
            payload = task['payload']
            
            # Extract parameters
            circuit_type = payload.get('circuit_type')
            circuit_data = payload.get('circuit_data')
            backend_name = payload.get('backend_name')
            shots = payload.get('shots', 1024)
            
            if not circuit_type or not circuit_data:
                raise ValueError("Missing circuit_type or circuit_data in payload")
            
            if not backend_name:
                raise ValueError("backend_name is required for backend execution")
            
            print(f"Processing {circuit_type} circuit on backend: {backend_name}")
            
            # Convert circuit to appropriate format
            # Determine best format for the backend
            target_format = self._determine_target_format(backend_name)
            
            circuit = CircuitConverter.deserialize_circuit(
                circuit_type, 
                circuit_data, 
                target_type=target_format
            )
            
            # Get backend device
            device = self.provider.get_device(backend_name)
            
            # Submit job to backend
            job = device.run(circuit, shots=shots)
            
            print(f"Job submitted: {job.id}")
            
            # For real hardware, we typically don't wait for completion
            # Instead, we return the job_id and let the client poll for results
            # or implement a separate result-fetching worker
            
            # Check if we should wait for completion
            wait_for_completion = payload.get('wait_for_completion', False)
            
            if wait_for_completion:
                # Wait for result (this could take a long time on real hardware)
                print(f"Waiting for job {job.id} to complete...")
                result = job.result()
                
                # Extract measurements
                measurements = None
                if hasattr(result, 'measurement_counts'):
                    measurements = result.measurement_counts()
                elif hasattr(result, 'measurements'):
                    measurements = result.measurements
                
                return {
                    "job_id": job.id,
                    "status": "completed",
                    "backend": backend_name,
                    "shots": shots,
                    "measurements": measurements,
                    "result_data": str(result)
                }
            else:
                # Return immediately with job_id
                return {
                    "job_id": job.id,
                    "status": "submitted",
                    "backend": backend_name,
                    "shots": shots,
                    "message": "Job submitted to quantum backend. Use job_id to fetch results."
                }
            
        except Exception as e:
            print(f"Error in backend task: {e}")
            raise
    
    def _determine_target_format(self, backend_name: str) -> str:
        """Determine the best circuit format for a given backend"""
        backend_lower = backend_name.lower()
        
        # AWS Braket devices
        if 'aws' in backend_lower or 'braket' in backend_lower:
            return 'braket'
        
        # IBM devices
        if 'ibm' in backend_lower:
            return 'qiskit'
        
        # Default to Braket
        return 'braket'


async def main():
    """Main entry point for backend worker"""
    
    # Initialize queue processor
    processor = QueueProcessor(
        stream_name=STREAMS["backend"],
        consumer_group="backend_workers",
        consumer_name=f"backend_worker_{os.getpid()}"
    )
    
    # Initialize backend worker
    worker = BackendWorker()
    
    try:
        # Initialize connections
        await processor.initialize()
        
        print("=" * 60)
        print("Backend Worker Started")
        print(f"Stream: {STREAMS['backend']}")
        print(f"Consumer: {processor.consumer_name}")
        print("=" * 60)
        
        # Start consuming messages
        await processor.start_consuming(
            processor_func=worker.process_backend_task,
            batch_size=5,  # Lower batch size for backend jobs
            block_ms=5000
        )
        
    except KeyboardInterrupt:
        print("\nShutting down backend worker...")
    finally:
        await processor.close()


if __name__ == "__main__":
    asyncio.run(main())
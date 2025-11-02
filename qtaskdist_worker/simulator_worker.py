import os
import asyncio
from typing import Dict, Any
from dotenv import load_dotenv
from qbraid import QbraidProvider
from qbraid.transpiler import transpile
from qiskit import QuantumCircuit
import cirq
import json

from circuit_processor import QueueProcessor, STREAMS

load_dotenv()

QBRAID_API_KEY = os.getenv("QBRAID_API_KEY")


class CircuitConverter:
    """Handles circuit conversion between different frameworks"""
    
    @staticmethod
    def qasm_to_circuit(qasm_string: str, target_type: str = "braket"):
        """Convert QASM string to specified circuit type"""
        # First convert QASM to Qiskit (most universal)
        qiskit_circuit = QuantumCircuit.from_qasm_str(qasm_string)
        
        if target_type == "qiskit":
            return qiskit_circuit
        elif target_type in ["braket", "amazon_braket"]:
            # Convert Qiskit to Braket
            return transpile(qiskit_circuit, "braket")
        elif target_type == "cirq":
            return transpile(qiskit_circuit, "cirq")
        else:
            # Default to Braket for QBraid
            return transpile(qiskit_circuit, "braket")
    
    @staticmethod
    def deserialize_circuit(circuit_type: str, circuit_data: str, target_type: str = "braket"):
        """Deserialize circuit based on type and convert to target type"""
        
        if circuit_type == "qasm":
            return CircuitConverter.qasm_to_circuit(circuit_data, target_type)
        
        elif circuit_type == "qiskit":
            # Deserialize Qiskit circuit from QASM
            qiskit_circuit = QuantumCircuit.from_qasm_str(circuit_data)
            if target_type == "qiskit":
                return qiskit_circuit
            return transpile(qiskit_circuit, target_type)
        
        elif circuit_type in ["braket", "amazon_braket"]:
            # Parse Braket circuit from QASM
            qiskit_circuit = QuantumCircuit.from_qasm_str(circuit_data)
            return transpile(qiskit_circuit, "braket")
        
        elif circuit_type == "cirq":
            # Parse Cirq circuit from JSON
            circuit = cirq.read_json(json_text=circuit_data)
            if target_type == "cirq":
                return circuit
            # Convert Cirq to target
            qiskit_circuit = transpile(circuit, "qiskit")
            return transpile(qiskit_circuit, target_type)
        
        else:
            raise ValueError(f"Unknown circuit type: {circuit_type}")


class SimulatorWorker:
    """Worker for processing simulator jobs"""
    
    def __init__(self):
        self.provider = QbraidProvider()
    
    async def process_simulate_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Process a simulation task"""
        try:
            payload = task['payload']
            
            # Extract parameters
            circuit_type = payload.get('circuit_type')
            circuit_data = payload.get('circuit_data')
            shots = payload.get('shots', 100)
            simulator_id = payload.get('simulator_id', 'qbraid_qir_simulator')
            
            if not circuit_type or not circuit_data:
                raise ValueError("Missing circuit_type or circuit_data in payload")
            
            print(f"Processing {circuit_type} circuit on {simulator_id}")
            
            # Convert circuit to appropriate format
            circuit = CircuitConverter.deserialize_circuit(
                circuit_type, 
                circuit_data, 
                target_type="braket"  # QBraid simulators work well with Braket
            )
            
            # Get simulator device
            device = self.provider.get_device(simulator_id)
            
            # Run circuit
            job = device.run(circuit, shots=shots)
            
            # Wait for result (simulators are usually fast)
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
                "shots": shots,
                "measurements": measurements,
                "result_data": str(result)
            }
            
        except Exception as e:
            print(f"Error in simulate task: {e}")
            raise


async def main():
    """Main entry point for simulator worker"""
    
    # Initialize queue processor
    processor = QueueProcessor(
        stream_name=STREAMS["simulate"],
        consumer_group="simulator_workers",
        consumer_name=f"simulator_worker_{os.getpid()}"
    )
    
    # Initialize simulator worker
    worker = SimulatorWorker()
    
    try:
        # Initialize connections
        await processor.initialize()
        
        print("=" * 60)
        print("Simulator Worker Started")
        print(f"Stream: {STREAMS['simulate']}")
        print(f"Consumer: {processor.consumer_name}")
        print("=" * 60)
        
        # Start consuming messages
        await processor.start_consuming(
            processor_func=worker.process_simulate_task,
            batch_size=10,
            block_ms=5000
        )
        
    except KeyboardInterrupt:
        print("\nShutting down simulator worker...")
    finally:
        await processor.close()


if __name__ == "__main__":
    asyncio.run(main())
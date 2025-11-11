
import os
import asyncio
from typing import Dict, Any
from dotenv import load_dotenv
from qbraid import QbraidProvider
from qbraid.transpiler import transpile
from qiskit import QuantumCircuit
import json
import sys
from io import StringIO
from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister
from qiskit.circuit.library import *

from circuit_processor import QueueProcessor, STREAMS

load_dotenv()

QBRAID_API_KEY = os.getenv("QBRAID_API_KEY")


class CircuitConverter:
    """Handles circuit conversion between different frameworks"""
    
    @staticmethod
    def execute_code_safely(code_string: str, circuit_type: str):
        """Execute user code and extract the circuit object"""
        # Create a restricted namespace with only necessary imports
        namespace = {
            '__builtins__': __builtins__,
        }
        
        # Add framework-specific imports
        if circuit_type == "qiskit":
            namespace.update({
                'QuantumCircuit': QuantumCircuit,
                'QuantumRegister': QuantumRegister,
                'ClassicalRegister': ClassicalRegister,
            })
        elif circuit_type in ["braket", "amazon_braket"]:
            from braket.circuits import Circuit
            namespace.update({'Circuit': Circuit})
        
        try:
            # Execute the code
            exec(code_string, namespace)
            
            # Extract circuit based on type
            if circuit_type == "qiskit":
                # Look for QuantumCircuit instance
                for key, value in namespace.items():
                    if isinstance(value, QuantumCircuit):
                        return value
                raise ValueError("No QuantumCircuit found in code")
            
            elif circuit_type in ["braket", "amazon_braket"]:
                from braket.circuits import Circuit
                for key, value in namespace.items():
                    if isinstance(value, Circuit):
                        return value
                raise ValueError("No Braket Circuit found in code")
        
        except Exception as e:
            raise ValueError(f"Error executing {circuit_type} code: {str(e)}")
    
    @staticmethod
    def qasm_to_circuit(qasm_string: str, target_type: str = "braket"):
        """Convert QASM string to specified circuit type"""
        qiskit_circuit = QuantumCircuit.from_qasm_str(qasm_string)
        
        if target_type == "qiskit":
            return qiskit_circuit
        elif target_type in ["braket", "amazon_braket"]:
            return transpile(qiskit_circuit, "braket")
        else:
            return transpile(qiskit_circuit, "braket")
    
    @staticmethod
    def deserialize_circuit(circuit_type: str, circuit_data: str, target_type: str = "braket"):
        """Deserialize circuit based on type and convert to target type"""
        
        if circuit_type == "qasm":
            # Direct QASM string
            return CircuitConverter.qasm_to_circuit(circuit_data, target_type)
        
        elif circuit_type == "qiskit":
            # Execute Qiskit code to get circuit
            qiskit_circuit = CircuitConverter.execute_code_safely(circuit_data, "qiskit")
            if target_type == "qiskit":
                return qiskit_circuit
            return transpile(qiskit_circuit, target_type)
        
        elif circuit_type in ["braket", "amazon_braket"]:
            # Execute Braket code to get circuit
            braket_circuit = CircuitConverter.execute_code_safely(circuit_data, "braket")
            if target_type == "braket":
                return braket_circuit
            # Convert via Qiskit
            qiskit_circuit = transpile(braket_circuit, "qiskit")
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
                target_type="braket"
            )
            
            # Get simulator device
            device = self.provider.get_device(simulator_id)
            
            # Run circuit
            job = device.run(circuit, shots=shots)
            
            # Wait for result
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
    
    processor = QueueProcessor(
        stream_name=STREAMS["simulate"],
        consumer_group="simulator_workers",
        consumer_name=f"simulator_worker_{os.getpid()}"
    )
    
    worker = SimulatorWorker()
    
    try:
        await processor.initialize()
        
        print("=" * 60)
        print("Simulator Worker Started")
        print(f"Stream: {STREAMS['simulate']}")
        print(f"Consumer: {processor.consumer_name}")
        print("=" * 60)
        
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
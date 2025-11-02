from pydantic import BaseModel, Field
from typing import Optional, Any, Dict
from uuid import UUID
from datetime import datetime

class ProfilingInfo(BaseModel):
    num_qubits: Optional[int] = None
    depth: Optional[int] = None
    gate_count: Optional[int] = None
    estimated_runtime: Optional[float] = None

class SimulatePayload(BaseModel):
    circuit_type: str
    circuit_data: str
    shots: int = 100
    simulator_id: str = "qbraid_qir_simulator"

class BackendPayload(BaseModel):
    circuit_type: str
    circuit_data: str
    backend_name: str
    shots: int = 1024
    wait_for_completion: bool = False

class TaskBase(BaseModel):
    task_type: str
    status: str = Field(default="pending")
    payload: SimulatePayload
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    scheduled_for: Optional[datetime] = None
    meta_data: Optional[ProfilingInfo] = Field(default_factory=dict)

class TaskCreate(TaskBase):
    pass

class TaskUpdate(BaseModel):
    status: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    retry_count: Optional[int] = None
    meta_data: Optional[ProfilingInfo] = None

class TaskRead(TaskBase):
    task_id: UUID
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True
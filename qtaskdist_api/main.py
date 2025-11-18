from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from database import get_session, engine, Base
import crud_task
from schemas import TaskCreate, TaskRead, TaskUpdate
from contextlib import asynccontextmanager 
from queue_manager import enqueue_task
from redis_client import redis_client

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()
    await redis_client.close()

app = FastAPI(title="Async Task Manager", lifespan=lifespan)

origins = [
    "https://quantumsimulator.vercel.app"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/tasks", response_model=TaskRead)
async def create_task(task: TaskCreate, db: AsyncSession = Depends(get_session)):
    db_task = await crud_task.create_task(db, task)
    await enqueue_task(str(db_task.task_id), db_task.task_type, db_task.payload)
    return db_task

@app.get("/tasks/{task_id}", response_model=TaskRead)
async def get_task(task_id: str, db: AsyncSession = Depends(get_session)):
    task = await crud_task.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

@app.get("/tasks", response_model=List[TaskRead])
async def list_tasks(db: AsyncSession = Depends(get_session)):
    return await crud_task.list_tasks(db)

@app.patch("/tasks/{task_id}", response_model=TaskRead)
async def update_task(task_id: str, update_data: TaskUpdate, db: AsyncSession = Depends(get_session)):
    updated = await crud_task.update_task(db, task_id, update_data)
    if not updated:
        raise HTTPException(status_code=404, detail="Task not found")
    return updated

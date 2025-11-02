from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update
from models import Task
from schemas import TaskCreate, TaskUpdate
from uuid import UUID

# Create task
async def create_task(db: AsyncSession, task_data: TaskCreate) -> Task:
    task = Task(**task_data.model_dump())
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task

# Get task by ID
async def get_task(db: AsyncSession, task_id: UUID) -> Task | None:
    result = await db.execute(select(Task).where(Task.task_id == task_id))
    return result.scalar_one_or_none()

# List all tasks
async def list_tasks(db: AsyncSession, skip: int = 0, limit: int = 50):
    result = await db.execute(select(Task).offset(skip).limit(limit))
    return result.scalars().all()

# Update task
async def update_task(db: AsyncSession, task_id: UUID, task_update: TaskUpdate) -> Task | None:
    result = await db.execute(select(Task).where(Task.task_id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        return None

    for field, value in task_update.model_dump(exclude_unset=True).items():
        setattr(task, field, value)

    await db.commit()
    await db.refresh(task)
    return task

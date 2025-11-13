import os
import json
import asyncio
from typing import Dict, Any, Optional, Callable
from datetime import datetime
from dotenv import load_dotenv
from redis import asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, update
from uuid import UUID
from models import Task

# Load environment variables
load_dotenv()

# Redis configuration
REDIS_URL = os.getenv("REDIS_URL")

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost/dbname")

# Stream names
STREAMS = {
    "simulate": "stream:simulate",
    "backend": "stream:backend",
}

class QueueProcessor:
    """Base class for processing tasks from Redis Streams"""
    
    def __init__(self, stream_name: str, consumer_group: str, consumer_name: str):
        self.stream_name = stream_name
        self.consumer_group = consumer_group
        self.consumer_name = consumer_name
        self.redis_client: Optional[aioredis.Redis] = None
        self.db_engine = None
        self.async_session_maker = None
        
        redis_client = await aioredis.from_url(
            REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            ssl_cert_reqs=None  # For Upstash compatibility
        )
        
        # Initialize Database
        self.db_engine = create_async_engine(DATABASE_URL, echo=False)
        self.async_session_maker = sessionmaker(
            self.db_engine, class_=AsyncSession, expire_on_commit=False
        )
        
        # Create consumer group if it doesn't exist
        try:
            await self.redis_client.xgroup_create(
                self.stream_name, 
                self.consumer_group, 
                id='0', 
                mkstream=True
            )
            print(f"Created consumer group: {self.consumer_group}")
        except Exception as e:
            if "BUSYGROUP" not in str(e):
                print(f"Error creating consumer group: {e}")
            else:
                print(f"Consumer group already exists: {self.consumer_group}")
    
    async def close(self):
        """Close connections"""
        if self.redis_client:
            await self.redis_client.close()
        if self.db_engine:
            await self.db_engine.dispose()
    
    def parse_task(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Parse task from Redis Stream message"""
        try:
            task_id = message.get('task_id')
            task_type = message.get('task_type')
            payload_str = message.get('payload')
            created_at = message.get('created_at')
            
            # Parse payload - it's stored as string
            if isinstance(payload_str, str):
                payload = json.loads(payload_str.replace("'", '"'))
            else:
                payload = payload_str
            
            return {
                'task_id': task_id,
                'task_type': task_type,
                'payload': payload,
                'created_at': created_at
            }
        except Exception as e:
            raise ValueError(f"Failed to parse task: {e}")
    
    async def update_task_status(
        self, 
        task_id: str, 
        status: str, 
        result: Optional[Dict] = None, 
        error: Optional[str] = None
    ):
        """Update task status in database"""
        async with self.async_session_maker() as session:
            try:
                task_uuid = UUID(task_id)
                
                update_values = {
                    'status': status,
                    'updated_at': datetime.utcnow()
                }
                
                if result is not None:
                    update_values['result'] = result
                
                if error is not None:
                    update_values['error'] = error
                
                stmt = (
                    update(Task)
                    .where(Task.task_id == task_uuid)
                    .values(**update_values)
                )
                
                await session.execute(stmt)
                await session.commit()
                
                print(f"Updated task {task_id} status to {status}")
                
            except Exception as e:
                print(f"Error updating task status: {e}")
                await session.rollback()
    
    async def process_message(
        self, 
        stream: str, 
        message_id: str, 
        message: Dict[str, Any], 
        processor_func: Callable
    ):
        """Process a single message from the stream"""
        try:
            # Parse task
            task = self.parse_task(message)
            task_id = task['task_id']
            
            print(f"Processing task {task_id} from {stream}")
            
            # Update status to processing
            await self.update_task_status(task_id, 'processing')
            
            # Execute the processor function
            result = await processor_func(task)
            
            # Update status to completed
            await self.update_task_status(
                task_id, 
                'completed', 
                result=result
            )
            
            # Acknowledge the message
            await self.redis_client.xack(stream, self.consumer_group, message_id)
            print(f"Task {task_id} completed successfully")
            
        except Exception as e:
            print(f"Error processing message {message_id}: {e}")
            
            # Try to update error status
            try:
                task = self.parse_task(message)
                await self.update_task_status(
                    task['task_id'], 
                    'failed', 
                    error=str(e)
                )
            except:
                pass
    
    async def start_consuming(
        self, 
        processor_func: Callable, 
        batch_size: int = 10, 
        block_ms: int = 5000
    ):
        """Start consuming messages from the stream"""
        print(f"Starting consumer: {self.consumer_name} on {self.stream_name}")
        
        while True:
            try:
                # Read from stream
                messages = await self.redis_client.xreadgroup(
                    self.consumer_group,
                    self.consumer_name,
                    {self.stream_name: '>'},
                    count=batch_size,
                    block=block_ms
                )
                
                if not messages:
                    continue
                
                # Process each message
                for stream, message_list in messages:
                    for message_id, message_data in message_list:
                        await self.process_message(
                            stream, 
                            message_id, 
                            message_data, 
                            processor_func
                        )
                
            except asyncio.CancelledError:
                print("Consumer cancelled, shutting down...")
                break
            except Exception as e:
                print(f"Error in consumer loop: {e}")
                await asyncio.sleep(5)  # Wait before retrying

import os
from dotenv import load_dotenv

import redis.asyncio as redis

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL")
redis_client = redis.from_url(REDIS_URL, decode_responses=True) 

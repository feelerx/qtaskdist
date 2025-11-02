import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import asyncio
from database import engine, Base
from models import *

async def init_models():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(init_models())

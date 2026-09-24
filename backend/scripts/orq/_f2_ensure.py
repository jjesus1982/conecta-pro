import asyncio

from core.database import async_session_factory
from modules.people_management.folha.services import cct_como_dado as cd


async def m():
    async with async_session_factory() as db:
        await cd.ensure(db)
        print("ensure ok")


asyncio.run(m())

"""Single-process periodic monitoring for the local SIH deployment."""

import asyncio, logging
from contextlib import asynccontextmanager
from sqlalchemy import select
from .models import Hive, Jurisdiction
from .database import now
from .telemetry_engine import evaluate
from .regional_engine import regional


def tick(app):
    with app.state.write_lock, app.state.sessions() as db:
        current = now()
        for hive in db.scalars(select(Hive)):
            evaluate(db, hive, app.state.settings, current)
        for jurisdiction in db.scalars(select(Jurisdiction)):
            regional(db, jurisdiction, app.state.settings, current)
        db.commit()


@asynccontextmanager
async def lifespan(app):
    async def worker():
        while True:
            await asyncio.sleep(30)
            try:
                await asyncio.to_thread(tick, app)
            except Exception:
                logging.exception("Periodic hive evaluation failed")

    task = asyncio.create_task(worker())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

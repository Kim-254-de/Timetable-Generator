"""RQ job entry points. Start a worker with: rq worker generator-runs --url $REDIS_URL"""

from __future__ import annotations

from app.services.runs import execute_run

__all__ = ["execute_run"]

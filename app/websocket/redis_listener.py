import asyncio
import json
import os

import redis.asyncio as aioredis
from logging_config import get_logger

from websocket.connection_manager import manager

logger = get_logger("websocket.redis_listener")

CHANNEL = "execution:updates"


async def listen_to_execution_updates():
    """Subscribe to Redis pub/sub and broadcast execution updates via WebSocket."""
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/1")

    while True:
        try:
            r = aioredis.from_url(redis_url, decode_responses=True)
            pubsub = r.pubsub()
            await pubsub.subscribe(CHANNEL)
            logger.info("Subscribed to Redis channel: %s", CHANNEL)

            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                try:
                    payload = json.loads(message["data"])
                    user_id = payload.get("user_id")
                    if user_id is not None:
                        await manager.broadcast_to_user(
                            int(user_id),
                            {"type": "execution_update", "payload": payload},
                        )
                except (json.JSONDecodeError, KeyError) as e:
                    logger.error("Failed to parse pub/sub message: %s", e)

        except Exception as e:
            logger.error("Redis pub/sub connection error: %s — reconnecting in 5s", e)
            await asyncio.sleep(5)

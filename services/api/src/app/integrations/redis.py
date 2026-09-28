from redis.asyncio import Redis


class RedisClient:
    def __init__(self, url: str) -> None:
        self.client: Redis = Redis.from_url(url, decode_responses=False)

    async def check_connection(self) -> None:
        if not await self.client.ping():
            raise ConnectionError("Redis did not acknowledge the health check.")

    async def close(self) -> None:
        await self.client.aclose()

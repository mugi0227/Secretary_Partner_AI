import asyncio
from httpx import AsyncClient, ASGITransport
from main import app

async def main():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/api/chat",
            json={"text": "縺薙ｓ縺ｫ縺｡縺ｯ", "mode": "dump"},
            headers={"Authorization": "Bearer dev_user"},
        )
        print("status", r.status_code)
        print("text", r.text)

asyncio.run(main())

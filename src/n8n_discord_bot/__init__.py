import asyncio
import logging
import os
import uuid
from functools import lru_cache

import httpx
from discord import Client, Intents, Message
from qdrant_client import AsyncQdrantClient, models

logger = logging.getLogger(__name__)

QDRANT_COLLECTION_NAME = "n8n-bot"
QDRANT_COLLECTION_DIMS = 1536
QDRANT_COLLECTION_PAYLOAD_INDEXES = [
    ("feedback", models.PayloadSchemaType.TEXT),
    ("success", models.PayloadSchemaType.BOOL),
]


@lru_cache(maxsize=1)
def get_intents() -> Intents:
    intents = Intents.default()
    intents.messages = True
    intents.message_content = True
    return intents


@lru_cache(maxsize=1)
def get_n8n_webhook_endpoint() -> str:
    endpoint = os.getenv("N8N_WEBHOOK_ENDPOINT")
    if endpoint is None:
        raise ValueError("Could not find a N8N webhook URL within the environment")
    return endpoint


@lru_cache(maxsize=1)
def get_token() -> str:
    tok = os.getenv("DISCORD_BOT_TOKEN")
    if tok is None:
        raise ValueError("Could not find a Discord bot token within the environment")
    return tok


bot = Client(intents=get_intents())


@bot.event
async def on_ready() -> None:
    logger.info("Bot is ready!")


@bot.event
async def on_message(message: Message) -> None:
    if bot.user is None:
        raise RuntimeError("Bot User cannot be null")
    # ignore the bot's own messages
    if message.author == bot.user:
        return

        # check if the bot was mentioned
    if bot.user.mentioned_in(message):
        req_id = str(uuid.uuid4())
        await message.add_reaction("👀")
        await message.channel.send(
            f"Hey, {message.author.mention}, I am now starting an agent task to fulfil your inquiry (ID: {req_id}). I will report back soon!"
        )
        async with httpx.AsyncClient(base_url=get_n8n_webhook_endpoint()) as client:
            response = await client.post(
                "/",
                json={
                    "message": " ".join(message.content.split(" ")[1:]),
                    "mention": message.author.mention,
                    "request_id": req_id,
                },
            )
            response.raise_for_status()
        return


@lru_cache(maxsize=1)
def get_qdrant_client() -> AsyncQdrantClient:
    url = os.getenv("QDRANT_URL")
    if url is None:
        raise ValueError("Could not find a Qdrant base URL within the environment")
    client = AsyncQdrantClient(url=url, api_key=os.getenv("QDRANT_API_KEY"))
    return client


async def create_collection() -> None:
    client = get_qdrant_client()
    await client.create_collection(
        collection_name=QDRANT_COLLECTION_NAME,
        vectors_config=models.VectorParams(
            distance=models.Distance.COSINE, size=QDRANT_COLLECTION_DIMS
        ),
    )
    for f, t in QDRANT_COLLECTION_PAYLOAD_INDEXES:
        await client.create_payload_index(
            collection_name=QDRANT_COLLECTION_NAME, field_name=f, field_type=t
        )
    print("Successfully created collection on Qdrant")


def collection_main() -> None:
    asyncio.run(create_collection())


def main() -> None:
    token = get_token()
    bot.run(token)

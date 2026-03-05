from dataclasses import dataclass
from dotenv import load_dotenv
import os

load_dotenv()

@dataclass
class RabbitConfig:

    url: str = None
    def __post_init__(self):
        if self.url is None:
            self.url = os.getenv("AMQP_URL", "amqp://localhost")


def room_key(room: str) -> str:
    return f"room.{room}"
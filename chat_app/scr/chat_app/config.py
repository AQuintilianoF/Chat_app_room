from dataclasses import dataclass
from dotenv import load_dotenv
import os

load_dotenv()

@dataclass
class RabbitConfig:

    url:  str = None
    port: int = None

    def __post_init__(self):
        if self.url is None:
            env_url = os.getenv("AMQP_URL")

            if env_url:
                self.url = env_url
            elif self.port:
                self.url = f"amqp://localhost:{self.port}"
            else:
                self.url = "amqp://localhost"

def room_key(room: str) -> str:
    return f"room.{room}"
    return f"room.{room}"
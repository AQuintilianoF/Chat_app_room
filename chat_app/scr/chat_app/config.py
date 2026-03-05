from dataclasses import dataclass

@dataclass
class RabbitConfig:
    host: str = "localhost"
    exchange: str = "chat.topic"
    exchange_type: str = "topic"


def room_key(room: str) -> str:
    return f"room.{room}"
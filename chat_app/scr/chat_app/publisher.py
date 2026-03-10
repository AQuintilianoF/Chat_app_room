from chat_app.middleware import create_connection
from chat_app.config import RabbitConfig

EXCHANGE = "chat.topic"

def make_publisher(config: RabbitConfig = None):

    connection, channel = create_connection(config)
    return connection, channel

def send_message(channel, room: str, username: str, text: str):

    room     = room.strip().upper()
    username = username.strip().title()
    text     = text.strip()

    if not text:
        return

    channel.basic_publish(
        exchange    = EXCHANGE,
        routing_key = f"room.{room}",
        body        = f"{username}: {text}".encode("utf-8")
    )
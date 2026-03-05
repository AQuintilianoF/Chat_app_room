from chat_app.middleware import create_connection
from chat_app.config import RabbitConfig

EXCHANGE = "chat.topic"
MAX_USERNAME = 35
MAX_ROOM = 15
MAX_MESSAGE = 255

def make_publisher(config: RabbitConfig = None):

    connection, channel = create_connection(config)
    return connection , channel

def send_message(channel, room: str , username: str, text :str):

    room     = room.strip().upper()
    username = username.strip().title()
    text     = text.strip()

    if not room:
        raise ValueError("room cannot be empty")
    if not username:
        raise ValueError("username cannot be empty")
    if len(username) > MAX_USERNAME:
        raise ValueError(f"username too long (max {MAX_USERNAME})")
    if len(room) > MAX_ROOM:
        raise ValueError(f"room name too long (max {MAX_ROOM})")
    if len(text) > MAX_MESSAGE:
        raise ValueError(f"message too long (max {MAX_MESSAGE})")
    if not text:
        return

    channel.basic_publish(
        exchange    = EXCHANGE,
        routing_key = f"room.{room}",
        body        = f"{username}: {text}".encode("utf-8")
    )
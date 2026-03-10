import threading
from chat_app.middleware import create_connection
from chat_app.config     import RabbitConfig

EXCHANGE = "chat.topic"

def start_consumer(room: str, on_message=None, config: RabbitConfig = None):

    connection, channel = create_connection(config)

    result     = channel.queue_declare(queue="", exclusive=True)
    queue_name = result.method.queue

    channel.queue_bind(
        exchange    = EXCHANGE,
        queue       = queue_name,
        routing_key = f"room.{room}"
    )

    if on_message is None:
        raise ValueError("on_message callback is required")

    callback = on_message

    def run():

        channel.basic_consume(
            queue               = queue_name,
            on_message_callback = callback,
            auto_ack            = True
        )

        print(f"[system] Connected to room '{room}'. Waiting for messages...")
        channel.start_consuming()

    t = threading.Thread(target=run, daemon=True)
    t.start()

    return connection,channel, t
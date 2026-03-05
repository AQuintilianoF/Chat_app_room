import pika 
from chat_app.config import RabbitConfig


def create_connection(config : RabbitConfig = None):

    if config is None:
        config = RabbitConfig()


    connection = pika.BlockingConnection(
        pika.ConnectionParameters(host=config.host)
    )

    channel = connection.channel()
    channel.exchange_declare(
        exchange      = "chat.topic",
        exchange_type = "topic",
        durable       = True
    )

    return connection,channel
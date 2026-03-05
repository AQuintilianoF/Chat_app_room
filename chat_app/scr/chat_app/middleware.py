import pika 
from chat_app.config import RabbitConfig


def create_connection(config : RabbitConfig = None):

    if config is None:
        config = RabbitConfig()


    parameters = pika.URLParameters(config.url)
    connection = pika.BlockingConnection(parameters)

    channel = connection.channel()
    channel.exchange_declare(
        exchange      = "chat.topic",
        exchange_type = "topic",
        durable       = True
    )

    return connection,channel
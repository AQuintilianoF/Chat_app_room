import threading
from chat_app.middleware import create_connection
from chat_app.config     import RabbitConfig

EXCHANGE = "chat.topic"

def start_consumer(room: str, on_message=None, config: RabbitConfig = None):
 
    connection, channel = create_connection(config) 

    result      = channel.queue_declare(queue="", exclusive=True)
    queue_name  = result.method.queue


    channel.queue_bind(
        exchange    = EXCHANGE,
        queue       = queue_name,
        routing_key = f"room.{room}"
    )

    
    def default_callback(ch, method, properties, body):
        text = body.decode("utf-8", errors="replace")
        print(f"\n{text}\n> ", end="", flush=True)

    callback = on_message if on_message is not None else default_callback


    def run():

        channel.basic_consume(
            queue               = queue_name,
            on_message_callback = callback,
            auto_ack            = True
        )

        print(f"[sistema] Conectado à sala '{room}'. Aguardando mensagens...")
        channel.start_consuming()

    t = threading.Thread(target=run, daemon=True)
    t.start()

    return connection, t
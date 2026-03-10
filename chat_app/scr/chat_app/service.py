from chat_app.pers_json import load_rooms, save_message, load_history, delete_room
from chat_app.consumer import start_consumer
from chat_app.publisher import make_publisher, send_message
from chat_app.config import RabbitConfig

class ChatService:

    def __init__(self):

        self.username          = None
        self.room              = None
        self._publisher_conn   = None
        self._publisher_ch     = None
        self._consumer_conn    = None
        self._consumer_thread  = None
        self._consumer_channel = None

    def get_available_rooms(self) -> list[str]:

        return load_rooms()

    def create_or_join_room(self, room: str) -> None:

        self.room = room.strip().upper()

    def get_history(self) -> list[dict]:

        if not self.room:
            return []
        return load_history(self.room)
    
    def delete_room(self, room : str) -> bool:
        
        return delete_room(room)

    def connect(self, username: str, room: str, on_message_received, port: int = None) -> None:

        self.username = username.strip().title()
        self.create_or_join_room(room)
        config = RabbitConfig(port=port)
        self._publisher_conn, self._publisher_ch = make_publisher(config)

        def _on_raw_message(ch, method, properties, body):

            text = body.decode("utf-8", errors="replace")

            if ": " in text:
                sender, msg = text.split(": ", 1)
            else:
                sender, msg = "?", text

            if sender != self.username:
                save_message(
                    room     = self.room,
                    username = sender,
                    text     = msg
                )

            on_message_received(sender, msg)

        self._consumer_conn,self._consumer_channel, self._consumer_thread = start_consumer(
            room       = self.room,
            on_message = _on_raw_message,
            config     = config
        )

    def disconnect(self) -> None:

        try:
            if self._consumer_channel and self._consumer_channel.is_open:
                self._consumer_conn.add_callback_threadsafe(
                    self._consumer_channel.stop_consuming
                )
                self._consumer_thread.join(timeout=3)
        except Exception as e:
            print(f"[warning] Error stopping consumer: {e}")

        try:
            if self._consumer_conn and self._consumer_conn.is_open:
                self._consumer_conn.close()
        except Exception as e:
            print(f"[warning] Error closing consumer connection: {e}")

        try:
            if self._publisher_conn and self._publisher_conn.is_open:
                self._publisher_conn.close()
        except Exception as e:
            print(f"[warning] Error closing publisher connection: {e}")

    def send(self, text: str) -> None:

        send_message(
            channel  = self._publisher_ch,
            room     = self.room,
            username = self.username,
            text     = text
        )

        save_message(
            room     = self.room,
            username = self.username,
            text     = text
        )

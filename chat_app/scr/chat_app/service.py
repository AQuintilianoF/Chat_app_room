
from chat_app.pers_json import load_rooms, save_message, load_history
from chat_app.consumer import start_consumer
from chat_app.publisher import make_publisher, send_message 


class ChatService:

    def __init__(self):

        self.username         = None
        self.room             = None
        self._publisher_conn  = None
        self._publisher_ch    = None
        self._consumer_conn   = None
        self._consumer_thread = None


    def get_available_rooms(self) -> list[str]:

        return load_rooms()


    def create_or_join_room(self, room: str) -> None:

        self.room = room.strip().upper()


    def get_history(self) -> list[dict]:

        if not self.room:
            return []
        return load_history(self.room)


    def connect(self, username: str, room: str, on_message_received) -> None:

        self.username = username.strip().title()
        self.create_or_join_room(room)
        self._publisher_conn, self._publisher_ch = make_publisher()

        def _on_raw_message(ch, method, properties, body):

            text = body.decode("utf-8", errors="replace")

            if ": " in text:
                sender, msg = text.split(": ", 1)
            else:
                sender, msg = "?", text

            save_message(
                room     = self.room,
                username = sender,
                text     = msg
            )

            on_message_received(sender, msg)

        self._consumer_conn, self._consumer_thread = start_consumer(
            room       = self.room,
            on_message = _on_raw_message
        )

    def disconnect(self) -> None:

        for conn in (self._consumer_conn, self._publisher_conn):
            try:
                if conn:       
                    conn.close()
            except Exception:
                pass            


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
import argparse
import time
from chat_app.service import ChatService

parser = argparse.ArgumentParser(description="Chat App")
parser.add_argument("--port", type=int, default=None, help="RabbitMQ TCP port")
args = parser.parse_args()

def display_history(history: list[dict]) -> None:

    if not history:
        print("\n[system] No previous messages in this room.\n")
        return

    print("\n[system] --- room history ---")

    for entry in history:
        print(f"[{entry['timestamp']}] {entry['username']}: {entry['text']}")

    print("[system] --- end of history ---\n")

def select_room(service: ChatService) -> str:

    rooms = service.get_available_rooms()

    print("\n" + "=" * 40)

    if not rooms:
        print("  No rooms available.")
        print("=" * 40)
    else:
        print("  Available rooms:")
        print("-" * 40)

        for number, name in enumerate(rooms, start=1):
            print(f"  [{number}] {name}")

        print("-" * 40)

    print("  [0] Create new room")
    print("  [D] Delete a room")
    print("=" * 40)

    while True:
        choice = input("\nChoose an option: ").strip().lower()

        if choice == "0":
            while True:
                new_room = input("Room name (max 15 characters): ").strip().upper()

                if not new_room:
                    print("[error] Room name cannot be empty.")
                    continue

                if len(new_room) > 15:
                    print("[error] Name too long — maximum 15 characters.")
                    continue

                if new_room in rooms:
                    print(f"[warning] Room '{new_room}' already exists. Joining it.")

                return new_room
            
        if choice == "d":
            bool = delete_choice(service)
            if bool:
                print("Room deleted successfully!!")
                
            else:
                print("Room did not delete!!")

            continue
            
            
        elif choice.isdigit():
            index = int(choice)


            if 1 <= index <= len(rooms):
                return rooms[index - 1]

        print(f"[error] Invalid option. Enter a number between 0 and {len(rooms)} or D(delete).")

def on_message_received(sender: str, text: str) -> None:

    print(f"\n[{sender}]: {text}\n> ", end="", flush=True)

def delete_choice(service: ChatService) -> bool:

    rooms = service.get_available_rooms()
    
    while True:
        print("  Available rooms:")
        print("-" * 40)

        for number, name in enumerate(rooms, start=1):
            print(f"  [{number}] {name}")

        print("-" * 40)

        room_delete = input('Which one do you wanna DELETE ? \n > ')

        if room_delete.isdigit():
            index = int(room_delete)
            room_delete = rooms[index -1]

            return service.delete_room(room_delete)
            
        print(f"[error] Invalid option. Enter a number between 1 and {len(rooms)}.")
  
def main():

    service = ChatService()

    print("\n" + "=" * 40)
    print("       Welcome to Chat App")
    print("=" * 40)

    while True:
        username = input("\nEnter your username: ").strip()

        if not username:
            print("[error] Username cannot be empty.")
            continue

        if len(username) > 25:
            print("[error] Username too long — maximum 25 characters.")
            continue

        break
    
    
    room = select_room(service)

    print(f"\n[system] Connecting to room '{room}'...")

    service.connect(
        username            = username,
        room                = room,
        on_message_received = on_message_received,
        port                = args.port
    )

    time.sleep(0.3)

    history = service.get_history()
    display_history(history)

    print(f"[system] You joined '{room}' as '{username.title()}'.")
    print("[system] Type your messages. Ctrl+C to exit.\n")

    try:
        while True:
            msg = input("> ")
            if msg == '':
                continue

            try:
                service.send(msg)

            except ValueError as e:
                print(f"[error] {e}")

    except KeyboardInterrupt:
        print("\n\n[system] Leaving room...")
        service.disconnect()
        print(f"[system] You left '{room}'.\n")
        main()

    '''finally:
        service.disconnect()
        print("[system] Connections closed. Goodbye!")'''

if __name__ == "__main__":
    main()
   
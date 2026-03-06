import argparse
import time
from chat_app.service import ChatService

parser = argparse.ArgumentParser()
parser.add_argument("--port", type=int, default=None, help="Porta TCP do RabbitMQ")
args = parser.parse_args()

def exibir_historico(historico: list[dict]) -> None:

    if not historico:
        print("\n[sistema] Nenhuma mensagem anterior nesta sala.\n")
        return

    print("\n[sistema] --- histórico da sala ---")

    for entrada in historico:
        print(f"[{entrada['timestamp']}] {entrada['username']}: {entrada['text']}")

    print("[sistema] --- fim do histórico ---\n")


def selecionar_sala(service: ChatService) -> str:

    salas = service.get_available_rooms()

    print("\n" + "=" * 40)

    if not salas:
        print("  Nenhuma sala disponível no momento.")
        print("=" * 40)
    else:
        print("  Salas disponíveis:")
        print("-" * 40)

        for numero, nome in enumerate(salas, start=1):
            print(f"  [{numero}] {nome}")

        print("-" * 40)

    print("  [0] Criar nova sala")
    print("=" * 40)

    while True:
        escolha = input("\nEscolha uma opção: ").strip()

        if escolha == "0":
            while True:
                nova_sala = input("Nome da nova sala (máx 15 caracteres): ").strip().upper()

                if not nova_sala:
                    print("[erro] O nome da sala não pode ser vazio.")
                    continue

                if len(nova_sala) > 15:
                    print(f"[erro] Nome muito longo — máximo 15 caracteres.")
                    continue

                if nova_sala in salas:
                    print(f"[aviso] A sala '{nova_sala}' já existe. Entrando nela.")

                return nova_sala

        if escolha.isdigit():
            indice = int(escolha)

            if 1 <= indice <= len(salas):
                return salas[indice - 1]

        print(f"[erro] Opção inválida. Digite um número entre 0 e {len(salas)}.")


def on_mensagem_received(sender: str, text: str) -> None:

    print(f"\n[{sender}]: {text}\n> ", end="", flush=True)


def main():

    service = ChatService()

    
    print("\n" + "=" * 40)
    print("       Bem-vindo ao Chat App")
    print("=" * 40)

    while True:
        username = input("\nDigite seu username: ").strip()

        if not username:
            print("[erro] O username não pode ser vazio.")
            continue

        if len(username) > 35:
            print("[erro] Username muito longo — máximo 35 caracteres.")
            continue

        break

    room = selecionar_sala(service)

    print(f"\n[sistema] Conectando à sala '{room}'...")


    service.connect(
        username            = username,
        room                = room,
        on_message_received = on_mensagem_received,
        port                = args.port
    )

    time.sleep(0.3)

    historico = service.get_history()
    exibir_historico(historico)

    print(f"[sistema] Você entrou em '{room}' como '{username.title()}'.")
    print("[sistema] Digite suas mensagens. Ctrl+C para sair.\n")

    try:
        while True:
            msg = input("> ")

            try:
                service.send(msg)

            except ValueError as e:
                print(f"[erro] {e}")

    except KeyboardInterrupt:
        print("\n\n[sistema] Saindo...")

    finally:
        service.disconnect()
        print("[sistema] Conexões encerradas. Até mais!")

if __name__ == "__main__":
    main()
# cli.py

# Importamos apenas o ChatService — a interface não conhece
# consumer, publisher, pers_json ou middleware diretamente.
# Essa é a camada de serviço funcionando como combinamos.
import time
from chat_app.service import ChatService


def exibir_historico(historico: list[dict]) -> None:
    """
    Exibe as mensagens antigas da sala ao entrar nela.

    Parâmetro:
        historico:
            Lista de dicts retornada por service.get_history().
            Cada item tem "timestamp", "username" e "text".

    Por que separar em função própria?
    Porque o cli.py vai crescer e ter várias funções pequenas
    é melhor do que um main() gigante e difícil de ler.
    """

    if not historico:
        # Sala nova ou sem mensagens — informa o usuário
        print("\n[sistema] Nenhuma mensagem anterior nesta sala.\n")
        return

    print("\n[sistema] --- histórico da sala ---")

    for entrada in historico:
        # Cada 'entrada' é um dicionário como:
        # {"timestamp": "2026-03-05 08:00:00", "username": "Andre", "text": "oi"}
        # Acessamos cada campo pela sua chave.
        print(f"[{entrada['timestamp']}] {entrada['username']}: {entrada['text']}")

    print("[sistema] --- fim do histórico ---\n")


def selecionar_sala(service: ChatService) -> str:
    """
    Mostra as salas disponíveis e deixa o usuário escolher
    ou criar uma nova.

    Parâmetro:
        service:
            A instância do ChatService — usamos ela para
            buscar a lista de salas disponíveis.

    Retorno:
        O nome da sala escolhida ou criada, em maiúsculas.

    Por que receber o service como parâmetro?
    Para não criar uma segunda instância — passamos a mesma
    que já existe no main(). Isso se chama "injeção de dependência":
    a função não cria o que precisa, recebe de fora.
    """

    # Busca as salas do JSON via service.
    # Se o arquivo não existir ainda, retorna lista vazia.
    salas = service.get_available_rooms()

    print("\n" + "=" * 40)

    if not salas:
        # Nenhuma sala existe ainda — o usuário vai criar a primeira.
        print("  Nenhuma sala disponível no momento.")
        print("=" * 40)
    else:
        print("  Salas disponíveis:")
        print("-" * 40)

        # enumerate(salas, start=1) gera pares (número, sala)
        # começando do 1 em vez do 0, que é mais natural para o usuário.
        # Ex: [(1, "GERAL"), (2, "PYTHON")]
        for numero, nome in enumerate(salas, start=1):
            print(f"  [{numero}] {nome}")

        print("-" * 40)

    # A opção 0 sempre aparece para criar nova sala.
    print("  [0] Criar nova sala")
    print("=" * 40)

    while True:
        # Loop até o usuário fazer uma escolha válida.
        escolha = input("\nEscolha uma opção: ").strip()

        # Opção 0 → criar nova sala
        if escolha == "0":
            while True:
                nova_sala = input("Nome da nova sala (máx 15 caracteres): ").strip().upper()

                if not nova_sala:
                    print("[erro] O nome da sala não pode ser vazio.")
                    continue

                if len(nova_sala) > 15:
                    print(f"[erro] Nome muito longo — máximo 15 caracteres.")
                    continue

                # Verifica se a sala já existe para evitar duplicata.
                if nova_sala in salas:
                    print(f"[aviso] A sala '{nova_sala}' já existe. Entrando nela.")

                # Retorna o nome da sala — seja nova ou já existente.
                return nova_sala

        # Opção numérica → escolher sala da lista
        # isdigit() verifica se a string é um número inteiro positivo.
        # Ex: "2".isdigit() → True, "abc".isdigit() → False
        if escolha.isdigit():
            indice = int(escolha)

            # Verificamos se o número está dentro do intervalo válido.
            # len(salas) é o máximo porque a lista começa no índice 0
            # mas mostramos ao usuário começando do 1.
            if 1 <= indice <= len(salas):

                # O usuário viu o número 1 na tela mas na lista
                # o índice 0 corresponde ao número 1.
                # Por isso subtraímos 1: salas[indice - 1]
                return salas[indice - 1]

        # Se chegou aqui, a entrada foi inválida.
        print(f"[erro] Opção inválida. Digite um número entre 0 e {len(salas)}.")


def on_mensagem_recebida(sender: str, text: str) -> None:
    """
    Callback chamado pelo service quando uma mensagem chega.

    Parâmetros:
        sender: nome de quem enviou a mensagem
        text:   texto da mensagem

    Essa função é passada para service.connect() e chamada
    automaticamente em background pela thread do consumer.

    O \n antes garante que a mensagem apareça numa linha nova,
    mesmo que o usuário esteja no meio de digitar algo.
    O \n> no final reexibe o prompt para o usuário continuar.
    flush=True força a impressão imediata, sem esperar buffer.
    """
    print(f"\n[{sender}]: {text}\n> ", end="", flush=True)


def main():
    """
    Função principal — orquestra todo o fluxo do CLI.

    Fluxo:
        1. Boas-vindas
        2. Usuário digita o username
        3. Usuário escolhe ou cria uma sala
        4. Conecta ao RabbitMQ via service
        5. Exibe histórico da sala
        6. Loop de chat até Ctrl+C
        7. Desconecta de forma segura
    """

    # Criamos uma única instância do service.
    # Ela vai gerenciar toda a lógica daqui para frente.
    service = ChatService()

    # Tela de boas-vindas simples.
    print("\n" + "=" * 40)
    print("       Bem-vindo ao Chat App")
    print("=" * 40)

    # Pede o username em loop até receber um válido.
    while True:
        username = input("\nDigite seu username: ").strip()

        if not username:
            print("[erro] O username não pode ser vazio.")
            continue

        if len(username) > 35:
            print("[erro] Username muito longo — máximo 35 caracteres.")
            continue

        # Username válido — sai do loop.
        break

    # Mostra as salas e deixa o usuário escolher ou criar uma.
    # A função retorna o nome da sala escolhida/criada.
    room = selecionar_sala(service)

    print(f"\n[sistema] Conectando à sala '{room}'...")

    # Conecta ao RabbitMQ, inicia consumer e publisher.
    # Passamos o callback on_mensagem_recebida para o service —
    # ele vai chamar essa função toda vez que uma mensagem chegar.
    service.connect(
        username            = username,
        room                = room,
        on_message_received = on_mensagem_recebida
    )

    # Pequena pausa para a thread do consumer iniciar
    # antes de exibir o histórico e o prompt.
    # Sem isso, o "Conectado à sala..." do consumer pode
    # aparecer misturado com o histórico na tela.
    time.sleep(0.3)

    # Busca e exibe o histórico da sala.
    historico = service.get_history()
    exibir_historico(historico)

    print(f"[sistema] Você entrou em '{room}' como '{username.title()}'.")
    print("[sistema] Digite suas mensagens. Ctrl+C para sair.\n")

    # Loop principal de chat.
    try:
        while True:
            # Exibe o prompt e aguarda o usuário digitar.
            # end="" evita quebra de linha extra após o "> ".
            msg = input("> ")

            try:
                # Envia a mensagem via service.
                # O service valida, envia ao RabbitMQ e salva no JSON.
                service.send(msg)

            except ValueError as e:
                # Erro de validação — mostra ao usuário e continua.
                # O programa não encerra, só avisa do problema.
                print(f"[erro] {e}")

    except KeyboardInterrupt:
        # Ctrl+C — encerramento limpo e esperado.
        print("\n\n[sistema] Saindo...")

    finally:
        # finally sempre executa — com erro ou sem erro.
        # Garante que as conexões sejam fechadas mesmo se
        # algo inesperado acontecer antes do KeyboardInterrupt.
        service.disconnect()
        print("[sistema] Conexões encerradas. Até mais!")


# Garante que main() só é chamado quando o arquivo é executado
# diretamente — não quando importado por outro módulo.
# Ex: "python cli.py" → executa main()
#     "from cli import algo" → não executa main()
if __name__ == "__main__":
    main()
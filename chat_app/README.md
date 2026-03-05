# Chat App

Chat em tempo real pelo terminal usando Python e RabbitMQ.
Suporte a múltiplas salas, múltiplos usuários simultâneos e histórico de mensagens.

---

## Pré-requisitos

- Python 3.10+
- Docker

---

## Instalação

```bash
# 1. clonar o repositório
git clone <url-do-repositorio>
cd chat_app

# 2. criar e ativar o ambiente virtual
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
.venv\Scripts\activate     # Windows

# 3. instalar dependências
pip install -r requirements.txt

# 4. subir o RabbitMQ
docker compose up -d
```
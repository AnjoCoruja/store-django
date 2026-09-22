# Store — Django E-commerce + AI Agents Platform

E-commerce em Django com API REST preparada para operação por agentes de IA (n8n/Telegram).

## Setup (desenvolvimento)

```bash
pip install -r requirements/dev.txt
cp .env.example .env   # preencha os valores
python manage.py migrate
python manage.py runserver
```

## Testes

```bash
pytest
```

## Ambientes

| Módulo de settings | Uso |
|---|---|
| `config.settings.development` | local + ngrok |
| `config.settings.testing` | pytest |
| `config.settings.production` | produção (PostgreSQL via `DATABASE_URL`) |

## Estrutura

Ver `docs/ARCHITECTURE.md`.

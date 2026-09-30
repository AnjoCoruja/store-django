# Store — Django E-commerce + AI Agents Platform

E-commerce em Django com API REST preparada para operação por agentes de IA (n8n/Telegram).

## Setup (desenvolvimento)

```bash
pip install -r requirements/dev.txt
cp .env.example .env   # preencha os valores
python manage.py migrate
python manage.py runserver
```

## Catálogo pelo Google Drive + descrições com Gemini

Organize as fotos assim no Drive (pasta raiz):

```text
Catálogo/
├── Inverno/
│   └── Jaquetas Femininas/
│       └── Jaqueta Puffer, Preto/Vinho, P ao GG, 189.90.jpg
└── Verão/
    └── Camiseta UV/
        └── Camiseta UV Manga Longa, Branco/Azul, P ao GG, 59.90, 49.90, 44.90.jpg
```

- 1º nível: estação (nome contém **Verão** ou **Inverno**).
- 2º nível: categoria (vira aba na página **/loja/**). Pastas mais internas viram subcategorias.
- Nome da foto: `Nome, Cor(es), Tamanhos, Preço[, Atacado 6+][, Caixa 24+]`. Várias cores com `/`.
- A descrição é gerada pelo Gemini (LangChain) olhando a foto. Sem chave, usa um texto padrão.

Preencha no `.env` os campos marcados com `API AQUI` (veja `.env.example`) e rode:

```bash
python manage.py sync_drive                 # importa/atualiza
python manage.py sync_drive --regenerate    # regera todas as descrições
python manage.py sync_drive --unpublish-missing  # esconde produtos cujas fotos saíram do Drive
```

## Pedido pelo WhatsApp

No carrinho, **Finalizar pelo WhatsApp** grava o pedido (preços conferidos no servidor), gera a
planilha XLSX e abre o WhatsApp da loja com o resumo e o link da planilha. Os pedidos ficam no
admin em **Pedidos**.

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

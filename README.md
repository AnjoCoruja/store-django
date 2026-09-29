# Store — Django E-commerce + AI Agents Platform

E-commerce em Django com API REST para agentes de IA e sincronização automática de produtos a partir do Google Drive — 100% Django, sem n8n.

## Setup (desenvolvimento)

```bash
pip install -r requirements/dev.txt
cp .env.example .env   # preencha os valores
python manage.py migrate
python manage.py runserver
```

## Sincronização com o Google Drive

Coloque as fotos no Drive e o site publica sozinho:

```text
<pasta raiz>/<Categoria>/<Nome - Cor - Tamanhos - Preço - Atacado 6+ - Caixa 24+>.jpg
ex.: Camisetas UV/Camiseta UV - Azul, Preto - P ao G - 49,90 - 44,90 - 42,90.jpg
```

- Foto nova → produto criado, imagem baixada, legenda gerada por IA e publicado.
- Renomear o arquivo → dados atualizados. Trocar a foto → imagem e legenda refeitas.
- Mover para outra pasta → muda a categoria. Apagar a foto → produto despublicado.
- Foto sem preço → produto criado despublicado para revisão no admin.

Configuração:

1. Crie uma service account no Google Cloud, ative a Google Drive API e baixe a chave JSON.
2. Compartilhe a pasta raiz do Drive com o e-mail da service account (leitor).
3. Preencha `DRIVE_ROOT_FOLDER_ID`, `GOOGLE_SERVICE_ACCOUNT_FILE` (ou `_JSON`) e, opcionalmente, `AI_API_KEY`/`AI_MODEL` no `.env`.
4. Rode o worker:

```bash
python manage.py sync_drive           # uma vez
python manage.py sync_drive --watch   # contínuo (a cada DRIVE_SYNC_INTERVAL s)
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

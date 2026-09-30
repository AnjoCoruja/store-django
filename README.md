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

Pasta do catálogo (já configurada): **REDBLUELINE**
https://drive.google.com/drive/folders/17aVjdXzO65x1LbpCclqJTzhX9zRJnWb0

```text
REDBLUELINE/
├── INVERNO/
│   ├── Jaquetas Femininas/   parka-lã-batida-p-m-g-gg-preto-bege-vermelho-190.00.jpg
│   ├── Jaqueta Masculina/ · Jaqueta Infantil/ · Corta Vento .../
└── VERÃO/
    ├── Camisas UV/           camiseta-uv-adulto-feminina-azul-branco-tamanho-p-ao-gg-30.00.jpg
    └── Vestidos Indianos/
```

- 1º nível: estação (nome contém **VERÃO** ou **INVERNO**). 2º nível: categoria (aba em **/loja/**).
- Nome da foto (com hífens): `nome-do-produto-TAMANHOS-CORES-PREÇO.jpg`
  - tamanhos: `p-m-g-gg`, `g1-g2-g3`, `6-8-10-12` ou `p-ao-gg` / `04-ao-16`
  - cores: `preto-azul-cinza.claro` (use ponto para cor composta: `azul.bebe`, `cinza.escuro`)
  - preço: o último número (`165.00`)
  - também aceita o formato com vírgulas: `Nome, Cor, Tamanhos, Preço.jpg`
- Fotos com o mesmo nome na mesma pasta são importadas uma vez só.
- Sem credencial, o site lê a pasta enquanto ela estiver compartilhada como "Qualquer pessoa com o link".
  Para usar a API oficial do Google, preencha `GOOGLE_API_KEY` ou `GOOGLE_SERVICE_ACCOUNT_FILE` no `.env`.
- Descrição: gerada pelo Gemini (LangChain) olhando a foto quando `GEMINI_API_KEY` estiver preenchida;
  sem chave, usa um texto padrão.

```bash
python manage.py sync_drive                      # importa/atualiza a pasta REDBLUELINE
python manage.py sync_drive --regenerate         # regera todas as descrições (Gemini)
python manage.py sync_drive --unpublish-missing  # esconde produtos cujas fotos saíram do Drive
python manage.py sync_drive --folder <link-ou-id> # outra pasta
```

## Pedido pelo WhatsApp

No carrinho, **Finalizar pelo WhatsApp** grava o pedido (preços conferidos no servidor), gera a
planilha XLSX e abre o WhatsApp da loja com o resumo e o link da planilha. Os pedidos ficam no
admin em **Pedidos**.

## Atualizando o projeto (git pull)

Se o `git pull` disser *"Your local changes ... would be overwritten"*:

```bash
git status                 # mostra quais arquivos você alterou
git stash                  # guarda suas alterações de lado
git pull                   # baixa a versão nova
git stash pop              # devolve suas alterações (se ainda quiser)
```

Para descartar as alterações locais de código e ficar igual ao GitHub:
`git fetch && git reset --hard origin/main`. Isso **não apaga** `.env`, `db.sqlite3` nem arquivos
`*.json` de chaves, que ficam fora do Git (estão no `.gitignore`).

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

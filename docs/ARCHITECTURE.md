# ARCHITECTURE.md — Django Store + AI Agents Platform

**Versão:** 1.0 · **Fase:** 1 (Planejamento) · **Data:** 2026-09-21

---

## 1. Visão Geral

E-commerce em Django com API REST preparada desde o início para ser operada por
agentes de IA (via n8n/Telegram). O Django é a fonte de verdade; o n8n e os
agentes são clientes da API — o site continua funcionando com o n8n offline.

```text
Telegram → n8n → AI Orchestrator → Website Agent → Django REST API → Django → PostgreSQL → Website
```

### Metas arquiteturais
- **Segurança primeiro:** nada administrativo aberto sem autenticação.
- **Desacoplamento:** agentes falam apenas com a API, nunca com o banco.
- **Testabilidade:** regras de negócio em services, não em views.
- **Simplicidade (KISS):** infra de produção só quando necessária.
- **Portabilidade de URL:** `PUBLIC_BASE_URL` em env, nunca ngrok hardcoded.

---

## 2. Decisões Arquiteturais (ADR resumido)

| # | Decisão | Justificativa |
|---|---------|---------------|
| ADR-1 | Django 5.x + DRF | Stack madura, admin pronto, ORM robusto |
| ADR-2 | SQLite em dev / PostgreSQL em prod via `DATABASE_URL` (dj-database-url) | Código agnóstico de engine |
| ADR-3 | `DecimalField` para valores monetários | Float causa erros de arredondamento |
| ADR-4 | Apps: `products`, `categories`, `images` (dentro de products), `audit`, `api` | Coesão alta; categories separado só se crescer — **decisão: Category fica em `products` no MVP** (KISS), extração futura é trivial |
| ADR-5 | Autenticação da API do agente: **DRF Token por serviço** (1 token = 1 agente) + escopo de permissões | Simples, revogável, auditável. JWT avaliado e adiado (complexidade sem ganho no MVP) |
| ADR-6 | Regras de negócio em camada `services.py` | Views finas, lógica testável isolada |
| ADR-7 | Confirmação de operações críticas: campo `requires_confirmation` no contrato da ação + endpoint de confirmação | O agente envia ação → API retorna resumo → agente confirma → API executa |
| ADR-8 | `AuditLog` append-only, escrito em toda mutação via API do agente | Rastreabilidade exigida pelo prompt |
| ADR-9 | Versão de API por URL (`/api/v1/`) | Evolução sem quebrar clientes |
| ADR-10 | Settings divididos: `base.py`, `development.py`, `testing.py`, `production.py` | Ambientes isolados, segredos só em env |
| ADR-11 | Slugs únicos com sufixo automático em colisão | SEO + unicidade sem erro 500 |
| ADR-12 | Rate limiting (DRF throttling) apenas nos endpoints do agente | Proteção mínima sem complexidade |

---

## 3. Estrutura de Diretórios (alvo)

```text
store/
├── manage.py
├── config/
│   ├── settings/{base,development,testing,production}.py
│   ├── urls.py · asgi.py · wsgi.py
├── apps/
│   ├── products/      # Product, Category, ProductImage, services
│   ├── audit/         # AuditLog + helpers
│   └── api/           # DRF: serializers, views, permissions, routers (v1)
├── templates/ · static/ · media/
├── tests/             # pytest por app
├── scripts/
├── docs/
├── requirements/{base,dev,prod}.txt
├── .env.example · .gitignore
├── Dockerfile · docker-compose.yml (adiado até fase de prod)
└── README.md
```

---

## 4. Modelo de Dados (rascunho — validar na FASE 3)

### Category
`name (unique)`, `slug (unique, indexed)`, `description`, `image`, `is_active`, `sort_order`, timestamps

### Product
`name`, `slug (unique, indexed)`, `description (text)`, `price (Decimal 10,2, ≥ 0)`,
`wholesale_price (Decimal, nullable)`, `stock (PositiveInteger, default 0)`,
`category (FK → Category, PROTECT)`, `is_active`, `is_published (indexed)`,
`created_at`, `updated_at`
- Índice composto: `(is_published, category)`
- Check constraints: `price >= 0`, `stock >= 0`

### ProductImage
`product (FK, related_name=images)`, `image`, `alt_text`, `is_primary`, `sort_order`, timestamps
- Validação: extensão + MIME real (python-magic ou validação de header), tamanho máx (ex.: 5 MB)

### AuditLog (append-only, sem update/delete)
`actor_type (user|agent)`, `actor_id`, `action`, `resource`, `resource_id`,
`old_value (JSON)`, `new_value (JSON)`, `status`, `ip`, `created_at (indexed)`
- **Nunca** registra tokens/senhas.

---

## 5. API REST v1 — Contratos

### Pública (leitura)
```
GET /api/v1/products/            # lista paginada, filtros: category, q, price_min/max
GET /api/v1/products/{id|slug}/
GET /api/v1/categories/
GET /api/v1/categories/{id|slug}/
```

### Agente (escrita, autenticada por token + permissão)
```
GET   /api/v1/agent/products/
POST  /api/v1/agent/products/
PATCH /api/v1/agent/products/{id}/
PATCH /api/v1/agent/products/{id}/price/     # crítica → confirmação
PATCH /api/v1/agent/products/{id}/stock/     # crítica → confirmação
POST  /api/v1/agent/products/{id}/publish/
POST  /api/v1/agent/products/{id}/unpublish/
POST  /api/v1/agent/actions/{action_id}/confirm/   # confirmação de ação pendente
```

### Fluxo de confirmação
1. Agente envia ação crítica → API cria `PendingAction` (ou resposta 202 + resumo) e **não executa**.
2. Resposta: `{ "action_id", "summary": {...atual → novo...}, "requires_confirmation": true }`
3. Agente chama `/confirm/` → API valida e executa → grava AuditLog.
4. Expiração de ações pendentes (ex.: 10 min) para evitar estado órfão.

### Erros (formato único)
```json
{ "success": false, "error": { "code": "PRODUCT_NOT_FOUND", "message": "..." } }
```

---

## 6. Segurança

- **Autenticação:** DRF Token (1 por agente) — header `Authorization: Token ...`.
- **Autorização:** permissões DRF dedicadas (`AgentPermission`), escopo por endpoint.
- **Nunca** expor endpoints do agente sem auth; bloqueio testado por testes de segurança.
- **Rate limiting:** `ScopedRateThrottle` nos endpoints do agente.
- **Segredos:** somente via variáveis de ambiente (`.env` fora do Git).
- **Logs:** requests do agente, auth failures, erros — sem segredos.
- **Uploads:** validação de MIME real, tamanho, nome sanitizado, armazenamento fora do código.
- **CSRF/ALLOWED_HOSTS/CSRF_TRUSTED_ORIGINS:** configurados por env (ngrok muda).

---

## 7. Ambientes e Configuração

| Ambiente | Banco | Debug | Uso |
|----------|-------|-------|-----|
| development | SQLite (ou Postgres via env) | True | local + ngrok |
| testing | SQLite em memória | False | pytest |
| production | PostgreSQL (`DATABASE_URL`) | False | futuro |

Env vars: `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_SETTINGS_MODULE`,
`DATABASE_URL`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `PUBLIC_BASE_URL`.

---

## 8. Testes (estratégia)

- **pytest + pytest-django** + factory-boy (factories) + coverage.
- Camadas: models (constraints), services (regras), API (status codes, payloads),
  permissões (403/401), fluxo de confirmação, casos de erro listados no prompt
  (preço inválido, estoque inválido, produto inexistente, sem permissão).
- Meta: nenhuma fase avança com testes vermelhos.

---

## 9. Performance & SEO (diretrizes iniciais)

- `select_related('category')` / `prefetch_related('images')` nas listagens.
- Paginação DRF padrão (ex.: 20 itens).
- SEO: URLs com slug, `<title>`/meta description dinâmicos, sitemap.xml,
  robots.txt, canonical, Open Graph básico.
- Imagens: lazy loading nativo (`loading="lazy"`); resize/WebP adiados até necessidade medida.

---

## 10. Roadmap de Fases (gates de validação)

| Fase | Entrega | Gate |
|------|---------|------|
| 1 | Este documento | ✅ Aprovado |
| 2 | Projeto Django + settings por ambiente + env + Git | ✅ `manage.py check` OK, 3 testes verdes, commit inicial |
| 3 | Models + migrations + testes de model | ✅ 16 testes verdes, migrations aplicadas |
| 4 | Website (home/catálogo/detalhe/categoria) responsivo | ✅ 28 testes verdes |
| 5 | Admin completo | ✅ 36 testes verdes |
| 6 | API v1 pública | testes de API |
| 7 | API do agente + auth + auditoria + confirmação | testes de segurança |
| 8 | ngrok + teste externo | request externo OK |
| 9 | Suíte completa + cobertura | suite verde |
| 10–13 | n8n / LangGraph / Website Agent / E2E | conforme prompt |

---

## 11. Lacunas e Decisões Tomadas (regra "não inventar requisitos")

| Lacuna | Decisão registrada |
|--------|--------------------|
| App `orders` e `users` citados no prompt, sem requisitos de checkout/carrinho | **Adiados** — não há fluxo de pedido definido; criar apps vazios agora violaria KISS. Serão criados na fase em que pedidos forem especificados |
| Mecanismo de confirmação | Pendente de ação persistida com expiração (ADR-7) |
| Engine de imagens (Pillow só, ou thumbnailing) | Pillow no MVP; sorl/easy-thumbnails adiados |
| Cache/Redis | Adiado até medição de necessidade |
| Autenticação de usuários finais do site (login de cliente) | Adiada junto com `orders` |

---

**Status FASE 1:** aguardando validação para iniciar FASE 2 (Inicialização Django).

## FASE 6 — API pública v1 (2026-09-21)

- App `apps.api` com DRF: routers em `/api/v1/` (`/api/v1/products/`, `/api/v1/categories/`).
- Endpoints somente leitura (ReadOnlyModelViewSet); escrita chega na fase da Agent API com autenticação por token, permissões e rate limiting.
- Apenas produtos publicados e categorias ativas expostos; lookup por slug.
- `product_count` anotado conta somente produtos publicados.
- Preços serializados como string (DecimalField) — sem ponto flutuante.
- Filtros: `?category=<slug>` e `?q=<termo>` (icontains em nome/descrição); paginação PageNumber (20/página).
- select_related + prefetch_related (sem N+1); imagens ordenadas primária primeiro.
- Correção no pytest.ini: `python_files` agora inclui `tests.py` (testes dos apps não estavam sendo coletados antes).
- 51 testes passando (15 novos da API); `manage.py check` limpo.

## FASE 7 — Agent API: autenticação, rate limiting e auditoria (2026-09-21)

- Submódulo `apps.api.agent` montado em `/api/v1/agent/products/` (lookup por slug).
- Autenticação: DRF Token (`Authorization: Token <key>`) vinculado a usuários de serviço staff e ativos (`IsAgentToken`). Sem token, token inválido, usuário comum ou inativo → 401/403.
- Rate limiting: `AgentRateThrottle` (SimpleRateThrottle, chave = hash do token, scope `agent`, 120/min em produção; testing.py usa limite alto).
- Auditoria: toda mutação grava AuditLog append-only com actor, ação, valores old/new e IP — nunca segredos/tokens.
- Escrita restrita: `ProductAgentSerializer` só expõe campos de negócio; slug read-only (gerado do nome); preço negativo rejeitado (400) além do check constraint.
- DELETE é **soft-delete** (desativa + despublica) — nenhuma operação destrutiva, conforme constraints do master prompt.
- 63 testes passando (12 novos: auth, escrita, auditoria, throttle 429); migrações do authtoken aplicadas.

## FASE 8 — Operações críticas com confirmação + provisionamento do agente (2026-09-21)

- `PendingAction` (apps.api.agent): ação crítica persistida (UUID, tipo, payload, resumo atual→novo, expiração 10 min, status pending/confirmed/expired).
- Endpoints: `POST /api/v1/agent/products/<slug>/price/` e `/stock/` retornam **202** com `{action_id, summary, requires_confirmation}` e **não aplicam** a mudança; `POST /api/v1/agent/actions/<uuid>/confirm/` valida (pendente, não expirada, mesmo agente) e aplica atomicamente (select_for_update), gravando AuditLog old/new.
- Regras: expiração marcada fora do bloco atômico (rollback não desfaz a marcação); confirmação dupla → 400; ação de outro agente → 403; validação de domínio (preço/estoque ≥ 0) → 400 sem criar ação.
- Management command `create_agent_token <username> [--rotate]`: cria/normaliza usuário de serviço (staff, sem senha utilizável, nunca superuser), emite token uma única vez por rotação — segredo fora do código e do versionamento.
- 77 testes passando (14 novos: propostas, confirmação, expiração, autorização entre agentes, command); migração `api.0001` aplicada.

## FASE 9 — Suíte completa + cobertura (2026-09-21)

- Cobertura medida com pytest-cov: **98,64%** total (955 stmts, 13 miss) sobre 86 testes.
- Gate permanente no `pytest.ini`: `--cov=apps --cov-fail-under=95` — a suíte falha se a cobertura cair abaixo de 95%.
- Lacunas cobertas nesta fase: validações de domínio (preço/stock inválido, ausente, negativo), `__str__` e auto-expiração de PendingAction, normalização de usuário no `create_agent_token`, fallback de `primary_image` sem prefetch, guarda `perform_destroy`, throttle sem token.
- Linhas não cobertas restantes são triviais e aceitas: views.py placeholder de apps sem view (audit/products), `__str__`/upload-path validators em products/models.py, e o ramo `validate_price` do serializer (o MinValueValidator do model dispara antes — comportamento verificado no teste).
- Observação: a suíte roda em ~1,1s (SQLite in-memory).

# fix Visita — 5 FKs cross-schema removidas (aplicado) + 2º bug descoberto

- **Data:** 2026-06-09
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Status:** ⚠️ **Fix de FK aplicado e correto (erro de FK eliminado), MAS o POST ainda 500** por um **SEGUNDO bug pré-existente independente** (enum nativo vs. varchar). Conforme a regra "se falhar, reportar e PARAR", **não commitei** e **não toquei mais no model**.
- **Arquivo:** `modules/campo/models/visita.py` · **Backup:** `visita.py.bak-fkfix-20260609-052604`
- **Commit:** ❌ não feito (TESTE PRINCIPAL não passou — POST ≠ 201).

---

## 1. Fix aplicado (5 linhas) — diff
Removido `ForeignKey(...)` (vira UUID puro, preservando nullable/index). `visita_origem_id` mantida.

| Linha | Antes | Depois |
|-------|-------|--------|
| 131 | `cliente_id = Column(UUID(as_uuid=True), ForeignKey("clients.clients.id"), nullable=True, index=True)` | `cliente_id = Column(UUID(as_uuid=True), nullable=True, index=True)` |
| 132 | `contrato_id = Column(UUID(as_uuid=True), ForeignKey("crm.contracts.id"), nullable=True)` | `contrato_id = Column(UUID(as_uuid=True), nullable=True)` |
| 149 | `lead_id = Column(UUID(as_uuid=True), ForeignKey("crm.leads.id"), nullable=True)` | `lead_id = Column(UUID(as_uuid=True), nullable=True)` |
| 150 | `oportunidade_id = Column(UUID(as_uuid=True), ForeignKey("crm.opportunities.id"), nullable=True)` | `oportunidade_id = Column(UUID(as_uuid=True), nullable=True)` |
| 215 | `proposta_id = Column(UUID(as_uuid=True), ForeignKey("crm.proposals.id"), nullable=True)` | `proposta_id = Column(UUID(as_uuid=True), nullable=True)` |
| 260 | `visita_origem_id = Column(..., ForeignKey("visitas.id"), nullable=True)` | **mantida (mesmo schema)** |

- `py_compile` OK · deploy nos 9 containers · **host==container** (`3a0c8d75…`) · backend **healthy**.

## 2. Resultado do TESTE PRINCIPAL — `POST /api/v1/campo/visitas/`
**HTTP 500** (ainda). MAS o erro **mudou** — prova que o fix de FK funcionou:
- Antes: `NoReferencedTableError: ... 'crm.proposals' / 'crm.opportunities' / 'clients.clients'` → **eliminado**.
- Agora: `asyncpg UndefinedObjectError: type "tipovisita" does not exist`.

## 3. SEGUNDO bug pré-existente (independente, fora do escopo das 5 FKs)
O model declara colunas como **enum NATIVO do Postgres**, mas o banco tem **varchar** e os tipos enum **não existem**:
- (a) `pg_type` para `tipovisita/statusvisita/origemvisita/tiporesponsavel/resultadovisita` = **vazio** (não existem).
- (b) colunas `tipo/status/origem/responsavel_tipo/resultado` em `visitas` = **`character varying`**.
- (c) model (`visita.py`): `tipo = Column(Enum(TipoVisita))`, `status = Column(Enum(StatusVisita))`, `origem = Column(Enum(OrigemVisita))`, `responsavel_tipo = Column(Enum(TipoResponsavel))`, `resultado = Column(Enum(ResultadoVisita))`.
- SQLAlchemy `Enum(...)` usa `native_enum=True` por padrão → no INSERT casta `$N::tipovisita`, que não existe → 500.

➡️ Outro motivo dos **0 registros**: além das FKs, os enums nativos nunca casaram com o banco (varchar). **Nunca foi possível criar visita** por 2 razões somadas.

## 4. Fix proposto para o 2º bug (próximo passo — só código, SEM migration)
Trocar `Enum(X)` por `Enum(X, native_enum=False)` nas 5 colunas (linhas 117, 118, 119, 125, 197). `native_enum=False` faz o SQLAlchemy tratar como **VARCHAR** (valida no Python, grava string) — **casa exatamente** com as colunas varchar já existentes. Sem migration (a coluna já é varchar). Risco baixo, cirúrgico, beneficia todo o módulo `campo`.

## 5. Estado atual
- Fix de FK **deployado** (host==container, healthy, health **200**), **NÃO commitado**.
- `visitas` = **0** (o POST falhou no INSERT → rollback, sem lixo).
- 3ª tool ainda preservada em `agent_service.py.fvisita3tools-pending-modelfix` (não reaplicada).
- Rollback do model: `visita.py.bak-fkfix-20260609-052604`.

## 6. DECISÃO necessária (sua)
Autorizar o **2º fix** (enum `native_enum=False` nas 5 colunas)? Com ele, o POST deve ir a 201 e aí: commit único (FK + enum) → reaplicar 3ª tool → bakar no próximo rebuild.

## 7. Durabilidade
Fix de FK (e o futuro fix de enum + a 3ª tool) precisam ser **bakados no próximo rebuild**. Hoje vivem só via docker cp; recreate reverteria para a imagem `5958168f`.

---

## Resumo
- 5 FKs cross-schema removidas (correto): **erro de FK eliminado**. ✅
- POST ainda 500 por **2º bug pré-existente**: enums nativos (`tipovisita` etc.) inexistentes no banco varchar. ⛔
- **Sem commit** (teste não passou). Fix de FK deployado e correto, aguardando o 2º fix.
- **Próximo passo (sua autorização):** `Enum(..., native_enum=False)` nas 5 colunas → testar 201 → commit.

*PAREI conforme a regra (falhou → reportar e parar). Não insisti, não toquei mais no model, não reapliquei a 3ª tool, não rebuildei.*

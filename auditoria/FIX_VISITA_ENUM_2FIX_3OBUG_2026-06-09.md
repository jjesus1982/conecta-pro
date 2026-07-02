# fix Visita — 2º fix (enum native_enum=False) aplicado + 3º bug descoberto

- **Data:** 2026-06-09
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Status:** ⚠️ **2º fix (enum) aplicado e correto — erro de enum eliminado — MAS POST ainda 500 por um 3º bug pré-existente** (descompasso de tipo: `confirmada_por` uuid no banco vs String no model). Conforme a regra "3º bug → reportar exato e PARAR", **não consertei sozinho** e **não commitei**.
- **Arquivo:** `modules/campo/models/visita.py` · **Backup:** `visita.py.bak-enumfix-20260609-053426`
- **Commit:** ❌ não feito (POST ≠ 201).

---

## 1. 2º fix aplicado (5 linhas Enum) — diff
`Enum(X)` → `Enum(X, native_enum=False)` (default/nullable/index preservados):

| Linha | Coluna | Depois |
|-------|--------|--------|
| 117 | `tipo` | `Column(Enum(TipoVisita, native_enum=False), nullable=False, default=...)` |
| 118 | `status` | `Column(Enum(StatusVisita, native_enum=False), nullable=False, default=..., index=True)` |
| 119 | `origem` | `Column(Enum(OrigemVisita, native_enum=False), nullable=False, default=...)` |
| 125 | `responsavel_tipo` | `Column(Enum(TipoResponsavel, native_enum=False), nullable=False, default=...)` |
| 197 | `resultado` | `Column(Enum(ResultadoVisita, native_enum=False), nullable=True)` |

- Fix de FK anterior preservado (FKs cross-schema restantes = **0**). `py_compile` OK · deploy 9 containers · **host==container** (`0b8244e0…`) · **healthy**.

## 2. Resultado do POST `/api/v1/campo/visitas/`
**HTTP 500** (ainda). MAS o erro mudou de novo — prova que o 2º fix funcionou:
- Antes: `UndefinedObjectError: type "tipovisita" does not exist` → **eliminado**.
- Agora: `DatatypeMismatchError: column "confirmada_por" is of type uuid but expression is of type character varying`.

## 3. 3º bug pré-existente (descompasso de TIPO model↔banco)
- Banco: `confirmada_por` = **uuid**.
- Model (`visita.py:176`): `confirmada_por = Column(String(100))  # Nome/canal de confirmacao`.
- O comentário sugere que o autor pensou em **nome/texto**, mas a coluna no banco é **uuid** → no INSERT, manda varchar p/ coluna uuid → 500.

**Auditoria read-only (actor-columns uuid no banco):** `confirmada_por` é o **único** declarado como `String` no model; `cancelada_por`, `created_by`, `updated_by` estão corretos como `UUID`. **Não auditei todas as ~50 colunas** — pode haver outros descompassos em colunas não-actor.

## 4. Padrão observado (importante)
**3 POSTs → 3 bugs pré-existentes distintos** no mesmo model:
1. FK cross-schema (corrigido).
2. Enum nativo vs varchar (corrigido).
3. Tipo `confirmada_por` String vs uuid (este).

➡️ O model `Visita` **nunca esteve alinhado** com o banco real. Sugestão (sua decisão): em vez de whack-a-mole POST-a-POST, fazer **uma auditoria read-only completa** comparando o tipo de TODAS as colunas do model vs `information_schema` da tabela `visitas`, listar todos os mismatches de uma vez, e então você decide o conserto (corrigir model coluna-a-coluna, ou alinhar de forma sistemática).

## 5. Decisão necessária (sua) — opções para o 3º bug
- **(a)** `confirmada_por` deve ser **uuid** (quem confirmou) → no model: `Column(UUID(as_uuid=True), nullable=True)`. (provável intenção real, alinha ao banco)
- **(b)** Deve ser **texto** (nome/canal) → então o BANCO está errado e precisaria migration (alterar coluna p/ varchar) — mais invasivo.
- **+ Recomendado:** antes de seguir, rodar a **auditoria completa de tipos** (read-only) p/ achar todos os mismatches.

## 6. Estado atual
- 2 fixes (FK + enum) **deployados** (host==container `0b8244e0`, healthy, **health 200**), **NÃO commitados**.
- `visitas` = **0** (POST falhou → rollback, sem lixo).
- 3ª tool ainda preservada em `agent_service.py.fvisita3tools-pending-modelfix`.
- Rollback: `visita.py.bak-enumfix-20260609-053426` (com 2 fixes) / `visita.py.bak-fkfix-20260609-052604` (só FK) / original na imagem `5958168f`.

## 7. Durabilidade
Os fixes (FK + enum + o que vier) + a 3ª tool precisam ser **bakados no próximo rebuild**. Hoje só via docker cp.

---

## Resumo
- 2º fix (enum `native_enum=False`) **correto**: erro de enum eliminado. ✅
- POST ainda 500 por **3º bug**: `confirmada_por` uuid(banco) vs String(model:176). ⛔
- **Sem commit.** 2 fixes deployados e corretos, aguardando sua decisão sobre o 3º + (recomendado) auditoria completa de tipos.

*PAREI conforme a regra (3º bug → reportar exato e parar, não consertar sozinho). Não commitei, não reapliquei a 3ª tool, não rebuildei.*

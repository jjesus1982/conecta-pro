# fix Visita — 3º fix (tipos) APLICADO → POST /campo/visitas/ = 201 ✅ RESOLVIDO

- **Data:** 2026-06-09
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Status:** ✅ **RESOLVIDO.** O `POST /api/v1/campo/visitas/` (500 desde sempre) agora retorna **201**. 3 grupos de bugs pré-existentes corrigidos.
- **Arquivo:** `modules/campo/models/visita.py` · **Backup:** `visita.py.bak-typefix-20260609-132025`
- **Commit:** **`4a1296e3`** — `fix(campo): alinha model Visita ao banco (FK + enum + tipos) - corrige POST visitas 500`

---

## 1. 3º fix — diff das 3 linhas (alinha ao banco, sem migration)
| Linha | Coluna | Antes | Depois |
|-------|--------|-------|--------|
| 176→178 | `confirmada_por` | `Column(String(100))` | `Column(UUID(as_uuid=True), nullable=True)` |
| 210 | `interesse_nivel` | `Column(Integer)` | `Column(String)` |
| 273 | `followup_data` | `Column(Date)` | `Column(DateTime)` |

- `UUID`/`DateTime`/`String` já importados (sem import novo). `py_compile` OK. Black reformatou (cosmético) no commit.
- Os 2 fixes anteriores preservados: **FKs cross-schema = 0**, **Enums native_enum=False = 5**.

## 2. TESTE PRINCIPAL — `POST /api/v1/campo/visitas/`
**HTTP 201** ✅ — `numero=VIS-2026-00001`, `status=agendada`, `id` retornado. Confirmado no banco (responsavel_id, origem=LEAD, status=AGENDADA, e os 3 campos antes problemáticos aceitos). Visita de teste **limpa** → `visitas` = 0.
- Re-confirmado após re-sync da versão commitada/reformatada: **201** de novo.

## 3. Jornada completa (3 grupos de bugs pré-existentes no model Visita)
| # | Bug | Erro | Fix |
|---|-----|------|-----|
| 1 | FK cross-schema | `NoReferencedTableError` (crm.*/clients.*) | removidas 5 ForeignKey → UUID puro |
| 2 | Enum nativo | `type "tipovisita" does not exist` | `Enum(..., native_enum=False)` em 5 colunas |
| 3 | Tipos | `column "confirmada_por" is of type uuid...` | 3 colunas alinhadas (UUID/DateTime/String) |

➡️ O `POST /campo/visitas/` **nunca funcionou** (0 registros na tabela). Agora funciona para **todo o módulo campo**, não só o agente.

## 4. Estado
- **host==container** (`829ad460…`) · backend **healthy** · **health 200** · `visitas` = 0.
- Commit `4a1296e3` no branch `feature/people-management-reorganization`.
- Mismatches restantes (NÃO corrigidos — não quebram): 2 benignos (varchar↔text), 3 nullable divergentes, 10 colunas DB-only. Ver auditoria.

## 5. Durabilidade + próximo passo
- Fixes (FK+enum+tipos) **commitados**, vivos via docker cp — **bakar no próximo rebuild** (imagem atual `5958168f` ainda tem o model antigo).
- **PRÓXIMO PASSO (separado):** reaplicar a 3ª tool `agendar_visita` (preservada em `agent_service.py.fvisita3tools-pending-modelfix`). Agora que `criar_visita` funciona, a tool deve passar o Teste A (criar AGENDADA). Depois: deploy + bakar tudo no rebuild.

---

## Resumo
- 3º fix (tipos) aplicado → **POST /campo/visitas/ = 201** ✅ (era 500).
- 3 grupos de bugs pré-existentes resolvidos (FK + enum + tipos), **commit único `4a1296e3`**.
- host==container, health 200, visitas limpa.
- Próximo: reaplicar a 3ª tool do agente (não feito agora). Não rebuildei.

*PAREI conforme instruído. Não reapliquei a 3ª tool. Não rebuildei.*

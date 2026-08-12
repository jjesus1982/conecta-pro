---
name: finding-schema-drift
description: Use ao investigar ou corrigir schema drift entre os models (SQLAlchemy) e o banco no Conecta PRO — quando endpoints dão 500 por UndefinedColumn/UndefinedTable, antes de desenvolver num módulo, ao fazer "raio-x de prontidão" de um módulo, ou ao aplicar migrations de colunas/tabelas que o model espera e o banco não tem. Cobre detecção read-only (ORM-load), classificação em 3 baldes, backup→staging→produção, reversibilidade e relatório.
---

# Finding & Fixing Schema Drift (Conecta PRO)

## Overview
Drift = o model espera coluna/tabela/enum que o banco não tem (model-sem-migration). Sintoma: endpoint 500 com `UndefinedColumnError` / `UndefinedTableError` / `LookupError` de enum.

**Princípio inegociável:** dado real (trabalhista/contábil/fiscal) é intocável. **Só `CREATE TABLE` / `ADD COLUMN`** de forma autônoma — nunca `DROP/UPDATE/DELETE`. Backup antes de cada produção, staging valida antes, e o que mexe em dado real **PARA** e vira decisão humana. Evidência antes de afirmar (ver `superpowers:verification-before-completion`).

## Quando NÃO agir sozinho
Se a correção mexe em dado real (rename de coluna/tabela com linhas, mudança de enum com dado, mudança de tipo) → **balde 3**: listar com SELECT de amostra e PARAR. Nunca adivinhar semântica de negócio.

---

## O método (read-only primeiro, sempre)

### PASSO 1 — Detectar (read-only, determinístico)
Sem token de auth, o detector confiável é o **ORM-load test**: carregar 1 amostra de cada model (`SELECT ... LIMIT 1`). Qualquer model com coluna/tabela faltando ou enum divergente **falha** = 500 garantido no endpoint que o usa. Roda dentro do container backend (tem os models + DATABASE_URL).

Use `scripts/drift_finder.py` (incluso). Ele: descobre os mappers via `gc`, faz load-test, classifica cada falha em **TABLE ausente / COLUMN ausente / ENUM / OUTRO**.

**Armadilha #1 — cascata de coluna:** o load-test mostra só a **PRIMEIRA** coluna ausente por tabela. Não itere coluna-a-coluna (lento e incompleto). Para cada tabela com falha de coluna, faça **full-diff**: `model.columns` vs `information_schema.columns` → adiciona TODAS as ausentes de uma vez.

### PASSO 2 — Classificar nos 3 baldes (ANTES de agir)
- **BALDE 1 — aditivo seguro (autônomo):** coluna nova que o model espera, em **tabela VAZIA** (`count(*)=0`), sem equivalente legado com dado. → `ADD COLUMN`.
- **BALDE 2 — tabela de funcionalidade (autônomo se model coerente):** tabela que não existe em **nenhum** nome (nem renomeada), model coerente (tem `__tablename__`, colunas). → criar **vazia** a partir do metadata do model.
- **BALDE 3 — redesenho com dado real (PARAR → decisão humana):**
  - tabela do model ↔ tabela legada **com linhas** (rename-com-dado). Ex.: model `nfse` ↔ `nfses` (27 reais); `employee_vacation_periods` ↔ `hr_vacation_periods` (67 reais).
  - **tabela POPULADA** (≥1 linha) com colunas ausentes → pode ser rename PT→EN. Ex.: `financial_widgets` (4 linhas) com 49 colunas novas = reescrita, não aditivo.
  - enum com valor de dado fora do tipo (ex.: `periodstatus` tem `PENDING`, enum não).
  - → listar cada caso com `SELECT` de amostra + opções de mapeamento. **Não aplicar.**

**Regra de ouro:** autônomo = só tabela/coluna em **tabela vazia**. Qualquer linha de dado → balde 3.

### PASSO 3 — Backup + Staging (mesmo que pareça trivial)
1. `pg_dump -Fc` da produção → `backups/postgresql/conecta_pro_PRE_<TAG>_$(date +%Y%m%d_%H%M%S).dump`. Validar (`pg_restore --list`, tamanho>0).
2. Recriar staging `conecta_pro_drift_check` a partir DESTE dump (estado = prod).
3. Aplicar balde 1+2 no staging. Confirmar ORM-load FAIL→OK e dado intacto.

### PASSO 4 — Produção
Aplicar as mesmas operações. Validar: ORM-load FAIL→OK, **backend health 200**, containers healthy, contagens de dado **idênticas ao backup** (nada tocado). Avançar alembic.

### PASSO 5 — Entregar
Relatório em `/opt/conecta-pro/auditoria/<NOME>_<data>.md`: 3 baldes classificados, FAIL→OK antes/depois (prova ORM), confirmação de zero-dado-tocado, balde 3 para decisão, models suspeitos não criados, bloco de reversão. **Sempre** dar o `scp` (ver memória `feedback-scp-usar-ip`: `scp root@82.25.75.74:<path> ~/Downloads/`).

---

## Armadilhas técnicas (caras — aprendidas na marra)

1. **`metadata.create_all(tables=[...])` NÃO basta** — ele tenta criar TODOS os enums do metadata global, inclusive de outros módulos em schemas inexistentes (ex.: `retention.step_type_enum`). Crie **tabela a tabela** ou via `CreateTable` raw.

2. **`meta.sorted_tables` quebra** — percorre o metadata inteiro e estoura em FK órfã de OUTRO módulo (ex.: `documentos_fiscais_diaristas → diaristas` inexistente). Faça **topo-sort só do seu subconjunto** usando `fk.target_fullname` (string, sem resolver).

3. **Criar tabela SEM FK constraints** — `CreateTable(tb, include_foreign_key_constraints=[])`. Vários models apontam FK para alvo quebrado (`funcionarios` inexistente; real é `employees`) ou para **VIEW** (`payroll_periods` é view → não se faz FK a view). Tabela nasce vazia, ORM carrega sem a FK do banco; adicione FK depois.

4. **FK → tabela inexistente = "model suspeito"** → NÃO criar; listar para revisão humana. (Ex.: 5 tabelas hr apontando `funcionarios`.)

5. **Criar enums manualmente** — `CreateTable` raw não cria os tipos. Gere `DO $$ BEGIN CREATE TYPE <n> AS ENUM (...); EXCEPTION WHEN duplicate_object THEN null; END $$;` (idempotente). **Sem isso o FORWARD.sql não faz replay** (disaster-recovery quebra com `type "..." does not exist`).

6. **`server_default` string de função** — models trazem `server_default='gen_random_uuid()'` (string) que renderiza `DEFAULT 'gen_random_uuid()'` (aspas) → inválido p/ UUID. Normalize: se `arg` termina em `)`, envolva em `text(arg)`.

7. **`ADD COLUMN ... NOT NULL` só em tabela VAZIA.** Em tabela com linha falha (`column contains null values`) e, dentro de `BEGIN/COMMIT`, derruba a migration toda. Regra: NOT NULL apenas se `count(*)=0`; senão nullable (e provavelmente é balde 3).

8. **`alembic_version` é VARCHAR(32)** — nome de revision ≤32 chars. Avance atômico: `UPDATE alembic_version SET version_num='novo' WHERE version_num='atual'` (a imagem pode não ter a cadeia; este DB usa update atômico).

9. **Backend está baked no Docker** (não montado): rode introspecção/DDL via `docker exec conecta-pro-backend python3 /tmp/x.py` (copie com `docker cp`). DDL no banco: `docker exec ... psql` ou engine asyncpg com URL trocando o dbname.

10. **`docker logs` de container ruidoso trava** — use `timeout 15 docker logs --since 72h --tail N`, ou consulte estado no banco direto (mais confiável).

---

## Artefatos de saída (sempre gerar)
- `FORWARD_<tag>_<data>.sql` — **com os CREATE TYPE idempotentes no topo** + CREATE TABLE (sem FK) + ADD COLUMN. Replayável.
- `REVERSAO_<tag>_<data>.sql` — `DROP COLUMN IF EXISTS` + `DROP TABLE IF EXISTS` em transação. ⚠️ Avisar: `DROP CASCADE` só é seguro enquanto as tabelas estiverem **vazias**.
- migration alembic com upgrade/downgrade embutidos.
- relatório `.md` + comando `scp`.

## Scripts
- `scripts/drift_finder.py <db> [--dry-run]` — detecta, classifica (3 baldes), e (sem --dry-run) aplica balde 1+2 (tabelas vazias only), depois reverifica FAIL→OK. Edite os sets `B3_TABLES`/`SUSPEITO` conforme o caso.
- `scripts/gen_forward_sql.py <db>` — gera FORWARD.sql (com enums) + REVERSAO.sql a partir do resultado.

## Referência
Caso real completo: `/opt/conecta-pro/auditoria/MIGRATIONS_FINANCEIRO_DP_2026-05-31.md` e `..._2026-06-01.md` (financial+hr: 55→16 FAIL, 17 tabelas + 324 colunas, zero dado tocado).

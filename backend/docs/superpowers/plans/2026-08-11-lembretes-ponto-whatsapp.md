# Lembretes de Ponto por WhatsApp — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lembrar cada funcionário escalado, pelo WhatsApp da empresa, no máximo 3 vezes por turno (15 min antes, no horário, 10 min depois), parando assim que ele bate o ponto.

**Architecture:** Uma task Celery nova (`operacional.lembrete_ponto_whatsapp`) roda no beat a cada 60s. Ela cruza `shifts` do dia com `gp_clock_punches` em fuso Manaus, calcula quantos minutos faltam para o início do turno, escolhe a etapa (-15 / 0 / +10), consulta a tabela de dedup `ponto_lembrete_log` e envia por `send_text_message` (Chatwoot/Baileys). **A escalada não é implementada aqui**: `operacional.check_late_employees` já roda a cada 5 min e já notifica pelo sino o líder do posto, o `gerente_operacional` e o `supervisor` — exatamente os três destinatários pedidos. A Tarefa 4 só verifica que essa escalada existente está de fato disparando.

**Tech Stack:** Python 3.11, Celery (beat + fila `operacional`), SQLAlchemy `text()`, PostgreSQL 16, pytest, Chatwoot/Baileys para WhatsApp.

## Global Constraints

- **O canal é Baileys (WhatsApp Web não-oficial)**, remetente `+558008804414`, o mesmo número usado pelo comercial. Teto rígido de **3 mensagens por pessoa por turno**. Nenhuma cadência menor que a definida neste plano pode ser introduzida — banimento do número derruba também proposta e follow-up de cliente.
- **Fuso canônico `America/Manaus`.** A sessão do Postgres roda em UTC; toda comparação de data/hora usa `now() AT TIME ZONE 'America/Manaus'`, nunca `CURRENT_DATE`. Misturar as duas bases desalinha o dia inteiro a partir das 20h.
- **Nunca enviar se já existe batida** do funcionário na janela do turno (início − 1h até início + 12h), com `status` fora de `('rejected','cancelado')`.
- **Respeitar opt-out:** não enviar para número presente em `crm_followup_optout` (`phone_canonical`).
- **Kill switch:** env `PONTO_LEMBRETE_ENABLED`, default `false`. Enquanto `false`, a task roda, calcula e loga o que enviaria, sem enviar nada.
- **Coorte:** `employees` com `status='ativo'`, `is_homologacao=false`, `tipo_contrato` em (`clt`, NULL) e diferente de `pj`.
- **Sem dado inventado:** funcionário sem telefone é contado e logado como pulado, nunca substituído por outro número. Hoje são 5 dos 52.
- **Sem corte silencioso:** todo envio suprimido (opt-out, sem telefone, teto por rodada) aparece no retorno da task e no log.

---

### Task 1: Tabela de dedup e escolha de etapa

**Files:**
- Create: `/opt/conecta-pro/backend/modules/operacional/lembrete_ponto.py`
- Create: `/opt/conecta-pro/backend/tests/operacional/test_lembrete_ponto.py`
- Migration (psql direto, sem alembic neste repo): tabela `ponto_lembrete_log`

**Interfaces:**
- Produces: `ETAPAS: dict[int, str]`, `etapa_para(delta_min: int) -> int | None`, onde `delta_min` = minutos desde o início do turno (negativo = antes). Retorna `-15`, `0`, `10` ou `None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/operacional/test_lembrete_ponto.py
from modules.operacional.lembrete_ponto import etapa_para


def test_etapa_para_janelas_exatas():
    assert etapa_para(-15) == -15   # 15 min antes do turno
    assert etapa_para(0) == 0       # no horário
    assert etapa_para(10) == 10     # 10 min depois, sem batida


def test_etapa_para_fora_das_janelas_nao_envia():
    for delta in (-60, -16, -14, -1, 1, 9, 11, 120):
        assert etapa_para(delta) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker exec conecta-pro-backend python -m pytest tests/operacional/test_lembrete_ponto.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'modules.operacional.lembrete_ponto'`

- [ ] **Step 3: Write minimal implementation**

```python
# modules/operacional/lembrete_ponto.py
"""Lembretes de ponto por WhatsApp — 3 por turno, para na batida.

Canal é Baileys (não-oficial) no número da empresa: cadência baixa é requisito,
não preferência. Ver docs/superpowers/plans/2026-08-11-lembretes-ponto-whatsapp.md.
"""
from __future__ import annotations

# delta_min (minutos desde o início do turno) -> texto
ETAPAS: dict[int, str] = {
    -15: "Seu turno no {posto} começa às {hora}. Bata o ponto pelo app do Conecta PRO.",
    0: "Seu turno no {posto} começou agora ({hora}). Bata o ponto pelo app.",
    10: "Você ainda não bateu o ponto do turno das {hora} no {posto}. Bata agora, por favor.",
}


def etapa_para(delta_min: int) -> int | None:
    """Etapa exata para este minuto, ou None. Janela de 1 minuto por etapa:
    o beat roda a cada 60s, e o dedup por (shift_id, etapa) impede repetição."""
    return delta_min if delta_min in ETAPAS else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker exec conecta-pro-backend python -m pytest tests/operacional/test_lembrete_ponto.py -v`
Expected: PASS, 2 passed

- [ ] **Step 5: Criar a tabela de dedup**

```bash
docker exec conecta-pro-postgres psql -U postgres -d conecta_pro -c "
CREATE TABLE IF NOT EXISTS ponto_lembrete_log (
  shift_id    uuid        NOT NULL,
  etapa       smallint    NOT NULL,
  employee_id uuid        NOT NULL,
  telefone    varchar(30),
  enviado_em  timestamptz NOT NULL DEFAULT now(),
  ok          boolean     NOT NULL DEFAULT true,
  PRIMARY KEY (shift_id, etapa)
);"
```

Expected: `CREATE TABLE`. A PK composta é o teto de 3: só existem 3 etapas.

- [ ] **Step 6: Verificar a tabela**

Run: `docker exec conecta-pro-postgres psql -U postgres -d conecta_pro -c "\d ponto_lembrete_log"`
Expected: PK `(shift_id, etapa)` listada.

---

### Task 2: Seleção dos turnos a lembrar (query, sem envio)

**Files:**
- Modify: `/opt/conecta-pro/backend/modules/operacional/lembrete_ponto.py`
- Modify: `/opt/conecta-pro/backend/tests/operacional/test_lembrete_ponto.py`

**Interfaces:**
- Consumes: `etapa_para` da Task 1.
- Produces: `SQL_PENDENTES: str` — query que devolve `shift_id, employee_id, nome, telefone, posto, hora, delta_min`.

- [ ] **Step 1: Write the failing test**

```python
def test_sql_pendentes_usa_fuso_manaus_e_exclui_pj_e_homologacao():
    from modules.operacional.lembrete_ponto import SQL_PENDENTES
    sql = SQL_PENDENTES.lower()
    assert "america/manaus" in sql
    assert "current_date" not in sql          # UTC viraria o dia às 20h
    assert "is_homologacao" in sql
    assert "'pj'" in sql
    assert "gp_clock_punches" in sql          # para na batida
    assert "ponto_lembrete_log" in sql        # dedup
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker exec conecta-pro-backend python -m pytest tests/operacional/test_lembrete_ponto.py::test_sql_pendentes_usa_fuso_manaus_e_exclui_pj_e_homologacao -v`
Expected: FAIL com `ImportError: cannot import name 'SQL_PENDENTES'`

- [ ] **Step 3: Write minimal implementation**

```python
SQL_PENDENTES = """
SELECT sh.id::text AS shift_id, e.id::text AS employee_id, e.nome,
       coalesce(nullif(e.celular,''), nullif(e.telefone,'')) AS telefone,
       p.name AS posto,
       to_char(sh.planned_start_time, 'HH24:MI') AS hora,
       (EXTRACT(EPOCH FROM (
          (now() AT TIME ZONE 'America/Manaus')
          - ((now() AT TIME ZONE 'America/Manaus')::date + sh.planned_start_time)
       ))/60)::int AS delta_min
FROM shifts sh
JOIN posts p ON p.id = sh.post_id
JOIN employees e ON e.id = sh.employee_id
WHERE sh.shift_date = (now() AT TIME ZONE 'America/Manaus')::date
  AND sh.is_active = TRUE
  AND sh.is_off_day = FALSE
  AND lower(coalesce(sh.status,'')) IN ('scheduled','agendado','ativo')
  AND coalesce(e.is_homologacao, false) = false
  AND e.status = 'ativo'
  AND (e.tipo_contrato = 'clt' OR e.tipo_contrato IS NULL)
  AND (e.tipo_contrato IS DISTINCT FROM 'pj')
  -- para na batida: qualquer batida válida na janela do turno cancela os lembretes
  AND NOT EXISTS (
    SELECT 1 FROM gp_clock_punches cp
    WHERE cp.employee_id = e.id
      AND coalesce(cp.status,'') NOT IN ('rejected','cancelado')
      AND cp.punch_timestamp BETWEEN
            ((now() AT TIME ZONE 'America/Manaus')::date + sh.planned_start_time - interval '1 hour')
        AND ((now() AT TIME ZONE 'America/Manaus')::date + sh.planned_start_time + interval '12 hours')
  )
  -- dedup: nunca repete a mesma etapa do mesmo turno
  AND NOT EXISTS (
    SELECT 1 FROM ponto_lembrete_log l
    WHERE l.shift_id = sh.id AND l.etapa = :etapa
  )
"""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker exec conecta-pro-backend python -m pytest tests/operacional/test_lembrete_ponto.py -v`
Expected: PASS, 3 passed

- [ ] **Step 5: Rodar a query contra o banco real (leitura)**

```bash
docker exec conecta-pro-backend python -c "
from modules.operacional.lembrete_ponto import SQL_PENDENTES
from core.database.session import get_sync_db
from sqlalchemy import text
with get_sync_db() as db:
    for et in (-15, 0, 10):
        n = len(db.execute(text(SQL_PENDENTES), {'etapa': et}).mappings().all())
        print('etapa', et, '->', n, 'turnos')
"
```
Expected: três linhas, sem erro de SQL. Números podem ser 0 — o que importa é a query rodar.

- [ ] **Step 6: Commit**

```bash
cd /opt/conecta-pro/backend
git add modules/operacional/lembrete_ponto.py tests/operacional/test_lembrete_ponto.py
git commit -m "feat(ponto): selecao de turnos para lembrete por whatsapp"
```

---

### Task 3: Envio com opt-out, kill switch e teto por rodada

**Files:**
- Modify: `/opt/conecta-pro/backend/modules/operacional/lembrete_ponto.py`
- Modify: `/opt/conecta-pro/backend/tests/operacional/test_lembrete_ponto.py`

**Interfaces:**
- Consumes: `SQL_PENDENTES`, `ETAPAS`.
- Produces: `async def rodar_lembretes(db) -> dict` com chaves `enviados, pulados_sem_telefone, pulados_optout, teto_rodada, dry_run`.

- [ ] **Step 1: Write the failing test**

```python
import asyncio
from modules.operacional import lembrete_ponto


class _FakeResult:
    def __init__(self, rows): self._rows = rows
    def mappings(self): return self
    def all(self): return self._rows


class _FakeDB:
    def __init__(self, rows): self.rows, self.executed = rows, []
    def execute(self, stmt, params=None):
        self.executed.append((str(stmt), params))
        return _FakeResult(self.rows if "FROM shifts" in str(stmt) else [])
    def commit(self): pass


def test_dry_run_nao_envia(monkeypatch):
    enviados = []
    monkeypatch.setattr(lembrete_ponto, "PONTO_LEMBRETE_ENABLED", False)
    monkeypatch.setattr(lembrete_ponto, "_enviar", lambda *a, **k: enviados.append(a))
    db = _FakeDB([{"shift_id": "s1", "employee_id": "e1", "nome": "FULANO",
                   "telefone": "92999999999", "posto": "PRIME", "hora": "06:00",
                   "delta_min": -15}])
    r = asyncio.run(lembrete_ponto.rodar_lembretes(db))
    assert r["dry_run"] is True
    assert enviados == []


def test_sem_telefone_e_contado_nao_silencioso(monkeypatch):
    monkeypatch.setattr(lembrete_ponto, "PONTO_LEMBRETE_ENABLED", True)
    monkeypatch.setattr(lembrete_ponto, "_optout", lambda db, tel: False)
    db = _FakeDB([{"shift_id": "s1", "employee_id": "e1", "nome": "FULANO",
                   "telefone": None, "posto": "PRIME", "hora": "06:00",
                   "delta_min": 0}])
    r = asyncio.run(lembrete_ponto.rodar_lembretes(db))
    assert r["pulados_sem_telefone"] == 1
    assert r["enviados"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker exec conecta-pro-backend python -m pytest tests/operacional/test_lembrete_ponto.py -v`
Expected: FAIL com `AttributeError: module ... has no attribute 'rodar_lembretes'`

- [ ] **Step 3: Write minimal implementation**

```python
import logging
import os

from sqlalchemy import text

logger = logging.getLogger(__name__)

PONTO_LEMBRETE_ENABLED = os.getenv("PONTO_LEMBRETE_ENABLED", "false").lower() == "true"
# ponytail: teto por rodada protege o número Baileys de uma escala malformada
# (ex.: 300 turnos com o mesmo horário). Se estourar, o excedente vai para o log,
# nunca sumindo em silêncio. Subir só depois de o número aguentar o volume real.
TETO_POR_RODADA = 30


def _optout(db, telefone: str) -> bool:
    return bool(db.execute(
        text("SELECT 1 FROM crm_followup_optout WHERE phone_canonical = :p LIMIT 1"),
        {"p": "".join(c for c in telefone if c.isdigit())},
    ).mappings().all())


async def _enviar(telefone: str, mensagem: str) -> bool:
    from modules.integrations.connectors.whatsapp.service import send_text_message
    try:
        await send_text_message(telefone, mensagem)
        return True
    except Exception as exc:
        logger.error("[Lembrete Ponto] falha ao enviar para %s: %s", telefone, exc)
        return False


async def rodar_lembretes(db) -> dict:
    """Uma rodada (1 minuto). Envia no máximo 1 mensagem por turno por etapa."""
    res = {"enviados": 0, "pulados_sem_telefone": 0, "pulados_optout": 0,
           "teto_rodada": 0, "dry_run": not PONTO_LEMBRETE_ENABLED}

    for etapa, modelo in ETAPAS.items():
        linhas = db.execute(text(SQL_PENDENTES), {"etapa": etapa}).mappings().all()
        for r in linhas:
            if etapa_para(int(r["delta_min"])) != etapa:
                continue
            tel = (r["telefone"] or "").strip()
            if not tel:
                res["pulados_sem_telefone"] += 1
                logger.warning("[Lembrete Ponto] %s sem telefone — turno %s",
                               r["nome"], r["shift_id"])
                continue
            if _optout(db, tel):
                res["pulados_optout"] += 1
                continue
            if res["enviados"] >= TETO_POR_RODADA:
                res["teto_rodada"] += 1
                logger.warning("[Lembrete Ponto] teto da rodada atingido — %s ficou de fora",
                               r["nome"])
                continue
            msg = modelo.format(posto=r["posto"], hora=r["hora"])
            if res["dry_run"]:
                logger.info("[Lembrete Ponto][DRY] -> %s (%s): %s", r["nome"], tel, msg)
                continue
            ok = await _enviar(tel, msg)
            db.execute(text(
                "INSERT INTO ponto_lembrete_log (shift_id, etapa, employee_id, telefone, ok) "
                "VALUES (:s, :e, :emp, :tel, :ok) ON CONFLICT DO NOTHING"),
                {"s": r["shift_id"], "e": etapa, "emp": r["employee_id"],
                 "tel": tel, "ok": ok})
            db.commit()
            if ok:
                res["enviados"] += 1
    return res
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker exec conecta-pro-backend python -m pytest tests/operacional/test_lembrete_ponto.py -v`
Expected: PASS, 5 passed

- [ ] **Step 5: Commit**

```bash
cd /opt/conecta-pro/backend
git add modules/operacional/lembrete_ponto.py tests/operacional/test_lembrete_ponto.py
git commit -m "feat(ponto): envio de lembrete com optout, kill switch e teto"
```

---

### Task 4: Task Celery e registro no beat

**Files:**
- Modify: `/opt/conecta-pro/backend/modules/operacional/tasks.py` (append ao final)
- Modify: `/opt/conecta-pro/backend/celery_app.py:111` (rota de fila) e no `beat_schedule`

**Interfaces:**
- Consumes: `rodar_lembretes` da Task 3.
- Produces: task `operacional.lembrete_ponto_whatsapp`.

- [ ] **Step 1: Adicionar a task**

```python
@app.task(
    name="operacional.lembrete_ponto_whatsapp",
    bind=True,
    max_retries=1,
)
def lembrete_ponto_whatsapp(self):
    """3 lembretes por turno (-15min, 0, +10min), param na batida. Beat a cada 60s.

    Canal Baileys no número da empresa: o teto de 3 é requisito, não preferência.
    A escalada para líder/supervisor/gerente NÃO é feita aqui — quem faz é
    operacional.check_late_employees, pelo sino, a cada 5 minutos.
    """
    from core.database.session import get_sync_db
    from modules.operacional.lembrete_ponto import rodar_lembretes

    async def _run():
        with get_sync_db() as db:
            return await rodar_lembretes(db)

    try:
        result = asyncio.run(_run())
        logger.info(f"[Operacional Task] Lembrete de ponto: {result}")
        return result
    except Exception as exc:
        logger.error(f"[Operacional Task] Erro no lembrete de ponto: {exc}")
        raise self.retry(exc=exc)
```

- [ ] **Step 2: Rodar a task na mão, ainda em dry-run**

Run:
```bash
docker exec conecta-pro-backend python -c "
from modules.operacional.tasks import lembrete_ponto_whatsapp
print(lembrete_ponto_whatsapp.apply().get())
"
```
Expected: dict com `dry_run: True` e `enviados: 0`.

- [ ] **Step 3: Registrar fila e beat**

Em `celery_app.py`, junto das outras rotas (perto da linha 111):
```python
    "operacional.lembrete_ponto_whatsapp": {"queue": "operacional"},
```

E no `beat_schedule`, junto do bloco OPERACIONAL:
```python
    # Lembrete de ponto por WhatsApp — a cada 60s (as janelas são de 1 minuto).
    # O volume real é baixo: só dispara nos minutos -15, 0 e +10 de cada turno.
    "operacional-lembrete-ponto-whatsapp": {
        "task": "operacional.lembrete_ponto_whatsapp",
        "schedule": 60.0,
        "options": {"queue": "operacional"},
    },
```

- [ ] **Step 4: Verificar que o beat enxerga a task**

Run: `docker exec conecta-pro-backend python -c "from celery_app import app; print('operacional-lembrete-ponto-whatsapp' in app.conf.beat_schedule)"`
Expected: `True`

- [ ] **Step 5: Commit**

```bash
cd /opt/conecta-pro/backend
git add modules/operacional/tasks.py celery_app.py
git commit -m "feat(ponto): agenda lembrete de ponto por whatsapp no beat"
```

---

### Task 5: Verificar a escalada que já existe

Nenhum código novo. `check_late_employees` já cobre os três destinatários pedidos; esta tarefa prova que ela dispara de verdade.

- [ ] **Step 1: Conferir que existem destinatários por papel**

```bash
docker exec conecta-pro-postgres psql -U postgres -d conecta_pro -c "
SELECT role, count(*) FROM users
WHERE lower(coalesce(role,'')) IN ('gerente_operacional','supervisor')
  AND coalesce(is_active,true) GROUP BY role;"
```
Expected: pelo menos 1 linha. Zero linhas = a task roda e não notifica ninguém.

- [ ] **Step 2: Conferir que os postos têm líder**

```bash
docker exec conecta-pro-postgres psql -U postgres -d conecta_pro -c "
SELECT count(*) FILTER (WHERE leader_id IS NOT NULL) AS com_lider, count(*) AS postos FROM posts;"
```
Expected: `com_lider` próximo de `postos`. Posto sem líder perde o alerta de líder (gerente/supervisor ainda recebem).

- [ ] **Step 3: Rodar a verificação de atrasados na mão**

```bash
docker exec conecta-pro-backend python -c "
from modules.operacional.tasks import check_late_employees_task
print(check_late_employees_task.apply().get())
"
```
Expected: dict com `notifications_sent`. Se vier `obs: sem destinatários operacionais (role)`, o Step 1 falhou e a escalada está muda.

---

### Task 6: Ligar de verdade (decisão do Jordan)

- [ ] **Step 1: Ativar o envio**

Adicionar `PONTO_LEMBRETE_ENABLED=true` ao ambiente do backend e dos workers no compose, depois `docker compose up -d`.

- [ ] **Step 2: Bake e deploy**

Seguir a skill `conecta-pro-skills:deploy-bake` — `docker cp` é volátil e some no recreate. O código precisa entrar na imagem.

- [ ] **Step 3: Primeiro dia observado**

```bash
docker exec conecta-pro-postgres psql -U postgres -d conecta_pro -c "
SELECT etapa, count(*), count(*) FILTER (WHERE ok) AS ok FROM ponto_lembrete_log
WHERE enviado_em::date = (now() AT TIME ZONE 'America/Manaus')::date GROUP BY etapa ORDER BY etapa;"
```
Expected: no máximo 3 linhas (etapas -15, 0, 10), e o total do dia na ordem de dezenas, não centenas. Centenas = escala malformada; desligar pelo kill switch antes que o número seja marcado.

- [ ] **Step 4: Conferir a saúde do número**

```bash
docker exec conecta-pro-backend python -c "
import asyncio
from modules.integrations.connectors.whatsapp.service import whatsapp_service
print(asyncio.run(whatsapp_service.check_status()))
"
```
Expected: `online: True`. Se cair depois de ligar, desligue o kill switch imediatamente — o número é o mesmo do comercial.

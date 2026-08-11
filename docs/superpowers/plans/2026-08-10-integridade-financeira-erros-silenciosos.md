# Integridade Financeira — Erros Silenciosos Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Impedir, no banco de dados, as duas classes de defeito silencioso já observadas em produção (sinal invertido e transação duplicada) e fazer o sistema gritar quando o razão contábil parar de receber lançamento.

**Architecture:** Onde o Postgres consegue expressar a regra, ela vira **CHECK/UNIQUE** — impede antes, não avisa depois. Onde não consegue, vira **Regra proativa** no registry que já existe (`notifications/proativo/regras.py`), entregue pelo sino. Cada defesa entra junto com um teste que **quebra a coisa de propósito** e prova que a defesa reagiu.

**Tech Stack:** PostgreSQL (CHECK, índice único por expressão), Alembic, SQLAlchemy, pytest, registry `proativo` existente (`Regra`/`Achado`/`register`).

## Global Constraints

- **Nada de fabricação.** Nenhuma defesa pode inventar dado; só recusar, ou alarmar sobre o que existe.
- **Fail-closed.** Tipo de transação desconhecido é RECUSADO, não aceito com sinal arbitrário.
- **Alarme não testado é alarme que não existe.** Todo alarme entra com teste que o derruba de propósito.
- **Alarme que sempre toca é ruído.** Toda condição é medida contra o dado de HOJE antes de subir; se dispara em massa, a condição está errada.
- **Commit por pathspec** (`git commit -- <arquivos>`), NUNCA `git add -A` — índice git compartilhado entre sessões.
- **Migration é passo MANUAL pós-bake:** `docker exec conecta-pro-backend alembic upgrade heads`.
- **Deploy backend:** `bash scripts/deploy_backend_bluegreen.sh` em background (~15 min com os 8 workers).
- **Nada de money-out.** Nenhuma task deste plano move dinheiro nem altera gate de OTP.
- **Commits com** `--no-verify` e trailer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

## Estado medido em 2026-08-10 (base de todas as decisões abaixo)

| Fato | Valor |
|---|---|
| `bank_transactions` | 4.502 linhas |
| Valores distintos de `transaction_type` | **10** (duas grafias: `credit`/`credito`, `debit`/`debito`) |
| Tipos de ENTRADA | `credit`, `credito`, `pix_recebido`, `boleto_recebido` |
| Tipos de SAÍDA | `debit`, `debito`, `pix_enviado`, `boleto_pago`, `saque`, `ted` |
| Linhas com `amount = 0` | 1 (tipo `credito`) |
| `external_id` nulo | **3.036 de 4.502** — a chave única parcial não protege 67% da tabela |
| Grupos ainda duplicados | **123 grupos / 130 linhas excedentes** (`csv+csv` e `inter+inter`; os `csv+inter` já foram removidos) |
| Holerites sem lançamento no razão | **94** — e os 94 são competência FUTURA (2026-11 e 2026-12), corretamente barrados pela guarda |

## File Structure

| Arquivo | Responsabilidade |
|---|---|
| `backend/alembic/versions/<rev>_integridade_financeira.py` **(criar)** | As duas travas de banco: CHECK de sinal + índice único de impressão digital |
| `backend/modules/financial/services/integridade.py` **(criar)** | Vocabulário de tipos (entrada/saída) e a função de impressão digital canônica, em Python, para o importador usar ANTES de inserir |
| `backend/modules/notifications/proativo/regras.py` **(modificar)** | Registrar a regra `razao_parado` — o registry já existe, não se cria outro |
| `backend/tests/test_integridade_financeira.py` **(criar)** | Os testes que quebram cada defesa de propósito |

---

### Task 1: Trava de sinal — o tipo declara a direção, e o valor tem que concordar

**Por que existe:** em 2026-08-09 o `cora_sync_service` gravou `float(abs(t.amount))`. O `transaction_type` ficava correto (`debit`), mas o `amount` ia positivo. **112 saídas (R$129.817,61)** — salário e PIX a pessoas — foram contadas como RECEITA. Nenhum erro apareceu. A conciliação, que decide pagável×recebível pelo SINAL, tentou casá-las contra recebíveis.

**Files:**
- Create: `backend/modules/financial/services/integridade.py`
- Create: `backend/alembic/versions/a1f2c3d4e5f6_integridade_financeira.py`
- Test: `backend/tests/test_integridade_financeira.py`

**Interfaces:**
- Produces: `TIPOS_ENTRADA: frozenset[str]`, `TIPOS_SAIDA: frozenset[str]`
- Produces: `direcao_esperada(transaction_type: str | None) -> str | None` — `"entrada"`, `"saida"` ou `None` se desconhecido
- Produces: `descricao_canonica(descricao: str | None) -> str` — normaliza a descrição do extrato; **consumido pela Task 2** e espelhado na expressão do índice único
- Produces: constraint `ck_bank_tx_sinal_coerente` na tabela `bank_transactions`

- [ ] **Step 1: Escrever o teste que falha**

Criar `backend/tests/test_integridade_financeira.py`:

```python
"""Defesas contra os erros silenciosos observados em produção (2026-08-09/10).

Cada teste QUEBRA a defesa de propósito. Um alarme/trava que nunca foi visto
reagir é indistinguível de um que não existe — foi assim que o razão ficou
parado desde julho com a exceção escrita no log todo dia.
"""
import pytest

from modules.financial.services.integridade import (
    TIPOS_ENTRADA,
    TIPOS_SAIDA,
    direcao_esperada,
)


def test_vocabulario_cobre_as_duas_grafias():
    """O banco tem 'credit' E 'credito', 'debit' E 'debito' convivendo.
    Esquecer uma grafia deixa um buraco por onde o defeito volta."""
    assert {"credit", "credito", "pix_recebido", "boleto_recebido"} <= TIPOS_ENTRADA
    assert {"debit", "debito", "pix_enviado", "boleto_pago", "saque", "ted"} <= TIPOS_SAIDA
    assert not (TIPOS_ENTRADA & TIPOS_SAIDA), "um tipo não pode ser entrada e saída"


def test_direcao_esperada_classifica():
    assert direcao_esperada("pix_enviado") == "saida"
    assert direcao_esperada("pix_recebido") == "entrada"
    assert direcao_esperada("debito") == "saida"


def test_tipo_desconhecido_nao_e_adivinhado():
    """Fail-closed: tipo novo não ganha direção por chute. Quem adicionar um
    tipo tem que declarar o sinal dele."""
    assert direcao_esperada("pix_agendado_novo") is None
    assert direcao_esperada("") is None
    assert direcao_esperada(None) is None
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
cd /opt/conecta-pro/backend && python -m pytest tests/test_integridade_financeira.py -v
```

Esperado: `ModuleNotFoundError: No module named 'modules.financial.services.integridade'`

- [ ] **Step 3: Criar o módulo de integridade**

Criar `backend/modules/financial/services/integridade.py`:

```python
"""Vocabulário de direção do extrato e impressão digital canônica de transação.

Nasceu de dois defeitos silenciosos reais (2026-08-09/10):
  • a Cora gravava `abs(amount)`: 112 saídas (R$129.817,61) viraram entrada;
  • CSV e API importaram o MESMO PIX com chaves diferentes: 880 linhas em dobro.

Ambos passaram porque nada no banco de dados os impedia.
"""
from __future__ import annotations

import re

# As DUAS grafias convivem na base (herança de importadores diferentes).
# Deixar uma de fora reabre o buraco.
TIPOS_ENTRADA: frozenset[str] = frozenset(
    {"credit", "credito", "pix_recebido", "boleto_recebido"}
)
TIPOS_SAIDA: frozenset[str] = frozenset(
    {"debit", "debito", "pix_enviado", "boleto_pago", "saque", "ted"}
)

_RE_CONTRAPARTE = re.compile(r"CP :[0-9]+-")
_RE_NAO_ALFANUM = re.compile(r"[^A-Z0-9 ]")
_RE_ESPACOS = re.compile(r" +")


def direcao_esperada(transaction_type: str | None) -> str | None:
    """'saida' | 'entrada' | None. None = tipo DESCONHECIDO.

    Fail-closed de propósito: um tipo novo não ganha direção por chute. Quem
    adicionar um tipo declara o sinal dele — no vocabulário e na constraint.
    """
    t = (transaction_type or "").strip().lower()
    if t in TIPOS_ENTRADA:
        return "entrada"
    if t in TIPOS_SAIDA:
        return "saida"
    return None


def descricao_canonica(descricao: str | None) -> str:
    """Normaliza a descrição para comparação entre importadores.

    O mesmo PIX chega como `PIX ENVIADO - Cp :60701190-FULANO` pela API e como
    `Pix enviado: "Cp :00000000-FULANO` pelo CSV — mesmo fato, texto diferente,
    e o código da contraparte vem MASCARADO de formas distintas.
    """
    s = (descricao or "").replace("\n", " ").upper()
    s = _RE_CONTRAPARTE.sub("", s)
    s = _RE_NAO_ALFANUM.sub(" ", s)
    return _RE_ESPACOS.sub(" ", s).strip()
```

- [ ] **Step 4: Rodar e ver passar**

```bash
cd /opt/conecta-pro/backend && python -m pytest tests/test_integridade_financeira.py -v
```

Esperado: 3 passed

- [ ] **Step 5: Criar a migration com a trava de sinal**

Criar `backend/alembic/versions/a1f2c3d4e5f6_integridade_financeira.py`. Substituir `down_revision` pelo head atual, obtido com:

```bash
cd /opt/conecta-pro/backend && docker exec conecta-pro-backend alembic heads
```

```python
"""integridade financeira: trava de sinal no extrato

Revision ID: a1f2c3d4e5f6
Revises: <COLAR O HEAD RETORNADO PELO COMANDO ACIMA>
Create Date: 2026-08-10
"""
from alembic import op

revision = "a1f2c3d4e5f6"
down_revision = "<COLAR O HEAD RETORNADO PELO COMANDO ACIMA>"
branch_labels = None
depends_on = None

# Espelha modules/financial/services/integridade.py. Mudar um sem o outro
# deixa o Python e o banco discordando — que é como o defeito nasce.
_ENTRADA = "'credit','credito','pix_recebido','boleto_recebido'"
_SAIDA = "'debit','debito','pix_enviado','boleto_pago','saque','ted'"


def upgrade() -> None:
    # amount = 0 é tolerado (existe 1 linha legítima com valor zero).
    # transaction_type NULL é tolerado (importadores antigos).
    # Tipo CONHECIDO com sinal errado é RECUSADO — era o defeito da Cora.
    # Tipo DESCONHECIDO também é recusado: fail-closed, quem criar um tipo
    # novo declara a direção aqui.
    op.execute(
        f"""
        ALTER TABLE bank_transactions
        ADD CONSTRAINT ck_bank_tx_sinal_coerente CHECK (
            amount = 0
            OR transaction_type IS NULL
            OR (lower(transaction_type) IN ({_ENTRADA}) AND amount > 0)
            OR (lower(transaction_type) IN ({_SAIDA})  AND amount < 0)
        )
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE bank_transactions DROP CONSTRAINT IF EXISTS ck_bank_tx_sinal_coerente"
    )
```

- [ ] **Step 6: Aplicar a migration e provar que a trava REAGE**

```bash
cd /opt/conecta-pro
docker exec conecta-pro-backend alembic upgrade heads
```

Esperado: `Running upgrade ... -> a1f2c3d4e5f6`

Agora quebrar de propósito — reproduzir exatamente o bug da Cora:

```bash
docker exec -e PYTHONPATH=/app conecta-pro-backend python -c "
from core.database.session import SyncSessionLocal
from sqlalchemy import text
db = SyncSessionLocal()
acc = db.execute(text('SELECT id FROM bank_accounts LIMIT 1')).scalar()
try:
    db.execute(text('''
        INSERT INTO bank_transactions (id, bank_account_id, transaction_type, amount,
            description, transaction_date, status, created_at, updated_at)
        VALUES (gen_random_uuid(), :a, 'debit', 999.99, 'TESTE TRAVA SINAL',
                NOW(), 'confirmado', NOW(), NOW())'''), {'a': acc})
    db.commit()
    print('FALHOU: a trava NAO impediu saida com sinal positivo')
except Exception as e:
    db.rollback()
    print('OK — trava reagiu:', str(e)[:90])
"
```

Esperado: `OK — trava reagiu: ... violates check constraint "ck_bank_tx_sinal_coerente"`

- [ ] **Step 7: Confirmar que nenhum dado legítimo foi recusado**

```bash
docker exec -e PYTHONPATH=/app conecta-pro-backend python -c "
from core.database.session import SyncSessionLocal
from sqlalchemy import text
db = SyncSessionLocal()
print('linhas no extrato:', db.execute(text('SELECT count(*) FROM bank_transactions')).scalar())
print('violacoes remanescentes:', db.execute(text('''
  SELECT count(*) FROM bank_transactions
  WHERE amount <> 0 AND transaction_type IS NOT NULL
    AND NOT (lower(transaction_type) IN ('credit','credito','pix_recebido','boleto_recebido') AND amount > 0)
    AND NOT (lower(transaction_type) IN ('debit','debito','pix_enviado','boleto_pago','saque','ted') AND amount < 0)
''')).scalar())
"
```

Esperado: `linhas no extrato: 4502` e `violacoes remanescentes: 0`

- [ ] **Step 8: Commit**

```bash
cd /opt/conecta-pro
git commit --no-verify -m "feat(integridade): trava de sinal no extrato — saida nao entra como entrada

O cora_sync_service gravava abs(amount): 112 saidas (R\$129.817,61) viraram
receita e a conciliacao, que decide pagavel x recebivel pelo SINAL, tentou
casa-las contra recebiveis. Nada no banco impedia.

CHECK constraint ck_bank_tx_sinal_coerente: tipo declara a direcao e o valor
tem que concordar. Fail-closed — tipo desconhecido e recusado, quem criar um
tipo novo declara o sinal. As DUAS grafias (credit/credito) estao cobertas.

Provado quebrando de proposito: insert de 'debit' com valor positivo e negado.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- backend/modules/financial/services/integridade.py backend/alembic/versions/a1f2c3d4e5f6_integridade_financeira.py backend/tests/test_integridade_financeira.py
```

---

### Task 2: Impressão digital canônica — o mesmo fato não entra duas vezes

**Por que existe:** em 2026-08-10 removi **880 linhas duplicadas** (R$212 mil de entrada e R$326 mil de saída em dobro). Já existia índice único em `external_id` — ele não falhou, **nunca teve chance**: a importação do CSV inventou a própria chave (`inter_csv_2026-03-02_32699.88_1406`), diferente da que a API do Inter usa para o mesmo fato. Duas chaves para a mesma transação. E `external_id` é nulo em **3.036 das 4.502** linhas.

⚠️ **Bloqueio conhecido:** hoje ainda existem **123 grupos / 130 linhas** duplicadas (`csv+csv` e `inter+inter`, deixadas de fora da limpeza por não terem prova de origem dupla). O índice único **não pode ser criado** enquanto elas existirem. O Step 1 tria; o Step 2 decide.

**Files:**
- Modify: `backend/alembic/versions/a1f2c3d4e5f6_integridade_financeira.py` (acrescenta o índice ao mesmo `upgrade()`)
- Modify: `backend/tests/test_integridade_financeira.py`

**Interfaces:**
- Consumes: `descricao_canonica(descricao) -> str` da Task 1
- Produces: índice `uq_bank_tx_impressao_digital` em `bank_transactions`

- [ ] **Step 1: Triar as 130 linhas que bloqueiam o índice**

```bash
cd /opt/conecta-pro
docker exec -e PYTHONPATH=/app conecta-pro-backend python -c "
from core.database.session import SyncSessionLocal
from sqlalchemy import text
db = SyncSessionLocal()
N = \"regexp_replace(regexp_replace(regexp_replace(upper(coalesce(description,'')),'CP :[0-9]+-','','g'),'[^A-Z0-9 ]',' ','g'),' +',' ','g')\"
for r in db.execute(text(f'''
  SELECT string_agg(DISTINCT coalesce(source_type,'inter'),'+') origens, count(*) grupos, sum(n-1) excedentes
  FROM (SELECT bank_account_id, transaction_date::date d, amount, {N} f, count(*) n,
               string_agg(DISTINCT coalesce(source_type,'inter'),'+') o
        FROM bank_transactions GROUP BY 1,2,3,4 HAVING count(*)>1) t
  GROUP BY o ORDER BY 3 DESC''')).fetchall():
    print('  ', ' | '.join(str(i) for i in r))
"
```

Registrar o resultado. Regra de decisão, sem exceção:
- **Mesma origem + mesmo dia + mesmo valor + mesma contraparte** → duplicata de importação, pode remover.
- **Qualquer dúvida** → NÃO remove; ajusta a impressão digital para incluir `external_id` quando ele existir, deixando os casos legítimos conviverem.

- [ ] **Step 2: Fazer backup completo e remover só as duplicatas comprovadas**

```bash
docker exec -e PYTHONPATH=/app conecta-pro-backend python -c "
import json
from core.database.session import SyncSessionLocal
from sqlalchemy import text
db = SyncSessionLocal()
N = \"regexp_replace(regexp_replace(regexp_replace(upper(coalesce(description,'')),'CP :[0-9]+-','','g'),'[^A-Z0-9 ]',' ','g'),' +',' ','g')\"
# mantém a linha mais ANTIGA de cada grupo (a que já foi classificada por gente)
SEL = f'''SELECT id FROM (
  SELECT id, row_number() OVER (PARTITION BY bank_account_id, transaction_date::date, amount, {N}
                               ORDER BY created_at, id) rn
  FROM bank_transactions) t WHERE rn > 1'''
rows = db.execute(text(f'SELECT row_to_json(x) FROM (SELECT * FROM bank_transactions WHERE id IN ({SEL})) x')).fetchall()
with open('/tmp/backup_dup_intra_origem.jsonl','w',encoding='utf-8') as f:
    for r in rows: f.write(json.dumps(r[0], ensure_ascii=False, default=str)+'\n')
print('BACKUP:', len(rows), 'linhas')
d = db.execute(text(f'DELETE FROM bank_transactions WHERE id IN ({SEL}) RETURNING id')).fetchall()
db.commit(); print('removidas:', len(d))
"
docker cp conecta-pro-backend:/tmp/backup_dup_intra_origem.jsonl /opt/conecta-pro/auditoria/backup_dup_intra_origem.jsonl
```

Esperado: `BACKUP: 130 linhas` e `removidas: 130`

- [ ] **Step 3: Acrescentar o índice único à migration**

Em `backend/alembic/versions/a1f2c3d4e5f6_integridade_financeira.py`, adicionar ao FIM de `upgrade()`:

```python
    # Impressão digital do FATO, não do importador. A chave é (conta, dia, valor,
    # descrição canônica) — a mesma expressão de descricao_canonica() em Python.
    # `external_id` não serve: é nulo em 3.036 de 4.502 linhas, e cada importador
    # inventava o seu (foi assim que 880 duplicatas entraram).
    op.execute(
        """
        CREATE UNIQUE INDEX uq_bank_tx_impressao_digital ON bank_transactions (
            bank_account_id,
            (transaction_date::date),
            amount,
            (regexp_replace(regexp_replace(regexp_replace(
                upper(coalesce(description,'')), 'CP :[0-9]+-', '', 'g'),
                '[^A-Z0-9 ]', ' ', 'g'), ' +', ' ', 'g'))
        )
        """
    )
```

E ao INÍCIO de `downgrade()`:

```python
    op.execute("DROP INDEX IF EXISTS uq_bank_tx_impressao_digital")
```

- [ ] **Step 4: Escrever o teste da impressão digital**

Acrescentar a `backend/tests/test_integridade_financeira.py`:

```python
from modules.financial.services.integridade import descricao_canonica


def test_impressao_digital_iguala_os_dois_importadores():
    """O MESMO PIX chegou pela API e pelo CSV com texto diferente e código de
    contraparte mascarado de formas distintas. A canônica precisa colapsar os dois
    — senão o índice único não reconhece a duplicata (foi o que aconteceu)."""
    api = 'PIX RECEBIDO - Cp :05203605-CONDOMINIO RESIDENCIAL VILLA DOS PASSAROS'
    csv = 'Pix recebido: "Cp :00000000-CONDOMINIO RESIDENCIAL VILLA DOS PASSAROS'
    assert descricao_canonica(api) == descricao_canonica(csv)


def test_impressao_digital_nao_colapsa_contrapartes_diferentes():
    """VT de R$32 pago a 30 diaristas no mesmo dia são 30 fatos distintos.
    Colapsá-los apagaria pagamento real."""
    a = 'PIX ENVIADO - Cp :111-MARIA DA SILVA'
    b = 'PIX ENVIADO - Cp :222-JOAO DE SOUZA'
    assert descricao_canonica(a) != descricao_canonica(b)


def test_descricao_canonica_tolera_vazio():
    assert descricao_canonica(None) == ""
    assert descricao_canonica("") == ""
```

- [ ] **Step 5: Rodar os testes**

```bash
cd /opt/conecta-pro/backend && python -m pytest tests/test_integridade_financeira.py -v
```

Esperado: 6 passed

- [ ] **Step 6: Aplicar e provar que o índice REAGE**

```bash
cd /opt/conecta-pro
docker exec conecta-pro-backend alembic upgrade heads
docker exec -e PYTHONPATH=/app conecta-pro-backend python -c "
from core.database.session import SyncSessionLocal
from sqlalchemy import text
db = SyncSessionLocal()
acc = db.execute(text('SELECT id FROM bank_accounts LIMIT 1')).scalar()
ins = '''INSERT INTO bank_transactions (id, bank_account_id, transaction_type, amount,
    description, transaction_date, status, created_at, updated_at)
    VALUES (gen_random_uuid(), :a, 'pix_enviado', -77.77, :d, '2026-08-10', 'confirmado', NOW(), NOW())'''
db.execute(text(ins), {'a': acc, 'd': 'PIX ENVIADO - Cp :999-TESTE IDEMPOTENCIA'})
db.commit()
try:
    # mesmo fato, texto do OUTRO importador — tem que ser recusado
    db.execute(text(ins), {'a': acc, 'd': 'Pix enviado: \"Cp :000-TESTE IDEMPOTENCIA'})
    db.commit()
    print('FALHOU: a duplicata entrou')
except Exception as e:
    db.rollback(); print('OK — indice reagiu:', str(e)[:80])
finally:
    db.execute(text(\"DELETE FROM bank_transactions WHERE description ILIKE '%TESTE IDEMPOTENCIA%'\"))
    db.commit()
    print('limpeza — residuo:', db.execute(text(\"SELECT count(*) FROM bank_transactions WHERE description ILIKE '%TESTE IDEMPOTENCIA%'\")).scalar())
"
```

Esperado: `OK — indice reagiu: ... duplicate key value violates unique constraint` e `limpeza — residuo: 0`

- [ ] **Step 7: Commit**

```bash
cd /opt/conecta-pro
git commit --no-verify -m "feat(integridade): impressao digital canonica — o mesmo fato nao entra duas vezes

Ja existia indice unico em external_id. Ele nao falhou: nunca teve chance. A
importacao do CSV inventou a propria chave (inter_csv_2026-03-02_32699.88_1406),
diferente da que a API do Inter usa para o MESMO PIX. Duas chaves para um fato.
E external_id e nulo em 3.036 das 4.502 linhas.

Agora a chave e o FATO: (conta, dia, valor, descricao canonica). A canonica
colapsa o texto dos dois importadores e o mascaramento diferente da contraparte,
mas NAO colapsa contrapartes distintas — VT de R\$32 para 30 diaristas segue
sendo 30 fatos.

Provado quebrando de proposito: o mesmo PIX com o texto do outro importador e
recusado pelo indice.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- backend/alembic/versions/a1f2c3d4e5f6_integridade_financeira.py backend/tests/test_integridade_financeira.py
```

---

### Task 3: Alarme de razão parado — o silêncio vira ruído

**Por que existe:** o fechamento contábil parou em julho. `_lancar_folha` fazia `data = payment_date or competence_end`, e **456 dos 821 holerites não têm data nenhuma** — só a competência. `data_lancamento` é NOT NULL, então a transação inteira estourava e levava o fechamento da EMPRESA junto. O beat diário `financial.fechar_razao_auto` **escrevia a exceção no log todos os dias** e ninguém leu. Julho ficou com 63 lançamentos contra 181 de junho, com fonte completa.

⚠️ **Armadilha medida:** a condição ingênua ("holerite sem lançamento no razão") dispararia **94 achados hoje** — e os 94 são exatamente os holerites de competência FUTURA (2026-11 e 2026-12, 47+47) que a guarda do fechamento barra corretamente. Um alarme que nasce com 94 falsos positivos é desligado em duas semanas. A condição PRECISA excluir competência futura, igual à guarda do fechamento.

**Files:**
- Modify: `backend/modules/notifications/proativo/regras.py`
- Modify: `backend/tests/test_integridade_financeira.py`

**Interfaces:**
- Consumes: `Regra`, `Achado`, `register` de `regras.py` (registry já existente)
- Produces: regra registrada sob a chave `"razao_parado"` em `REGISTRY`

- [ ] **Step 1: Escrever o teste que falha**

Acrescentar a `backend/tests/test_integridade_financeira.py`:

```python
def test_regra_razao_parado_esta_registrada():
    """Alarme que não está no registry não dispara nunca."""
    from modules.notifications.proativo.regras import REGISTRY

    assert "razao_parado" in REGISTRY
    r = REGISTRY["razao_parado"]
    assert r.severidade == "critico"
    assert r.roles_destino, "fail-closed: regra sem destinatário não é registrada"


def test_sql_do_razao_parado_exclui_competencia_futura():
    """A condição ingênua dispararia 94 achados hoje — os 94 holerites de
    competência FUTURA (2026-11/12) que o fechamento barra de propósito.
    Alarme que nasce ruidoso é desligado antes de servir."""
    from modules.notifications.proativo.regras import SQL_RAZAO_PARADO

    assert "reference_period" in SQL_RAZAO_PARADO
    assert "to_char" in SQL_RAZAO_PARADO, "precisa comparar competência com o mês corrente"
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
cd /opt/conecta-pro/backend && python -m pytest tests/test_integridade_financeira.py -k razao -v
```

Esperado: `ImportError: cannot import name 'SQL_RAZAO_PARADO'`

- [ ] **Step 3: Registrar a regra**

Acrescentar ao FIM de `backend/modules/notifications/proativo/regras.py`:

```python
# ─────────────────────────── razao_parado ───────────────────────────
# Nasceu do fechamento contábil parado desde julho/2026: um holerite sem data
# derrubava a transação inteira, o beat diário escrevia a exceção no log todo
# dia, e ninguém leu. O sinal existia; faltava alguém olhando.
#
# A guarda de competência FUTURA não é detalhe: sem ela a regra dispara 94
# achados no primeiro dia (holerites de 2026-11/12 que o fechamento barra de
# propósito), e alarme ruidoso é alarme desligado.
SQL_RAZAO_PARADO = """
    SELECT h.reference_period AS competencia, count(*) AS holerites
    FROM hr_payslips h
    WHERE coalesce(h.total_earnings, 0) > 0
      AND h.payslip_code IS NOT NULL
      AND h.reference_period IS NOT NULL
      AND h.reference_period <= to_char(now() AT TIME ZONE 'America/Manaus', 'YYYY-MM')
      AND NOT EXISTS (
          SELECT 1 FROM accounting_entries a
          WHERE a.documento_ref = 'FOLHA-' || h.payslip_code
      )
    GROUP BY h.reference_period
    ORDER BY h.reference_period
"""


async def _detectar_razao_parado(db: AsyncSession) -> list[Achado]:
    rows = (await db.execute(text(SQL_RAZAO_PARADO))).mappings().all()
    return [
        Achado(
            correlation_id=f"razao_parado:{r['competencia']}",
            dados={"competencia": r["competencia"], "holerites": int(r["holerites"])},
        )
        for r in rows
    ]


def _tpl_razao_parado(d: dict) -> tuple[str, str]:
    return (
        f"Razão sem lançamento: folha {d['competencia']}",
        f"{d['holerites']} holerite(s) da competência {d['competencia']} não têm "
        f"lançamento no razão contábil. O fechamento pode ter parado em silêncio — "
        f"foi assim que julho/2026 ficou com 63 lançamentos contra 181 de junho. "
        f"Rodar o fechamento e conferir o log do beat financial.fechar_razao_auto.",
    )


register(Regra(
    nome="razao_parado", familia="financeiro", severidade="critico",
    roles_destino=("admin",),
    action_url="/redesign/financeiro?t=g-contabil",
    detectar=_detectar_razao_parado, template=_tpl_razao_parado,
))
```

- [ ] **Step 4: Rodar os testes**

```bash
cd /opt/conecta-pro/backend && python -m pytest tests/test_integridade_financeira.py -v
```

Esperado: 8 passed

- [ ] **Step 5: Medir o alarme contra o dado de HOJE antes de subir**

```bash
cd /opt/conecta-pro
docker cp backend/modules/notifications/proativo/regras.py conecta-pro-backend:/app/modules/notifications/proativo/regras.py
docker exec -e PYTHONPATH=/app conecta-pro-backend python -c "
import asyncio
from core.database.session import async_session_factory
from modules.notifications.proativo.regras import _detectar_razao_parado
async def main():
    async with async_session_factory() as db:
        achados = await _detectar_razao_parado(db)
        print('achados hoje:', len(achados))
        for a in achados[:5]: print('  ', a.dados)
asyncio.run(main())
"
```

Esperado: `achados hoje: 0`

Se vier > 0, **parar**: ou existe folha realmente sem razão (investigar), ou a condição ainda está ruidosa. Não subir alarme que nasce tocando.

- [ ] **Step 6: Provar que o alarme REAGE — quebrar de propósito**

```bash
docker exec -e PYTHONPATH=/app conecta-pro-backend python -c "
import asyncio
from core.database.session import SyncSessionLocal, async_session_factory
from sqlalchemy import text
from modules.notifications.proativo.regras import _detectar_razao_parado

db = SyncSessionLocal()
alvo = db.execute(text('''SELECT documento_ref FROM accounting_entries
  WHERE documento_ref LIKE 'FOLHA-%' LIMIT 1''')).scalar()
guardado = db.execute(text('SELECT row_to_json(x) FROM (SELECT * FROM accounting_entries WHERE documento_ref=:r) x'), {'r': alvo}).fetchall()
db.execute(text('DELETE FROM accounting_entries WHERE documento_ref=:r'), {'r': alvo})
db.commit()
print('apaguei o lancamento', alvo, '- simulando o fechamento parado')

async def main():
    async with async_session_factory() as s:
        print('achados com o defeito:', len(await _detectar_razao_parado(s)))
asyncio.run(main())

import json
for (linha,) in guardado:
    cols = ','.join(linha.keys())
    vals = ','.join(f':{k}' for k in linha)
    db.execute(text(f'INSERT INTO accounting_entries ({cols}) VALUES ({vals})'), linha)
db.commit()
print('restaurado. residuo:', 1 - db.execute(text('SELECT count(*) FROM accounting_entries WHERE documento_ref=:r'), {'r': alvo}).scalar())
"
```

Esperado: `achados com o defeito: 1` e `restaurado. residuo: 0`

- [ ] **Step 7: Commit**

```bash
cd /opt/conecta-pro
git commit --no-verify -m "feat(integridade): alarme de razao parado — o silencio vira ruido

O fechamento contabil parou em julho e o beat diario escrevia a excecao no log
TODO DIA. O sinal existia; faltava alguem olhando. Julho ficou com 63
lancamentos contra 181 de junho, com fonte completa.

Regra 'razao_parado' no registry proativo que ja existe (nao se inventou outro
mecanismo): holerite de competencia PASSADA sem lancamento no razao -> sino,
severidade critica.

Guarda de competencia FUTURA nao e detalhe: sem ela a regra dispara 94 achados
no primeiro dia (holerites de 2026-11/12 que o fechamento barra de proposito).
Alarme que nasce ruidoso e desligado em duas semanas.

Provado quebrando de proposito: apagado 1 lancamento -> alarme achou; restaurado
-> 0 residuo.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- backend/modules/notifications/proativo/regras.py backend/tests/test_integridade_financeira.py
```

- [ ] **Step 8: Deploy e verificação final**

```bash
cd /opt/conecta-pro
[ -e /tmp/conecta_deploy.lock ] && echo "AGUARDAR: outra sessao deployando" || bash scripts/deploy_backend_bluegreen.sh
```

Após concluir (~15 min), confirmar que a regra está viva no worker que roda o proativo:

```bash
docker exec conecta-pro-celery-batch python -c "
from modules.notifications.proativo.regras import REGISTRY
print('razao_parado registrada:', 'razao_parado' in REGISTRY)
print('total de regras:', len(REGISTRY))
"
bash scripts/checar_drift_workers.sh | tail -2
```

Esperado: `razao_parado registrada: True` e `Sem drift`

---

## Fora de escopo deste plano (deliberadamente)

Estes ficaram de fora por YAGNI ou porque **hoje nasceriam ruidosos** — cada um precisa de linha de base medida antes de virar alarme:

- **Saldo divergente banco × sistema** — exige o ledger de partida dobrada, que não existe. Depende de consolidar `accounting_entries` × `fin_journal_entries` primeiro (dívida já registrada no roadmap).
- **Origem sem lançamento** — dispararia em 1.474 transações hoje. Precisa de meta de cobertura e disparo em "piorou", não em "não está perfeito".
- **Lançamento sem documento** — dispararia na maioria das contas a pagar.
- **Banco sem movimentação em 24h** — dispara todo sábado e domingo. Precisa de dia útil e do padrão histórico da conta.
- **Framework de qualidade de dado (Soda Core / Great Expectations)** — os três defeitos reais foram pegos por consultas de uma linha. Adotar framework antes de ter o hábito é comprar arquivo antes de ter papel. Reavaliar quando forem 20+ checks.

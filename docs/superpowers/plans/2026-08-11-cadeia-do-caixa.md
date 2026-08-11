# Cadeia do Caixa Implementation Plan

> **CONCLUÍDO em 2026-08-11** — 4 tasks no ar e bakeadas (sem drift). Resultado medido:
> razão contas 1.1.1.x = R$83.542,62 = extrato líquido, **Δ R$0,00**. Não re-executar:
> a escrituração é idempotente, mas o mutirão de classificação já rodou.
>
> **Divergi do plano em dois pontos, com motivo medido:**
> 1. Task 2 — a lista chumbada de PJ por primeiro nome mandava dois AGENTES DE PORTARIA
>    CLT (`RUAN`, `RAMON`) para pró-labore. Trocada por `employees.status IN
>    ('pj_ativo','pj_pendente')` + `unaccent`. Mapeado também o dialeto legado da base
>    (`servico_sem_nf`, `adiantamento`, `impostos` no plural), que jogava R$307.471,72 na
>    transitória por vocabulário e não por falta de informação.
> 2. Task 4 — o oráculo previsto (`bank_accounts.current_balance`) está **parado desde
>    14/04/2026**. Alarme sobre número velho toca sozinho. Ancorado no extrato, que é
>    invariante exato → `TOLERANCIA_CAIXA = R$1,00`.
>
> **Aberto, precisa do Jordan:** faltam ~R$74k de entradas no extrato do Inter (abertura
> real em 01/01 era +R$7.625,62 pela âncora `balance_after`; o extrato implica
> −R$66.747,91). Nenhum mês faltando → faltam linhas dentro dos meses, com três fontes de
> importação convivendo. Exige sync real do Inter.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Fazer o razão contábil refletir o caixa — hoje ele conhece 6% do extrato e diz que há R$1.401.547,03 no banco quando o banco tem R$16.826,71.

**Architecture:** Cada movimentação bancária vira UM lançamento contábil, com o banco de um lado e a contrapartida do outro. A contrapartida sai da classificação da saída; **onde a despesa já foi lançada na competência (folha, NFS-e tomada, ISS), o pagamento debita o PASSIVO, não a despesa** — senão dobra, que é o erro que já custou R$692.818,98 hoje. O que não tem classificação cai numa conta TRANSITÓRIA visível, e não em silêncio: assim o banco fecha desde o primeiro dia e o que falta classificar fica à vista.

**Tech Stack:** PostgreSQL, SQLAlchemy (async), pytest, o registry `proativo` para o alarme, `accounting_entries` como razão único.

## Global Constraints

- **Nunca dobrar despesa.** Categoria cuja despesa já é lançada por outra fonte → contrapartida é conta de PASSIVO. Regra derivada do bug de hoje (folha lançada 2×, R$692.818,98).
- **Idempotente por `bank_transaction_id`.** Movimentação com lançamento já ligado NÃO é relançada. Hoje 266 transações já têm lançamento (200 `banco_inter` + 68 `baixa_recebimento`).
- **Transitória visível, nunca silêncio.** Sem classificação → conta "a classificar", jamais omitir o lançamento.
- **Competência futura não entra** (mesma guarda do fechamento da folha).
- **`data_lancamento` é NOT NULL** — sem data, não lança (a guarda que já existe em `_post`).
- **Commit por pathspec** (`git commit -- <arqs>`), NUNCA `git add -A` — índice git compartilhado entre sessões.
- **Deploy:** `bash scripts/deploy_backend_bluegreen.sh` em background (~15 min). `docker cp` é volátil.
- **Migration é passo MANUAL pós-bake:** `docker exec conecta-pro-backend alembic upgrade heads`.
- **Não move dinheiro.** Tudo aqui é escrituração; nenhum gate de OTP é tocado.
- Commits com `--no-verify` e trailer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

## Estado medido em 2026-08-11 (base de todas as decisões)

| Fato | Valor |
|---|---|
| Razão diz que há no banco | R$1.401.547,03 |
| Banco realmente tem (sync 05:00) | **R$16.826,71** (Inter 9.651,35 + Cora 7.175,36) |
| Movimentações do extrato | 4.502 |
| Já com lançamento contábil | **266** (5,9%) — 200 `banco_inter`, 68 `baixa_recebimento` |
| **A lançar** | **4.250** (4.129 saídas + 121 entradas) |
| Saídas já classificadas | 3.111 (R$1.027.386,67) |
| Saídas sem classificação | 1.205 (R$966.364,65) — vão para a transitória |
| Contas bancárias | Inter `20663dc9…` (4.391 mov) · Cora `1268590a…` (126 mov) |

**Contrapartidas que o razão JÁ usa (por isso o pagamento debita passivo):**
`2.1.1.01` Salários a Pagar (543 lanç.) · `2.1.1.02` FGTS a Recolher (355) · `2.1.4.01` Fornecedores a Pagar (330) · `2.1.2.01` ISS a Recolher (85) · `2.1.1.03` INSS a Recolher (14) · `2.1.2.04` Parcelamento Simples (5)

## File Structure

| Arquivo | Responsabilidade |
|---|---|
| `backend/alembic/versions/b2c3d4e5f6a7_contas_cadeia_caixa.py` **(criar)** | As 6 contas novas do plano (transitórias, diarista, sócio, transferência) |
| `backend/modules/financial/services/plano_contas_caixa.py` **(criar)** | Mapa categoria → conta contábil, e a conta do banco por `bank_account_id`. Só regra pura, testável sem banco |
| `backend/modules/financial/services/extrato_para_razao.py` **(criar)** | O motor: varre `bank_transactions` sem lançamento e escritura, idempotente |
| `backend/modules/notifications/proativo/regras.py` **(modificar)** | Regra `caixa_divergente` — razão × banco, todo dia |
| `backend/modules/financial/tasks.py` **(modificar)** | Task `financial.escriturar_extrato` |
| `backend/celery_app.py` **(modificar)** | Beat 05:30 (depois do sync de saldo das 05:00, antes do fechamento das 05:00… ver Task 4) |
| `backend/tests/test_cadeia_caixa.py` **(criar)** | Testes das regras e das guardas |

---

### Task 1: Contas novas + mapa categoria → conta

**Por que existe:** não dá para escriturar o que não tem conta. E jogar diarista em `5.1.1.01` (Salários) quebraria a prova `folha × razão = Δ 0,00` estabelecida hoje — a conta precisa ser própria.

**Files:**
- Create: `backend/modules/financial/services/plano_contas_caixa.py`
- Create: `backend/alembic/versions/b2c3d4e5f6a7_contas_cadeia_caixa.py`
- Test: `backend/tests/test_cadeia_caixa.py`

**Interfaces:**
- Produces: `CONTA_BANCO: dict[str, str]` — `bank_account_id` → código contábil
- Produces: `contrapartida_saida(categoria: str | None, descricao: str) -> tuple[str, str]` — `(codigo_conta, motivo)`
- Produces: `contrapartida_entrada(descricao: str) -> tuple[str, str]`
- Produces: `CONTA_SAIDA_A_CLASSIFICAR = "5.9.9.01"`, `CONTA_ENTRADA_A_CLASSIFICAR = "4.9.9.01"`

- [x] **Step 1: Escrever o teste que falha**

Criar `backend/tests/test_cadeia_caixa.py`:

```python
"""Cadeia do caixa: o razão precisa refletir o banco.

Em 2026-08-11 o razão dizia R$1.401.547,03 e o banco tinha R$16.826,71, porque
só 6% do extrato virava lançamento — e quase só entrada.
"""

from modules.financial.services.plano_contas_caixa import (
    CONTA_ENTRADA_A_CLASSIFICAR,
    CONTA_SAIDA_A_CLASSIFICAR,
    contrapartida_entrada,
    contrapartida_saida,
)


def test_despesa_ja_provisionada_debita_PASSIVO_nao_despesa():
    """A regra mais cara do plano. A folha já lança D 5.1.1.01 / C 2.1.1.01 na
    competência. Se o pagamento pelo banco debitasse 5.1.1.01 de novo, a despesa
    dobraria — foi exatamente o bug de R$692.818,98 encontrado hoje."""
    assert contrapartida_saida("salario", "PIX ENVIADO FULANO")[0] == "2.1.1.01"
    assert contrapartida_saida("fornecedor", "PAGAMENTO DE TITULO ACME")[0] == "2.1.4.01"


def test_despesa_sem_provisao_debita_DESPESA():
    """Diarista, benefício e tarifa não passam por provisão — o pagamento É a
    despesa."""
    assert contrapartida_saida("diarista", "PIX")[0] == "5.1.1.07"
    assert contrapartida_saida("beneficio_vtvr", "PIX")[0] == "5.1.1.03"
    assert contrapartida_saida("taxa_bancaria", "TARIFA")[0] == "5.2.3.01"
    assert contrapartida_saida("pj_prolabore", "PIX")[0] == "5.2.1.04"


def test_imposto_afina_pela_descricao():
    """'imposto' é categoria guarda-chuva; o passivo correto depende do tributo.
    Sem afinar, FGTS cairia em ISS a Recolher."""
    assert contrapartida_saida("imposto", "PAGAMENTO FGTS CAIXA")[0] == "2.1.1.02"
    assert contrapartida_saida("imposto", "PIX ENVIADO GPS INSS")[0] == "2.1.1.03"
    assert contrapartida_saida("imposto", "ISS MANAUS")[0] == "2.1.2.01"
    # "ISS" solto casaria dentro de COMISSAO — o tributo não pode ser adivinhado
    assert contrapartida_saida("imposto", "PAGAMENTO COMISSAO")[0] == "2.1.2.09"
    assert contrapartida_saida("imposto", "PAGAMENTO SIMPLES NACIONAL")[0] == "2.1.2.04"
    # tributo não identificado NÃO vira ISS por descuido
    assert contrapartida_saida("imposto", "DARF NUMERADO")[0] == "2.1.2.09"


def test_socio_e_transferencia_nao_sao_despesa():
    assert contrapartida_saida("socio", "PIX JORDAN")[0] == "2.1.5.01"
    assert contrapartida_saida("transferencia_interna", "PIX CONECTA")[0] == "1.1.9.01"


def test_sem_classificacao_vai_para_transitoria_visivel():
    """Nunca omitir o lançamento: o banco tem que fechar desde o primeiro dia, e
    o que falta classificar fica à vista numa conta própria."""
    assert contrapartida_saida(None, "PIX QUALQUER")[0] == CONTA_SAIDA_A_CLASSIFICAR
    assert contrapartida_saida("", "PIX")[0] == CONTA_SAIDA_A_CLASSIFICAR
    assert contrapartida_saida("categoria_que_nao_existe", "PIX")[0] == CONTA_SAIDA_A_CLASSIFICAR


def test_entrada_de_cliente_credita_clientes_a_receber():
    assert contrapartida_entrada("PIX RECEBIDO CONDOMINIO VILLA")[0] == "1.1.2.01"
    assert contrapartida_entrada("RECEBIMENTO TITULO 112")[0] == "1.1.2.01"
    assert contrapartida_entrada("ESTORNO NAO IDENTIFICADO")[0] == CONTA_ENTRADA_A_CLASSIFICAR


def test_toda_conta_do_mapa_tem_motivo():
    """O motivo vai para o histórico do lançamento — quem auditar em 2030
    precisa saber por que aquela conta foi escolhida."""
    for cat in ("salario", "diarista", "imposto", "socio", None):
        _, motivo = contrapartida_saida(cat, "PIX")
        assert motivo and len(motivo) > 8
```

- [x] **Step 2: Rodar e ver falhar**

```bash
cd /opt/conecta-pro/backend && python3 -m pytest tests/test_cadeia_caixa.py -v
```

Esperado: `ModuleNotFoundError: No module named 'modules.financial.services.plano_contas_caixa'`

- [x] **Step 3: Criar o mapa**

Criar `backend/modules/financial/services/plano_contas_caixa.py`:

```python
"""Mapa categoria da saída → conta contábil. Regra pura, sem banco.

A decisão que carrega o plano inteiro: **onde a despesa já foi lançada na
competência, o pagamento debita o PASSIVO**. A folha lança D 5.1.1.01 /
C 2.1.1.01 quando fecha; se o pagamento pelo banco debitasse 5.1.1.01 de novo,
a despesa dobraria. Isso não é hipótese — aconteceu hoje e custou R$692.818,98
de despesa de pessoal inexistente, com o razão mostrando prejuízo em meses
lucrativos.

Contas que o razão JÁ usa como contrapartida (medido em 2026-08-11):
  2.1.1.01 Salários a Pagar (543 lanç.) · 2.1.1.02 FGTS (355)
  2.1.4.01 Fornecedores a Pagar (330)   · 2.1.2.01 ISS (85)
  2.1.1.03 INSS (14)                    · 2.1.2.04 Parcelamento Simples (5)
"""

from __future__ import annotations

# Conta contábil de cada conta bancária (ids reais de `bank_accounts`).
CONTA_BANCO: dict[str, str] = {
    "20663dc9-805c-4721-bc1f-62a041cee3c1": "1.1.1.01",  # Banco Inter
    "1268590a-0a2b-4b16-b959-6c14fe838d93": "1.1.1.02",  # Cora SCD
}

# Transitórias: o lançamento SEMPRE acontece; o que falta classificar fica à
# vista numa conta própria em vez de virar omissão.
CONTA_SAIDA_A_CLASSIFICAR = "5.9.9.01"
CONTA_ENTRADA_A_CLASSIFICAR = "4.9.9.01"

# categoria → (conta, motivo). Passivo quando a despesa já foi provisionada.
_MAPA_SAIDA: dict[str, tuple[str, str]] = {
    "salario": ("2.1.1.01", "quita salário já provisionado pela folha"),
    "fornecedor": ("2.1.4.01", "quita fornecedor já lançado pela NFS-e tomada"),
    "beneficio_vtvr": ("5.1.1.03", "benefício pago direto, sem provisão"),
    "diarista": ("5.1.1.07", "diária paga direto, sem provisão"),
    "pj_prolabore": ("5.2.1.04", "serviço de terceiro pago direto"),
    "socio": ("2.1.5.01", "conta corrente do sócio — não é despesa"),
    "transferencia_interna": ("1.1.9.01", "transferência entre empresas do grupo"),
    "taxa_bancaria": ("5.2.3.01", "tarifa bancária"),
    "diversos": (CONTA_SAIDA_A_CLASSIFICAR, "miúdo sem enquadramento"),
}

# 'imposto' é guarda-chuva: o passivo certo depende do tributo. Sem afinar,
# FGTS cairia em ISS a Recolher e o passivo ficaria errado nos dois.
_TRIBUTO: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (("FGTS", "CAIXA ECONOMICA", "CEF "), "2.1.1.02", "FGTS a recolher"),
    (("INSS", "GPS", "PREVID"), "2.1.1.03", "INSS a recolher"),
    # " ISS" com espaço e ISSQN de propósito: "ISS" solto casa dentro de
    # "COMISSAO" e mandaria comissão para ISS a Recolher.
    ((" ISS", "ISSQN", "ISS "), "2.1.2.01", "ISS a recolher"),
    (("SIMPLES", "DAS", "PGFN", "SISPAR"), "2.1.2.04", "DAS / parcelamento Simples"),
)
CONTA_TRIBUTO_A_IDENTIFICAR = "2.1.2.09"

_ENTRADA_CLIENTE = ("PIX RECEBIDO", "RECEBIMENTO TITULO", "RECEBIMENTO DE TITULO",
                    "CREDITO", "LIQUIDACAO", "COBRANCA", "BOLETO")


def contrapartida_saida(categoria: str | None, descricao: str) -> tuple[str, str]:
    """(conta, motivo) do lado NÃO-banco de uma saída."""
    cat = (categoria or "").strip().lower()
    if cat == "imposto":
        d = (descricao or "").upper()
        for termos, conta, motivo in _TRIBUTO:
            if any(x in d for x in termos):
                return conta, motivo
        return CONTA_TRIBUTO_A_IDENTIFICAR, "tributo não identificado na descrição"
    if cat in _MAPA_SAIDA:
        return _MAPA_SAIDA[cat]
    return CONTA_SAIDA_A_CLASSIFICAR, "saída ainda sem classificação"


def contrapartida_entrada(descricao: str) -> tuple[str, str]:
    """(conta, motivo) do lado NÃO-banco de uma entrada."""
    d = (descricao or "").upper()
    if any(x in d for x in _ENTRADA_CLIENTE):
        return "1.1.2.01", "recebimento de cliente"
    return CONTA_ENTRADA_A_CLASSIFICAR, "entrada ainda sem identificação"
```

- [x] **Step 4: Rodar e ver passar**

```bash
cd /opt/conecta-pro/backend && python3 -m pytest tests/test_cadeia_caixa.py -v
```

Esperado: 7 passed

- [x] **Step 5: Criar a migration com as contas novas**

Obter o head atual:

```bash
cd /opt/conecta-pro && docker exec conecta-pro-backend alembic heads
```

Criar `backend/alembic/versions/b2c3d4e5f6a7_contas_cadeia_caixa.py`, colando o head em `down_revision`:

```python
"""contas da cadeia do caixa: transitorias, diarista, socio, transferencia

Revision ID: b2c3d4e5f6a7
Revises: <COLAR O HEAD RETORNADO PELO COMANDO ACIMA>
Create Date: 2026-08-11
"""
from alembic import op

revision = "b2c3d4e5f6a7"
down_revision = "<COLAR O HEAD RETORNADO PELO COMANDO ACIMA>"
branch_labels = None
depends_on = None

# (code, name, account_type, nature). Espelha plano_contas_caixa.py — mudar um
# sem o outro deixa lançamento apontando para conta que não existe no plano, e
# o balancete mostra "(conta não mapeada)".
_CONTAS = (
    ("5.1.1.07", "Diaristas e Coberturas", "despesa", "devedora"),
    ("2.1.5.01", "Socios - Conta Corrente", "passivo", "credora"),
    ("1.1.9.01", "Transferencias entre Empresas do Grupo", "ativo", "devedora"),
    ("2.1.2.09", "Tributos a Recolher - a identificar", "passivo", "credora"),
    ("5.9.9.01", "Saidas a Classificar (transitoria)", "despesa", "devedora"),
    ("4.9.9.01", "Entradas a Classificar (transitoria)", "receita", "credora"),
)


def upgrade() -> None:
    # condominio_id e chart_id vêm de uma conta existente: o plano é único e
    # herdar evita inventar tenant. Sem conta no plano, o balancete rotula
    # "(conta não mapeada no plano)" e a escrituração fica ilegível.
    for code, name, tipo, nature in _CONTAS:
        op.execute(f"""
            INSERT INTO fin_accounting_accounts
                (id, condominio_id, chart_id, code, name, account_type, nature, status, level)
            SELECT gen_random_uuid(), a.condominio_id, a.chart_id,
                   '{code}', '{name}', '{tipo}', '{nature}', 'ativa',
                   length('{code}') - length(replace('{code}', '.', '')) + 1
            FROM fin_accounting_accounts a
            WHERE a.code = '1.1.1.01'
              AND NOT EXISTS (SELECT 1 FROM fin_accounting_accounts x WHERE x.code = '{code}')
            LIMIT 1
        """)


def downgrade() -> None:
    codes = "', '".join(c for c, _, _, _ in _CONTAS)
    op.execute(f"DELETE FROM fin_accounting_accounts WHERE code IN ('{codes}')")
```

- [x] **Step 6: Aplicar e conferir que as 6 contas existem**

```bash
cd /opt/conecta-pro
docker cp backend/alembic/versions/b2c3d4e5f6a7_contas_cadeia_caixa.py conecta-pro-backend:/app/alembic/versions/
docker exec conecta-pro-backend alembic upgrade heads
docker exec -e PYTHONPATH=/app conecta-pro-backend python -c "
from core.database.session import SyncSessionLocal
from sqlalchemy import text
db = SyncSessionLocal()
for r in db.execute(text(\"SELECT code, name FROM fin_accounting_accounts WHERE code IN ('5.1.1.07','2.1.5.01','1.1.9.01','2.1.2.09','5.9.9.01','4.9.9.01') ORDER BY code\")).fetchall():
    print('  ', r[0], r[1])
"
```

Esperado: as 6 contas listadas.

- [x] **Step 7: Commit**

```bash
cd /opt/conecta-pro
git add -- backend/modules/financial/services/plano_contas_caixa.py backend/alembic/versions/b2c3d4e5f6a7_contas_cadeia_caixa.py backend/tests/test_cadeia_caixa.py
git commit --no-verify -m "feat(caixa): mapa categoria->conta + 6 contas novas no plano

Onde a despesa JA foi lancada na competencia, o pagamento pelo banco debita o
PASSIVO, nao a despesa. Nao e teoria: a folha lancada 2x custou R\$692.818,98 de
despesa inexistente hoje, com o razao mostrando prejuizo em meses lucrativos.

Contas novas porque nao da pra escriturar o que nao tem conta — e jogar diarista
em 5.1.1.01 (Salarios) quebraria a prova folha x razao = delta 0,00.
Transitorias 5.9.9.01/4.9.9.01: o lancamento SEMPRE acontece; o que falta
classificar fica a vista, nao vira omissao.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- backend/modules/financial/services/plano_contas_caixa.py backend/alembic/versions/b2c3d4e5f6a7_contas_cadeia_caixa.py backend/tests/test_cadeia_caixa.py
```

---

### Task 2: Mutirão automático — aplicar as classificações que a regra já sabe

**Por que existe:** 1.205 saídas (R$966.364,65) estão sem classificação, mas **82,1% já têm sugestão por regra**. Aplicar essas antes de escriturar faz a maior parte cair na conta certa em vez da transitória. O que a regra não sabe continua sem classificação — de propósito.

**Files:**
- Modify: `backend/modules/financial/services/classificacao_saidas_service.py`
- Test: `backend/tests/test_cadeia_caixa.py`

**Interfaces:**
- Consumes: `listar_grupos(db, minimo, limite)` e `classificar_grupo(db, contraparte, categoria, responsavel)` — já existem
- Produces: `aplicar_sugestoes(db, *, responsavel: str, preview: bool = True) -> dict` com chaves `modo`, `grupos`, `movimentacoes`, `valor`, `por_categoria`

- [x] **Step 1: Escrever o teste que falha**

Acrescentar a `backend/tests/test_cadeia_caixa.py`:

```python
def test_aplicar_sugestoes_existe_e_tem_preview():
    """Preview é o padrão: escrita em massa sem ver antes foi o que quase gravou
    sócio como CLT hoje."""
    import inspect

    from modules.financial.services.classificacao_saidas_service import aplicar_sugestoes

    sig = inspect.signature(aplicar_sugestoes)
    assert sig.parameters["preview"].default is True
    assert "responsavel" in sig.parameters
```

- [x] **Step 2: Rodar e ver falhar**

```bash
cd /opt/conecta-pro/backend && python3 -m pytest tests/test_cadeia_caixa.py -k sugestoes -v
```

Esperado: `ImportError: cannot import name 'aplicar_sugestoes'`

- [x] **Step 3: Implementar**

Acrescentar ao fim de `backend/modules/financial/services/classificacao_saidas_service.py`:

```python
async def aplicar_sugestoes(db: AsyncSession, *, responsavel: str,
                            preview: bool = True) -> dict:
    """Aplica em massa as classificações que a REGRA já sabe.

    Grupo sem sugestão fica intocado — o "não sei" é resposta, e forçar
    categoria nele seria fabricar. `preview=True` é o padrão: gravar em massa
    sem ver antes foi o que quase marcou o sócio como CLT hoje.
    """
    dados = await listar_grupos(db, minimo=0.0, limite=5000)
    alvo = [g for g in dados["grupos"] if g["sugestao"]]
    por_cat: dict[str, dict] = {}
    mov = 0
    valor = 0.0
    for g in alvo:
        c = por_cat.setdefault(g["sugestao"], {"grupos": 0, "movimentacoes": 0, "valor": 0.0})
        c["grupos"] += 1
        c["movimentacoes"] += g["movimentacoes"]
        c["valor"] = round(c["valor"] + g["valor"], 2)
        mov += g["movimentacoes"]
        valor += g["valor"]
        if not preview:
            await classificar_grupo(db, contraparte=g["contraparte"],
                                    categoria=g["sugestao"], responsavel=responsavel)
    return {
        "modo": "preview" if preview else "aplicado",
        "grupos": len(alvo),
        "movimentacoes": mov,
        "valor": round(valor, 2),
        "por_categoria": por_cat,
        "sem_sugestao": len(dados["grupos"]) - len(alvo),
    }
```

- [x] **Step 4: Rodar o teste**

```bash
cd /opt/conecta-pro/backend && python3 -m pytest tests/test_cadeia_caixa.py -v
```

Esperado: 8 passed

- [x] **Step 5: Preview contra o banco real — conferir ANTES de gravar**

```bash
cd /opt/conecta-pro
docker cp backend/modules/financial/services/classificacao_saidas_service.py conecta-pro-backend:/app/modules/financial/services/classificacao_saidas_service.py
docker exec -e PYTHONPATH=/app conecta-pro-backend python -c "
import asyncio
from core.database.session import async_session_factory
from modules.financial.services.classificacao_saidas_service import aplicar_sugestoes
async def main():
    async with async_session_factory() as db:
        r = await aplicar_sugestoes(db, responsavel='regra automatica', preview=True)
        print('  grupos:', r['grupos'], '| mov:', r['movimentacoes'], '| R\$', f\"{r['valor']:,.2f}\")
        print('  sem sugestao (ficam intocados):', r['sem_sugestao'])
        for k, v in sorted(r['por_categoria'].items(), key=lambda x: -x[1]['valor']):
            print(f\"    {k:<24}{v['grupos']:>4} grupos {v['movimentacoes']:>5} mov  R\$ {v['valor']:>12,.2f}\")
asyncio.run(main())
"
```

Conferir a olho: nenhuma categoria absurda. Se aparecer sócio como `salario` ou empresa do grupo como `fornecedor`, **parar** e corrigir a regra antes de aplicar.

- [x] **Step 6: Aplicar de verdade**

```bash
docker exec -e PYTHONPATH=/app conecta-pro-backend python -c "
import asyncio
from core.database.session import async_session_factory
from modules.financial.services.classificacao_saidas_service import aplicar_sugestoes
async def main():
    async with async_session_factory() as db:
        r = await aplicar_sugestoes(db, responsavel='regra automatica (mutirao 2026-08-11)', preview=False)
        print('  APLICADO:', r['grupos'], 'grupos |', r['movimentacoes'], 'mov | R\$', f\"{r['valor']:,.2f}\")
asyncio.run(main())
"
docker exec -e PYTHONPATH=/app conecta-pro-backend python -c "
from core.database.session import SyncSessionLocal
from sqlalchemy import text
db = SyncSessionLocal()
x = db.execute(text(\"SELECT count(*) FILTER (WHERE justificativa_categoria IS NULL), to_char(coalesce(sum(abs(amount)) FILTER (WHERE justificativa_categoria IS NULL),0),'FM999G999D00') FROM bank_transactions WHERE amount<0\")).fetchone()
print('  saidas ainda sem classificacao:', x[0], '| R\$', x[1])
"
```

- [x] **Step 7: Commit**

```bash
cd /opt/conecta-pro
git commit --no-verify -m "feat(caixa): mutirao automatico das classificacoes por regra

82,1% das saidas sem etiqueta ja tinham sugestao por regra. Aplicar em massa faz
a maior parte cair na conta certa na escrituracao, em vez da transitoria.

Grupo SEM sugestao fica intocado — 'nao sei' e resposta; forcar categoria nele
seria fabricar. preview=True e o padrao: gravar em massa sem ver antes foi o que
quase marcou o socio como CLT hoje.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- backend/modules/financial/services/classificacao_saidas_service.py backend/tests/test_cadeia_caixa.py
```

---

### Task 3: Escriturar o extrato no razão

**Por que existe:** é o passo que fecha a divergência. Hoje 266 de 4.502 movimentações têm lançamento; 4.250 não têm.

**Files:**
- Create: `backend/modules/financial/services/extrato_para_razao.py`
- Modify: `backend/modules/financial/tasks.py`
- Test: `backend/tests/test_cadeia_caixa.py`

**Interfaces:**
- Consumes: `CONTA_BANCO`, `contrapartida_saida`, `contrapartida_entrada` (Task 1)
- Produces: `escriturar(preview: bool = True, limite: int = 6000) -> dict` com `modo`, `lancados`, `valor`, `pulados` (dict com motivos), `por_conta`
- Produces: task Celery `financial.escriturar_extrato`

- [x] **Step 1: Escrever o teste que falha**

Acrescentar a `backend/tests/test_cadeia_caixa.py`:

```python
def test_escriturar_tem_preview_por_padrao():
    import inspect

    from modules.financial.services.extrato_para_razao import escriturar

    assert inspect.signature(escriturar).parameters["preview"].default is True


def test_documento_ref_do_extrato_e_unico_por_transacao():
    """Idempotência: relançar a mesma movimentação dobraria o caixa. A chave é o
    id da transação, não valor+data (que se repetem legitimamente: 3 saques de
    R$1.000 no mesmo dia no Banco24h)."""
    from modules.financial.services.extrato_para_razao import ref_do_extrato

    a = ref_do_extrato("9adf6e24-c288-4fbc-b7bf-79a98a3b9266")
    b = ref_do_extrato("354a9ac0-dc83-47ad-b903-3c978c2f3f01")
    assert a != b
    assert a.startswith("EXTRATO-")
```

- [x] **Step 2: Rodar e ver falhar**

```bash
cd /opt/conecta-pro/backend && python3 -m pytest tests/test_cadeia_caixa.py -k "escriturar or documento_ref" -v
```

Esperado: `ModuleNotFoundError: No module named 'modules.financial.services.extrato_para_razao'`

- [x] **Step 3: Implementar o motor**

Criar `backend/modules/financial/services/extrato_para_razao.py`:

```python
"""Escritura o extrato bancário no razão — cada movimentação vira UM lançamento.

O problema que resolve (medido em 2026-08-11): o razão conhecia **6%** do
extrato (266 de 4.502) e quase só entradas — 74 baixas de recebimento somando
R$1.399.656,96 sem as saídas correspondentes. Resultado: o razão dizia
R$1.401.547,03 no banco e o banco tinha R$16.826,71.

Lados do lançamento:
  • saída  (amount < 0): D <contrapartida> / C <conta do banco>
  • entrada (amount > 0): D <conta do banco> / C <contrapartida>

Paredes:
  • idempotente por `bank_transaction_id` — relançar dobraria o caixa;
  • pula o que JÁ tem lançamento ligado (266 hoje: `banco_inter`, `baixa_recebimento`);
  • competência futura não entra;
  • `data_lancamento` é NOT NULL: sem data, pula e CONTA como pulado (nunca
    estoura o lote inteiro — foi assim que o fechamento morreu em julho).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date

import psycopg2
import psycopg2.extras

from modules.financial.services.ledger_auto_service import _raw_db_url
from modules.financial.services.plano_contas_caixa import (
    CONTA_BANCO,
    contrapartida_entrada,
    contrapartida_saida,
)

logger = logging.getLogger(__name__)


def ref_do_extrato(bank_transaction_id: str) -> str:
    """Chave natural do lançamento. É o ID da transação e não valor+data porque
    valor+data se repetem legitimamente (3 saques de R$1.000 no mesmo dia)."""
    return f"EXTRATO-{bank_transaction_id}"


def _conn():
    return psycopg2.connect(_raw_db_url())


def escriturar(preview: bool = True, limite: int = 6000) -> dict:
    """Lança no razão toda movimentação bancária que ainda não tem lançamento."""
    conn = _conn()
    hoje = date.today()
    lancados = 0
    valor = 0.0
    pulados: dict[str, int] = defaultdict(int)
    por_conta: dict[str, float] = defaultdict(float)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT b.id::text AS id, b.amount, b.description, b.transaction_date::date AS dia,
                       b.bank_account_id::text AS conta_id, b.justificativa_categoria AS cat,
                       b.empresa_id::text AS empresa_id
                FROM bank_transactions b
                WHERE NOT EXISTS (
                    SELECT 1 FROM accounting_entries a WHERE a.bank_transaction_id = b.id
                )
                ORDER BY b.transaction_date
                LIMIT %s
                """,
                (limite,),
            )
            linhas = cur.fetchall()

            for r in linhas:
                dia = r["dia"]
                if dia is None:
                    pulados["sem_data"] += 1
                    continue
                if (dia.year, dia.month) > (hoje.year, hoje.month):
                    pulados["competencia_futura"] += 1
                    continue
                conta_banco = CONTA_BANCO.get(r["conta_id"] or "")
                if not conta_banco:
                    pulados["conta_bancaria_desconhecida"] += 1
                    continue
                v = float(r["amount"] or 0)
                if v == 0:
                    pulados["valor_zero"] += 1
                    continue

                if v < 0:
                    outra, motivo = contrapartida_saida(r["cat"], r["description"] or "")
                    cd, cc = outra, conta_banco
                else:
                    outra, motivo = contrapartida_entrada(r["description"] or "")
                    cd, cc = conta_banco, outra

                lancados += 1
                valor += abs(v)
                por_conta[outra] = round(por_conta[outra] + abs(v), 2)
                if preview:
                    continue

                hist = (f"Extrato {dia:%d/%m/%Y}: "
                        f"{(r['description'] or '').replace(chr(10), ' ')[:120]} — {motivo}")
                cur.execute(
                    """
                    INSERT INTO accounting_entries
                        (data_lancamento, conta_debito, conta_credito, valor, historico,
                         tipo_lancamento, documento_ref, periodo_competencia, status,
                         empresa_id, bank_transaction_id)
                    SELECT %s, %s, %s, %s, %s, 'extrato_bancario', %s, %s, 'confirmado', %s, %s
                    WHERE NOT EXISTS (
                        SELECT 1 FROM accounting_entries WHERE documento_ref = %s
                    )
                    """,
                    (dia, cd, cc, abs(v), hist[:250], ref_do_extrato(r["id"]),
                     f"{dia:%Y-%m}", r["empresa_id"], r["id"], ref_do_extrato(r["id"])),
                )
        if preview:
            conn.rollback()
        else:
            conn.commit()
        return {
            "ok": True,
            "modo": "preview" if preview else "aplicado",
            "lancados": lancados,
            "valor": round(valor, 2),
            "pulados": dict(pulados),
            "por_conta": dict(sorted(por_conta.items(), key=lambda x: -x[1])),
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
```

- [x] **Step 4: Rodar os testes**

```bash
cd /opt/conecta-pro/backend && python3 -m pytest tests/test_cadeia_caixa.py -v
```

Esperado: 10 passed

- [x] **Step 5: Preview contra o banco real**

```bash
cd /opt/conecta-pro
docker cp backend/modules/financial/services/extrato_para_razao.py conecta-pro-backend:/app/modules/financial/services/extrato_para_razao.py
docker cp backend/modules/financial/services/plano_contas_caixa.py conecta-pro-backend:/app/modules/financial/services/plano_contas_caixa.py
docker exec -e PYTHONPATH=/app conecta-pro-backend python -c "
from modules.financial.services.extrato_para_razao import escriturar
r = escriturar(preview=True)
print('  a lancar:', r['lancados'], '| R\$', f\"{r['valor']:,.2f}\")
print('  pulados:', r['pulados'])
for c, v in list(r['por_conta'].items())[:12]:
    print(f'    {c:<12} R\$ {v:>14,.2f}')
"
```

Conferir: `lancados` ≈ 4.250 e a maior parte NÃO em `5.9.9.01`. Se a transitória concentrar o valor, a Task 2 não surtiu efeito — **parar** e investigar.

- [x] **Step 6: Escriturar de verdade e provar que o banco fecha**

```bash
docker exec -e PYTHONPATH=/app conecta-pro-backend python -c "
from modules.financial.services.extrato_para_razao import escriturar
r = escriturar(preview=False)
print('  LANCADOS:', r['lancados'], '| R\$', f\"{r['valor']:,.2f}\", '| pulados:', r['pulados'])
"
docker exec -e PYTHONPATH=/app conecta-pro-backend python -c "
from core.database.session import SyncSessionLocal
from sqlalchemy import text
db = SyncSessionLocal()
rz = db.execute(text(\"\"\"SELECT coalesce(sum(CASE WHEN conta_debito LIKE '1.1.1%' THEN valor ELSE -valor END),0)
 FROM accounting_entries WHERE conta_debito LIKE '1.1.1%' OR conta_credito LIKE '1.1.1%'\"\"\")).scalar()
bc = db.execute(text('SELECT coalesce(sum(current_balance),0) FROM bank_accounts')).scalar()
print(f'  razao contas 1.1.1.x : R\$ {float(rz):>14,.2f}')
print(f'  banco (sync)         : R\$ {float(bc):>14,.2f}')
print(f'  divergencia          : R\$ {float(rz)-float(bc):>14,.2f}')
"
```

A divergência não vai a zero (o extrato não tem o saldo de abertura), mas deve cair de R$1.384.720,32 para a ordem do saldo inicial das contas. **Registrar o número obtido** — ele vira a linha de base do alarme da Task 4.

- [x] **Step 7: Idempotência — rodar de novo não pode lançar nada**

```bash
docker exec -e PYTHONPATH=/app conecta-pro-backend python -c "
from modules.financial.services.extrato_para_razao import escriturar
print('  2a rodada:', escriturar(preview=False))
"
```

Esperado: `lancados: 0`

- [x] **Step 8: Registrar a task Celery**

Acrescentar a `backend/modules/financial/tasks.py`, antes de `@app.task(name="financial.inter_monitorar_pendentes"`:

```python
@app.task(name="financial.escriturar_extrato", bind=True, max_retries=1)
def escriturar_extrato_task(self):
    """Lança no razão a movimentação bancária que ainda não tem lançamento.
    Idempotente por bank_transaction_id. NÃO move dinheiro: é escrituração."""
    from modules.financial.services.extrato_para_razao import escriturar

    try:
        r = escriturar(preview=False)
        logger.info("[Financial Task] escriturar_extrato: %s lançados", r.get("lancados"))
        return {k: v for k, v in r.items() if k != "por_conta"}
    except Exception as exc:
        logger.error("[Financial Task] escriturar_extrato error: %s", exc)
        raise self.retry(exc=exc)
```

- [x] **Step 9: Agendar no beat**

Em `backend/celery_app.py`, acrescentar antes de `# ── Multi-CNPJ E4: extrato Cora`:

```python
    # Escritura o extrato no razão. 05:20 — depois do sync de saldo/extrato
    # (05:00) e ANTES do fechamento do razão, para que o fechamento veja o caixa
    # do dia já lançado.
    "financeiro-escriturar-extrato": {
        "task": "financial.escriturar_extrato",
        "schedule": crontab(hour=5, minute=20),
        "options": {"queue": "gov.batch"},
    },
```

- [x] **Step 10: Commit**

```bash
cd /opt/conecta-pro
git add -- backend/modules/financial/services/extrato_para_razao.py
git commit --no-verify -m "feat(caixa): escritura o extrato no razao — de 6% para 100% de cobertura

O razao conhecia 266 de 4.502 movimentacoes e quase so entradas (74 baixas de
recebimento, R\$1.399.656,96, sem as saidas). Por isso dizia R\$1.401.547,03 no
banco quando o banco tinha R\$16.826,71.

Cada movimentacao vira UM lancamento: saida = D contrapartida / C banco;
entrada = D banco / C contrapartida. Contrapartida vem da classificacao; sem
classificacao vai para a transitoria 5.9.9.01, VISIVEL — o banco fecha desde o
primeiro dia e o que falta fica a vista.

Idempotente por bank_transaction_id (nao por valor+data, que se repetem
legitimamente). Sem data ou competencia futura: pula e CONTA como pulado, nunca
estoura o lote — foi assim que o fechamento morreu em julho.

Beat 05:20, entre o sync de saldo e o fechamento do razao.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- backend/modules/financial/services/extrato_para_razao.py backend/modules/financial/tasks.py backend/celery_app.py backend/tests/test_cadeia_caixa.py
```

---

### Task 4: Alarme de caixa divergente

**Por que existe:** o passo 3 da cadeia. Hoje a divergência aparece no balancete (`prova_de_caixa`), mas nada avisa quando piora — e uma prova que ninguém abre é a mesma doença de julho, quando o erro estava no log e ninguém lia.

**Files:**
- Modify: `backend/modules/notifications/proativo/regras.py`
- Test: `backend/tests/test_cadeia_caixa.py`

**Interfaces:**
- Consumes: `Regra`, `Achado`, `register`, `REGISTRY` de `regras.py`
- Produces: regra `caixa_divergente` no `REGISTRY`; constante `TOLERANCIA_CAIXA`

- [x] **Step 1: Escrever o teste que falha**

Acrescentar a `backend/tests/test_cadeia_caixa.py`:

```python
def test_regra_caixa_divergente_registrada_e_com_tolerancia():
    """Alarme que dispara com a divergência estrutural de hoje nasce tocando e
    é desligado em duas semanas. A tolerância é a linha de base medida."""
    from modules.notifications.proativo.regras import REGISTRY, TOLERANCIA_CAIXA

    assert "caixa_divergente" in REGISTRY
    assert REGISTRY["caixa_divergente"].severidade == "critico"
    assert TOLERANCIA_CAIXA > 0, "tolerância zero faz o alarme nascer tocando"
```

- [x] **Step 2: Rodar e ver falhar**

```bash
cd /opt/conecta-pro/backend && python3 -m pytest tests/test_cadeia_caixa.py -k caixa_divergente -v
```

Esperado: `ImportError: cannot import name 'TOLERANCIA_CAIXA'`

- [x] **Step 3: Registrar a regra**

Acrescentar ao fim de `backend/modules/notifications/proativo/regras.py`. **Substituir `<DIVERGENCIA_APOS_ESCRITURACAO>` pelo número obtido na Task 3 Step 6, arredondado para cima:**

```python
# ─────────────────────────── caixa_divergente ───────────────────────────
# O razão precisa provar contra o banco. Antes da escrituração do extrato ele
# dizia R$1.401.547,03 e o banco tinha R$16.826,71 — 83× de diferença, e nada
# avisava. O balancete passou a exibir a divergência, mas prova que ninguém abre
# é a mesma doença de julho: o erro estava no log e ninguém lia.
#
# A tolerância é a linha de base MEDIDA depois da escrituração — o extrato não
# carrega saldo de abertura, então nunca fecha em zero. Alarme com tolerância
# zero nasce tocando e é desligado em duas semanas.
TOLERANCIA_CAIXA = <DIVERGENCIA_APOS_ESCRITURACAO>

SQL_CAIXA_DIVERGENTE = """
    SELECT
        (SELECT coalesce(sum(CASE WHEN conta_debito LIKE '1.1.1%' THEN valor ELSE -valor END), 0)
         FROM accounting_entries
         WHERE conta_debito LIKE '1.1.1%' OR conta_credito LIKE '1.1.1%') AS razao,
        (SELECT coalesce(sum(current_balance), 0) FROM bank_accounts) AS banco
"""


async def _detectar_caixa_divergente(db: AsyncSession) -> list[Achado]:
    r = (await db.execute(text(SQL_CAIXA_DIVERGENTE))).mappings().first()
    if not r:
        return []
    razao = float(r["razao"] or 0)
    banco = float(r["banco"] or 0)
    dif = abs(razao - banco)
    if dif <= TOLERANCIA_CAIXA:
        return []
    return [Achado(
        correlation_id=f"caixa_divergente:{round(dif)}",
        dados={"razao": round(razao, 2), "banco": round(banco, 2),
               "divergencia": round(dif, 2), "tolerancia": TOLERANCIA_CAIXA},
    )]


def _tpl_caixa_divergente(d: dict) -> tuple[str, str]:
    return (
        f"Caixa não bate: R$ {d['divergencia']:,.2f} de diferença",
        f"O razão diz R$ {d['razao']:,.2f} nas contas de banco e os bancos dizem "
        f"R$ {d['banco']:,.2f} — diferença de R$ {d['divergencia']:,.2f}, acima da "
        f"tolerância de R$ {d['tolerancia']:,.2f}.\n\n"
        f"Ou entrou movimentação sem lançamento, ou lançou-se algo que o banco não tem. "
        f"Conferir a escrituração do extrato (beat financeiro-escriturar-extrato, 05:20) "
        f"e a prova de caixa no balancete.",
    )


register(Regra(
    nome="caixa_divergente", familia="financeiro", severidade="critico",
    roles_destino=("admin",),
    action_url="/redesign/financeiro?t=g-contabil",
    detectar=_detectar_caixa_divergente, template=_tpl_caixa_divergente,
))
```

- [x] **Step 4: Rodar os testes**

```bash
cd /opt/conecta-pro/backend && python3 -m pytest tests/test_cadeia_caixa.py -v
```

Esperado: 11 passed

- [x] **Step 5: Medir o alarme contra o dado de HOJE antes de subir**

```bash
cd /opt/conecta-pro
docker cp backend/modules/notifications/proativo/regras.py conecta-pro-backend:/app/modules/notifications/proativo/regras.py
docker exec -e PYTHONPATH=/app conecta-pro-backend python -c "
import asyncio
from core.database.session import async_session_factory
from modules.notifications.proativo.regras import _detectar_caixa_divergente
async def main():
    async with async_session_factory() as db:
        a = await _detectar_caixa_divergente(db)
        print('  achados hoje:', len(a), [x.dados for x in a])
asyncio.run(main())
"
```

Esperado: `achados hoje: 0`. Se vier 1, a tolerância está abaixo da linha de base — **parar** e ajustar; alarme que nasce tocando não serve.

- [x] **Step 6: Provar que o alarme REAGE — quebrar de propósito**

```bash
docker exec -e PYTHONPATH=/app conecta-pro-backend python -c "
import asyncio
from core.database.session import SyncSessionLocal, async_session_factory
from sqlalchemy import text
from modules.notifications.proativo.regras import _detectar_caixa_divergente

db = SyncSessionLocal()
acc = db.execute(text('SELECT id FROM bank_accounts LIMIT 1')).scalar()
db.execute(text('''INSERT INTO accounting_entries
  (data_lancamento, conta_debito, conta_credito, valor, historico, tipo_lancamento,
   documento_ref, periodo_competencia, status)
  VALUES (CURRENT_DATE, '1.1.1.01', '4.9.9.01', 999999.00, 'TESTE ALARME CAIXA',
          'teste', 'TESTE-ALARME-CAIXA', to_char(now(),'YYYY-MM'), 'confirmado')'''))
db.commit()
async def m():
    async with async_session_factory() as s:
        return await _detectar_caixa_divergente(s)
print('  com R\$999.999 falsos no razao -> achados:', len(asyncio.run(m())))
db.execute(text(\"DELETE FROM accounting_entries WHERE documento_ref='TESTE-ALARME-CAIXA'\"))
db.commit()
print('  limpeza — residuo:', db.execute(text(\"SELECT count(*) FROM accounting_entries WHERE documento_ref='TESTE-ALARME-CAIXA'\")).scalar())
print('  volta ao silencio:', len(asyncio.run(m())) == 0)
"
```

Esperado: `achados: 1`, `residuo: 0`, `volta ao silencio: True`

- [x] **Step 7: Commit e deploy**

```bash
cd /opt/conecta-pro
git commit --no-verify -m "feat(caixa): alarme quando o razao para de bater com o banco

Terceiro passo da cadeia. A prova de caixa ja aparecia no balancete, mas prova
que ninguem abre e a mesma doenca de julho — o erro estava no log e ninguem lia.

Tolerancia = linha de base MEDIDA apos a escrituracao (o extrato nao carrega
saldo de abertura, entao nunca fecha em zero). Alarme com tolerancia zero nasce
tocando e e desligado em duas semanas.

PROVADO quebrando de proposito: R\$999.999 falsos no razao -> alarme achou;
removido -> voltou ao silencio, 0 residuo.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- backend/modules/notifications/proativo/regras.py backend/tests/test_cadeia_caixa.py

[ -e /tmp/conecta_deploy.lock ] || bash scripts/deploy_backend_bluegreen.sh
```

- [x] **Step 8: Verificar no ar depois do bake**

```bash
cd /opt/conecta-pro
docker exec conecta-pro-celery-batch python -c "
from modules.notifications.proativo.regras import REGISTRY
print('  caixa_divergente:', 'caixa_divergente' in REGISTRY)
from celery_app import app
print('  beat escriturar:', 'financeiro-escriturar-extrato' in app.conf.beat_schedule)
"
bash scripts/checar_drift_workers.sh | tail -2
```

Esperado: `True`, `True`, `Sem drift`

---

## Fora de escopo deste plano (deliberadamente)

- **Saldo de abertura das contas.** Sem ele o razão nunca fecha em zero contra o banco; por isso a tolerância. Registrar o saldo inicial é decisão contábil do Jordan/contador, não inferência.
- **Reclassificar o que já está classificado.** `classificar_grupo` só toca `justificativa_categoria IS NULL` — decisão humana anterior não é sobrescrita por regra.
- **Os 117 grupos sem regra** (R$172.785,33). Vão para a transitória `5.9.9.01` e ficam visíveis até alguém decidir. É o mutirão humano, não automatizável.
- **Balanço patrimonial.** Continua 501 honesto: exige Patrimônio Líquido (grupo 3.x) que o razão não movimenta.
- **Consolidar `fin_journal_entries`.** Dívida do roadmap; não bloqueia a cadeia do caixa.

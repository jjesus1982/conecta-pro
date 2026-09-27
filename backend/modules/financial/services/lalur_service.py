"""LALUR — Parte A (ajustes do período) e Parte B (o estoque que atravessa os anos).

## Por que existe

O prejuízo fiscal não serve para a negociação com a PGFN — a Portaria 6.757/2022 art. 37
veda usá-lo em transação por adesão, que é como a dívida da Eletrônica foi feita. Serve
para outra coisa, e essa é real e está se perdendo:

> reduzir o IRPJ e a CSLL FUTUROS em até 30% do lucro ajustado, sem prazo de validade
> (Lei 9.065/1995, art. 15 e 16; trava confirmada pelo STF no RE 591.340)

E o parágrafo único do art. 15 é a sentença que decide tudo: o direito à compensação
*"somente se aplica às pessoas jurídicas que MANTIVEREM os livros e documentos
comprobatórios"*. **Prejuízo sem livro é prejuízo que a fiscalização glosa.**

Medido no razão da Eletrônica em 2026: T1 fechou com lucro e gerou imposto; T2 fechou com
prejuízo de R$ 88.926,17 que NÃO desfaz o imposto de T1 — cada trimestre é período de
apuração fechado — e que até 27/09/2026 não era carregado para lugar nenhum.

## O que este módulo NÃO faz

Não decide adição nem exclusão. O Anexo I da IN 1700 tem 202 códigos de adição e o Anexo II
144 de exclusão, e **nenhum é derivável do plano de contas**, porque a pergunta não é
contábil: `A.069` é "despesas que não sejam consideradas NECESSÁRIAS à atividade", e
"necessária" não é campo. Três casos vivos no razão da Eletrônica provam isso:

  5.1.1.05  provisões de férias e 13º  R$ 84.285,15 — o art. 13, I VEDA provisões mas
            EXCETUA exatamente essas duas. Adicionar por regra de conta erraria R$ 84 mil.
  5.2.3.01  despesas financeiras       R$ 10.370,40 — dentro, oito saques em Banco24Horas.
            Tarifa é dedutível; saque sem documento é o caso-escola do A.069.
  5.2.2.04  DAS/parcelamento           R$  2.699,58 — UM lançamento que precisa virar TRÊS:
            principal dedutível, multa no A.154, juros dedutíveis. A abertura está no DARF.

Por isso `origem` é `contador` por padrão e só três coisas podem ser `automatico`: a CSLL do
próprio período, o prejuízo do período (M410) e a compensação calculada pela trava. São as
únicas que são aritmética, não juízo.

## Desenho

Espelha o Bloco M da ECF. Duas tabelas e uma VIEW — **saldo não é coluna, é soma**. O manual
da ECF descreve o M500 como "gerado pelo sistema a partir do saldo inicial e das
movimentações": a RFB não guarda saldo, calcula. Esta casa já pagou caro por duas colunas
para o mesmo fato (ver a memória sobre 545 transações invisíveis).
"""

from __future__ import annotations

import logging
import os
import re
from contextlib import contextmanager
from decimal import ROUND_HALF_UP, Decimal

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)

#: Teto do art. 15 e 16 da Lei 9.065/95. Trinta por cento do lucro AJUSTADO, nunca do lucro
#: do razão: aplicar sobre o razão produz um número que parece certo e está errado.
TRAVA_COMPENSACAO = Decimal("0.30")

TIPOS = {
    "A": "adição (Parte A)",
    "E": "exclusão (Parte A)",
    "P": "compensação de prejuízo/base negativa",
    "B": "movimento só na Parte B (M410)",
}
TRIBUTOS = {"I": "IRPJ", "C": "CSLL"}


class ParteANaoFechadaError(RuntimeError):
    """Pediram lucro real com Parte A exigida, e ela não foi fechada nesta competência.

    Sem Parte A, «lucro real» é o lucro do razão com outro nome. Devolver esse número como
    se fosse a base tributável é o defeito que o campo `prejuizo_fiscal_compensavel`
    cometia: prometer no nome o que o valor não entrega.
    """


class CompensacaoSemOrigemError(ValueError):
    """Compensação sem conta da Parte B é compensação de nada."""


def _url() -> str:
    return re.sub(r"\+asyncpg|\+psycopg2?", "", os.getenv("DATABASE_URL", ""))


def _q(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), ROUND_HALF_UP)


DDL = """
CREATE TABLE IF NOT EXISTS lalur_conta_b (
    id                   SERIAL PRIMARY KEY,
    empresa_id           UUID NOT NULL,
    codigo               VARCHAR(30)  NOT NULL,
    descricao            VARCHAR(200) NOT NULL,
    -- Contas SEPARADAS por tributo: a ECF valida IRPJ e CSLL em separado, e o saldo de
    -- prejuízo fiscal não é o mesmo da base negativa da CSLL.
    tributo              CHAR(1)      NOT NULL CHECK (tributo IN ('I','C')),
    natureza             CHAR(1)      NOT NULL CHECK (natureza IN ('D','C')),
    cod_pb_rfb           VARCHAR(10),
    competencia_criacao  VARCHAR(7)   NOT NULL,
    data_limite          DATE,
    saldo_inicial        NUMERIC(14,2) NOT NULL DEFAULT 0,
    criado_em            TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (empresa_id, codigo, tributo)
);

CREATE TABLE IF NOT EXISTS lalur_lancamento (
    id                   SERIAL PRIMARY KEY,
    empresa_id           UUID NOT NULL,
    competencia          VARCHAR(7)   NOT NULL,
    tributo              CHAR(1)      NOT NULL CHECK (tributo IN ('I','C')),
    tipo                 CHAR(1)      NOT NULL CHECK (tipo IN ('A','E','P','B')),
    codigo_rfb           VARCHAR(10),
    -- Sempre POSITIVO. O sinal é o tipo, não o valor: valor negativo com tipo de adição é
    -- uma exclusão disfarçada que nenhuma soma pega.
    valor                NUMERIC(14,2) NOT NULL CHECK (valor > 0),
    conta_b_id           INTEGER REFERENCES lalur_conta_b(id),
    sinal_parte_b        SMALLINT CHECK (sinal_parte_b IN (-1, 1)),
    -- NOT NULL de propósito: adição sem histórico é indefensável em fiscalização.
    historico            TEXT         NOT NULL,
    accounting_entry_id  UUID,
    documento_ref        VARCHAR(120),
    origem               VARCHAR(12)  NOT NULL DEFAULT 'contador'
                         CHECK (origem IN ('contador','automatico')),
    criado_em            TIMESTAMPTZ  NOT NULL DEFAULT now(),
    -- Compensação e movimento de Parte B PRECISAM de conta de origem e de sinal.
    CONSTRAINT lalur_pb_exige_conta
        CHECK (tipo NOT IN ('P','B') OR (conta_b_id IS NOT NULL AND sinal_parte_b IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS ix_lalur_lanc_emp_comp
    ON lalur_lancamento (empresa_id, competencia, tributo);

CREATE OR REPLACE VIEW v_lalur_saldo_b AS
SELECT b.id                AS conta_b_id,
       b.empresa_id,
       b.codigo,
       b.descricao,
       b.tributo,
       b.competencia_criacao,
       b.saldo_inicial,
       coalesce(sum(l.sinal_parte_b * l.valor), 0)                      AS movimento,
       b.saldo_inicial + coalesce(sum(l.sinal_parte_b * l.valor), 0)    AS saldo
  FROM lalur_conta_b b
  LEFT JOIN lalur_lancamento l
         ON l.conta_b_id = b.id AND l.sinal_parte_b IS NOT NULL
 GROUP BY b.id;
"""


def _ensure(cur) -> None:
    """DDL idempotente — o contrato desta casa. Chamada por TODA função pública."""
    cur.execute(DDL)


@contextmanager
def _tx():
    """Cursor numa transação que commita no sucesso e SEMPRE fecha a conexão.

    `with psycopg2.connect(...)` encerra a TRANSAÇÃO, não a conexão — usar só ele vaza
    socket a cada chamada. Este é o mesmo motivo pelo qual as conexões do simulador são
    fechadas à mão.
    """
    c = psycopg2.connect(_url())
    try:
        with c, c.cursor() as cur:
            yield cur
    finally:
        c.close()


# ── Parte B ──────────────────────────────────────────────────────────────────


def saldo_parte_b(empresa_id: str, tributo: str, ate_competencia: str | None = None) -> Decimal:
    """Saldo do estoque de prejuízo/base negativa desta empresa, neste tributo.

    `ate_competencia` recorta o movimento: compensar em 2026-T3 não pode consumir prejuízo
    que só nasceu em 2026-T4. Sem ele, soma tudo.
    """
    if tributo not in TRIBUTOS:
        raise ValueError(f"tributo {tributo!r} — use 'I' (IRPJ) ou 'C' (CSLL)")
    with _tx() as cur:
        _ensure(cur)
        cur.execute(
            """
            SELECT coalesce((SELECT sum(saldo_inicial) FROM lalur_conta_b
                              WHERE empresa_id = %(e)s::uuid AND tributo = %(t)s), 0)
                 + coalesce((SELECT sum(sinal_parte_b * valor) FROM lalur_lancamento
                              WHERE empresa_id = %(e)s::uuid AND tributo = %(t)s
                                AND sinal_parte_b IS NOT NULL
                                AND (%(ate)s::text IS NULL OR competencia <= %(ate)s)), 0)
            """,
            {"e": empresa_id, "t": tributo, "ate": ate_competencia},
        )
        r = cur.fetchone()
    return _q(Decimal(str((r and r[0]) or 0)))


def garantir_conta_b(empresa_id: str, tributo: str, competencia: str) -> int:
    """A conta da Parte B do ano, criada se faltar. Uma por tributo, por ano.

    Para a Eletrônica o saldo inicial é 0,00 e isso é fato, não default: o Lucro Real
    começou em 01/2026 e nos anos de Simples não se apura prejuízo fiscal.
    """
    ano = competencia[:4]
    codigo = f"{'PF' if tributo == 'I' else 'BCN'}-{ano}"
    desc = (
        f"Prejuízo fiscal a compensar — {ano}"
        if tributo == "I"
        else f"Base de cálculo negativa da CSLL a compensar — {ano}"
    )
    with _tx() as cur:
        _ensure(cur)
        cur.execute(
            "INSERT INTO lalur_conta_b "
            "  (empresa_id, codigo, descricao, tributo, natureza, cod_pb_rfb, "
            "   competencia_criacao, saldo_inicial) "
            "VALUES (%s::uuid, %s, %s, %s, 'D', %s, %s, 0) "
            "ON CONFLICT (empresa_id, codigo, tributo) DO NOTHING",
            (empresa_id, codigo, desc, tributo, "173" if tributo == "I" else "347", competencia),
        )
        cur.execute(
            "SELECT id FROM lalur_conta_b WHERE empresa_id=%s::uuid AND codigo=%s AND tributo=%s",
            (empresa_id, codigo, tributo),
        )
        return int(cur.fetchone()[0])


def lancar(
    empresa_id: str,
    competencia: str,
    tributo: str,
    tipo: str,
    valor: Decimal | float,
    historico: str,
    *,
    codigo_rfb: str | None = None,
    conta_b_id: int | None = None,
    sinal_parte_b: int | None = None,
    accounting_entry_id: str | None = None,
    documento_ref: str | None = None,
    origem: str = "contador",
) -> int:
    """Grava um lançamento do LALUR. `origem='automatico'` só para o que é aritmética."""
    if tipo not in TIPOS:
        raise ValueError(f"tipo {tipo!r} — use A, E, P ou B")
    if tipo in ("P", "B") and (conta_b_id is None or sinal_parte_b is None):
        raise CompensacaoSemOrigemError(
            f"tipo {tipo!r} exige conta_b_id e sinal_parte_b — compensação sem origem é "
            "compensação de nada, e movimento de Parte B sem sinal não entra no saldo."
        )
    if not (historico or "").strip():
        raise ValueError("histórico é obrigatório — adição sem histórico não se defende")
    v = _q(Decimal(str(valor)))
    if v <= 0:
        raise ValueError(f"valor {v} — sempre positivo; o sinal é o tipo")
    with _tx() as cur:
        _ensure(cur)
        cur.execute(
            "INSERT INTO lalur_lancamento "
            "  (empresa_id, competencia, tributo, tipo, codigo_rfb, valor, conta_b_id, "
            "   sinal_parte_b, historico, accounting_entry_id, documento_ref, origem) "
            "VALUES (%s::uuid,%s,%s,%s,%s,%s,%s,%s,%s,%s::uuid,%s,%s) RETURNING id",
            (
                empresa_id,
                competencia,
                tributo,
                tipo,
                codigo_rfb,
                v,
                conta_b_id,
                sinal_parte_b,
                historico.strip(),
                accounting_entry_id,
                documento_ref,
                origem,
            ),
        )
        return int(cur.fetchone()[0])


def parte_a(empresa_id: str, competencias: list[str], tributo: str) -> dict:
    """Soma das adições e exclusões do período, e se houve alguma decisão registrada."""
    with _tx() as cur:
        _ensure(cur)
        cur.execute(
            "SELECT tipo, coalesce(sum(valor),0), count(*) FROM lalur_lancamento "
            " WHERE empresa_id=%s::uuid AND tributo=%s AND competencia = ANY(%s) "
            "   AND tipo IN ('A','E') GROUP BY tipo",
            (empresa_id, tributo, competencias),
        )
        por_tipo = {t: (Decimal(str(s)), int(n)) for t, s, n in cur.fetchall()}
    adicoes, n_a = por_tipo.get("A", (Decimal("0"), 0))
    exclusoes, n_e = por_tipo.get("E", (Decimal("0"), 0))
    return {
        "adicoes": _q(adicoes),
        "exclusoes": _q(exclusoes),
        "lancamentos": n_a + n_e,
        "fechada": (n_a + n_e) > 0,
    }


# ── A trava dos 30%, como REGRA ──────────────────────────────────────────────


def compensar(
    empresa_id: str,
    competencia_final: str,
    tributo: str,
    lucro_ajustado: Decimal,
    *,
    solicitada: Decimal | float | None = None,
) -> dict:
    """Quanto se pode compensar, e por quê. NÃO grava — decidir é do contribuinte.

    Três regras que não cabem em SQL:

    1. A base dos 30% é o lucro AJUSTADO (razão ± Parte A), nunca o lucro do razão.
    2. O saldo disponível é o da Parte B ATÉ esta competência: prejuízo de T4 não
       compensa imposto de T3.
    3. Compensar é OPÇÃO. Por isso `solicitada` é parâmetro, não coluna — e quando vem
       `None` o retorno é o MÁXIMO possível, rotulado como tal, não uma compensação feita.
    """
    if lucro_ajustado <= 0:
        return {
            "teto_30pct": 0.0,
            "disponivel": 0.0,
            "solicitada": None,
            "compensavel": 0.0,
            "limitador": "sem lucro ajustado — não há o que compensar",
        }
    teto = _q(lucro_ajustado * TRAVA_COMPENSACAO)
    disponivel = saldo_parte_b(empresa_id, tributo, competencia_final)
    cand = [("teto de 30% do lucro ajustado (Lei 9.065/95)", teto), ("saldo da Parte B nesta data", disponivel)]
    if solicitada is not None:
        cand.append(("valor solicitado pelo contribuinte", _q(Decimal(str(solicitada)))))
    limitador, compensavel = min(cand, key=lambda x: x[1])
    return {
        "teto_30pct": float(teto),
        "disponivel": float(disponivel),
        "solicitada": (float(_q(Decimal(str(solicitada)))) if solicitada is not None else None),
        "compensavel": float(max(Decimal("0"), compensavel)),
        "limitador": limitador,
    }


def _ja_registrado(empresa_id: str, competencia: str, tributo: str) -> bool:
    """Já existe M410 automático desta competência e tributo?

    Sem esta pergunta, chamar `apurar_lucro_real(..., registrar_prejuizo=True)` duas vezes
    grava o mesmo prejuízo duas vezes e infla o estoque — e um livro fiscal que conta em
    dobro é pior que livro nenhum, porque o erro só aparece quando a compensação for
    glosada. Não dá para resolver com UNIQUE na tabela: nada impede o contador de lançar
    DOIS ajustes legítimos na mesma competência; o que não pode repetir é o M410
    AUTOMÁTICO, que é derivado e não decidido.
    """
    with _tx() as cur:
        _ensure(cur)
        cur.execute(
            "SELECT 1 FROM lalur_lancamento "
            " WHERE empresa_id=%s::uuid AND competencia=%s AND tributo=%s "
            "   AND tipo='B' AND origem='automatico' LIMIT 1",
            (empresa_id, competencia, tributo),
        )
        return cur.fetchone() is not None


def apurar_lucro_real(
    empresa_id: str,
    ano: int,
    trimestre: int | None = None,
    *,
    compensacao_solicitada: Decimal | float | None = None,
    exigir_parte_a: bool = False,
    registrar_prejuizo: bool = False,
) -> dict:
    """Lucro real do período: razão ± Parte A − compensação, com a trava aplicada.

    `exigir_parte_a=True` LEVANTA quando nenhuma adição/exclusão foi decidida. É a diferença
    entre «este é o lucro real» e «este é o lucro do razão». O segundo é uma estimativa
    honesta; chamá-lo de primeiro é o defeito que este módulo veio apagar.

    `registrar_prejuizo=True` grava o M410 quando o período fecha negativo — e só então.
    Padrão é False porque escrever no livro é ato, não efeito colateral de uma consulta.
    """
    from modules.financial.services.apuracao_lucro_real_service import (  # noqa: PLC0415
        CSLL,
        IRPJ,
        IRPJ_ADICIONAL,
        LIMITE_ADICIONAL_MES,
        ApuracaoLucroRealService,
    )

    base = ApuracaoLucroRealService().apurar(ano, trimestre, empresa_id)
    meses = base["meses"]
    lucro_razao = Decimal(str(base["base"]["lucro_antes_ircsll"]))
    limite = LIMITE_ADICIONAL_MES * len(meses)
    comp_final = meses[-1]

    out: dict = {
        "periodo": base["periodo"],
        "ano": ano,
        "trimestre": trimestre,
        "empresa_id": empresa_id,
        "meses": meses,
        "lucro_do_razao": float(_q(lucro_razao)),
        "por_tributo": {},
    }

    for tributo in ("I", "C"):
        pa = parte_a(empresa_id, meses, tributo)
        if exigir_parte_a and not pa["fechada"]:
            raise ParteANaoFechadaError(
                f"{TRIBUTOS[tributo]}, {base['periodo']}: nenhuma adição ou exclusão foi "
                f"decidida nesta competência. Sem Parte A, «lucro real» é o lucro do razão "
                f"com outro nome — e o razão tem R$ 84.285,15 de provisões e R$ 10.370,40 "
                f"de despesas financeiras que precisam de uma decisão por linha."
            )
        ajustado = lucro_razao + Decimal(str(pa["adicoes"])) - Decimal(str(pa["exclusoes"]))
        comp = compensar(empresa_id, comp_final, tributo, ajustado, solicitada=compensacao_solicitada)
        lucro_real = ajustado - Decimal(str(comp["compensavel"]))

        if tributo == "I":
            tributo_devido = max(Decimal("0"), lucro_real) * IRPJ
            adicional = max(Decimal("0"), lucro_real - limite) * IRPJ_ADICIONAL
        else:
            tributo_devido = max(Decimal("0"), lucro_real) * CSLL
            adicional = Decimal("0")

        if ajustado < 0 and registrar_prejuizo and not _ja_registrado(empresa_id, comp_final, tributo):
            cid = garantir_conta_b(empresa_id, tributo, comp_final)
            lancar(
                empresa_id,
                comp_final,
                tributo,
                "B",
                -ajustado,
                f"M410 — {'prejuízo fiscal' if tributo == 'I' else 'base negativa da CSLL'} "
                f"apurado em {base['periodo']} (lucro do razão {lucro_razao:,.2f}, "
                f"adições {pa['adicoes']:,.2f}, exclusões {pa['exclusoes']:,.2f})",
                conta_b_id=cid,
                sinal_parte_b=1,
                origem="automatico",
            )

        out["por_tributo"][TRIBUTOS[tributo]] = {
            "parte_a": pa,
            "lucro_ajustado": float(_q(ajustado)),
            "compensacao": comp,
            "lucro_real": float(_q(lucro_real)),
            "tributo": float(_q(tributo_devido)),
            "adicional_10": float(_q(adicional)),
            "saldo_parte_b_apos": float(saldo_parte_b(empresa_id, tributo, comp_final)),
        }

    out["parte_a_fechada"] = all(v["parte_a"]["fechada"] for v in out["por_tributo"].values())
    out["observacao"] = (
        "Lucro real = lucro do razão ± Parte A − compensação, com a trava de 30% do art. 15 "
        "e 16 da Lei 9.065/95 sobre o lucro AJUSTADO. Cada trimestre é período fechado: o "
        "prejuízo de um NÃO desfaz o imposto do anterior. "
        + (
            "Parte A FECHADA nesta competência."
            if out["parte_a_fechada"]
            else "Parte A NÃO fechada: nenhuma adição/exclusão decidida, então o ajustado é "
            "igual ao lucro do razão. Isto é estimativa, não a base tributável."
        )
    )
    return out

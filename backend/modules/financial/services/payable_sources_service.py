"""Pagáveis a partir das fontes REAIS de obrigação (NFS-e tomadas, folha, guias).

Por que existe: `payable_auto_service` cria pagável a partir de `nfse_entrada` —
tabela com **0 linhas**. Os 301 documentos de serviço tomado reais vivem em
`nfse_tomadas_nacional` (portal nacional gov.br/ADN). Resultado: a empresa pagava
R$1,2M pelo extrato e o contas-a-pagar tinha 69 registros. Este módulo liga o
contas-a-pagar às fontes que de fato existem.

Paredes:
  • **Nada de vencimento inventado.** NFS-e não traz prazo → vencimento = emissão
    (registrado em `notes`). Guia sem `vencimento` é PULADA, não chutada.
    Folha usa o 5º dia útil do mês seguinte porque isso é LEI (CLT art. 459 §1º),
    não convenção nossa.
  • **Competência futura não vira obrigação** (mesma guarda do razão).
  • **Idempotente** por chave natural: chave de acesso da NFS-e, `code` da folha/guia.
  • **Não move dinheiro.** Registrar a obrigação ≠ pagar. Baixa e pagamento seguem
    nos seus caminhos, com os gates de sempre.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

import psycopg2
import psycopg2.extras

from modules.financial.services.ledger_auto_service import _raw_db_url

logger = logging.getLogger(__name__)

FONTES = ("nfse_tomadas", "folha", "tributos")

# Horizonte do sistema financeiro: o extrato bancário e o razão começam em
# 2026-01. Documento anterior a isso não vira obrigação em aberto — não há como
# conciliar contra extrato que não existe, e um pagável 'pendente' de 2022
# afirmaria uma dívida que não existe. Fora do horizonte = reportado, não criado.
HORIZONTE = date(2026, 1, 1)


def _conn():
    return psycopg2.connect(_raw_db_url())


def _quinto_dia_util(ano: int, mes: int) -> date:
    """5º dia útil do mês (CLT art. 459 §1º — prazo legal do salário).
    Só desconta fim de semana; feriado municipal não muda o mês."""
    d = date(ano, mes, 1)
    uteis = 0
    while True:
        if d.weekday() < 5:
            uteis += 1
            if uteis == 5:
                return d
        d += timedelta(days=1)


def _proxima_competencia(periodo: str) -> tuple[int, int]:
    """'2026-07' → (2026, 8): o salário de julho vence em agosto."""
    ano, mes = int(periodo[:4]), int(periodo[5:7])
    return (ano + 1, 1) if mes == 12 else (ano, mes + 1)


def _condominio_padrao(cur) -> str:
    """Reusa o condominio_id que os pagáveis existentes já usam (coluna NOT NULL,
    herança do multi-tenant antigo). Sem inventar valor novo."""
    cur.execute(
        "SELECT condominio_id::text FROM payable_accounts "
        "GROUP BY 1 ORDER BY count(*) DESC LIMIT 1"
    )
    r = cur.fetchone()
    return r[0] if r else "a1b2c3d4-e5f6-7890-abcd-ef1234567890"


def _limite_competencia() -> tuple[int, int]:
    h = date.today()
    return (h.year, h.month)


# ─────────────────────────────────────────────────────────── fonte 1: NFS-e ──
def _nfse_tomadas(cur, cond_id: str, preview: bool) -> dict:
    """Serviço TOMADO com nota = obrigação com documento fiscal. Idempotente por
    chave de acesso."""
    cur.execute(
        """
        SELECT t.chave_acesso, t.numero, t.data_emissao::date, t.prestador_cnpj,
               t.prestador_nome, t.valor_servicos, t.empresa_id, t.competencia
        FROM nfse_tomadas_nacional t
        WHERE COALESCE(t.valor_servicos, 0) > 0
          AND NOT EXISTS (
              SELECT 1 FROM payable_accounts p WHERE p.nota_fiscal_chave = t.chave_acesso
          )
        ORDER BY t.data_emissao
        """
    )
    linhas = cur.fetchall()
    lim = _limite_competencia()
    criados, valor_total, futuros, antigos = 0, 0.0, 0, 0
    amostra = []
    for chave, numero, emissao, cnpj, nome, valor, empresa_id, _comp in linhas:
        if emissao is None:
            continue
        if emissao < HORIZONTE:
            antigos += 1
            continue
        if (emissao.year, emissao.month) > lim:
            futuros += 1
            continue
        desc = f"NFS-e {numero} - {nome}" if numero else f"NFS-e - {nome}"
        valor_total += float(valor)
        criados += 1
        if len(amostra) < 5:
            amostra.append({"desc": desc[:60], "valor": float(valor), "emissao": emissao.isoformat()})
        if preview:
            continue
        cur.execute(
            """
            INSERT INTO payable_accounts (
                id, condominio_id, description, gross_value, net_value,
                issue_date, due_date, competence_date, status,
                document_type, nota_fiscal_tipo, nota_fiscal_numero, nota_fiscal_chave,
                fornecedor_cnpj, fornecedor_nome, supplier_name,
                origem, notes, empresa_id, created_at, updated_at
            ) VALUES (
                gen_random_uuid(), %s, %s, %s, %s,
                %s, %s, %s, 'pendente',
                'nfse', 'nfse', %s, %s,
                %s, %s, %s,
                'nfse_tomada_nacional',
                'Vencimento = data de emissao: a NFS-e nao traz prazo de pagamento.',
                %s, NOW(), NOW()
            )
            """,
            (cond_id, desc[:250], float(valor), float(valor),
             emissao, emissao, emissao,
             str(numero or "")[:50], chave,
             (cnpj or "")[:20], (nome or "")[:150], (nome or "")[:150],
             empresa_id),
        )
    return {"fonte": "nfse_tomadas", "criados": criados, "valor": round(valor_total, 2),
            "competencia_futura_ignorados": futuros,
            "anteriores_ao_horizonte_ignorados": antigos, "amostra": amostra}


# ──────────────────────────────────────────────────────────── fonte 2: folha ──
def _folha(cur, cond_id: str, preview: bool) -> dict:
    """UMA obrigação por (competência, empresa) — é assim que a folha é devida,
    ainda que liquidada em N PIX. Fecha o circuito com a baixa de folha, que já
    existe e hoje não acha pagável nenhum pra dar baixa."""
    # ARMADILHA: cada competência tem holerite das DUAS fontes para os mesmos
    # funcionários (motor 'conecta' + espelho 'portte'). Somar tudo dobrava a
    # obrigação (junho: 87.736,63 + 73.075,36). Portte é a verdade fiscal e o
    # nosso motor converge nela (julho difere R$28,89) → uma fonte por
    # competência/empresa, Portte na frente.
    cur.execute(
        """
        SELECT reference_period, empresa_id, slug, liquido, qtd, fonte, fechada FROM (
            SELECT h.reference_period, h.empresa_id, e.slug,
                   SUM(h.net_salary)::numeric AS liquido, COUNT(*) AS qtd,
                   h.source_system AS fonte,
                   BOOL_OR(h.status = 'published') AS fechada,
                   ROW_NUMBER() OVER (
                       PARTITION BY h.reference_period, h.empresa_id
                       ORDER BY (h.source_system = 'portte') DESC
                   ) AS prioridade
            FROM hr_payslips h
            LEFT JOIN empresas e ON e.id = h.empresa_id
            WHERE COALESCE(h.net_salary, 0) > 0 AND h.reference_period IS NOT NULL
            GROUP BY 1, 2, 3, h.source_system
        ) t
        WHERE prioridade = 1
        ORDER BY reference_period
        """
    )
    lim = _limite_competencia()
    criados, valor_total, futuros, existentes = 0, 0.0, 0, 0
    amostra = []
    for periodo, empresa_id, slug, liquido, qtd, fonte, fechada in cur.fetchall():
        try:
            ano, mes = int(periodo[:4]), int(periodo[5:7])
        except (ValueError, TypeError):
            continue
        if (ano, mes) > lim:
            futuros += 1
            continue
        # `code` é varchar(30): 'FOLHA-conecta_patrimonial-2026-07' não cabe.
        sigla = (slug or "EMP").replace("conecta_", "")[:6].upper()
        code = f"FOLHA-{sigla}-{periodo}"
        cur.execute("SELECT 1 FROM payable_accounts WHERE code = %s LIMIT 1", (code,))
        if cur.fetchone():
            existentes += 1
            continue
        venc_ano, venc_mes = _proxima_competencia(periodo)
        vencimento = _quinto_dia_util(venc_ano, venc_mes)
        desc = f"Folha {periodo} - {(slug or 'empresa').replace('_', ' ').upper()} ({qtd} colaboradores)"
        # Folha FECHADA na Portte (holerite 'published') = competência processada e
        # paga — o Jordan confirmou que não há folha pendente. Registrá-la como
        # 'pendente' inventaria meio milhão de salário em atraso. Enquanto está só
        # como rascunho do nosso motor, a obrigação é real e ainda em aberto.
        pago = bool(fechada) and fonte == "portte"
        status = "pago" if pago else "pendente"
        base = ("Folha fechada na Portte (holerites 'published') — competência processada e paga."
                if pago else "Folha ainda em rascunho no motor Conecta — obrigação em aberto.")
        valor_total += float(liquido)
        criados += 1
        if len(amostra) < 8:
            amostra.append({"desc": desc[:58], "valor": float(liquido),
                            "vencimento": vencimento.isoformat(), "status": status})
        if preview:
            continue
        cur.execute(
            """
            INSERT INTO payable_accounts (
                id, condominio_id, code, description, gross_value, net_value,
                issue_date, due_date, competence_date, status,
                paid_value, payment_date,
                document_type, origem, notes, empresa_id, created_at, updated_at
            ) VALUES (
                gen_random_uuid(), %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s,
                'folha', 'hr_payslips',
                %s, %s, NOW(), NOW()
            )
            """,
            (cond_id, code, desc[:250], float(liquido), float(liquido),
             date(ano, mes, 1), vencimento, date(ano, mes, 1), status,
             float(liquido) if pago else None, vencimento if pago else None,
             "Vencimento = 5o dia util do mes seguinte (CLT art. 459 §1o). "
             "Liquido somado dos holerites. " + base,
             empresa_id),
        )
    return {"fonte": "folha", "criados": criados, "valor": round(valor_total, 2),
            "ja_existiam": existentes, "competencia_futura_ignorados": futuros,
            "amostra": amostra}


# ───────────────────────────────────────────────────────── fonte 3: tributos ──
def _tributos(cur, cond_id: str, preview: bool) -> dict:
    """Guias FGTS/INSS extraídas do Onvio. SÓ entra guia com `vencimento` real —
    guia sem vencimento é reportada, nunca chutada (data de tributo errada gera
    multa; inventar aqui é pior que não registrar)."""
    criados, valor_total, sem_venc = 0, 0.0, 0
    amostra = []
    for tabela, rotulo in (("fgts_guias", "FGTS"), ("inss_guias", "INSS")):
        cur.execute(
            f"SELECT id::text, mes_ref, valor, vencimento FROM {tabela} "  # noqa: S608 - nome fixo
            "WHERE COALESCE(valor,0) > 0"
        )
        for gid, mes_ref, valor, vencimento in cur.fetchall():
            if vencimento is None:
                sem_venc += 1
                continue
            if vencimento < HORIZONTE:
                continue
            code = f"{rotulo}-{str(mes_ref).replace('.', '-')}-{gid[:8]}"
            cur.execute("SELECT 1 FROM payable_accounts WHERE code = %s LIMIT 1", (code,))
            if cur.fetchone():
                continue
            desc = f"Guia {rotulo} {mes_ref}"
            valor_total += float(valor)
            criados += 1
            if len(amostra) < 5:
                amostra.append({"desc": desc, "valor": float(valor),
                                "vencimento": vencimento.isoformat()})
            if preview:
                continue
            cur.execute(
                """
                INSERT INTO payable_accounts (
                    id, condominio_id, code, description, gross_value, net_value,
                    issue_date, due_date, status, document_type, origem, notes,
                    created_at, updated_at
                ) VALUES (
                    gen_random_uuid(), %s, %s, %s, %s, %s,
                    %s, %s, 'pendente', 'guia', %s,
                    'Guia extraida do Onvio (OCR). Conferir valor antes de pagar.',
                    NOW(), NOW()
                )
                """,
                (cond_id, code, desc[:250], float(valor), float(valor),
                 vencimento, vencimento, f"{tabela}"),
            )
    return {"fonte": "tributos", "criados": criados, "valor": round(valor_total, 2),
            "sem_vencimento_ignorados": sem_venc, "amostra": amostra}


# ────────────────────────────────────────────────────────────────── público ──
def gerar_pagaveis(preview: bool = True, fontes: tuple[str, ...] | None = None) -> dict:
    """Registra como pagável o que a empresa de fato deve. `preview=True` (padrão)
    não escreve nada — só mostra o que faria."""
    alvo = tuple(f for f in (fontes or FONTES) if f in FONTES)
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cond_id = _condominio_padrao(cur)
            saida = []
            if "nfse_tomadas" in alvo:
                saida.append(_nfse_tomadas(cur, cond_id, preview))
            if "folha" in alvo:
                saida.append(_folha(cur, cond_id, preview))
            if "tributos" in alvo:
                saida.append(_tributos(cur, cond_id, preview))
            if preview:
                conn.rollback()
            else:
                conn.commit()
        return {
            "ok": True,
            "modo": "preview" if preview else "aplicado",
            "total_criados": sum(s["criados"] for s in saida),
            "total_valor": round(sum(s["valor"] for s in saida), 2),
            "fontes": saida,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

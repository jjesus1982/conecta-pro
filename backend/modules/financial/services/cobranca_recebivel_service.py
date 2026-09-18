"""Emite a cobrança BANCÁRIA de uma conta a receber que já existe.

Regra do dono (07/09/2026): boleto/PIX nasce no Conecta PRO, não no app do banco — a Eletrônica
cobra pelo Inter (boleto registrado com PIX na mesma emissão) e a Patrimonial pela Cora
(boleto + PIX). O gerador do dia 1 (`gerar_recebiveis`) cria a conta a receber a partir do
contrato; este serviço emite a cobrança para ESSA conta e grava o boleto/PIX nela — nada de
segunda conta paralela (o `recurring_billing_service` criava a própria e ficou sem uso).

Banco pela empresa credora da conta (`receivable_accounts.empresa_id`, que vem do contrato).
Idempotente: conta que já tem `boleto_id`/`pix_txid` não é reemitida. Não envia nada ao cliente —
emitir é registrar a cobrança no banco; comunicar é outro passo. Dinheiro não sai daqui.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import date
from decimal import Decimal

from modules.financial.services.recurring_billing_service import (
    _build_inter_adapter,
    _chamar_cobranca_cora,
    _get_conn,
)

logger = logging.getLogger(__name__)

PATRIMONIAL_ID = "7d79ed12-d480-4906-b2e0-2b2c4d299bab"
_SQL_CONTA = """
    SELECT r.id::text, r.code, r.customer_name, r.customer_document, r.gross_value, r.net_value, r.due_date,
           r.description, r.status::text, r.empresa_id::text, r.boleto_id, r.pix_txid,
           c.email, c.address_street, c.address_number, c.address_neighborhood, c.address_city,
           c.address_state, c.address_zipcode, c.document_number
    FROM receivable_accounts r
    LEFT JOIN clients c ON regexp_replace(coalesce(c.document_number,''), '\\D', '', 'g')
                          = regexp_replace(coalesce(r.customer_document,''), '\\D', '', 'g')
                         AND coalesce(r.customer_document,'') <> ''
    WHERE r.id::text = %s
"""


def _banco_da_conta(empresa_id: str | None) -> str:
    return "cora" if (empresa_id or "") == PATRIMONIAL_ID else "inter"


def _emitir_inter(conta: dict) -> dict:
    """Boleto registrado no Inter (cobrança v3) — devolve boleto_id, linha digitável e PIX copia-e-cola."""

    async def _run():
        adapter = _build_inter_adapter()
        try:
            return await adapter.generate_boleto(
                amount=Decimal(str(conta["valor"])),
                due_date=conta["vencimento"],
                payer_name=conta["nome"],
                payer_document=conta["documento"],
                description=conta["descricao"],
                payer_address=conta.get("rua"),
                payer_number=conta.get("numero"),
                payer_neighborhood=conta.get("bairro"),
                payer_city=conta.get("cidade"),
                payer_state=conta.get("uf"),
                payer_zip=conta.get("cep"),
            )
        finally:
            try:
                await adapter.close()
            except Exception:  # noqa: BLE001
                pass

    try:
        r = asyncio.run(_run())
        return {
            "success": True,
            "banco": "inter",
            "boleto_id": r.get("boleto_id") or "",
            "boleto_digitavel": r.get("digitable_line") or "",
            "boleto_url": r.get("pdf_url") or r.get("url") or "",
            "pix_copy_paste": r.get("pix_qrcode") or "",
            "txid": r.get("boleto_id") or "",
            "bruto": r,
        }
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "banco": "inter", "error": str(exc)[:300]}


def _emitir_por_banco(banco: str, conta: dict, documento: str, venc) -> dict:
    if banco == "cora":
        return _chamar_cobranca_cora(
            conta["code"], conta["valor"], documento, conta["nome"], conta["descricao"], venc.isoformat()
        )
    return _emitir_inter(conta)


def emitir(receivable_id: str, preview: bool = False) -> dict:
    """Emite (ou só mostra, com preview=True) a cobrança bancária de UMA conta a receber."""
    with _get_conn() as conn:  # noqa: SIM117
        with conn.cursor() as cur:
            cur.execute(_SQL_CONTA, (receivable_id,))
            row = cur.fetchone()
    if not row:
        return {"ok": False, "erro": "conta a receber não encontrada"}
    (
        rid,
        code,
        nome,
        doc,
        bruto,
        liquido,
        venc,
        desc,
        status,
        empresa_id,
        boleto_id,
        pix_txid,
        email,
        rua,
        numero,
        bairro,
        cidade,
        uf,
        cep,
        doc_cli,
    ) = row
    banco = _banco_da_conta(empresa_id)
    documento = "".join(ch for ch in (doc or doc_cli or "") if ch.isdigit())
    valor = float(liquido or bruto or 0)
    conta = {
        "id": rid,
        "code": code or f"REC-{rid[:8]}",
        "nome": (nome or "cliente")[:60],
        "documento": documento,
        "valor": round(valor, 2),
        "vencimento": venc,
        "descricao": (desc or "Serviços")[:100],
        "email": email,
        "rua": rua,
        "numero": numero,
        "bairro": bairro,
        "cidade": cidade,
        "uf": uf,
        "cep": cep,
    }
    base = {
        "ok": False,
        "id": rid,
        "cliente": conta["nome"],
        "valor": conta["valor"],
        "vencimento": str(venc),
        "banco": banco,
        "preview": preview,
    }
    if status not in ("pendente", "parcial"):
        return {**base, "erro": f"conta com status {status!r} — só se emite cobrança de conta em aberto"}
    if boleto_id or pix_txid:
        return {**base, "ok": True, "situacao": "ja_emitida", "boleto_id": boleto_id, "pix_txid": pix_txid}
    if not documento or len(documento) not in (11, 14):
        return {**base, "erro": "cliente sem CPF/CNPJ válido na conta e no cadastro"}
    if not venc or venc < date.today():
        return {**base, "erro": f"vencimento {venc} já passou — ajuste a data antes de emitir"}
    if valor < 5.0:
        return {**base, "erro": "valor mínimo de cobrança bancária é R$ 5,00"}
    if preview:
        return {**base, "ok": True, "situacao": "preview", "documento": documento, "email": email}

    with _get_conn() as conn:  # reserva: só um emissor por conta (dois cliques emitiam duas cobranças, 08/09/2026)
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE receivable_accounts SET boleto_id = 'reservando' WHERE id::text = %s "
                "AND boleto_id IS NULL AND pix_txid IS NULL RETURNING id",
                (rid,),
            )
            reservou = cur.fetchone() is not None
        conn.commit()
    if not reservou:
        return {
            **base,
            "ok": True,
            "situacao": "ja_emitida",
            "boleto_id": "em emissão por outra chamada",
            "pix_txid": None,
        }
    try:
        r = _emitir_por_banco(banco, conta, documento, venc)
    except Exception as exc:  # noqa: BLE001
        r = {"success": False, "error": str(exc)}
    if not r.get("success"):
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE receivable_accounts SET boleto_id = NULL WHERE id::text = %s AND boleto_id = 'reservando'",
                    (rid,),
                )
            conn.commit()
        return {**base, "erro": f"{banco}: {r.get('error')}"}
    meta = {
        "banco": banco,
        "emitido_em": date.today().isoformat(),
        "resposta": {k: v for k, v in r.items() if k != "bruto"},
    }
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE receivable_accounts
                   SET boleto_id = %s, boleto_digitable_line = %s, boleto_url = %s, boleto_number = %s,
                       boleto_generated = TRUE, boleto_generated_at = NOW(),
                       pix_txid = %s, pix_copy_paste = %s,
                       pix_generated = (%s <> ''), pix_generated_at = CASE WHEN %s <> '' THEN NOW() ELSE pix_generated_at END,
                       metadata = coalesce(metadata, '{}'::jsonb) || CAST(%s AS jsonb), updated_at = NOW()
                 WHERE id::text = %s
                """,
                (
                    str(r.get("txid") or r.get("boleto_id") or ""),
                    r.get("boleto_digitavel") or "",
                    r.get("boleto_url") or "",
                    str(r.get("boleto_id") or r.get("txid") or ""),
                    str(r.get("txid") or ""),
                    r.get("pix_copy_paste") or "",
                    r.get("pix_copy_paste") or "",
                    r.get("pix_copy_paste") or "",
                    json.dumps({"cobranca": meta}),
                    rid,
                ),
            )
        conn.commit()
    logger.info("cobrança emitida: conta %s · %s · R$ %.2f · %s", rid, banco, valor, r.get("txid"))
    return {
        **base,
        "ok": True,
        "situacao": "emitida",
        "txid": r.get("txid"),
        "boleto_id": r.get("boleto_id"),
        "boleto_digitavel": r.get("boleto_digitavel"),
        "boleto_url": r.get("boleto_url"),
        "pix_copy_paste": (r.get("pix_copy_paste") or "")[:60],
    }


# Nota → conta a receber. DUAS vias, nesta ordem:
#
#   1. VÍNCULO GRAVADO — `metadata->>'nfse_chave'` na conta. Ele existe desde 18/09/2026 e é
#      a via boa: dito uma vez, vale para sempre, e sobrevive a mudança de valor, de
#      vencimento ou de competência.
#   2. PALPITE por empresa + CNPJ + competência (a nota diz "2026-08", a conta diz "08/2026"),
#      desempatado pelo valor mais próximo. É o que existia sozinho até 18/09 e continua como
#      rede: ele acerta 14 de 14 notas de ago/set. Mas é recalculado a cada consulta e não
#      deixa rastro — ninguém, olhando a conta, sabe qual nota a cobre.
#
# O palpite não alcança contrato de VALOR ÚNICO: as parcelas nascem sem `reference_month`
# (elas não têm competência mensal — vencem em datas, não em meses), e a comparação de
# competência nunca casa. O vínculo gravado é o único caminho para elas.
#
# NÃO cria conta: o gerador do dia 1 já cria uma por contrato/mês — nota sem conta é exceção
# que o dono precisa ver, não um buraco para o código tapar inventando vencimento.
_SQL_CONTA_DA_NOTA = """
    SELECT n.numero, n.tomador_nome, n.valor_servicos, n.competencia, coalesce(n.cancelada, FALSE),
           coalesce(
             (SELECT r.id::text FROM receivable_accounts r
               WHERE r.deleted_at IS NULL
                 AND r.metadata->>'nfse_chave' = n.chave_acesso
               LIMIT 1),
             (SELECT r.id::text FROM receivable_accounts r
               WHERE r.deleted_at IS NULL AND r.empresa_id = n.empresa_id
                 AND regexp_replace(coalesce(r.customer_document,''), '\\D', '', 'g')
                     = regexp_replace(coalesce(n.tomador_cnpj,''), '\\D', '', 'g')
                 AND r.reference_month = substr(n.competencia, 6, 2) || '/' || substr(n.competencia, 1, 4)
                 AND r.status::text IN ('pendente', 'parcial')
                 -- Conta já vinculada a OUTRA nota não entra no palpite: ela tem dono.
                 AND coalesce(r.metadata->>'nfse_chave', '') = ''
               ORDER BY abs(r.net_value - n.valor_servicos) LIMIT 1)
           )
    FROM nfse_emitidas_nacional n WHERE n.chave_acesso = %s
"""


#: Conta a receber candidata a uma nota, SEM decidir por ela. Quem chama decide o que fazer
#: com 0, 1 ou várias — porque «várias» é ambiguidade real e adivinhar aqui seria escolher a
#: conta errada em silêncio, que é o defeito que este módulo inteiro existe para evitar.
#:
#: Conta PAGA entra. Vincular é REGISTRO — dizer qual nota cobre qual conta —, não cobrança:
#: medido em 18/09/2026, 12 das 14 notas de ago/set foram recusadas porque a conta delas já
#: estava paga, e o histórico nunca se formaria. A conta em aberto vem primeiro na ordem,
#: porque é a que ainda pode virar boleto.
_SQL_CANDIDATAS = """
    SELECT r.id::text, r.code, r.description, r.net_value, r.due_date, r.status::text,
           coalesce(r.metadata->>'nfse_chave', '') AS ja_vinculada,
           coalesce(r.reference_month, '') AS competencia_da_conta
      FROM receivable_accounts r, nfse_emitidas_nacional n
     WHERE n.chave_acesso = %s
       AND r.deleted_at IS NULL AND r.empresa_id = n.empresa_id
       AND regexp_replace(coalesce(r.customer_document,''), '\\D', '', 'g')
           = regexp_replace(coalesce(n.tomador_cnpj,''), '\\D', '', 'g')
       AND r.status::text IN ('pendente', 'parcial', 'paga')
     ORDER BY (r.status::text IN ('pendente', 'parcial')) DESC,
              abs(r.net_value - n.valor_servicos), r.due_date
"""


def _documento_da_nota(numero: str | None, empresa_id: str | None) -> str:
    """Número da nota QUALIFICADO pela empresa emissora, para `receivable_accounts.document_number`.

    18/09/2026, achado pelo oráculo antes de chegar à produção: o índice
    `ix_receivable_accounts_document` é UNIQUE em `(condominio_id, document_number)`, e todos
    os recebíveis da casa usam o mesmo `condominio_id` — na prática o número é único no
    sistema inteiro. Só que a numeração de NFS-e é POR EMPRESA: medido, os números 10, 11, 12,
    14 e 15 existem duas vezes, uma na Eletrônica e outra na Patrimonial. Gravar o número
    puro faria a segunda nota legítima estourar `duplicate key`.

    `121-PATR` / `121-ELET` é único por construção (uma empresa não repete o próprio número)
    e continua legível para quem abre a conta na tela.
    """
    sufixo = "PATR" if (empresa_id or "") == PATRIMONIAL_ID else "ELET"
    return f"{str(numero or '').strip()}-{sufixo}"[:50]


def vincular_nota(chave_acesso: str, receivable_id: str | None = None, preview: bool = False) -> dict:
    """Grava na conta a receber QUAL nota a cobre — o vínculo que faltava.

    Sem `receivable_id`, procura a candidata do mesmo tomador e mesma empresa em aberto.
    **Recusa quando há mais de uma** em vez de escolher a mais parecida: ligar a nota à conta
    errada é pior que não ligar — some do lugar certo e aparece no errado, e ninguém vê.

    Idempotente: a mesma nota na mesma conta devolve `ja_vinculada` sem escrever. Uma conta
    só pode ter uma nota; uma nota já usada noutra conta é recusada.
    """
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT numero, tomador_nome, valor_servicos, competencia, coalesce(cancelada, FALSE), "
                "       empresa_id::text "
                "FROM nfse_emitidas_nacional WHERE chave_acesso = %s",
                (chave_acesso,),
            )
            n = cur.fetchone()
            if not n:
                return {"ok": False, "erro": "NFS-e não encontrada"}
            numero, tomador, valor_nota, comp, cancelada, emp_nota = n
            base = {"nota": numero, "tomador": tomador, "competencia": comp, "valor_nota": float(valor_nota or 0)}
            if cancelada:
                return {**base, "ok": False, "erro": f"NFS-e {numero} está cancelada"}

            # A nota já está gravada nalguma conta?
            cur.execute(
                "SELECT id::text, code FROM receivable_accounts "
                "WHERE deleted_at IS NULL AND metadata->>'nfse_chave' = %s LIMIT 1",
                (chave_acesso,),
            )
            usada = cur.fetchone()

            if receivable_id:
                if usada and usada[0] != receivable_id:
                    return {**base, "ok": False, "erro": f"esta nota já está vinculada à conta {usada[1]}"}
                cur.execute(
                    "SELECT id::text, code, coalesce(metadata->>'nfse_chave','') "
                    "FROM receivable_accounts WHERE id::text = %s AND deleted_at IS NULL",
                    (receivable_id,),
                )
                alvo = cur.fetchone()
                if not alvo:
                    return {**base, "ok": False, "erro": "conta a receber não encontrada"}
                if alvo[2] and alvo[2] != chave_acesso:
                    return {**base, "ok": False, "erro": f"a conta {alvo[1]} já está vinculada a OUTRA nota"}
                escolhida = (alvo[0], alvo[1])
            else:
                if usada:
                    return {**base, "ok": True, "situacao": "ja_vinculada", "conta": usada[1]}
                cur.execute(_SQL_CANDIDATAS, (chave_acesso,))
                todas = cur.fetchall()
                # Competência da nota na forma da conta: a nota diz "2026-08", a conta "08/2026".
                comp_conta = f"{comp[5:7]}/{comp[0:4]}" if comp and len(comp) >= 7 else ""
                # Conta SEM competência é parcela de valor único (vence em data, não em mês) —
                # ela serve a qualquer nota do contrato, e é o caso que este vínculo resolve.
                da_competencia = [c for c in todas if not c[7] or c[7] == comp_conta]
                livres = [c for c in da_competencia if not c[6]]

                # LIMITE CONHECIDO: uma conta, uma nota. A realidade tem N:1 — medido em
                # 18/09/2026, o CONDOMINIO PRIME ARENA tem DUAS notas de 08/2026
                # (R$ 29.600,00 + R$ 3.879,60) que somam EXATAMENTE a única conta do mês,
                # R$ 33.479,60. A primeira vincula; a segunda cai aqui. Dizer isso de frente
                # importa: a mensagem de competência era verdadeira e enganosa — culpava o mês
                # quando o motivo era a conta da competência CERTA já ter dona.
                if da_competencia and not livres:
                    return {
                        **base,
                        "ok": False,
                        "situacao": "conta_ja_tem_nota",
                        "erro": (
                            f"a conta de {tomador} em {comp_conta} já tem nota. Se esta nota cobre a "
                            f"MESMA conta que a outra (duas notas somando uma conta), o sistema ainda "
                            f"não sabe registrar isso — me avise"
                        ),
                    }
                # Competência incompatível NÃO é escolhida sozinha: sem esta parede, uma nota
                # de julho grudaria na conta de setembro que estivesse aberta — em silêncio, e
                # a de julho ficaria sem nota para sempre.
                outras = [c for c in todas if not c[6] and c not in da_competencia]
                if not livres and outras:
                    return {
                        **base,
                        "ok": False,
                        "erro": (
                            f"a(s) conta(s) livre(s) de {tomador} são de outra competência "
                            f"({', '.join(sorted({c[7] for c in outras if c[7]}))}) e esta nota é de "
                            f"{comp_conta} — diga qual passando `receivable_id` se for mesmo essa"
                        ),
                    }
                if not livres:
                    return {
                        **base,
                        "ok": False,
                        "erro": (
                            f"nenhuma conta a receber de {tomador} sem nota — "
                            f"confira em Financeiro › Contas a receber (todas já têm nota, ou não há conta dele)"
                        ),
                    }
                if len(livres) > 1:
                    return {
                        **base,
                        "ok": False,
                        "situacao": "ambiguo",
                        "erro": (
                            f"{len(livres)} contas em aberto de {tomador} — diga qual passando "
                            f"`receivable_id`, que eu não escolho por você"
                        ),
                        "candidatas": [
                            {
                                "id": c[0],
                                "code": c[1],
                                "descricao": (c[2] or "")[:70],
                                "valor": float(c[3] or 0),
                                "vencimento": str(c[4]),
                            }
                            for c in livres
                        ],
                    }
                escolhida = (livres[0][0], livres[0][1])

            if usada and usada[0] == escolhida[0]:
                return {**base, "ok": True, "situacao": "ja_vinculada", "conta": escolhida[1]}
            if preview:
                return {**base, "ok": True, "situacao": "preview", "conta": escolhida[1]}

            cur.execute(
                """
                UPDATE receivable_accounts
                   SET document_number = %s,
                       metadata = coalesce(metadata, '{}'::jsonb) || CAST(%s AS jsonb),
                       updated_at = NOW()
                 WHERE id::text = %s
                """,
                (
                    _documento_da_nota(numero, emp_nota),
                    json.dumps(
                        {
                            "nfse_chave": chave_acesso,
                            "nfse_numero": str(numero or ""),
                            "nfse_competencia": comp,
                            "nfse_valor": float(valor_nota or 0),
                        }
                    ),
                    escolhida[0],
                ),
            )
        conn.commit()
    logger.info("nota %s vinculada à conta %s (%s)", numero, escolhida[1], chave_acesso)
    return {**base, "ok": True, "situacao": "vinculada", "conta": escolhida[1], "receivable_id": escolhida[0]}


def emitir_por_nota(chave_acesso: str, preview: bool = False) -> dict:
    """Fluxo natural nota → boleto: emite a cobrança da conta a receber que corresponde à NFS-e."""
    with _get_conn() as conn:  # noqa: SIM117
        with conn.cursor() as cur:
            cur.execute(_SQL_CONTA_DA_NOTA, (chave_acesso,))
            row = cur.fetchone()
    if not row:
        return {"ok": False, "erro": "NFS-e não encontrada"}
    numero, tomador, valor, comp, cancelada, rid = row
    nota = {"nota": numero, "tomador": tomador, "valor_nota": float(valor or 0), "competencia": comp}
    if cancelada:
        return {**nota, "ok": False, "erro": f"NFS-e {numero} está cancelada"}
    if not rid:
        return {
            **nota,
            "ok": False,
            "erro": (
                f"nenhuma conta a receber EM ABERTO de {tomador} na competência "
                f"{comp} — confira em Financeiro › Contas a receber (pode já estar paga)"
            ),
        }
    return {**nota, **emitir(rid, preview)}


def emitir_pendentes_mes(ano: int, mes: int, preview: bool = True) -> dict:
    """Todas as contas a receber em aberto do mês (origem contrato) ainda sem cobrança bancária."""
    with _get_conn() as conn:  # noqa: SIM117
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id::text FROM receivable_accounts WHERE status IN ('pendente','parcial') "
                "AND boleto_id IS NULL AND pix_txid IS NULL AND due_date >= current_date "
                "AND extract(year from due_date) = %s AND extract(month from due_date) = %s "
                "ORDER BY due_date, customer_name",
                (ano, mes),
            )
            ids = [r[0] for r in cur.fetchall()]
    itens = [emitir(i, preview=preview) for i in ids]
    return {
        "ano": ano,
        "mes": mes,
        "preview": preview,
        "total": len(itens),
        "emitidas": sum(1 for i in itens if i.get("situacao") == "emitida"),
        "erros": [i for i in itens if i.get("erro")],
        "itens": itens,
    }

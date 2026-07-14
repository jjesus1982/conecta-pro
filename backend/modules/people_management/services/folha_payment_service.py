"""
Folha Payment Service — Pagamento de Salários via PIX Inter
Processa pagamento de salários líquidos para até 51 funcionários
via PIX usando a API do Banco Inter (mTLS OAuth2).

Colunas reais usadas:
  employees:         id, nome, cpf, pix_key, pix_key_type, status
  hr_payslips:       id, employee_id, reference_month, reference_year,
                     net_salary, status
  payroll_payments:  tabela de histórico (criada em PASSO 2)
"""

import logging
import os
import uuid
from datetime import datetime
from decimal import Decimal

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "").replace("+asyncpg", "")

INTER_CLIENT_ID = os.getenv("INTER_CLIENT_ID", "")
INTER_CLIENT_SECRET = os.getenv("INTER_CLIENT_SECRET", "")
INTER_CERT_PATH = os.getenv("INTER_CERT_PATH", "/app/credentials/inter/Inter_API_Certificado.crt")
INTER_KEY_PATH = os.getenv("INTER_KEY_PATH", "/app/credentials/inter/Inter_API_Chave.key")
INTER_ENV = os.getenv("INTER_ENVIRONMENT", "production")


def _get_conn():
    return psycopg2.connect(DATABASE_URL)


def _build_inter_adapter():
    """Constrói InterAdapter com credenciais reais do .env."""
    from modules.integrations.banking.adapters.base import BankCredentials
    from modules.integrations.banking.adapters.inter import InterAdapter

    creds = BankCredentials(
        client_id=INTER_CLIENT_ID,
        client_secret=INTER_CLIENT_SECRET,
        certificate_path=INTER_CERT_PATH if os.path.exists(INTER_CERT_PATH) else None,
        private_key_path=INTER_KEY_PATH if os.path.exists(INTER_KEY_PATH) else None,
        environment=INTER_ENV,
    )
    return InterAdapter(creds)


def preparar_lote_folha(mes: int, ano: int) -> dict:
    """
    Prepara lote de pagamentos para todos os funcionários
    com holerite publicado no período.

    TRANSPARÊNCIA (nunca exclusão silenciosa): lê TODOS os holerites do período,
    classifica em PAGÁVEIS (status ativo + chave PIX + líquido > 0) e EXCLUÍDOS,
    e para cada excluído registra o MOTIVO (afastado/demitido/suspenso, sem chave
    PIX, líquido zero). O total do lote + o total dos excluídos reconcilia com o
    total integral da folha do período.

    Retorna:
      funcionarios       — pagáveis (compat. legado: lista com PIX/nome/líquido)
      excluidos          — [{nome, cpf, valor_liquido, motivo, status, tem_pix}]
      total_valor        — soma dos pagáveis
      total_excluidos    — soma dos excluídos
      total_folha        — soma integral do período (lote + excluídos)
    """
    conn = _get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        # Lê TODOS os holerites do período (sem filtrar por status na query),
        # para poder mostrar e explicar cada exclusão.
        cur.execute(
            """
            SELECT
                e.id::text  AS employee_id,
                e.nome,
                e.cpf,
                e.pix_key,
                e.pix_key_type,
                e.status    AS employee_status,
                p.id::text  AS payslip_id,
                p.net_salary AS valor_liquido,
                p.status    AS payslip_status
            FROM hr_payslips p
            JOIN employees e ON e.id = p.employee_id
            WHERE p.reference_month = %s
              AND p.reference_year  = %s
            ORDER BY e.nome
            """,
            (mes, ano),
        )
        todos = [dict(r) for r in cur.fetchall()]

        pagaveis: list[dict] = []
        excluidos: list[dict] = []

        for f in todos:
            liquido = float(f.get("valor_liquido") or 0)
            status_emp = (f.get("employee_status") or "").strip().lower()
            tem_pix = bool(f.get("pix_key"))

            motivos: list[str] = []
            if status_emp and status_emp != "ativo":
                # afastado_inss, demitido, suspenso, etc. → rótulo legível
                rotulo = {
                    "afastado_inss": "Afastado (INSS)",
                    "demitido": "Demitido",
                    "suspenso": "Suspenso",
                    "ferias": "Em férias",
                    "afastado": "Afastado",
                }.get(status_emp, f"Status: {status_emp}")
                motivos.append(rotulo)
            if not tem_pix:
                motivos.append("Sem chave PIX cadastrada")
            if liquido <= 0:
                motivos.append("Líquido zero")

            if motivos:
                excluidos.append(
                    {
                        "employee_id": f["employee_id"],
                        "nome": f["nome"],
                        "cpf": f.get("cpf"),
                        "valor_liquido": round(liquido, 2),
                        "employee_status": status_emp,
                        "tem_pix": tem_pix,
                        "motivo": " · ".join(motivos),
                        "motivos": motivos,
                    }
                )
            else:
                pagaveis.append(f)

        total_lote = sum(float(f["valor_liquido"] or 0) for f in pagaveis)
        total_excluidos = sum(e["valor_liquido"] for e in excluidos)
        total_folha = round(total_lote + total_excluidos, 2)

        # Compat legado: sem_chave_pix (lista de nomes) permanece disponível.
        sem_pix = [e["nome"] for e in excluidos if not e["tem_pix"]]

        return {
            "mes": mes,
            "ano": ano,
            "total_funcionarios": len(pagaveis),
            "total_valor": round(total_lote, 2),
            "sem_chave_pix": sem_pix,
            "prontos_para_pagar": len(pagaveis),
            "funcionarios": pagaveis,
            # ── Transparência: quem NÃO entra no lote e por quê ──
            "excluidos": excluidos,
            "total_excluidos_qtd": len(excluidos),
            "total_excluidos_valor": round(total_excluidos, 2),
            # ── Reconciliação: lote + excluídos = folha integral do período ──
            "total_folha_qtd": len(todos),
            "total_folha_valor": total_folha,
            "reconcilia": abs((round(total_lote, 2) + round(total_excluidos, 2)) - total_folha) < 0.01,
        }
    finally:
        cur.close()
        conn.close()


async def pagar_funcionario_pix(
    employee_id: str,
    payslip_id: str,
    pix_key: str,
    valor: float,
    mes: int,
    ano: int,
    nome: str,
) -> dict:
    """
    Envia PIX para um funcionário via InterAdapter async.
    Registra resultado em payroll_payments.
    """
    conn = _get_conn()
    cur = conn.cursor()

    # Verificar se já pago neste período
    cur.execute(
        "SELECT id, status FROM payroll_payments WHERE employee_id = %s AND mes = %s AND ano = %s",
        (employee_id, mes, ano),
    )
    existing = cur.fetchone()
    if existing and existing[1] == "pago":
        conn.close()
        return {
            "employee_id": employee_id,
            "nome": nome,
            "valor": valor,
            "status": "ja_pago",
            "payment_id": str(existing[0]),
        }

    try:
        # Registrar/assumir como 'processando' de forma IDEMPOTENTE pela chave real
        # (employee_id, mes, ano). Se já existe linha do período (ex.: pendente_pagamento),
        # assume-a e usa o id REAL — nunca gera uuid órfão que deixaria o UPDATE final
        # sem efeito (bug de pagar-em-dobro). A cláusula WHERE evita corrida: se a linha
        # já está 'pago'/'processando', NADA é retornado e o envio do PIX é pulado.
        cur.execute(
            """
            INSERT INTO payroll_payments (
                id, employee_id, payslip_id, mes, ano,
                valor_liquido, metodo, pix_key, status,
                created_at, updated_at
            ) VALUES (%s,%s,%s,%s,%s,%s,'PIX',%s,'processando',NOW(),NOW())
            ON CONFLICT (employee_id, mes, ano) DO UPDATE
                SET status='processando', updated_at=NOW()
                WHERE payroll_payments.status NOT IN ('pago','processando')
            RETURNING id
            """,
            (str(uuid.uuid4()), employee_id, payslip_id, mes, ano, valor, pix_key),
        )
        row_pid = cur.fetchone()
        conn.commit()
        if not row_pid:
            # já 'pago' ou 'processando' (outra execução) → NÃO reenvia PIX (idempotência)
            conn.close()
            return {
                "employee_id": employee_id,
                "nome": nome,
                "valor": valor,
                "status": "ja_processado",
                "obs": "Já pago ou em processamento para o período — envio ignorado (idempotência).",
            }
        payment_id = str(row_pid[0])

        # Enviar PIX via Inter
        adapter = _build_inter_adapter()
        try:
            resp = await adapter.initiate_pix(
                pix_key=pix_key,
                amount=Decimal(str(round(valor, 2))),
                description=f"Salario {mes:02d}/{ano} - {nome[:30]}",
            )
            success = resp.status.value in ("CONCLUIDO", "PROCESSANDO")
            e2e_id = resp.authentication_code or resp.payment_id or ""
            erro_msg = None
        except Exception as exc:
            success = False
            e2e_id = ""
            erro_msg = str(exc)[:500]
        finally:
            await adapter.close()

        status = "pago" if success else "erro"

        cur.execute(
            """
            UPDATE payroll_payments SET
                status = %s,
                pix_e2e_id = %s,
                data_pagamento = %s,
                comprovante_id = %s,
                erro_msg = %s,
                updated_at = NOW()
            WHERE id = %s
            """,
            (status, e2e_id, datetime.now() if success else None, e2e_id, erro_msg, payment_id),
        )

        # Atualizar payslip para paid se pagou
        if success and payslip_id:
            cur.execute(
                "UPDATE hr_payslips SET status='paid', updated_at=NOW() WHERE id = %s",
                (payslip_id,),
            )

        conn.commit()
        return {
            "employee_id": employee_id,
            "nome": nome,
            "valor": valor,
            "pix_key": pix_key,
            "status": status,
            "e2e_id": e2e_id,
            "erro": erro_msg,
        }

    except Exception as exc:
        conn.rollback()
        logger.error("Erro pagar %s: %s", nome, exc)
        return {
            "employee_id": employee_id,
            "nome": nome,
            "valor": valor,
            "status": "erro",
            "erro": str(exc)[:500],
        }
    finally:
        cur.close()
        conn.close()


async def processar_folha_completa(mes: int, ano: int, apenas_preview: bool = False) -> dict:
    """
    Processa pagamento de toda a folha do período via PIX Inter.
    apenas_preview=True: simula sem enviar PIX.
    """
    lote = preparar_lote_folha(mes, ano)

    if apenas_preview:
        return {**lote, "modo": "preview", "aviso": "Nenhum pagamento realizado"}

    if not lote["funcionarios"]:
        return {"erro": f"Sem holerites publicados para {mes:02d}/{ano}"}

    resultados = []
    pagos = 0
    erros = 0
    total_pago = 0.0

    for func in lote["funcionarios"]:
        if not func.get("pix_key"):
            resultados.append(
                {
                    "employee_id": func["employee_id"],
                    "nome": func["nome"],
                    "status": "sem_pix",
                    "erro": "Chave PIX não cadastrada",
                }
            )
            erros += 1
            continue

        resultado = await pagar_funcionario_pix(
            employee_id=func["employee_id"],
            payslip_id=func["payslip_id"] or "",
            pix_key=func["pix_key"],
            valor=float(func["valor_liquido"] or 0),
            mes=mes,
            ano=ano,
            nome=func["nome"],
        )
        resultados.append(resultado)
        if resultado["status"] in ("pago", "ja_pago"):
            pagos += 1
            total_pago += float(func["valor_liquido"] or 0)
        else:
            erros += 1

    return {
        "mes": mes,
        "ano": ano,
        "total_funcionarios": len(resultados),
        "pagos": pagos,
        "erros": erros,
        "total_pago": round(total_pago, 2),
        "taxa_sucesso_pct": round(pagos / max(1, len(resultados)) * 100, 1),
        "resultados": resultados,
    }


def registrar_lote_pendente(mes: int, ano: int) -> dict:
    """
    Registra folha como pendente_pagamento sem executar PIX real.
    Monta payload PIX por funcionário e salva como 'pendente_pagamento'
    para aprovação manual — conforme instrução: NÃO executar PIX real.
    """
    lote = preparar_lote_folha(mes, ano)

    if not lote["funcionarios"]:
        return {
            "mes": mes,
            "ano": ano,
            "total_funcionarios": 0,
            "registrados_pendente": 0,
            "erros": 0,
            "total_valor": 0.0,
            "status": "pendente_pagamento",
            "aviso": f"Sem holerites publicados para {mes:02d}/{ano}",
        }

    conn = _get_conn()
    cur = conn.cursor()
    registrados = 0
    erros_list = []

    try:
        for func in lote["funcionarios"]:
            if not func.get("pix_key"):
                erros_list.append({"nome": func["nome"], "erro": "Sem chave PIX cadastrada"})
                continue

            payment_id = str(uuid.uuid4())
            try:
                cur.execute(
                    """
                    INSERT INTO payroll_payments (
                        id, employee_id, payslip_id, mes, ano,
                        valor_liquido, metodo, pix_key, status,
                        created_at, updated_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,'PIX',%s,'pendente_pagamento',NOW(),NOW())
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        payment_id,
                        func["employee_id"],
                        func.get("payslip_id") or "",
                        mes,
                        ano,
                        float(func["valor_liquido"] or 0),
                        func["pix_key"],
                    ),
                )
                registrados += 1
            except Exception as exc:
                erros_list.append({"nome": func["nome"], "erro": str(exc)[:200]})

        conn.commit()
    finally:
        cur.close()
        conn.close()

    return {
        "mes": mes,
        "ano": ano,
        "total_funcionarios": len(lote["funcionarios"]),
        "registrados_pendente": registrados,
        "erros": len(erros_list),
        "total_valor": lote["total_valor"],
        "status": "pendente_pagamento",
        "aviso": (
            f"{registrados} pagamentos registrados como pendente_pagamento"
            " — aguardando aprovação manual. Nenhum PIX real executado."
        ),
        "detalhes_erros": erros_list,
    }


def status_pagamentos_folha(mes: int, ano: int) -> dict:
    """Retorna status dos pagamentos de folha do período."""
    conn = _get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            """
            SELECT
                pp.status,
                COUNT(*) AS qtd,
                SUM(pp.valor_liquido) AS total
            FROM payroll_payments pp
            WHERE pp.mes = %s AND pp.ano = %s
            GROUP BY pp.status
            """,
            (mes, ano),
        )
        rows = [dict(r) for r in cur.fetchall()]

        cur.execute(
            """
            SELECT
                pp.*, e.nome
            FROM payroll_payments pp
            JOIN employees e ON e.id = pp.employee_id
            WHERE pp.mes = %s AND pp.ano = %s
            ORDER BY pp.status, e.nome
            """,
            (mes, ano),
        )
        detalhes = []
        for r in cur.fetchall():
            d = dict(r)
            # serialize datetime/uuid
            for k, v in d.items():
                if hasattr(v, "isoformat"):
                    d[k] = v.isoformat()
                elif hasattr(v, "hex"):
                    d[k] = str(v)
            detalhes.append(d)

        return {
            "mes": mes,
            "ano": ano,
            "resumo": {r["status"]: {"qtd": r["qtd"], "total": float(r["total"] or 0)} for r in rows},
            "total_registros": len(detalhes),
            "detalhes": detalhes,
        }
    finally:
        cur.close()
        conn.close()

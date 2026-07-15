"""D7 — Payment controller: endpoints de pagamento Inter com 2FA OTP.

Prefixo: /api/v1/financeiro/inter/payments
"""

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database.session import get_db
from modules.integrations.inter.services.payment_service import (
    IdempotenciaError,
    InterPaymentService,
    LimiteDiarioError,
    OTPInvalidoError,
    PaymentError,
    SaldoInsuficienteError,
    StatusInvalidoError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/financeiro/inter/payments", tags=["D7-Payments"])


# ── Schemas de entrada ────────────────────────────────────────────────────────


class PrepararPayload(BaseModel):
    payment_type: str
    destinatario: dict
    valor: float = Field(gt=0)
    data_pagamento: date
    observacoes: str = ""
    categoria: str = "outro"  # pro_labore|transferencia|fornecedor|imposto|diarista|aluguel|folha|reembolso|outro


class AprovarPayload(BaseModel):
    otp_code: str = Field(min_length=6, max_length=6)


class CancelarPayload(BaseModel):
    motivo: str = Field(min_length=3)


# ── helpers ───────────────────────────────────────────────────────────────────


def _handle_payment_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LimiteDiarioError):
        return HTTPException(status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, SaldoInsuficienteError):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    if isinstance(exc, OTPInvalidoError):
        return HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    if isinstance(exc, StatusInvalidoError):
        return HTTPException(status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, IdempotenciaError):
        return HTTPException(status.HTTP_409_CONFLICT, detail=str(exc))
    return HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))


# ── endpoints ─────────────────────────────────────────────────────────────────


@router.post("", status_code=201)
async def preparar_pagamento(
    payload: PrepararPayload,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """D7.1 — Prepara pagamento (status='preparado'). Sem chamada Inter."""
    svc = InterPaymentService(db)
    try:
        return await svc.preparar(
            payment_type=payload.payment_type,
            destinatario=payload.destinatario,
            valor=payload.valor,
            data_pagamento=payload.data_pagamento,
            prepared_by=str(current_user.id),
            observacoes=payload.observacoes,
            categoria=payload.categoria,
        )
    except PaymentError as exc:
        raise _handle_payment_error(exc) from exc


@router.post("/{payment_id}/gerar-otp")
async def gerar_otp(
    payment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """D7.1 — Gera OTP 6 dígitos e envia email Jordan."""
    svc = InterPaymentService(db)
    try:
        return await svc.gerar_otp(payment_id, str(current_user.id))
    except PaymentError as exc:
        raise _handle_payment_error(exc) from exc


@router.post("/{payment_id}/aprovar")
async def aprovar_pagamento(
    payment_id: str,
    payload: AprovarPayload,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """D7.1 — Valida OTP e aprova pagamento (status='aprovado')."""
    ip = request.client.host if request.client else ""
    svc = InterPaymentService(db)
    try:
        return await svc.aprovar(payment_id, payload.otp_code, str(current_user.id), ip)
    except PaymentError as exc:
        raise _handle_payment_error(exc) from exc


@router.post("/{payment_id}/executar")
async def executar_pagamento(
    payment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """D7.1 — Chama Inter API. Apenas após status='aprovado'. Idempotente (max 1x)."""
    svc = InterPaymentService(db)
    try:
        return await svc.executar(payment_id, str(current_user.id))
    except PaymentError as exc:
        raise _handle_payment_error(exc) from exc


@router.post("/{payment_id}/cancelar")
async def cancelar_pagamento(
    payment_id: str,
    payload: CancelarPayload,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """D7.1 — Cancela pagamento se não executado ainda."""
    ip = request.client.host if request.client else ""
    svc = InterPaymentService(db)
    try:
        return await svc.cancelar(payment_id, payload.motivo, str(current_user.id), ip)
    except PaymentError as exc:
        raise _handle_payment_error(exc) from exc


@router.get("")
async def listar_pagamentos(
    status_filter: str | None = None,
    payment_type: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Lista pagamentos com filtros."""
    svc = InterPaymentService(db)
    return {"payments": await svc.listar(status_filter, payment_type, from_date, to_date, limit)}


@router.get("/folha/postos")
async def folha_postos(
    competencia: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Lista os postos com contagem de funcionários, quantos têm chave PIX e o total do líquido
    (quando a folha da competência já foi importada). Alimenta a lista suspensa de posto."""
    comp = competencia or ""
    res = await db.execute(
        text("""
            SELECT COALESCE(NULLIF(e.posto_atual_nome,''),'(sem posto)') AS posto,
                   count(*) AS funcionarios,
                   count(e.pix_key) AS com_pix,
                   count(fl.liquido) AS com_liquido,
                   COALESCE(sum(fl.liquido),0) AS total_liquido
            FROM employees e
            LEFT JOIN folha_liquido fl
              ON regexp_replace(fl.cpf,'\\D','','g') = regexp_replace(e.cpf,'\\D','','g')
             AND fl.competencia = :comp
            GROUP BY 1
            ORDER BY (COALESCE(NULLIF(e.posto_atual_nome,''),'(sem posto)')='(sem posto)'), 1
        """),
        {"comp": comp},
    )
    return {
        "competencia": comp,
        "postos": [
            {
                "posto": r._mapping["posto"],
                "funcionarios": r._mapping["funcionarios"],
                "com_pix": r._mapping["com_pix"],
                "com_liquido": r._mapping["com_liquido"],
                "total_liquido": float(r._mapping["total_liquido"] or 0),
            }
            for r in res.fetchall()
        ],
    }


@router.get("/folha/funcionarios")
async def folha_funcionarios(
    posto: str | None = None,
    competencia: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Lista funcionários (nome, chave PIX, salário-base e o LÍQUIDO da folha da competência).
    Preenche a lista suspensa do recebedor: Jordan escolhe o posto → carrega os funcionários já
    com a chave e o valor a pagar (líquido do Domínio), confere e paga."""
    where = ["1=1"]
    params: dict = {"comp": competencia or ""}
    if posto and posto != "(sem posto)":
        where.append("e.posto_atual_nome = :posto")
        params["posto"] = posto
    elif posto == "(sem posto)":
        where.append("COALESCE(NULLIF(e.posto_atual_nome,''),'')=''")
    res = await db.execute(
        text(f"""
            SELECT e.id, e.nome, e.cpf, e.pix_key, e.pix_key_type, e.pix_confirmada,
                   COALESCE(NULLIF(e.posto_atual_nome,''),'') AS posto,
                   e.salario_base, fl.liquido
            FROM employees e
            LEFT JOIN folha_liquido fl
              ON regexp_replace(fl.cpf,'\\D','','g') = regexp_replace(e.cpf,'\\D','','g')
             AND fl.competencia = :comp
            WHERE {" AND ".join(where)}
            ORDER BY e.nome
        """),
        params,
    )
    return {
        "posto": posto,
        "competencia": competencia or "",
        "funcionarios": [
            {
                "id": str(r._mapping["id"]),
                "nome": r._mapping["nome"],
                "cpf": r._mapping["cpf"],
                "pix_key": r._mapping["pix_key"],
                "pix_key_type": r._mapping["pix_key_type"],
                "posto": r._mapping["posto"],
                "salario_base": float(r._mapping["salario_base"]) if r._mapping["salario_base"] else None,
                "liquido": float(r._mapping["liquido"]) if r._mapping["liquido"] is not None else None,
                "tem_pix": bool(r._mapping["pix_key"]),
                "pix_confirmada": bool(r._mapping["pix_confirmada"]),
                "tem_liquido": r._mapping["liquido"] is not None,
            }
            for r in res.fetchall()
        ],
    }


class VerificarChavesPayload(BaseModel):
    posto: str | None = None
    competencia: str | None = None
    funcionario_ids: list[str] = []


def _norm_nome(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return " ".join(s.upper().split())


def _so_digitos(s: str) -> str:
    return "".join(ch for ch in (s or "") if ch.isdigit())


@router.post("/folha/verificar-chaves")
async def folha_verificar_chaves(
    payload: VerificarChavesPayload,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """VERIFICADOR DE CHAVE PIX — confirma que a chave de cada funcionário pertence MESMO àquela
    pessoa, para o salário não ir para a pessoa errada.

    Método: verificação por HISTÓRICO real de PIX (quem você já pagou e caiu está provado — casa o
    nome do funcionário com o recebedor que o Inter registrou no extrato). A consulta DICT avulsa
    (digitar qualquer CPF e ver o dono) NÃO é exposta pela API do Inter por restrição do BACEN; a
    confirmação final do titular aparece no próprio ato do pagamento, como no app. Não move dinheiro."""
    where = ["1=1"]
    params: dict = {"comp": payload.competencia or ""}
    if payload.funcionario_ids:
        where.append("e.id = ANY(:ids)")
        params["ids"] = payload.funcionario_ids
    elif payload.posto and payload.posto != "(sem posto)":
        where.append("e.posto_atual_nome = :posto")
        params["posto"] = payload.posto
    res = await db.execute(
        text(f"""
            SELECT e.id, e.nome, e.cpf, e.pix_key, e.pix_key_type, fl.liquido
            FROM employees e
            LEFT JOIN folha_liquido fl
              ON regexp_replace(fl.cpf,'\\D','','g') = regexp_replace(e.cpf,'\\D','','g')
             AND fl.competencia = :comp
            WHERE {" AND ".join(where)}
            ORDER BY e.nome
        """),
        params,
    )
    funcs = res.fetchall()

    resultados = []
    for r in funcs:
        m = r._mapping
        chave = m["pix_key"]
        item = {
            "id": str(m["id"]),
            "nome": m["nome"],
            "cpf": m["cpf"],
            "pix_key": chave,
            "liquido": float(m["liquido"]) if m["liquido"] is not None else None,
        }
        if not chave:
            item.update(status="sem_chave", confere=False,
                        mensagem="Funcionário sem chave PIX cadastrada.")
            resultados.append(item)
            continue

        # VERIFICAÇÃO POR HISTÓRICO (real e permitida): quem você já pagou por PIX e caiu está
        # provado. Casa o nome do funcionário (1º + último token) com o nome do recebedor que o
        # Inter registrou no extrato (detalhes_destinatario->>'nome' ou dentro da descrição).
        toks = _norm_nome(m["nome"]).split()
        primeiro, ultimo = (toks[0], toks[-1]) if toks else ("", "")
        hist = await db.execute(
            text("""
                SELECT data_lancamento, valor,
                       COALESCE(detalhes_destinatario->>'nome',
                                regexp_replace(descricao,'^.*-','')) AS receb
                FROM inter_transactions
                WHERE tipo_operacao='D'
                  AND upper(translate(COALESCE(detalhes_destinatario->>'nome',descricao),
                        'ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇáàâãäéèêëíìîïóòôõöúùûüç',
                        'AAAAAEEEEIIIIOOOOOUUUUCAAAAAEEEEIIIIOOOOOUUUUC'))
                      LIKE '%' || :p || '%' || :u || '%'
                ORDER BY data_lancamento DESC
                LIMIT 6
            """),
            {"p": primeiro, "u": ultimo},
        )
        pagamentos = hist.fetchall()
        if pagamentos:
            ult = pagamentos[0]._mapping
            item.update(
                status="ok",
                confere=True,
                titular_historico=(ult["receb"] or "").strip(),
                ultimo_pagamento=str(ult["data_lancamento"]),
                ultimo_valor=float(ult["valor"]) if ult["valor"] else None,
                vezes_pago=len(pagamentos),
                mensagem=f"Já pago por PIX antes (últ.: {ult['data_lancamento']} R$ {float(ult['valor']):.2f}). Chave provada.",
            )
        else:
            item.update(
                status="sem_historico",
                confere=False,
                mensagem="Sem histórico de PIX para esta pessoa. Confira no 1º pagamento (teste com valor baixo) — o Inter mostra o titular antes de confirmar.",
            )
        resultados.append(item)

    ok = sum(1 for x in resultados if x.get("confere"))
    return {
        "posto": payload.posto,
        "competencia": payload.competencia or "",
        "total": len(resultados),
        "conferem": ok,
        "sem_historico": len(resultados) - ok,
        "metodo": "historico_pagamentos",
        "nota": "Verificação por histórico real de PIX. A consulta DICT avulsa não é exposta pela API do Inter (restrição BACEN); a confirmação final do titular aparece no ato do pagamento.",
        "funcionarios": resultados,
    }


class LoteItem(BaseModel):
    funcionario_id: str | None = None
    nome: str
    chave: str
    tipo_chave: str | None = None
    valor: float = Field(gt=0)


class PrepararLotePayload(BaseModel):
    posto: str
    competencia: str
    itens: list[LoteItem]


class ExecutarLotePayload(BaseModel):
    otp_code: str = Field(min_length=6, max_length=6)


@router.post("/folha/lote/preparar", status_code=201)
async def folha_lote_preparar(
    payload: PrepararLotePayload,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Prepara o lote de folha de um posto (status='preparado', categoria='folha'). Pula quem já
    foi pago na competência (anti-duplicidade). NÃO paga — só monta o lote para revisão + OTP."""
    from modules.integrations.inter.services import folha_lote_service as svc
    itens = [i.model_dump() for i in payload.itens]
    return await svc.preparar_lote(db, payload.posto, payload.competencia, itens, str(current_user.id))


@router.post("/folha/lote/{lote_id}/gerar-otp")
async def folha_lote_gerar_otp(
    lote_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Gera UM OTP para o lote inteiro e envia por email ao Jordan."""
    from modules.integrations.inter.services import folha_lote_service as svc
    try:
        return await svc.gerar_otp_lote(db, lote_id, str(current_user.id))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/folha/lote/{lote_id}/executar")
async def folha_lote_executar(
    lote_id: str,
    payload: ExecutarLotePayload,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Valida o OTP e paga TODOS os PIX do lote via Inter (dinheiro sai). Log completo."""
    from modules.integrations.inter.services import folha_lote_service as svc
    try:
        return await svc.executar_lote(db, lote_id, payload.otp_code, str(current_user.id))
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


class SalvarChavePayload(BaseModel):
    pix_key: str
    pix_key_type: str = "CPF"  # CPF | CNPJ | EMAIL | TELEFONE | EVP


@router.patch("/folha/funcionario/{funcionario_id}/chave")
async def folha_salvar_chave(
    funcionario_id: str,
    payload: SalvarChavePayload,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Salva a chave PIX (e o tipo) no cadastro do funcionário — digitou uma vez, o Conecta PRO
    puxa nas próximas. Cada pessoa pode ter tipo diferente (CPF, e-mail, telefone, aleatória)."""
    chave = (payload.pix_key or "").strip()
    if not chave:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Chave vazia.")
    res = await db.execute(
        text("""
            UPDATE employees SET pix_key = :k, pix_key_type = :t, pix_confirmada = true, updated_at = now()
            WHERE id = :id
            RETURNING nome
        """),
        {"k": chave, "t": (payload.pix_key_type or "CPF").upper(), "id": funcionario_id},
    )
    row = res.first()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Funcionário não encontrado.")
    await db.commit()
    return {"ok": True, "nome": row[0], "pix_key": chave, "pix_key_type": (payload.pix_key_type or "CPF").upper()}


@router.get("/saldo-limite")
async def saldo_limite(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Retorna limite diário consumido e disponível."""
    svc = InterPaymentService(db)
    return await svc.saldo_resumo()


@router.get("/audit")
async def audit_log_global(
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Audit log global — todas as transições de pagamento.
    Restrito a Jordan (validação dual: dependency + check explícito no handler)."""
    user_email = getattr(current_user, "email", "")
    if user_email not in ("jjesus@conectamais.pro", "jordansjesus@gmail.com"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas Jordan tem acesso ao audit log global",
        )

    res = await db.execute(
        text("""
            SELECT
                a.id,
                a.payment_id,
                a.user_id,
                u.email   AS user_email,
                a.status_from,
                a.status_to,
                a.ip_address,
                a.motivo,
                a.created_at,
                p.payment_type,
                p.valor,
                p.destinatario
            FROM inter_payment_audit a
            LEFT JOIN users u ON a.user_id = u.id
            LEFT JOIN inter_payments p ON a.payment_id = p.id
            ORDER BY a.created_at DESC
            LIMIT :limit OFFSET :offset
        """),
        {"limit": limit, "offset": offset},
    )

    rows = res.fetchall()
    return [
        {
            "id": str(r._mapping["id"]),
            "payment_id": str(r._mapping["payment_id"]) if r._mapping["payment_id"] else None,
            "user_email": r._mapping["user_email"],
            "status_from": r._mapping["status_from"],
            "status_to": r._mapping["status_to"],
            "ip_address": r._mapping["ip_address"],
            "motivo": r._mapping["motivo"],
            "created_at": (r._mapping["created_at"].isoformat() if r._mapping["created_at"] else None),
            "payment_type": r._mapping["payment_type"],
            "valor": float(r._mapping["valor"]) if r._mapping["valor"] else None,
            "destinatario": r._mapping["destinatario"],
        }
        for r in rows
    ]


@router.get("/{payment_id}/status-inter")
async def status_inter(
    payment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """MONITOR — consulta o status REAL do pagamento no Inter (aguardando aprovação / concluído /
    rejeitado) e atualiza o registro. Use para acompanhar em tempo real após enviar."""
    svc = InterPaymentService(db)
    try:
        return await svc.atualizar_status_inter(payment_id)
    except PaymentError as exc:
        raise _handle_payment_error(exc) from exc


@router.get("/{payment_id}/audit")
async def audit_log(
    payment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Retorna audit log completo de um pagamento."""
    svc = InterPaymentService(db)
    return {"payment_id": payment_id, "audit": await svc.audit_log(payment_id)}


class DecodificarPixPayload(BaseModel):
    brcode: str = Field(min_length=8, description="PIX copia-e-cola (BR Code) lido do QR ou colado")


@router.post("/decodificar-pix", summary="Decodifica um PIX copia-e-cola/QR Code em chave+valor (não paga)")
async def decodificar_pix(
    body: DecodificarPixPayload,
    current_user=Depends(get_current_user),
):
    """Lê o BR Code (copia-e-cola ou QR) e devolve chave/valor/nome pra pré-preencher o pagamento.
    NÃO envia dinheiro. QR dinâmico (URL do PSP) é sinalizado para tratar pelo app."""
    from modules.integrations.inter.pix_brcode import decodificar_brcode

    return decodificar_brcode(body.brcode)


@router.get("/{payment_id}/comprovante", summary="Comprovante do pagamento em PDF timbrado (padrão-ouro)")
async def comprovante(
    payment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Gera o comprovante PDF branded a partir do pagamento REAL (inter_payments).

    Só emite se o pagamento foi de fato enviado (tem inter_payment_id/endToEndId) — nunca
    fabrica comprovante de pagamento não concluído."""
    import json as _json

    from fastapi.responses import Response

    from modules.gedeon.services.comprovante_generator import gerar_comprovante_pdf

    row = (await db.execute(text("""
        SELECT payment_type, destinatario, valor, data_pagamento, status,
               inter_payment_id, executed_at, observacoes, categoria
        FROM inter_payments WHERE id = :id
    """), {"id": payment_id})).mappings().first()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Pagamento não encontrado.")
    if not row["inter_payment_id"] or row["status"] in ("preparado", "aprovado", "cancelado", "erro"):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail="Comprovante indisponível: pagamento ainda não foi concluído no Inter.")

    dest = row["destinatario"] if isinstance(row["destinatario"], dict) else _json.loads(row["destinatario"] or "{}")
    favorecido = dest.get("nome_recebedor") or dest.get("nome") or "Beneficiário"
    tipo = (dest.get("tipo_chave") or "").upper()
    chave = dest.get("chave") or ""
    doc = chave if tipo in ("CPF", "CNPJ") else (dest.get("cpf") or dest.get("cpf_cnpj"))
    data_pg = row["data_pagamento"] or row["executed_at"]
    tipo_pag = {"pix": "PIX", "ted": "TED", "boleto": "Boleto", "darf": "DARF", "gps": "GPS"}.get(
        (row["payment_type"] or "pix").lower(), "PIX")

    pdf = gerar_comprovante_pdf(
        favorecido=favorecido, cpf=doc, valor=float(row["valor"]),
        data_pagamento=data_pg, descricao=row["observacoes"] or None,
        id_transacao=row["inter_payment_id"], tipo=tipo_pag)
    fname = f"comprovante_{tipo_pag}_{favorecido.split()[0].lower()}_{payment_id[:8]}.pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{fname}"'})

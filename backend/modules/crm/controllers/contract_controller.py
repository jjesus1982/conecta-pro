"""
Controller (endpoints) para Gestão de Contratos.
"""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
import re

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from core.logging import logger
from modules.crm.models.contract import (
    ContractStatus,
    ContractType,
    ServiceType,
)
from modules.crm.repositories.contract_repository import ContractRepository
from modules.crm.schemas.contract import (
    ContractAddendumCreate,
    ContractAddendumResponse,
    ContractAddendumSign,
    ContractCreate,
    ContractDetailResponse,
    ContractFilter,
    ContractItemCreate,
    ContractItemResponse,
    ContractItemUpdate,
    ContractListResponse,
    ContractRenewal,
    ContractResponse,
    ContractTemplateCreate,
    ContractTemplateListResponse,
    ContractTemplateResponse,
    ContractTemplateUpdate,
    ContractUpdate,
)
from modules.crm.services.contract_service import (
    AdjustmentResult,
    ContractService,
    RenewalResult,
)

router = APIRouter(prefix="/contracts", tags=["CRM - Contracts"])


@router.get("/{contract_id}/pdf")
async def gerar_pdf_contrato(
    contract_id: str,
    current_user: CurrentActiveUser,  # noqa: ARG001
    db: AsyncSession = Depends(get_db),
    salvar: bool = False,
    teste: bool = False,
):
    """Gera o PDF do contrato no padrão visual Conecta Mais (com selo).
    salvar=true: registra no Conecta PRO e devolve link público de download."""
    from types import SimpleNamespace

    from fastapi import Response

    row = (
        (
            await db.execute(
                text("""
        SELECT c.contract_number, c.name, c.description, c.contract_type, c.monthly_value, c.total_value,
               c.start_date, c.end_date, c.auto_renewal, c.renewal_period_months, c.content, c.clauses,
               c.retencao_iss, c.retencao_inss, c.retencao_csll,
               cl.name AS client_name, cl.document_number AS client_document
        FROM contracts c LEFT JOIN clients cl ON cl.id = c.client_id
        WHERE c.contract_number = :k OR c.id::text = :k
    """),
                {"k": contract_id},
            )
        )
        .mappings()
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")

    from modules.crm.services.contract_pdf import build_contract_pdf

    try:
        pdf_bytes = build_contract_pdf(SimpleNamespace(**dict(row)))
    except Exception as e:  # noqa: BLE001
        logger.exception("Erro ao gerar PDF do contrato %s", contract_id)
        raise HTTPException(status_code=500, detail=f"Erro ao gerar PDF: {e}") from e

    if salvar:
        from modules.crm.services.docs_registry import salvar_pdf

        return await salvar_pdf(
            db,
            "contrato",
            f"Contrato {row['contract_number']} - {row.get('client_name', '')}",
            pdf_bytes,
            ref_tipo="contract",
            ref_id=contract_id,
            teste=teste,
        )

    fname = f"contrato_{(row['contract_number'] or contract_id).replace('/', '-')}.pdf"
    return Response(
        content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{fname}"'}
    )


@router.get("/{contract_id}/pdf-modelo")
async def gerar_pdf_por_modelo(
    contract_id: str,
    current_user: CurrentActiveUser,  # noqa: ARG001
    db: AsyncSession = Depends(get_db),
    template_id: str | None = None,
    salvar: bool = False,
    teste: bool = False,
    minuta: bool = False,
    formato: str = "pdf",
):
    """Gera o contrato REAL a partir do modelo cadastrado (não o molde de 3 páginas).

    Diferença para `/{id}/pdf`: aquele monta um resumo fixo; este renderiza o
    `content_template` do modelo — 12 cláusulas, texto jurídico completo — com as
    variáveis do contrato, e resolve a CONTRATADA pelo tipo de serviço (mão de obra sai
    pela Patrimonial, eletrônica pela Eletrônica).

    Falha em 422 com o motivo em português quando faltar variável ou quando não der para
    saber quem presta o serviço. Isso é de propósito: contrato com campo vazio ou com o
    CNPJ errado vai para assinatura assim.
    """
    from fastapi import Response

    from modules.crm.services.contract_render import RenderError, renderizar_contrato

    try:
        # `?minuta=1` gera o RASCUNHO para o cliente levar ao jurídico dele: o que ainda
        # não foi negociado sai como [A DEFINIR] e a capa se identifica como minuta, em vez
        # de o render recusar. Pedido do Jordan em 10/09/2026 — ele precisava mandar o
        # Kopenhagen para o síndico analisar, e o sistema exigia o CPF de quem assina, que
        # é justamente uma das coisas que a análise vai definir.
        res = await renderizar_contrato(db, contract_id, template_id, minuta=minuta)
    except RenderError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        logger.exception("Erro ao renderizar contrato %s por modelo", contract_id)
        raise HTTPException(status_code=500, detail=f"Erro ao gerar contrato: {e}") from e

    if res.clausulas_faltando:
        raise HTTPException(
            status_code=422,
            detail=(
                "O texto renderizado não contém todas as cláusulas do modelo — faltam: "
                + "; ".join(res.clausulas_faltando[:3])
            ),
        )

    if salvar:
        from modules.crm.services.docs_registry import salvar_pdf

        out = await salvar_pdf(
            db,
            "contrato",
            f"Contrato {contract_id} — {res.contratada.razao_social}",
            res.pdf,
            ref_tipo="contract",
            ref_id=contract_id,
            teste=teste,
        )
        if isinstance(out, dict):
            out["contratada"] = res.contratada.razao_social
            out["contratada_cnpj"] = res.contratada.cnpj
            out["clausulas"] = res.n_clausulas
            if res.contratada.divergencia:
                out["aviso"] = res.contratada.divergencia
        return out

    # `formato=json`: o mesmo documento em ENVELOPE LEGÍVEL, para quem não tem navegador.
    #
    # Nasceu do relatório de campo do Jordan sobre o Cowork (11/09/2026): o agente que usa o
    # MCP recebe uma `download_url` de um binário que ele não consegue abrir — `web_fetch`
    # devolve vazio e `curl` é proibido por política. Resultado: gera o contrato e não pode
    # conferir se saiu certo. Já aconteceu de sair a casca de 3 páginas e ninguém perceber.
    #
    # ⭐ O `texto` aqui NÃO é extração do PDF: é o texto que o próprio render produziu, antes
    # de virar papel (`Resultado.texto`). É mais fiel que qualquer extrator e não custa
    # dependência nenhuma — só parar de jogar fora o que já estava na mão.
    if str(formato).lower() == "json":
        import base64 as _b64

        pdf_b64 = _b64.b64encode(res.pdf).decode("ascii")
        grande = len(res.pdf) > 8 * 1024 * 1024
        return {
            "ok": True,
            "arquivo": {
                "nome": f"contrato_{contract_id.replace('/', '-')}.pdf",
                "mime": "application/pdf",
                "tamanho_kb": round(len(res.pdf) / 1024, 1),
                # acima de 8 MB o base64 sai e o texto fica: o agente ainda consegue VALIDAR
                # o conteúdo, que é o que ele precisa; baixar é problema de quem tem browser.
                **({} if grande else {"base64": pdf_b64}),
            },
            "texto_extraido": res.texto,
            "clausulas": res.n_clausulas,
            "contratada": res.contratada.razao_social,
            "contratada_cnpj": res.contratada.cnpj,
            "minuta": bool(minuta),
            **({"aviso": "PDF acima de 8 MB — base64 omitido; use texto_extraido ou a URL."}
               if grande else {}),
        }

    fname = f"contrato_{contract_id.replace('/', '-')}.pdf"
    headers = {
        "Content-Disposition": f'inline; filename="{fname}"',
        "X-Contratada-CNPJ": res.contratada.cnpj,
        "X-Clausulas": str(res.n_clausulas),
    }
    if res.contratada.divergencia:
        # o PDF sai certo pela REGRA; o aviso denuncia o dado gravado que a contradiz
        headers["X-Aviso-Empresa"] = res.contratada.divergencia[:180]
    return Response(content=res.pdf, media_type="application/pdf", headers=headers)


@router.post("/{contract_id}/abrir-assinatura")
async def abrir_assinatura_contrato(
    contract_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    email_cliente: str | None = None,
):
    """Abre a assinatura eletrônica do contrato: a empresa assina, depois o cliente por link.

    Renderiza o instrumento, calcula o hash do PDF e registra a solicitação no motor
    universal com dois signatários em ordem — CONTRATADA primeiro, CLIENTE depois. Devolve
    o LINK único do cliente, que é o que se manda para o síndico.

    O hash é do PDF renderizado NESTE momento: é ele que a verificação confere depois. Se
    o contrato mudar, a assinatura anterior deixa de bater — que é o comportamento certo.
    """
    from modules.crm.services import contract_signature as CS
    from modules.crm.services import contract_wizard as W
    from modules.crm.services.contract_render import RenderError, renderizar_contrato

    try:
        W.exigir_emitente(current_user)
    except W.NaoAutorizado as e:
        raise HTTPException(status_code=403, detail=str(e)) from e

    try:
        res = await renderizar_contrato(db, contract_id)
    except RenderError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    dados = (
        (
            await db.execute(
                text("""
        SELECT c.contract_number, cl.name AS cliente,
               (SELECT k.name FROM crm_contacts k WHERE k.client_id = c.client_id
                 AND (k.role ILIKE '%representante%' OR k.role ILIKE '%s%ndic%')
                ORDER BY k.is_primary DESC NULLS LAST LIMIT 1) AS representante,
               (SELECT k.notes FROM crm_contacts k WHERE k.client_id = c.client_id
                 AND (k.role ILIKE '%representante%' OR k.role ILIKE '%s%ndic%')
                ORDER BY k.is_primary DESC NULLS LAST LIMIT 1) AS rep_cpf,
               (SELECT k.email FROM crm_contacts k WHERE k.client_id = c.client_id
                 AND (k.role ILIKE '%representante%' OR k.role ILIKE '%s%ndic%')
                ORDER BY k.is_primary DESC NULLS LAST LIMIT 1) AS rep_email
        FROM contracts c LEFT JOIN clients cl ON cl.id = c.client_id
        WHERE c.id::text = :k OR c.contract_number = :k
    """),
                {"k": contract_id},
            )
        )
        .mappings()
        .first()
    )
    if not dados:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")

    sol = await CS.abrir_assinatura(
        db,
        dados["contract_number"],
        res.pdf,
        contratante_nome=dados["cliente"] or "",
        representante=dados["representante"] or "",
        representante_cpf=dados["rep_cpf"] or "",
        representante_email=email_cliente or dados["rep_email"],
        contratada_nome=res.contratada.razao_social,
        assinante_empresa=getattr(current_user, "full_name", None) or "Jordan Santos de Jesus",
        assinante_empresa_id=getattr(current_user, "id", None),
        solicitado_por=getattr(current_user, "id", None),
    )
    return {
        "contrato": dados["contract_number"],
        "documento_hash": sol.documento_hash,
        "assinatura_empresa_id": sol.request_id_empresa,
        "assinatura_cliente_id": sol.request_id_cliente,
        "link_do_cliente": sol.link_cliente,
        "resumo": (
            f"Assinatura aberta para {dados['contract_number']}. "
            f"1º a CONTRATADA assina pelo painel; depois envie o link ao "
            f"{dados['representante'] or 'representante'}."
        ),
    }


@router.post("/{contract_id}/assinar-empresa")
async def assinar_contrato_pela_empresa(
    contract_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
):
    """A Conecta Mais firma o contrato pelo painel (1º signatário).

    Mesmo portão da emissão: só Jordan e Pyetra assinam pela empresa. Depois disto o link
    do cliente pode ser enviado — e não antes.
    """
    from modules.crm.services import contract_signature as CS
    from modules.crm.services import contract_wizard as W
    from modules.crm.services.contract_render import RenderError, renderizar_contrato

    W.exigir_emitente(current_user)
    num = (
        await db.execute(
            text("SELECT contract_number FROM contracts WHERE id::text = :k OR contract_number = :k"),
            {"k": contract_id},
        )
    ).scalar()
    if not num:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")
    try:
        res = await renderizar_contrato(db, num)
    except RenderError as e:
        raise HTTPException(status_code=422, detail=str(e))
    try:
        r = await CS.assinar_pela_empresa(
            db,
            num,
            nome=getattr(current_user, "full_name", None) or "Conecta Mais",
            pdf=res.pdf,
            usuario_id=getattr(current_user, "id", None),
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    await db.commit()
    return {
        "contrato": num,
        "assinado_por": getattr(current_user, "full_name", ""),
        "quando": str(r.get("signed_at") or ""),
        "hash": r.get("signature_hash"),
        "completo": bool(r.get("group_completed")),
        "resumo": f"{num} assinado pela CONTRATADA. Agora envie o link ao cliente.",
    }


@router.post("/{contract_id}/enviar-link")
async def enviar_link_assinatura(
    contract_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    email: str | None = None,
    parte: str = "cliente",
):
    """Manda o link de assinatura ao signatário — ou devolve o link para envio manual.

    `email` opcional: sem ele, devolve só o link (para mandar por WhatsApp). Com ele,
    dispara o convite. Nunca manda o código junto — o código vai depois, para o e-mail
    que a pessoa informar na própria tela.
    """
    from modules.crm.services import contract_signature as CS
    from modules.crm.services import contract_wizard as W

    W.exigir_emitente(current_user)
    papel = "customer" if parte.lower().startswith(("cli", "cont_ante", "contratante")) else "company"
    linha = (
        (
            await db.execute(
                text(
                    "SELECT access_token, signer_name, signer_email, signed_at IS NOT NULL AS assinou "
                    "FROM sig_signature_requests WHERE reference_code = :k AND signer_type = :p"
                ),
                {"k": contract_id, "p": papel},
            )
        )
        .mappings()
        .first()
    )
    if not linha or not linha["access_token"]:
        raise HTTPException(
            status_code=404,
            detail=f"não há link de assinatura em aberto para a parte '{parte}' "
            f"em {contract_id}. Abra a assinatura primeiro.",
        )
    if linha["assinou"]:
        raise HTTPException(status_code=409, detail=f"{linha['signer_name']} já assinou.")

    # a ordem importa: não se manda ao cliente o que a CONTRATADA ainda não firmou
    if papel == "customer":
        pendente = (
            await db.execute(
                text(
                    "SELECT signer_name FROM sig_signature_requests WHERE reference_code = :k "
                    "AND signer_type = 'company' AND signed_at IS NULL"
                ),
                {"k": contract_id},
            )
        ).scalar()
        if pendente:
            raise HTTPException(
                status_code=409,
                detail="a Conecta Mais ainda não assinou este contrato — o link do cliente "
                "seria recusado. Assine primeiro.",
            )

    link = f"{CS.BASE_PUBLICA}/assinar/contrato/{linha['access_token']}"
    destino = email or linha["signer_email"]
    enviado = False
    if destino:
        enviado = await CS.convidar_para_assinar(
            db,
            contract_id,
            para=destino,
            link=link,
            nome=linha["signer_name"] or "",
            papel="CONTRATANTE" if papel == "customer" else "CONTRATADA",
        )
        if enviado and not linha["signer_email"]:
            await db.execute(
                text(
                    "UPDATE sig_signature_requests SET signer_email = :e WHERE reference_code = :k AND signer_type = :p"
                ),
                {"e": destino, "k": contract_id, "p": papel},
            )
            await db.commit()
    return {
        "contrato": contract_id,
        "signatario": linha["signer_name"],
        "link": link,
        "email_enviado_para": destino if enviado else None,
        "resumo": (
            f"Convite enviado para {destino}."
            if enviado
            else "Sem e-mail informado — mande o link abaixo por WhatsApp."
        ),
    }


@router.get("/{contract_id}/assinaturas")
async def status_assinaturas_contrato(
    contract_id: str,
    current_user: CurrentActiveUser,  # noqa: ARG001
    db: AsyncSession = Depends(get_db),
):
    """Quem já assinou este contrato, quando e com que hash."""
    from modules.crm.services.contract_signature import assinaturas_do_contrato

    num = (
        await db.execute(
            text("SELECT contract_number FROM contracts WHERE id::text=:k OR contract_number=:k"), {"k": contract_id}
        )
    ).scalar()
    if not num:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")
    assinadas = await assinaturas_do_contrato(db, num)
    pendentes = (
        (
            await db.execute(
                text(
                    "SELECT signer_type::text, signer_name, access_token IS NOT NULL AS tem_link "
                    "FROM sig_signature_requests WHERE reference_code=:k AND signed_at IS NULL "
                    "ORDER BY signature_order"
                ),
                {"k": num},
            )
        )
        .mappings()
        .all()
    )
    return {
        "contrato": num,
        "assinadas": assinadas,
        "pendentes": [dict(p) for p in pendentes],
        "completo": bool(assinadas) and not pendentes,
    }


@router.post("/briefing")
async def briefing_contrato_novo(
    current_user: CurrentActiveUser,
    payload: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
):
    """Briefing de contrato NOVO — o que perguntar antes de montar.

    Mesma função que o chat usa, exposta por HTTP para o jurídico e o Cowork: as três
    superfícies fazem a MESMA pergunta na mesma ordem.
    """
    from modules.crm.services import contract_wizard as W

    try:
        W.exigir_emitente(current_user)
    except W.NaoAutorizado as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    return await W.briefing(
        db,
        servicos=payload.get("servicos"),
        cliente_cnpj=payload.get("cliente_cnpj"),
        cliente_nome=payload.get("cliente_nome"),
    )


@router.post("/criar-por-modelo")
async def criar_contrato_por_modelo(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
):
    """Cria o contrato já ligado ao modelo/tipo/empresa. Mesma lógica das três superfícies."""
    from modules.ai.conversation.services.orquestrador.tools_comercial_doc import (
        _criar_contrato_por_modelo,
    )

    res = await _criar_contrato_por_modelo(db, current_user, None, **payload)
    if res.get("status") == "recusado":
        raise HTTPException(status_code=403, detail=res.get("motivo", "recusado"))
    return res


@router.post("/validar-modelo")
async def validar_modelo(
    current_user: CurrentActiveUser,  # noqa: ARG001
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Diz quais `{{variaveis}}` de um corpo o ERP sabe preencher — ANTES de cadastrar.

    Item 2.3 do relatório de campo (11/09/2026): dava para cadastrar um modelo bonito que
    só falhava na hora de emitir, com o cliente esperando. Aqui o corpo é confrontado com o
    CONTEXTO REAL de um contrato existente: o que tem valor, o que viria vazio, e o que o
    ERP não conhece de jeito nenhum.

    Não grava nada e não gera PDF — é o ensaio antes do palco.
    """
    from modules.crm.services.contract_render import montar_contexto, variaveis_vazias

    corpo = (payload.get("corpo") or "").strip()
    chave = (payload.get("contrato") or "").strip()
    if not corpo or not chave:
        raise HTTPException(status_code=422, detail="Informe `corpo` e `contrato`.")

    tpl = (await db.execute(text(
        "SELECT t.id::text, t.name, t.service_type FROM contracts c "
        "LEFT JOIN contract_templates t ON t.id = c.template_id "
        "WHERE c.contract_number = :k OR c.id::text = :k"), {"k": chave})).mappings().first()
    if tpl is None:
        raise HTTPException(status_code=404, detail=f"Contrato não encontrado: {chave}")

    try:
        ctx, contratada = await montar_contexto(db, chave, dict(tpl or {}))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=str(e)) from e

    usadas = sorted(set(re.findall(r"\{\{\s*([a-z_0-9]+)", corpo)))
    vazias = set(variaveis_vazias(ctx, corpo))
    desconhecidas = [v for v in usadas if v not in ctx]
    return {
        "ok": not vazias and not desconhecidas,
        "contrato_exemplo": chave,
        "contratada": contratada.razao_social,
        "variaveis": usadas,
        "com_valor": [v for v in usadas if v in ctx and v not in vazias],
        "viriam_vazias": sorted(vazias),
        "desconhecidas_do_erp": desconhecidas,
        "dica": ("O ERP não conhece estas variáveis — ou você as escreveu com outro nome, "
                 "ou elas precisam virar dado do contrato: " + ", ".join(desconhecidas))
        if desconhecidas else "Todas as variáveis do corpo têm origem no ERP.",
    }


@router.post("/emitir-por-modelo")
async def emitir_contrato_por_modelo(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
):
    """Emite o contrato completo pelo modelo — a MESMA lógica que o chat usa.

    Existe para o conector MCP (Cowork) e para qualquer superfície que fale HTTP: as três
    entradas (jurídico, chat, Cowork) passam pelo mesmo caminho, então a regra de quem
    pode emitir e o diagnóstico do que falta não divergem entre elas.

    Devolve `faltam_dados` com as PERGUNTAS quando o contrato ainda não está completo —
    200, não erro: quem chamou precisa da lista para perguntar ao usuário.
    """
    from modules.ai.conversation.services.orquestrador.tools_comercial_doc import (
        _gerar_contrato_por_modelo,
    )

    res = await _gerar_contrato_por_modelo(db, current_user, None, **payload)
    if res.get("status") == "recusado":
        raise HTTPException(status_code=403, detail=res.get("motivo", "recusado"))
    return res


# ============== Contract Endpoints ==============


@router.post("", response_model=ContractDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_contract(
    data: ContractCreate,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ContractDetailResponse:
    """
    Cria um novo contrato.

    Requer autenticação. Contrato inicia em status DRAFT.
    """
    repo = ContractRepository(db)
    contract = await repo.create(data, created_by_id=str(current_user.id))
    logger.info(f"Contract criado por {current_user.email}: {contract.contract_number}")
    return ContractDetailResponse.model_validate(contract)


@router.get("", response_model=ContractListResponse)
async def list_contracts(  # pylint: disable=too-many-locals
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1, description="Página atual"),
    page_size: int = Query(20, ge=1, le=100, description="Itens por página"),
    status_filter: ContractStatus | None = Query(None, alias="status"),
    contract_type: ContractType | None = None,
    client_id: str | None = None,
    commercial_manager_id: str | None = None,
    account_manager_id: str | None = None,
    has_sla: bool | None = None,
    min_value: float | None = Query(None, ge=0),
    max_value: float | None = Query(None, ge=0),
    search: str | None = None,
) -> ContractListResponse:
    """
    Lista contratos com filtros e paginação.
    """
    repo = ContractRepository(db)

    filters = ContractFilter(
        status=status_filter,
        contract_type=contract_type,
        client_id=client_id,
        commercial_manager_id=commercial_manager_id,
        account_manager_id=account_manager_id,
        has_sla=has_sla,
        min_value=Decimal(str(min_value)) if min_value else None,
        max_value=Decimal(str(max_value)) if max_value else None,
        search=search,
    )

    contracts, total = await repo.list(filters=filters, page=page, page_size=page_size)
    total_pages = (total + page_size - 1) // page_size

    # Nome e CNPJ do cliente em UMA consulta para a página inteira — não uma por linha.
    # Sem isto, descobrir "quais contratos são do Maiápolis" custava 19 chamadas.
    _ids = {str(c.client_id) for c in contracts if getattr(c, "client_id", None)}
    _cli: dict[str, tuple[str | None, str | None]] = {}
    if _ids:
        _rs = await db.execute(
            text("SELECT id::text, name, document_number FROM clients WHERE id::text = ANY(:i)"),
            {"i": sorted(_ids)},
        )
        _cli = {r[0]: (r[1], r[2]) for r in _rs}

    def _com_cliente(c) -> ContractResponse:
        item = ContractResponse.model_validate(c)
        nome, doc = _cli.get(str(getattr(c, "client_id", "") or ""), (None, None))
        item.client_name, item.client_document = nome, doc
        return item

    return ContractListResponse(
        items=[_com_cliente(c) for c in contracts],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


# ============== Contract Template Endpoints (antes de /{contract_id} para evitar captura) ==============


@router.post(
    "/templates",
    response_model=ContractTemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_template(
    data: ContractTemplateCreate,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ContractTemplateResponse:
    """
    Cria template de contrato.
    """
    repo = ContractRepository(db)
    template = await repo.create_template(data)
    logger.info(f"Template criado por {current_user.email}: {template.name}")
    return ContractTemplateResponse.model_validate(template)


@router.get("/templates", response_model=ContractTemplateListResponse)
async def list_templates(
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
    service_type: ServiceType | None = None,
    approved_only: bool = False,
) -> ContractTemplateListResponse:
    """
    Lista templates de contrato.
    """
    repo = ContractRepository(db)
    templates = await repo.list_templates(
        service_type=service_type.value if service_type else None,
        approved_only=approved_only,
    )
    return ContractTemplateListResponse(
        items=[ContractTemplateResponse.model_validate(t) for t in templates],
        total=len(templates),
    )


# ============== Contract by ID (deve vir DEPOIS de rotas estáticas) ==============


@router.get("/{contract_id}", response_model=ContractDetailResponse)
async def get_contract(
    contract_id: str,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ContractDetailResponse:
    """
    Obtém um contrato pelo ID com todos os itens.
    """
    repo = ContractRepository(db)
    contract = await repo.get_by_id(contract_id)

    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contrato não encontrado",
        )

    return ContractDetailResponse.model_validate(contract)


@router.put("/{contract_id}", response_model=ContractDetailResponse)
async def update_contract(
    contract_id: str,
    data: ContractUpdate,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ContractDetailResponse:
    """
    Atualiza um contrato.

    Apenas contratos em rascunho podem ser editados completamente.
    """
    repo = ContractRepository(db)
    contract = await repo.update(contract_id, data)

    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contrato não encontrado ou não pode ser editado",
        )

    logger.info(f"Contract atualizado por {current_user.email}: {contract.contract_number}")
    return ContractDetailResponse.model_validate(contract)


@router.post("/{contract_id}/submit", response_model=ContractResponse, status_code=201)
async def submit_contract_for_signature(
    contract_id: str,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ContractResponse:
    """
    Envia contrato para assinatura.

    Muda status de DRAFT para PENDING_SIGNATURE.
    """
    repo = ContractRepository(db)
    contract = await repo.update_status(
        contract_id,
        ContractStatus.PENDING_SIGNATURE,
        user_id=str(current_user.id),
    )

    if not contract:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contrato não encontrado ou não está em rascunho",
        )

    logger.info(f"Contract enviado para assinatura por {current_user.email}: {contract.contract_number}")
    return ContractResponse.model_validate(contract)


@router.post("/{contract_id}/activate", response_model=ContractResponse, status_code=201)
async def activate_contract(
    contract_id: str,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ContractResponse:
    """
    Ativa o contrato após assinatura.
    """
    repo = ContractRepository(db)
    contract = await repo.update_status(
        contract_id,
        ContractStatus.ACTIVE,
        user_id=str(current_user.id),
    )

    if not contract:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contrato não encontrado ou não está pendente de assinatura",
        )

    logger.info(f"Contract ativado por {current_user.email}: {contract.contract_number}")

    # Captura valores planos p/ lançar o MRR em sessão isolada (depois dos publishers).
    _mrr_args = (
        contract.contract_number,
        str(getattr(contract.contract_type, "value", contract.contract_type)),
        float(contract.monthly_value or 0),
        contract.name,
        str(contract.client_id) if contract.client_id else None,
        contract.start_date,
    )

    import asyncio

    from modules.crm.publishers import publish_cliente_ativo, publish_contrato_assinado

    asyncio.create_task(
        publish_contrato_assinado(
            contrato_id=str(contract.id),
            numero=contract.contract_number,
            cliente_id=str(getattr(contract, "client_id", "") or ""),
            nome_cliente=str(getattr(contract, "client_name", "") or ""),
            tipo_contrato=str(getattr(contract, "contract_type", "") or ""),
            valor_mensal=float(getattr(contract, "monthly_value", 0) or 0),
            vigencia_inicio=str(getattr(contract, "start_date", "") or ""),
            vigencia_fim=str(getattr(contract, "end_date", "") or ""),
        )
    )
    asyncio.create_task(
        publish_cliente_ativo(
            cliente_id=str(getattr(contract, "client_id", "") or ""),
            nome=str(getattr(contract, "client_name", "") or ""),
            tipo_contrato=str(getattr(contract, "contract_type", "") or ""),
            valor_contrato=float(getattr(contract, "monthly_value", 0) or 0),
        )
    )

    # MRR: contrato ativo recorrente -> lança a linha de faturamento (client_contracts).
    await _bridge_contract_to_billing(*_mrr_args)

    return ContractResponse.model_validate(contract)


@router.post("/{contract_id}/suspend", response_model=ContractResponse, status_code=201)
async def suspend_contract(
    contract_id: str,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
    reason: str | None = None,  # pylint: disable=unused-argument
) -> ContractResponse:
    """
    Suspende um contrato ativo.
    """
    repo = ContractRepository(db)
    contract = await repo.update_status(
        contract_id,
        ContractStatus.SUSPENDED,
        user_id=str(current_user.id),
    )

    if not contract:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contrato não encontrado ou não pode ser suspenso",
        )

    logger.info(f"Contract suspenso por {current_user.email}: {contract.contract_number}")
    return ContractResponse.model_validate(contract)


@router.post("/{contract_id}/terminate", response_model=ContractResponse, status_code=201)
async def terminate_contract(
    contract_id: str,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
    reason: str | None = None,  # pylint: disable=unused-argument
) -> ContractResponse:
    """
    Encerra um contrato.
    """
    repo = ContractRepository(db)
    contract = await repo.update_status(
        contract_id,
        ContractStatus.TERMINATED,
        user_id=str(current_user.id),
    )

    if not contract:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contrato não encontrado ou não pode ser encerrado",
        )

    logger.info(f"Contract encerrado por {current_user.email}: {contract.contract_number}")
    return ContractResponse.model_validate(contract)


@router.post("/{contract_id}/renew", response_model=RenewalResult, status_code=201)
async def calculate_renewal(
    contract_id: str,
    data: ContractRenewal,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> RenewalResult:
    """
    Calcula renovação do contrato.

    Retorna simulação sem aplicar alterações.
    """
    repo = ContractRepository(db)
    service = ContractService()

    contract = await repo.get_by_id(contract_id)

    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contrato não encontrado",
        )

    try:
        return service.calculate_renewal(
            contract=contract,
            custom_adjustment_percent=data.adjustment_percent,
            new_end_date=data.new_end_date,
        )
    except ValueError as exc:  # índice sem percentual (08/09/2026)
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{contract_id}/calculate-adjustment", response_model=AdjustmentResult, status_code=201)
async def calculate_adjustment(
    contract_id: str,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
    custom_percent: float | None = None,
    effective_date: date | None = None,
) -> AdjustmentResult:
    """
    Calcula reajuste do contrato.

    Retorna simulação sem aplicar alterações.
    """
    repo = ContractRepository(db)
    service = ContractService()

    contract = await repo.get_by_id(contract_id)

    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contrato não encontrado",
        )

    try:
        return service.calculate_adjustment(
            contract=contract,
            custom_percent=Decimal(str(custom_percent)) if custom_percent else None,
            effective_date=effective_date,
        )
    except ValueError as exc:  # índice sem percentual (08/09/2026)
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/{contract_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contract(
    contract_id: str,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Remove um contrato (soft delete).

    Apenas contratos em rascunho podem ser excluídos.
    """
    repo = ContractRepository(db)
    deleted = await repo.delete(contract_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contrato não encontrado ou não pode ser excluído",
        )

    logger.info(f"Contract deletado por {current_user.email}: {contract_id}")


# ============== Contract Item Endpoints ==============


@router.post("/{contract_id}/items", response_model=ContractItemResponse, status_code=201)
async def add_contract_item(
    contract_id: str,
    data: ContractItemCreate,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ContractItemResponse:
    """
    Adiciona item ao contrato.
    """
    repo = ContractRepository(db)
    item = await repo.add_item(contract_id, data)

    if not item:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contrato não encontrado ou não pode ser editado",
        )

    logger.info(f"Item adicionado ao contrato {contract_id} por {current_user.email}")
    return ContractItemResponse.model_validate(item)


@router.put("/{contract_id}/items/{item_id}", response_model=ContractItemResponse)
async def update_contract_item(
    contract_id: str,
    item_id: str,
    data: ContractItemUpdate,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ContractItemResponse:
    """
    Atualiza item do contrato.
    """
    repo = ContractRepository(db)
    item = await repo.update_item(contract_id, item_id, data)

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item ou contrato não encontrado",
        )

    logger.info(f"Item {item_id} atualizado por {current_user.email}")
    return ContractItemResponse.model_validate(item)


@router.delete(
    "/{contract_id}/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_contract_item(
    contract_id: str,
    item_id: str,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Remove item do contrato.
    """
    repo = ContractRepository(db)
    removed = await repo.remove_item(contract_id, item_id)

    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item ou contrato não encontrado",
        )

    logger.info(f"Item {item_id} removido do contrato {contract_id}")


# ============== Contract Addendum Endpoints ==============


@router.post("/{contract_id}/addendums", response_model=ContractAddendumResponse, status_code=201)
async def create_addendum(
    contract_id: str,
    data: ContractAddendumCreate,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ContractAddendumResponse:
    """
    Cria aditivo do contrato.
    """
    repo = ContractRepository(db)
    addendum = await repo.create_addendum(contract_id, data, created_by_id=str(current_user.id))

    if not addendum:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contrato não encontrado ou não está ativo",
        )

    logger.info(f"Aditivo criado por {current_user.email}: {addendum.addendum_number}")
    return ContractAddendumResponse.model_validate(addendum)


@router.get("/{contract_id}/addendums", response_model=list[ContractAddendumResponse])
async def list_addendums(
    contract_id: str,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> list[ContractAddendumResponse]:
    """
    Lista aditivos do contrato.
    """
    repo = ContractRepository(db)
    addendums = await repo.list_addendums(contract_id)
    return [ContractAddendumResponse.model_validate(a) for a in addendums]


@router.post("/addendums/{addendum_id}/sign", response_model=ContractAddendumResponse, status_code=201)
async def sign_addendum(
    addendum_id: str,
    data: ContractAddendumSign,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ContractAddendumResponse:
    """
    Assina aditivo e aplica alterações ao contrato.
    """
    repo = ContractRepository(db)
    addendum = await repo.sign_addendum(addendum_id, data.signature_document_id)

    if not addendum:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Aditivo não encontrado ou já assinado",
        )

    logger.info(f"Aditivo assinado por {current_user.email}: {addendum.addendum_number}")
    return ContractAddendumResponse.model_validate(addendum)


# (create_template e list_templates movidos para antes de /{contract_id} — ver acima)


@router.get("/templates/{template_id}", response_model=ContractTemplateResponse)
async def get_template(
    template_id: str,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ContractTemplateResponse:
    """
    Obtém template por ID.
    """
    repo = ContractRepository(db)
    template = await repo.get_template_by_id(template_id)

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template não encontrado",
        )

    return ContractTemplateResponse.model_validate(template)


@router.put("/templates/{template_id}", response_model=ContractTemplateResponse)
async def update_template(
    template_id: str,
    data: ContractTemplateUpdate,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ContractTemplateResponse:
    """
    Atualiza template.
    """
    repo = ContractRepository(db)
    template = await repo.update_template(template_id, data)

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template não encontrado",
        )

    logger.info(f"Template atualizado por {current_user.email}: {template.name}")
    return ContractTemplateResponse.model_validate(template)


@router.post("/templates/{template_id}/approve", response_model=ContractTemplateResponse, status_code=201)
async def approve_template(
    template_id: str,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ContractTemplateResponse:
    """
    Aprova template juridicamente.
    """
    repo = ContractRepository(db)
    template = await repo.approve_template(template_id, str(current_user.id))

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template não encontrado",
        )

    logger.info(f"Template aprovado por {current_user.email}: {template.name}")
    return ContractTemplateResponse.model_validate(template)


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: str,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Remove template (soft delete).
    """
    repo = ContractRepository(db)
    deleted = await repo.delete_template(template_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template não encontrado",
        )

    logger.info(f"Template deletado por {current_user.email}: {template_id}")


# ============== SLA Report Endpoints ==============


# ============================================================================
# ATIVAR CONTRATO -> alimenta o MRR (cria a linha de billing em client_contracts)
# ============================================================================


async def _bridge_contract_to_billing(num, ctype_val, monthly, name, client_id, start_date) -> bool:
    """Cria a linha de faturamento (client_contracts) p/ entrar no MRR, em SESSÃO ISOLADA com
    valores planos (evita MissingGreenlet). Idempotente (dedup por contract_number). Best-effort."""
    try:
        monthly = float(monthly or 0)
        if str(ctype_val or "").lower() != "recurring" or monthly <= 0 or not client_id:
            return False
        nome = (name or "").lower()
        if "cerca" in nome:
            st = "cerca_eletrica"
        elif "cftv" in nome or "câmera" in nome or "camera" in nome:
            st = "cftv"
        elif "monitor" in nome:
            st = "monitoramento_24h"
        elif "alarme" in nome:
            st = "alarme"
        else:
            st = "portaria_remota"

        from core.database import async_session_factory

        async with async_session_factory() as s:
            existing = (
                await s.execute(text("SELECT id FROM client_contracts WHERE contract_number = :n LIMIT 1"), {"n": num})
            ).first()
            if existing:
                return False
            await s.execute(
                text("""
                INSERT INTO client_contracts
                    (id, client_id, contract_number, service_type, status, monthly_value, start_date,
                     auto_renewal, ativo, created_at, updated_at)
                VALUES
                    (gen_random_uuid(), :cid, :num, CAST(:st AS contract_service_type_enum),
                     CAST('active' AS service_status_enum), :mv, :sd, true, true, now(), now())
                """),
                {"cid": client_id, "num": num, "st": st, "mv": monthly, "sd": start_date or date.today()},
            )
            await s.execute(
                text("UPDATE clients SET mrr = COALESCE(mrr, 0) + :mv WHERE id = :cid"),
                {"mv": monthly, "cid": client_id},
            )
            await s.commit()
        logger.info(f"MRR: contrato {num} -> billing client_contracts (R$ {monthly}/mês)")
        return True
    except Exception as exc:  # noqa: BLE001 — bridge nunca quebra a ativação
        logger.warning(f"Bridge contrato->MRR falhou ({num}): {exc}")
        return False

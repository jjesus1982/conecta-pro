"""Tools GERA-DOC comercial (Fase 6, Fatia 1) — módulo crm, scope_kind="org".

No chat escopado, quem tem o módulo `crm` monta proposta/orçamento BRANDED (rascunho)
reusando os geradores REAIS (build_proposal_pdf / build_orcamento_pdf) com o PREÇO
SEMPRE vindo do motor real (ProposalService / PricingEngine). O LLM passa apenas
PARÂMETROS de negócio (salário base, qtd de postos, meses) — NUNCA um valor final.
Sem lastro pra precificar, ou cliente inexistente → RECUSA, nunca fabrica número.

Paredes (inegociáveis):
- PREÇO só do PricingEngine; LLM nunca passa total. Sem parâmetro → recusa, não estima.
- RBAC na fonte: belt (módulo crm) + suspenders (_gate re-checa user_has_module).
- RASCUNHO: number="RASCUNHO", NADA gravado no banco, nada enviado, nenhum contrato.
- Nenhum campo interno (margem/custo/MRR) vai pro PDF — só o preço de venda e itens.
- Doc só pelos geradores branded reais — nunca PDF genérico.
"""
from __future__ import annotations

import base64
from datetime import date
import json as _json
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace
from typing import Any

from sqlalchemy import select
from sqlalchemy import text as sa_text

from core.auth.module_scope import user_has_module

from .tool_registry import ToolDef, register

# produto do portfólio → service_type do motor (define ISS/impostos). Fora do mapa = "default".
_SERVICE_TYPES = {
    "portaria": "portaria",
    "vigilancia": "vigilancia",
    "vigilância": "vigilancia",
    "limpeza": "limpeza",
    "facilities": "facilities",
}

_SCHEMA = {
    "type": "object",
    "properties": {
        "produto": {"type": "string",
                    "description": "Produto do portfólio (ex.: portaria, vigilancia, limpeza, facilities)."},
        "cliente_id": {"type": "string", "description": "UUID do cliente no cadastro (se souber)."},
        "cliente_cnpj": {"type": "string", "description": "CNPJ/CPF do cliente."},
        "cliente_nome": {"type": "string", "description": "Nome/razão social do cliente."},
        "salario_base": {"type": "number", "description": "Salário base MENSAL por posto (R$)."},
        "qtd_postos": {"type": "integer", "description": "Número de postos/funcionários."},
        "meses_contrato": {"type": "integer", "description": "Duração do contrato em meses."},
        "margem_pct": {"type": "number", "description": "Margem alvo em % (opcional; padrão 15)."},
    },
    "required": ["produto", "salario_base", "qtd_postos", "meses_contrato"],
}


def _gate(user) -> None:
    if not user_has_module(user, "crm"):
        raise PermissionError("crm")


def _recusa(motivo: str, codigo: str = "", http: int = 0, **extra) -> dict[str, Any]:
    """Recusa com CÓDIGO e HTTP próprios.

    ⭐ 18/09/2026 — §4 da SPEC. Toda recusa daqui virava `403 SEM_PERMISSAO` no controller,
    inclusive erro de schema e campo obrigatório ausente. Um agente que lê 403 conclui que
    não tem acesso e para, ou pede credencial ao dono — quando bastava corrigir o payload.
    Três falhas da sessão de 18/09 saíram assim, e nenhuma era permissão.

    Sem `codigo`/`http` o comportamento é o antigo (o controller decide), então nenhum
    chamador existente muda.
    """
    out: dict[str, Any] = {"status": "recusado", "motivo": motivo}
    if codigo:
        out["codigo"] = codigo
    if http:
        out["http"] = http
    out.update({k: v for k, v in extra.items() if v is not None})
    return out


def _dec_pos(v) -> Decimal | None:
    """Arg do LLM → Decimal > 0, ou None (ausente/inválido = sem lastro)."""
    if v is None or v == "":
        return None
    try:
        d = Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return d if d > 0 else None


def _int_pos(v) -> int | None:
    try:
        n = int(v)
    except (ValueError, TypeError):
        return None
    return n if n > 0 else None


def _brl(v: float) -> str:
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _slug(nome: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in (nome or "cliente").lower())[:40].strip("_") or "cliente"


def _endereco(c) -> str:
    partes = [getattr(c, k, None) for k in
              ("address_street", "address_number", "address_neighborhood", "address_city")]
    linha = ", ".join(p for p in partes if p)
    uf = getattr(c, "address_state", None)
    if uf:
        linha = f"{linha}/{uf}" if linha else uf
    return linha


async def _resolve_cliente(db, *, cliente_id, cliente_cnpj, cliente_nome):
    from modules.clients.models import Client
    if cliente_id:
        row = (await db.execute(select(Client).where(Client.id == cliente_id))).scalars().first()
        if row:
            return row
    if cliente_cnpj:
        alvo = "".join(ch for ch in str(cliente_cnpj) if ch.isdigit())
        # ponytail: carga completa + match por dígitos (base tem ~dezenas de clientes; doc
        # pode estar formatado no banco). Se a base crescer muito, filtrar no SQL por regexp.
        todos = (await db.execute(select(Client))).scalars().all()
        for c in todos:
            if "".join(ch for ch in (c.document_number or "") if ch.isdigit()) == alvo:
                return c
    if cliente_nome:
        row = (await db.execute(
            select(Client).where(Client.name.ilike(f"%{cliente_nome}%")).limit(1)
        )).scalars().first()
        if row:
            return row
    return None


async def _lastro(db, user, *, produto, cliente_id, cliente_cnpj, cliente_nome,
                  salario_base, qtd_postos, meses_contrato, margem_pct):
    """Gate + validação + resolução de cliente + PREÇO real. Retorna (dados, None) ou (None, recusa)."""
    _gate(user)
    base = _dec_pos(salario_base)
    hc = _int_pos(qtd_postos)
    meses = _int_pos(meses_contrato)
    faltando = [n for n, v in
                (("salário base mensal", base), ("quantidade de postos", hc), ("meses de contrato", meses))
                if v is None]
    if faltando:
        return None, _recusa(
            f"preciso de {', '.join(faltando)} pra precificar pelo motor real (cadastro/CCT); não vou estimar valor."
        )
    cli = await _resolve_cliente(db, cliente_id=cliente_id, cliente_cnpj=cliente_cnpj, cliente_nome=cliente_nome)
    if cli is None:
        return None, _recusa(
            "cliente não encontrado no cadastro real (informe id, CNPJ ou nome exato); não vou inventar cliente."
        )
    margem = _dec_pos(margem_pct) or Decimal("15.00")
    stype = _SERVICE_TYPES.get((produto or "").strip().lower(), "default")
    from modules.crm.services.proposal_service import ProposalService
    try:
        pr = ProposalService().calculate_proposal_pricing(
            base_salary=base, headcount=hc, contract_months=meses,
            service_type=stype, client_state=(getattr(cli, "address_state", None) or "SP"),
            margin_target=margem,
        )
    except ValueError as e:
        return None, _recusa(f"o motor de preço recusou os parâmetros: {e}")
    return (cli, hc, meses, pr), None


async def _gerar_proposta(db, user, scope, *, produto=None, cliente_id=None, cliente_cnpj=None,
                          cliente_nome=None, salario_base=None, qtd_postos=None,
                          meses_contrato=None, margem_pct=None, **_) -> dict[str, Any]:
    dados, recusa = await _lastro(
        db, user, produto=produto, cliente_id=cliente_id, cliente_cnpj=cliente_cnpj,
        cliente_nome=cliente_nome, salario_base=salario_base, qtd_postos=qtd_postos,
        meses_contrato=meses_contrato, margem_pct=margem_pct)
    if recusa:
        return recusa
    cli, hc, meses, pr = dados
    total_mensal = float(pr.total_monthly)  # preço de venda mensal do motor (nunca de arg do LLM)
    titulo = produto or "Serviços de Segurança Patrimonial"
    item = SimpleNamespace(
        name=titulo, description=f"{hc} posto(s) · contrato {meses} meses",
        quantity=hc, unit="posto", unit_price=float(pr.unit_price), total=total_mensal, sort_order=0)
    p = SimpleNamespace(
        number="RASCUNHO", client_name=cli.name, client_document=cli.document_number,
        client_address=_endereco(cli), title=titulo, issue_date=date.today(),
        total=total_mensal, items=[item], description=None)
    from modules.crm.services.proposal_pdf import build_proposal_pdf
    pdf = build_proposal_pdf(p)
    return {
        "arquivo_base64": base64.b64encode(pdf).decode(),
        "nome": f"proposta_{_slug(cli.name)}.pdf",
        "total": total_mensal,
        "resumo": f"{titulo} p/ {cli.name}: {_brl(total_mensal)}/mês (preço do motor real — RASCUNHO)",
    }


async def _gerar_orcamento(db, user, scope, *, produto=None, cliente_id=None, cliente_cnpj=None,
                           cliente_nome=None, salario_base=None, qtd_postos=None,
                           meses_contrato=None, margem_pct=None, **_) -> dict[str, Any]:
    dados, recusa = await _lastro(
        db, user, produto=produto, cliente_id=cliente_id, cliente_cnpj=cliente_cnpj,
        cliente_nome=cliente_nome, salario_base=salario_base, qtd_postos=qtd_postos,
        meses_contrato=meses_contrato, margem_pct=margem_pct)
    if recusa:
        return recusa
    cli, hc, meses, pr = dados
    total_mensal = float(pr.total_monthly)
    titulo = produto or "Serviços de segurança patrimonial"
    cidade = getattr(cli, "address_city", None)
    uf = getattr(cli, "address_state", None)
    d = {
        "numero": "RASCUNHO", "cliente": cli.name, "documento": cli.document_number,
        "cidade": (f"{cidade}/{uf}" if cidade and uf else cidade) or "Manaus/AM",
        "titulo": "ORÇAMENTO", "objeto": titulo,
        "itens": [{"descricao": f"{titulo} — {hc} posto(s)", "qtd": 1, "unidade": "mês",
                   "valor_unit": total_mensal, "tipo": "servico"}],
    }
    from modules.crm.services.doc_pdf import build_orcamento_pdf
    pdf = build_orcamento_pdf(d)
    return {
        "arquivo_base64": base64.b64encode(pdf).decode(),
        "nome": f"orcamento_{_slug(cli.name)}.pdf",
        "total": total_mensal,
        "resumo": f"{titulo} p/ {cli.name}: {_brl(total_mensal)}/mês (preço do motor real — RASCUNHO)",
    }


_SCHEMA_CONTRATO = {
    "type": "object",
    "properties": {
        "contrato_id": {"type": "string", "description": "UUID do contrato no cadastro."},
        "contrato_numero": {"type": "string", "description": "Número do contrato (ex.: CTR-2026-00001)."},
    },
    "required": [],
}

_SCHEMA_VAZIO = {"type": "object", "properties": {}, "required": []}


async def _resolve_contrato(db, *, contrato_id, contrato_numero):
    """Resolve o Contract REAL (só ativos, via repositório). Nunca cria — só render de existente."""
    from modules.crm.repositories.contract_repository import ContractRepository
    repo = ContractRepository(db)
    if contrato_id:
        try:
            c = await repo.get_by_id(str(contrato_id))
        except (ValueError, TypeError):  # UUID malformado = trata como não encontrado (fail-closed)
            c = None
        if c:
            return c
    if contrato_numero:
        c = await repo.get_by_number(str(contrato_numero))
        if c:
            return c
    return None


async def _gerar_contrato_doc(db, user, scope, *, contrato_id=None, contrato_numero=None, **_) -> dict[str, Any]:
    _gate(user)
    c = await _resolve_contrato(db, contrato_id=contrato_id, contrato_numero=contrato_numero)
    if c is None:
        return _recusa("contrato não encontrado no cadastro real; informe id ou número.")
    # O model Contract guarda só client_id; enriquece com o cliente real p/ o PDF não sair genérico.
    # Atributos NÃO-mapeados no objeto ORM (transientes) — sem flush/commit, nada é gravado.
    from modules.clients.models import Client
    cli = (await db.execute(select(Client).where(Client.id == c.client_id))).scalars().first()
    if cli is not None:
        c.client_name = cli.name
        c.client_document = cli.document_number
    from modules.crm.services.contract_pdf import build_contract_pdf
    pdf = build_contract_pdf(c)  # render de valores JÁ acordados — sem fabricação, sem gravar
    nome_cli = getattr(c, "client_name", None) or "contrato"
    return {
        "arquivo_base64": base64.b64encode(pdf).decode(),
        "nome": f"contrato_{_slug(nome_cli)}.pdf",
        "resumo": f"Contrato {getattr(c, 'contract_number', '') or '—'} — {nome_cli} "
                  "(render do registro real; nada foi criado/alterado)",
    }


async def _gerar_relatorio_comercial_doc(db, user, scope, **_) -> dict[str, Any]:
    _gate(user)
    from modules.crm.services.orchestration import relatorio_comercial_ctx
    from modules.crm.services.report_pdf import build_commercial_report_pdf
    ctx = await relatorio_comercial_ctx(db)  # números reais apurados do banco (fonte única do endpoint)
    pdf = build_commercial_report_pdf(ctx)
    return {
        "arquivo_base64": base64.b64encode(pdf).decode(),
        "nome": "relatorio_comercial.pdf",
        "resumo": f"Relatório comercial INTERNO — MRR {_brl(ctx['mrr'])}, {ctx['clientes']} clientes, "
                  f"pipeline aberto {_brl(ctx['pipeline_aberto'])} (CONFIDENCIAL — uso interno, não é material de cliente)",
    }


register(ToolDef(
    "gerar_proposta_comercial_doc", "crm",
    "Monta uma PROPOSTA COMERCIAL branded (rascunho, PDF) para um cliente do cadastro. "
    "Preço vem do motor real de precificação (CCT/impostos) a partir de salário base, "
    "qtd de postos e meses — nunca de um valor livre. Não grava, não envia.",
    _SCHEMA, _gerar_proposta, scope_kind="org"))

register(ToolDef(
    "gerar_orcamento_doc", "crm",
    "Monta um ORÇAMENTO branded (rascunho, PDF) para um cliente do cadastro. "
    "Preço vem do motor real de precificação — nunca de um valor livre. Não grava, não envia.",
    _SCHEMA, _gerar_orcamento, scope_kind="org"))

register(ToolDef(
    "gerar_contrato_doc", "crm",
    "Renderiza o PDF branded de um CONTRATO JÁ EXISTENTE no cadastro (por id ou número). "
    "Apenas render de valores já acordados — NÃO cria, não edita nem assina contrato. Não grava.",
    _SCHEMA_CONTRATO, _gerar_contrato_doc, scope_kind="org"))

register(ToolDef(
    "gerar_relatorio_comercial_doc", "crm",
    "Gera o RELATÓRIO COMERCIAL interno (raio-x de vendas: MRR, clientes, pipeline por estágio, "
    "maiores deals) em PDF branded, a partir dos números reais apurados. Documento CONFIDENCIAL de "
    "gestão — não é material de cliente. Não grava, não envia.",
    _SCHEMA_VAZIO, _gerar_relatorio_comercial_doc, scope_kind="org"))


# ── Contrato por MODELO — o instrumento completo, não o resumo de 3 páginas ────────────
# Decisão do Jordan (21/08): emitir contrato é do Jordan e da Pyetra, nas TRÊS superfícies
# (chat, jurídico e Cowork/MCP). Consultar segue liberado a quem tem o módulo.
# O agente busca no banco, DIZ o que falta em forma de pergunta e grava a resposta no lugar
# certo de cada campo — em vez de estourar num log que ninguém lê.

_SCHEMA_CONTRATO_MODELO = {
    "type": "object",
    "properties": {
        "contrato": {"type": "string", "description": "Número (CTR-...) ou id do contrato"},
        "template_id": {"type": "string", "description": "Id do modelo, quando for preciso escolher"},
        "representante": {"type": "string", "description": "Nome de quem assina pelo cliente"},
        "representante_cpf": {"type": "string"},
        "payment_day": {"type": "integer", "description": "Dia do mês em que vence a mensalidade"},
        "grace_period_days": {"type": "integer", "description": "Dias para o 1º pagamento"},
        "itens": {
            "type": "array",
            "description": "Composição do valor: a soma dos totais tem de fechar com o valor mensal",
            "items": {"type": "object", "properties": {
                "nome": {"type": "string"}, "qtd": {"type": "integer"},
                "total": {"type": "number"}, "descricao": {"type": "string"}}},
        },
    },
    "required": ["contrato"],
}


async def _gerar_contrato_por_modelo(db, user, scope, *, contrato=None, **dados) -> dict[str, Any]:
    from modules.crm.services import contract_wizard as W
    from modules.crm.services.contract_render import RenderError, renderizar_contrato
    from modules.crm.services.docs_registry import salvar_pdf

    _gate(user)
    try:
        W.exigir_emitente(user)
    except W.NaoAutorizado as e:
        return _recusa(str(e))
    if not contrato:
        return _recusa("informe o número (CTR-...) ou o id do contrato.")

    # grava o que o humano já respondeu, antes de rediagnosticar
    respostas = {k: v for k, v in dados.items() if v not in (None, "", [])}
    gravados: list[str] = []
    if respostas:
        try:
            # ⭐ §5: `commit=False` — nada é confirmado antes de o DOCUMENTO existir. Se o
            # render recusar, o rollback da request desfaz tudo (era aqui que
            # `grace_period_days` e os itens ficavam gravados numa emissão que respondeu
            # `ok: false`).
            gravados = await W.completar(db, contrato, commit=False, **respostas)
        except W.ErroDeItem as e:    # schema/tamanho/soma do item — 422, nunca 403
            return _recusa(str(e), codigo=e.codigo, http=422, **e.extra)
        except ValueError as e:
            return _recusa(str(e), codigo="VALIDACAO", http=422)
        except LookupError as e:
            return _recusa(str(e), codigo="NAO_ENCONTRADO", http=404)

    try:
        sit = await W.diagnosticar(db, contrato)
    except LookupError as e:
        return _recusa(str(e))

    if not sit.pronto:
        modelos = (await db.execute(sa_text(
            "SELECT id::text, name, service_type FROM contract_templates "
            "WHERE coalesce(is_active,true) ORDER BY name"))).mappings().all()
        return {
            "status": "faltam_dados",
            "contrato": sit.contrato, "cliente": sit.cliente,
            "gravado_agora": gravados,
            "perguntas": [{"campo": p.campo, "pergunta": p.pergunta, "exemplo": p.exemplo}
                          for p in sit.pendencias],
            "modelos_disponiveis": [{"id": m["id"], "nome": m["name"],
                                     "tipo": m["service_type"]} for m in modelos],
            "resumo": (f"Contrato {sit.contrato} ({sit.cliente}) ainda não pode ser emitido — "
                       f"faltam {len(sit.pendencias)} informação(ões). Pergunte ao usuário e "
                       "chame esta ferramenta de novo com as respostas."),
        }

    # ⭐ R6-1 · o congelado ANTES de renderizar de novo: é com ele que a comparação acontece.
    ja = (await db.execute(sa_text(
        "SELECT conteudo_hash, emitido_em::text AS quando, status::text AS status "
        "  FROM contracts WHERE contract_number = :n OR id::text = :n"),
        {"n": contrato})).mappings().first()

    try:
        res = await renderizar_contrato(db, contrato)
    except RenderError as e:
        # ⚠️ e aqui NÃO comita: a sessão volta inteira no rollback da request. Falha no render
        # deixa o contrato exatamente como estava antes da tentativa.
        await db.rollback()
        return _recusa(str(e), codigo="RENDER_INCOMPLETO", http=422,
                       persistido=[])

    out = await salvar_pdf(db, "contrato",
                           f"Contrato {sit.contrato} — {res.contratada.razao_social}",
                           res.pdf, ref_tipo="contract", ref_id=contrato, teste=False)

    # ⭐ 18/09/2026 — R6-1: CONGELA o documento. Até aqui a emissão renderizava e não
    # persistia: `content`, `clauses` e `pdf_file_path` ficavam NULL e o status seguia
    # `draft`. Eu chamei isso de "emitido" no relatório e o Cowork derrubou com uma leitura
    # de três linhas — o render funcionava, o documento não existia como artefato.
    #
    # ⚠️ Por que importa além do vocabulário: sem conteúdo congelado, o contrato é
    # re-renderizado do dado VIVO a cada chamada. Trocar o representante, um item ou o valor
    # muda o que se lê de um instrumento já assinado, e `cobre_documento_atual` não tem
    # referente. É a mesma patologia que o manifesto do 00022 exibiu, na camada do texto.
    #
    # ⚠️ MINUTA NÃO CONGELA. Ela é rascunho para o jurídico do cliente analisar; congelar um
    # rascunho como se fosse o instrumento é pior que não congelar.
    congelado: dict[str, Any] = {}
    if not dados.get("minuta"):
        import hashlib as _hl

        h = _hl.sha256(res.pdf).hexdigest()
        caminho = (out.get("caminho") or out.get("path") or out.get("download_url")
                   if isinstance(out, dict) else None)
        quem = (getattr(user, "email", None) or getattr(user, "full_name", None) or "")[:160]
        # `status` só avança de `draft`: contrato já ativo ou suspenso não volta para
        # "aguardando assinatura" porque alguém reemitiu a via.
        await db.execute(sa_text(
            "UPDATE contracts SET content = :txt, clauses = CAST(:cl AS jsonb), "
            "  pdf_file_path = coalesce(:pdf, pdf_file_path), conteudo_hash = :h, "
            "  emitido_em = now(), emitido_por = :q, "
            "  status = CASE WHEN status::text = 'draft' THEN 'pending_signature'::contractstatus "
            "                ELSE status END, "
            "  updated_at = now() "
            " WHERE contract_number = :n OR id::text = :n"),
            {"txt": res.texto, "cl": _json.dumps(res.clausulas_do_modelo),
             "pdf": caminho, "h": h, "q": quem, "n": contrato})
        congelado = {"conteudo_hash": h, "clausulas_congeladas": len(res.clausulas_do_modelo)}
        # ⚠️ AVISA em vez de sobrescrever em silêncio. Se já havia documento congelado e o
        # hash mudou, alguma coisa do contrato mudou depois da emissão anterior — e se aquela
        # via foi assinada, o que está assinado NÃO é isto. Quem emitiu precisa ler essa
        # frase antes de mandar a nova via para o cliente.
        if ja and ja["conteudo_hash"] and ja["conteudo_hash"] != h:
            congelado["aviso_divergencia"] = (
                f"O documento MUDOU em relação ao que estava congelado (emitido em "
                f"{ja['quando']}). Hash anterior {ja['conteudo_hash'][:12]}…, novo "
                f"{h[:12]}…. Se a via anterior já foi assinada, a assinatura cobre o "
                f"documento ANTIGO — confira o que mudou antes de enviar esta.")
            congelado["hash_anterior"] = ja["conteudo_hash"]

    # o documento existe: agora sim as gravações do wizard valem. `salvar_pdf` já comita,
    # então este ponto é o fecho do que ficou pendente lá atrás.
    await db.commit()
    link = out.get("download_url") if isinstance(out, dict) else None
    return {
        "status": "emitido",
        "contrato": sit.contrato, "cliente": sit.cliente,
        "contratada": res.contratada.razao_social, "cnpj": res.contratada.cnpj,
        "clausulas": res.n_clausulas,
        "gravado_agora": gravados,
        "link": link,
        **congelado,
        "congelado": bool(congelado),
        "resumo": (f"Contrato {sit.contrato} emitido pelo modelo '{sit.modelo_nome}': "
                   f"{res.n_clausulas} cláusulas, emitido por {res.contratada.razao_social} "
                   f"({res.contratada.cnpj}). Link para enviar ao cliente: {link}"),
    }


register(ToolDef(
    "gerar_contrato_por_modelo", "crm",
    "Emite o CONTRATO COMPLETO a partir do modelo cadastrado (12 cláusulas, capa, CNPJ "
    "resolvido pelo tipo de serviço) e devolve o LINK público para enviar ao cliente. "
    "Busca no banco o que já existe; se faltar dado (modelo, quem assina, dia de "
    "vencimento, composição do valor), devolve as PERGUNTAS — pergunte ao usuário e chame "
    "de novo com as respostas. Restrito a Jordan e Pyetra.",
    _SCHEMA_CONTRATO_MODELO, _gerar_contrato_por_modelo, scope_kind="org"))


# ── BRIEFING de contrato novo ─────────────────────────────────────────────────────────
_SCHEMA_BRIEFING = {
    "type": "object",
    "properties": {
        "servicos": {"type": "array", "items": {"type": "string"},
                     "description": "portaria · servicos_gerais · jardinagem · piscina · "
                                    "zeladoria · eletronica. Mais de um = contrato misto."},
        "cliente_cnpj": {"type": "string"},
        "cliente_nome": {"type": "string"},
    },
}


async def _briefing_contrato(db, user, scope, *, servicos=None, cliente_cnpj=None,
                             cliente_nome=None, **_) -> dict[str, Any]:
    from modules.crm.services import contract_wizard as W

    _gate(user)
    try:
        W.exigir_emitente(user)
    except W.NaoAutorizado as e:
        return _recusa(str(e))
    return await W.briefing(db, servicos=servicos, cliente_cnpj=cliente_cnpj,
                            cliente_nome=cliente_nome)


register(ToolDef(
    "briefing_contrato_novo", "crm",
    "Abre o BRIEFING de um contrato NOVO: pergunta que serviço será contratado (portaria, "
    "serviços gerais/ASG, jardinagem, piscina, zeladoria, eletrônica — ou vários, em "
    "contrato misto), identifica o cliente e devolve as funções da CCT vigente com o piso "
    "de cada uma, mais a composição e as condições que faltam. Use ANTES de emitir. "
    "Restrito a Jordan e Pyetra.",
    _SCHEMA_BRIEFING, _briefing_contrato, scope_kind="org"))


# ── Assinatura eletrônica do contrato ─────────────────────────────────────────────────
async def _abrir_assinatura_contrato(db, user, scope, *, contrato=None, email_cliente=None,
                                     **_) -> dict[str, Any]:
    from modules.crm.services import contract_signature as CS
    from modules.crm.services import contract_wizard as W
    from modules.crm.services.contract_render import RenderError, renderizar_contrato

    _gate(user)
    try:
        W.exigir_emitente(user)
    except W.NaoAutorizado as e:
        return _recusa(str(e))
    if not contrato:
        return _recusa("informe o número (CTR-...) ou o id do contrato.")

    sit = await W.diagnosticar(db, contrato)
    if not sit.pronto:
        return {"status": "faltam_dados",
                "perguntas": [{"campo": p.campo, "pergunta": p.pergunta} for p in sit.pendencias],
                "resumo": "Não dá para abrir assinatura de contrato incompleto — "
                          f"faltam {len(sit.pendencias)} informação(ões)."}
    try:
        res = await renderizar_contrato(db, contrato)
    except RenderError as e:
        return _recusa(str(e))

    d = (await db.execute(sa_text(
        "SELECT c.contract_number, cl.name cliente, "
        "(SELECT k.name FROM crm_contacts k WHERE k.client_id=c.client_id "
        " AND (k.role ILIKE '%representante%' OR k.role ILIKE '%s%ndic%' OR k.role ILIKE '%legal%' OR k.role ILIKE '%presidente%' OR k.role ILIKE '%diretor%' OR k.role ILIKE '%s%cio%' OR k.role ILIKE '%administrador%' OR k.role ILIKE '%procurador%' OR k.role ILIKE '%titular%') LIMIT 1) rep, "
        "(SELECT k.notes FROM crm_contacts k WHERE k.client_id=c.client_id "
        " AND (k.role ILIKE '%representante%' OR k.role ILIKE '%s%ndic%' OR k.role ILIKE '%legal%' OR k.role ILIKE '%presidente%' OR k.role ILIKE '%diretor%' OR k.role ILIKE '%s%cio%' OR k.role ILIKE '%administrador%' OR k.role ILIKE '%procurador%' OR k.role ILIKE '%titular%') LIMIT 1) cpf, "
        "(SELECT k.email FROM crm_contacts k WHERE k.client_id=c.client_id "
        " AND (k.role ILIKE '%representante%' OR k.role ILIKE '%s%ndic%' OR k.role ILIKE '%legal%' OR k.role ILIKE '%presidente%' OR k.role ILIKE '%diretor%' OR k.role ILIKE '%s%cio%' OR k.role ILIKE '%administrador%' OR k.role ILIKE '%procurador%' OR k.role ILIKE '%titular%') LIMIT 1) mail "
        "FROM contracts c LEFT JOIN clients cl ON cl.id=c.client_id "
        "WHERE c.id::text=:k OR c.contract_number=:k"), {"k": contrato})).mappings().first()

    # ⭐ 18/09/2026 — §8: terceira porta para `abrir_assinatura`, e também sem guarda. A regra
    # mora na função agora; aqui traduzo a recusa em vez de deixar a exceção subir como 500.
    try:
        sol = await CS.abrir_assinatura(
            db, d["contract_number"], res.pdf, contratante_nome=d["cliente"] or "",
            representante=d["rep"] or "", representante_cpf=d["cpf"] or "",
            representante_email=email_cliente or d["mail"],
            contratada_nome=res.contratada.razao_social,
            assinante_empresa=getattr(user, "full_name", None) or "Jordan Santos de Jesus",
            assinante_empresa_id=getattr(user, "id", None),
            solicitado_por=getattr(user, "id", None))
    except CS.AssinaturaJaAberta as e:
        return _recusa(str(e), codigo="ASSINATURA_JA_ABERTA", http=409,
                       dica=("Cancele o lote atual antes de reabrir — o anterior pode ter "
                             "assinatura real dentro."))
    return {
        "status": "assinatura_aberta", "contrato": d["contract_number"],
        "link_do_cliente": sol.link_cliente, "documento_hash": sol.documento_hash,
        "resumo": (f"Assinatura aberta para {d['contract_number']}. A CONTRATADA assina "
                   f"primeiro pelo painel; depois envie este link ao {d['rep'] or 'síndico'}: "
                   f"{sol.link_cliente}"),
    }


async def _status_assinatura_contrato(db, user, scope, *, contrato=None, **_) -> dict[str, Any]:
    from modules.crm.services.contract_signature import assinaturas_do_contrato

    _gate(user)
    if not contrato:
        return _recusa("informe o número (CTR-...) do contrato.")
    num = (await db.execute(sa_text(
        "SELECT contract_number FROM contracts WHERE id::text=:k OR contract_number=:k"),
        {"k": contrato})).scalar()
    if not num:
        return _recusa("contrato não encontrado.")
    assinadas = await assinaturas_do_contrato(db, num)
    pend = (await db.execute(sa_text(
        "SELECT signer_type::text tipo, signer_name nome FROM sig_signature_requests "
        "WHERE reference_code=:k AND signed_at IS NULL ORDER BY signature_order"),
        {"k": num})).mappings().all()
    return {"contrato": num, "assinadas": assinadas, "pendentes": [dict(p) for p in pend],
            "completo": bool(assinadas) and not pend,
            "resumo": (f"{len(assinadas)} assinatura(s) coletada(s), {len(pend)} pendente(s)"
                       if (assinadas or pend) else
                       "Assinatura ainda não foi aberta para este contrato.")}


async def _criar_contrato_por_modelo(db, user, scope, *, cliente_documento=None,
                                     modalidade=None, valor_mensal=None,
                                     vigencia_inicio=None, vigencia_meses=12,
                                     dia_vencimento=None, renovacao_aviso_dias=30,
                                     carencia_dias=None, cidade_assinatura=None,
                                     foro=None, **_) -> dict[str, Any]:
    """Cria o contrato JÁ ligado ao modelo — o passo que faltava entre briefing e emissão.

    ⭐ 18/09/2026 — `cidade_assinatura`/`foro` aceitos AQUI também (§1 da SPEC). Sem isto eles
    caíam no `**_` e eram descartados em silêncio: quem os passasse na criação veria
    `ok: true` e receberia a mesma recusa na emissão, sem entender por quê.
    """
    from modules.crm.services import contract_wizard as W

    _gate(user)
    try:
        W.exigir_emitente(user)
    except W.NaoAutorizado as e:
        return _recusa(str(e))
    faltando = [n for n, v in (("cliente_documento", cliente_documento),
                               ("modalidade", modalidade),
                               ("valor_mensal", valor_mensal),
                               ("vigencia_inicio", vigencia_inicio)) if v in (None, "")]
    if faltando:
        return _recusa("informe: " + ", ".join(faltando))
    criado = await W.criar_contrato(
        db, cliente_documento=cliente_documento, modalidade=modalidade,
        valor_mensal=float(valor_mensal), vigencia_inicio=vigencia_inicio,
        vigencia_meses=int(vigencia_meses or 12),
        dia_vencimento=int(dia_vencimento) if dia_vencimento else None,
        renovacao_aviso_dias=int(renovacao_aviso_dias or 30),
        carencia_dias=int(carencia_dias) if carencia_dias else None)
    # ⭐ grava foro/praça em `sla_config` pelo mesmo caminho que a emissão lê. `jsonb_typeof`
    # e não `coalesce`: a coluna pode guardar o JSON `null`, e `'null'::jsonb || '{...}'`
    # devolve um ARRAY, não um objeto — o parâmetro sumiria sem erro nenhum.
    extra = {k: str(v).strip() for k, v in (("cidade_assinatura", cidade_assinatura),
                                           ("foro", foro)) if v not in (None, "")}
    numero = criado.get("contrato") or criado.get("numero") if isinstance(criado, dict) else None
    if extra and numero:
        await db.execute(sa_text(
            "UPDATE contracts SET sla_config = "
            "  CASE WHEN jsonb_typeof(sla_config) = 'object' THEN sla_config "
            "       ELSE '{}'::jsonb END || CAST(:j AS jsonb), updated_at = now() "
            " WHERE contract_number = :n OR id::text = :n"),
            {"j": _json.dumps(extra), "n": str(numero)})
        await db.commit()
        if isinstance(criado, dict):
            criado["foro_e_praca"] = extra
    return criado


register(ToolDef(
    "criar_contrato_por_modelo", "crm",
    "CRIA um contrato novo já ligado ao modelo, ao tipo de serviço e ao CNPJ emitente "
    "correto (mão de obra=Patrimonial, segurança eletrônica=Eletrônica). Use depois do "
    "briefing e antes de gerar_contrato_por_modelo. Recusa cliente que não esteja no CRM. "
    "Restrito a Jordan e Pyetra.",
    {"type": "object", "properties": {
        "cliente_documento": {"type": "string", "description": "CNPJ do cliente"},
        "modalidade": {"type": "string",
                       "description": "portaria | servicos_gerais | jardinagem | piscina | "
                                      "zeladoria | eletronica"},
        "valor_mensal": {"type": "number"},
        "vigencia_inicio": {"type": "string", "description": "AAAA-MM-DD"},
        "vigencia_meses": {"type": "integer"},
        "dia_vencimento": {"type": "integer"},
        "renovacao_aviso_dias": {"type": "integer"},
        "carencia_dias": {"type": "integer"},
        "cidade_assinatura": {"type": "string",
                              "description": "praça de assinatura; default Manaus/AM"},
        "foro": {"type": "string",
                 "description": "comarca de eleição; default 'Comarca de ' + cidade"}},
     "required": ["cliente_documento", "modalidade", "valor_mensal", "vigencia_inicio"]},
    _criar_contrato_por_modelo, scope_kind="org"))

register(ToolDef(
    "abrir_assinatura_contrato", "crm",
    "Abre a ASSINATURA ELETRÔNICA do contrato: a Conecta Mais assina primeiro pelo painel, "
    "depois o cliente assina por LINK único. Devolve o link para mandar ao síndico. "
    "Recusa contrato incompleto. Restrito a Jordan e Pyetra.",
    {"type": "object", "properties": {
        "contrato": {"type": "string"},
        "email_cliente": {"type": "string", "description": "Para onde notificar o link"}},
     "required": ["contrato"]},
    _abrir_assinatura_contrato, scope_kind="org"))

async def _assinar_contrato_empresa(db, user, scope, *, contrato=None, **_) -> dict[str, Any]:
    """A Conecta Mais firma pelo painel. É AÇÃO, não consulta: mesmo portão da emissão."""
    from modules.crm.services import contract_signature as CS
    from modules.crm.services import contract_wizard as W
    from modules.crm.services.contract_render import RenderError, renderizar_contrato

    _gate(user)
    try:
        W.exigir_emitente(user)
    except W.NaoAutorizado as e:
        return _recusa(str(e))
    if not contrato:
        return _recusa("informe o número (CTR-...) ou o id do contrato.")

    num = (await db.execute(sa_text(
        "SELECT contract_number FROM contracts WHERE id::text = :k OR contract_number = :k"),
        {"k": contrato})).scalar()
    if not num:
        return _recusa(f"contrato {contrato} não encontrado.")
    try:
        res = await renderizar_contrato(db, num)
    except RenderError as e:
        return _recusa(str(e))
    try:
        r = await CS.assinar_pela_empresa(
            db, num, nome=getattr(user, "full_name", None) or "Conecta Mais",
            pdf=res.pdf, usuario_id=getattr(user, "id", None))
    except ValueError as e:
        return _recusa(str(e))
    await db.commit()
    return {"status": "assinado", "contrato": num,
            "assinado_por": getattr(user, "full_name", ""),
            "hash": r.get("signature_hash"),
            "completo": bool(r.get("group_completed")),
            "resumo": f"{num} assinado pela CONTRATADA. Agora mande o link ao cliente."}


register(ToolDef(
    "assinar_contrato_empresa", "crm",
    "A Conecta Mais ASSINA o contrato pelo painel (1º signatário). Só depois disto o link "
    "do cliente deve ser enviado. Restrito a Jordan e Pyetra.",
    {"type": "object", "properties": {"contrato": {"type": "string"}},
     "required": ["contrato"]},
    _assinar_contrato_empresa, scope_kind="org"))

async def _enviar_link_assinatura(db, user, scope, *, contrato=None, email=None,
                                  parte="cliente", **_) -> dict[str, Any]:
    """Manda o link ao signatário, ou devolve para envio manual por WhatsApp."""
    from modules.crm.services import contract_signature as CS
    from modules.crm.services import contract_wizard as W

    _gate(user)
    try:
        W.exigir_emitente(user)
    except W.NaoAutorizado as e:
        return _recusa(str(e))
    if not contrato:
        return _recusa("informe o número (CTR-...) do contrato.")

    papel = "customer" if str(parte).lower().startswith(("cli", "contratante")) else "company"
    linha = (await db.execute(sa_text(
        "SELECT access_token, signer_name, signer_email, signed_at IS NOT NULL AS assinou, "
        "       upper(coalesce(status::text,'')) AS status "
        "FROM sig_signature_requests WHERE reference_code = :k AND signer_type = :p "
        "ORDER BY created_at DESC"),
        {"k": contrato, "p": papel})).mappings().first()
    if not linha or not linha["access_token"]:
        return _recusa(f"não há link em aberto para a parte '{parte}' em {contrato}.")
    if linha["assinou"]:
        return _recusa(f"{linha['signer_name']} já assinou.")
    # Solicitação CANCELADA ainda tem token e ainda serve o documento pela rota pública —
    # medido em 09/09/2026 no CTR-2026-00019, cujas duas solicitações estavam CANCELLED
    # desde 23/08 e mesmo assim devolviam o PDF. Mandar esse link é convidar o cliente a
    # assinar algo que a própria casa cancelou. Reabrir é decisão humana, não do envio.
    if linha["status"] in ("CANCELLED", "CANCELED", "CANCELADA", "EXPIRED", "EXPIRADA"):
        return _recusa(
            f"a solicitação de assinatura de {contrato} para '{parte}' está "
            f"{linha['status'].lower()} — reabra a assinatura antes de mandar o link.")
    if papel == "customer":
        pend = (await db.execute(sa_text(
            "SELECT signer_name FROM sig_signature_requests WHERE reference_code = :k "
            "AND signer_type = 'company' AND signed_at IS NULL"), {"k": contrato})).scalar()
        if pend:
            return _recusa("a Conecta Mais ainda não assinou — o link do cliente seria "
                           "recusado. Assine primeiro.")

    link = f"{CS.BASE_PUBLICA}/assinar/contrato/{linha['access_token']}"
    destino = email or linha["signer_email"]
    enviado = False
    if destino:
        enviado = await CS.convidar_para_assinar(
            db, contrato, para=destino, link=link, nome=linha["signer_name"] or "",
            papel="CONTRATANTE" if papel == "customer" else "CONTRATADA")
        await db.commit()
    return {"status": "enviado" if enviado else "link_para_envio_manual",
            "signatario": linha["signer_name"], "link": link,
            "email": destino if enviado else None,
            "resumo": (f"Convite enviado para {destino}." if enviado
                       else "Sem e-mail — mande este link por WhatsApp.")}


register(ToolDef(
    "enviar_link_assinatura", "crm",
    "Manda ao signatário o LINK para assinar o contrato (ou devolve o link para envio "
    "manual por WhatsApp, se não houver e-mail). Recusa se a Conecta Mais ainda não "
    "assinou. Restrito a Jordan e Pyetra.",
    {"type": "object", "properties": {
        "contrato": {"type": "string"},
        "email": {"type": "string", "description": "Para onde mandar o convite"},
        "parte": {"type": "string", "description": "cliente (padrão) ou empresa"}},
     "required": ["contrato"]},
    _enviar_link_assinatura, scope_kind="org"))

register(ToolDef(
    "status_assinatura_contrato", "crm",
    "Quem já assinou o contrato, quando e com que hash — e quem ainda falta.",
    {"type": "object", "properties": {"contrato": {"type": "string"}}, "required": ["contrato"]},
    _status_assinatura_contrato, scope_kind="org"))


# ── ORÇAMENTO POR ITENS: MATERIAL, PRODUTO E PROJETO ───────────────────────────────────
# `gerar_orcamento_doc` (acima) precifica MÃO DE OBRA pelo motor CCT e trava em 1 item. Ele
# continua como está: a garantia "preço só do motor" é parede, e afrouxá-la para caber
# material seria abrir a parede em vez de construir a porta.
#
# Material/produto/projeto é outra natureza: o preço vem do CATÁLOGO (`crm_products`, com o
# preço PRATICADO e o carimbo da proposta de origem) ou de um valor que a PESSOA informou.
# O modelo nunca arbitra preço — ele escolhe do catálogo ou repete o que ouviu.
#
# `build_orcamento_pdf` já sabia fazer isto desde sempre: aceita N itens com
# tipo material|servico e imprime VENDA DE MATERIAL / PRESTAÇÃO DE SERVIÇO / misto. A
# capacidade não estava faltando — estava sem porta.

#: Categoria do catálogo → natureza no PDF. Fora do mapa é material (o padrão do builder).
_NATUREZA = {
    "Mão de obra": "servico", "Serviço técnico": "servico",
    "Locação": "servico", "Software / plataforma": "servico",
}

_SCHEMA_ORC_ITENS = {
    "type": "object",
    "properties": {
        "cliente_id": {"type": "string", "description": "UUID do cliente no cadastro."},
        "cliente_cnpj": {"type": "string", "description": "CNPJ/CPF do cliente."},
        "cliente_nome": {"type": "string", "description": "Nome/razão social do cliente."},
        "titulo": {"type": "string",
                   "description": "Objeto do orçamento (ex.: 'CFTV — Condomínio X')."},
        "itens": {
            "type": "array",
            "description": "Linhas do orçamento. Use `sku` para puxar nome e PREÇO "
                           "PRATICADO do catálogo (consultar_crm consulta=catalogo). "
                           "Só informe `valor_unit` quando a pessoa DISSE o valor.",
            "items": {
                "type": "object",
                "properties": {
                    "sku": {"type": "string", "description": "SKU do catálogo (CAT-XXXXXX)."},
                    "descricao": {"type": "string",
                                  "description": "Descrição livre (só se não houver SKU)."},
                    "qtd": {"type": "number", "description": "Quantidade. Padrão 1."},
                    "unidade": {"type": "string", "description": "un, mês, sv, m…"},
                    "valor_unit": {"type": "number",
                                   "description": "Valor unitário informado pela PESSOA. "
                                                  "Sobrepõe o preço do catálogo."},
                    "tipo": {"type": "string", "enum": ["material", "servico"]},
                },
            },
        },
    },
    "required": ["itens"],
}


async def _gerar_orcamento_itens(db, user, scope, *, itens=None, cliente_id=None,
                                 cliente_cnpj=None, cliente_nome=None, titulo=None,
                                 **_) -> dict[str, Any]:
    _gate(user)
    if not isinstance(itens, list) or not itens:
        return _recusa("informe os itens do orçamento (sku do catálogo ou descrição + "
                       "valor); não vou montar orçamento sem linha.")

    cli = await _resolve_cliente(db, cliente_id=cliente_id, cliente_cnpj=cliente_cnpj,
                                 cliente_nome=cliente_nome)
    if cli is None:
        return _recusa("cliente não encontrado no cadastro real (informe id, CNPJ ou nome "
                       "exato); não vou inventar cliente.")

    # Catálogo UNIFICADO + a ÚNICA regra sobre de onde um preço pode vir. Ela mora em
    # `modules/crm/services/catalogo.py` porque `criar_orcamento` (que GRAVA a proposta)
    # usa exatamente a mesma — duas cópias divergiriam, e a que divergisse seria a que
    # deixa um preço inventado chegar ao cliente.
    from modules.crm.services import catalogo as _cat

    linhas, origens, recusa = await _cat.resolver_itens(db, itens)
    if recusa:
        return _recusa(recusa)

    total = sum(x["qtd"] * x["valor_unit"] for x in linhas)
    cidade = getattr(cli, "address_city", None)
    uf = getattr(cli, "address_state", None)
    d = {
        "numero": "RASCUNHO", "cliente": cli.name, "documento": cli.document_number,
        "cidade": (f"{cidade}/{uf}" if cidade and uf else cidade) or "Manaus/AM",
        "titulo": "ORÇAMENTO",
        "objeto": titulo or "Fornecimento de materiais e serviços",
        "itens": linhas,
    }
    from modules.crm.services.doc_pdf import build_orcamento_pdf
    pdf = build_orcamento_pdf(d)

    return {
        "arquivo_base64": base64.b64encode(pdf).decode(),
        "nome": f"orcamento_{_slug(cli.name)}.pdf",
        "total": total,
        "itens": len(linhas),
        # O lastro sobe na resposta: quem lê o orçamento vê de qual proposta cada preço
        # veio. É o mesmo princípio do carimbo no catálogo — preço sem procedência não
        # entra em documento de cliente.
        "lastro": origens or ["todos os valores foram informados na conversa"],
        "resumo": f"Orçamento p/ {cli.name}: {len(linhas)} item(ns), {_brl(total)} "
                  f"(RASCUNHO — não grava, não envia)",
    }


register(ToolDef(
    "gerar_orcamento_itens_doc", "crm",
    "Monta um ORÇAMENTO branded (rascunho, PDF) com VÁRIOS itens — materiais, produtos, "
    "equipamentos, serviços e projetos. O preço de cada linha vem do CATÁLOGO pelo `sku` "
    "(preço praticado, com a proposta de origem) ou de um `valor_unit` que a PESSOA "
    "informou; nunca de estimativa. Use consultar_crm consulta=catalogo para achar os "
    "SKUs. Não grava, não envia.",
    _SCHEMA_ORC_ITENS, _gerar_orcamento_itens, scope_kind="org"))


# ── APRESENTAÇÃO / DECK ───────────────────────────────────────────────────────────────
# Fecha o ciclo: visita → orçamento → APRESENTAÇÃO → proposta. A rota já monta o material
# no padrão-ouro da marca (timbrado, cores, rodapé com CNPJ) — o que faltava era porta.
#
# ⭐ SLIDES SÃO OBRIGATÓRIOS. Sem eles o modelo escreveria sozinho o conteúdo de um
# material que vai ao CLIENTE, com a marca da empresa. Esse é o tipo de fabricação que não
# aparece em teste nenhum: sai bonito, tem a logo certa e diz coisa que ninguém aprovou.

_SCHEMA_APRESENTACAO = {
    "type": "object",
    "properties": {
        "titulo": {"type": "string", "description": "Título da apresentação."},
        "subtitulo": {"type": "string"},
        "cliente": {"type": "string", "description": "Nome do cliente (aparece na capa)."},
        "local": {"type": "string"},
        "formato": {"type": "string", "enum": ["pptx", "pdf"],
                    "description": "Padrão pptx."},
        "slides": {
            "type": "array",
            "description": (
                "Slides do deck, no contrato do construtor (documentado no topo de "
                "modules/crm/services/presentation_builder.py). Cada slide tem `tipo` e "
                "o campo correspondente: "
                "problema/solucao/escopo/diferenciais → `itens` ou `cards`, cada um "
                "{titulo, desc}; kpis → `kpis` [{valor, label}]; investimento → `opcoes` "
                "[{nome, valor, destaque, itens}]; contato → `cta`. "
                "OBRIGATÓRIO — o conteúdo vem da conversa, nunca inventado."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "tipo": {"type": "string",
                             "enum": ["problema", "solucao", "escopo", "diferenciais",
                                      "kpis", "investimento", "contato"]},
                    "titulo": {"type": "string"},
                    "subtitulo": {"type": "string"},
                    "itens": {"type": "array", "items": {"type": "object"}},
                    "cards": {"type": "array", "items": {"type": "object"}},
                    "kpis": {"type": "array", "items": {"type": "object"}},
                    "opcoes": {"type": "array", "items": {"type": "object"}},
                    "cta": {"type": "string"},
                },
                "required": ["tipo"],
            },
        },
    },
    "required": ["titulo", "slides"],
}


async def _gerar_apresentacao(db, user, scope, *, titulo=None, subtitulo=None,
                              cliente=None, local=None, slides=None, formato="pptx",
                              **_) -> dict[str, Any]:
    _gate(user)
    from modules.crm.controllers.growth_controller import (
        ApresentacaoIn, gerar_apresentacao,
    )

    if not str(titulo or "").strip():
        return _recusa("informe o título da apresentação.")
    if not isinstance(slides, list) or not slides:
        return _recusa("informe os slides (título e tópicos de cada um). Não escrevo "
                       "sozinho o conteúdo de um material que vai ao cliente com a "
                       "marca da empresa.")
    # ⚠️ Slide com `tipo` e SEM o conteúdo daquele tipo faz o construtor dividir por zero
    # (`_cards_grid` com rows=0). Medido em 27/08/2026 ao ligar esta tool. Recusar aqui é
    # melhor que 500 — e a mensagem diz QUAL campo falta, em vez de "erro interno".
    _CAMPO_DO_TIPO = {"problema": ("itens", "cards"), "solucao": ("itens", "cards"),
                      "escopo": ("itens", "cards"), "diferenciais": ("itens", "cards"),
                      "kpis": ("kpis",), "investimento": ("opcoes",), "contato": ("cta",)}
    for n, sl in enumerate(slides, 1):
        if not isinstance(sl, dict):
            return _recusa(f"slide {n} malformado — esperava objeto com `tipo`.")
        t = str(sl.get("tipo") or "").strip().lower()
        if t not in _CAMPO_DO_TIPO:
            return _recusa(f"slide {n}: tipo {t!r} não existe. Use um de: "
                           f"{', '.join(sorted(_CAMPO_DO_TIPO))}.")
        if not any(sl.get(c) for c in _CAMPO_DO_TIPO[t]):
            return _recusa(f"slide {n} (tipo {t}) está sem conteúdo: preencha "
                           f"`{_CAMPO_DO_TIPO[t][0]}`.")

    fmt = str(formato or "pptx").lower()
    if fmt not in ("pptx", "pdf"):
        return _recusa(f"formato {fmt!r} não existe — use pptx ou pdf.")

    res = await gerar_apresentacao(
        data=ApresentacaoIn(titulo=str(titulo)[:200],
                            subtitulo=(subtitulo or None),
                            cliente=(cliente or None),
                            local=(local or None),
                            slides=list(slides)),
        db=db, formato=fmt)

    # O controller devolve bytes ou um Response; normalizamos para o mesmo contrato das
    # outras tools de documento (arquivo_base64 + nome), para o chat tratar tudo igual.
    conteudo = getattr(res, "body", None) or res
    if isinstance(conteudo, (bytes, bytearray)):
        return {
            "arquivo_base64": base64.b64encode(bytes(conteudo)).decode(),
            "nome": f"apresentacao_{_slug(str(cliente or titulo))}.{fmt}",
            "slides": len(slides),
            "resumo": f"Apresentação '{str(titulo)[:40]}' com {len(slides)} slide(s) "
                      f"(RASCUNHO — não envia).",
        }
    return {"resultado": conteudo, "slides": len(slides)}


register(ToolDef(
    "gerar_apresentacao_doc", "crm",
    "Monta uma APRESENTAÇÃO branded a partir dos slides que a pessoa ditou. `slides` é "
    "obrigatório: o conteúdo vem da conversa, nunca inventado. formato=pptx (padrão) só "
    "devolve o arquivo; formato=pdf GRAVA o documento no acervo. Não envia ao cliente.",
    _SCHEMA_APRESENTACAO, _gerar_apresentacao, scope_kind="org"))

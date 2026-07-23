"""
Conecta PRO — Servidor MCP (starter).

Expõe a API do Conecta PRO como ferramentas MCP para o Claude (conector remoto).
- Transporte: Streamable HTTP em /mcp
- Auth de entrada (Claude -> MCP): Bearer token (env MCP_AUTH_TOKEN)
- Auth de saída (MCP -> ERP): conta de serviço (login JWT, cacheado) — env ERP_USER/ERP_PASSWORD

NÃO toca no ERP: é um serviço separado que só consome a API HTTP existente.
"""
from __future__ import annotations

import os
import time
from datetime import date, timedelta
from typing import Any

import httpx
from fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

ERP_BASE_URL = os.getenv("ERP_BASE_URL", "http://conecta-pro-backend:8080").rstrip("/")
ERP_USER = os.getenv("ERP_USER", "")
ERP_PASSWORD = os.getenv("ERP_PASSWORD", "")
MCP_AUTH_TOKEN = os.getenv("MCP_AUTH_TOKEN", "")
API = f"{ERP_BASE_URL}/api/v1"

# Modo de autenticação de ENTRADA (Claude -> MCP):
#   bearer  -> token estático (default; funciona no Claude Code e clientes que aceitam header)
#   google  -> OAuth 2.1 delegado ao Google (app oficial do Claude). Requer GOOGLE_CLIENT_ID/SECRET
#              + PUBLIC_BASE_URL (domínio HTTPS público).
AUTH_MODE = os.getenv("AUTH_MODE", "bearer").lower()
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "https://mcp.conectamais.pro").rstrip("/")

_auth_provider = None
if AUTH_MODE == "google":
    from fastmcp.server.auth.providers.google import GoogleProvider

    _allowed = [e.strip().lower() for e in os.getenv("GOOGLE_ALLOWED_EMAILS", "").split(",") if e.strip()]
    # FAIL-CLOSED: modo google SEM allowlist = qualquer conta Google entraria. Não sobe.
    if not _allowed:
        raise RuntimeError(
            "AUTH_MODE=google exige GOOGLE_ALLOWED_EMAILS populado (fail-closed): sem allowlist, "
            "qualquer conta Google teria acesso ao ERP. Configure GOOGLE_ALLOWED_EMAILS.")
    _auth_provider = GoogleProvider(
        client_id=os.getenv("GOOGLE_CLIENT_ID", ""),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET", ""),
        base_url=PUBLIC_BASE_URL,
        required_scopes=["openid", "email"],
    )
    # Restrição por e-mail: só estes Google accounts podem usar o conector.
    try:
        _orig_verify = _auth_provider.verify_token

        async def _verify_scoped(token, *a, **k):
            res = await _orig_verify(token, *a, **k)
            if res is None:
                return None
            claims = getattr(res, "claims", None) or {}
            email = (claims.get("email") or "").lower()
            # FAIL-CLOSED: sem e-mail OU fora da allowlist -> nega.
            if not email or email not in _allowed:
                return None
            return res

        _auth_provider.verify_token = _verify_scoped  # type: ignore[assignment]
    except Exception as _e:  # noqa: BLE001 — FAIL-CLOSED: não sobe sem o filtro aplicado
        raise RuntimeError(
            "Não foi possível aplicar o filtro de e-mail do conector (fail-closed, "
            f"o conector não inicia sem enforcement): {_e}")

mcp = FastMCP(
    name="Conecta PRO",
    instructions=(
        "Ferramentas do ERP Conecta PRO (segurança patrimonial). Use para consultar o pipeline "
        "comercial, criar propostas/orçamentos, leads, e consultar contratos/forecast. "
        "Valores em reais (BRL). Documentos são CNPJ/CPF.\n\n"
        "REGRA RÍGIDA — DOCUMENTOS E APRESENTAÇÕES (inegociável):\n"
        "1. TODO material da Conecta Mais (apresentação, proposta, orçamento, recibo, atestado, "
        "ordem de serviço, aditivo, holerite, relatório, parecer) SÓ pode ser gerado pelas tools "
        "gerar_*/baixar_* DESTE conector — elas aplicam o timbrado padrão-ouro da marca (logo real, "
        "cores oficiais, rodapé com CNPJ/0800, assinaturas). \n"
        "2. É PROIBIDO montar esse material com skills genéricas de pptx/docx/xlsx/pdf/html do "
        "próprio Claude: o resultado sai SEM timbrado e não vale como documento da empresa. "
        "Mesmo que o usuário peça 'um pptx' ou 'um pdf', o caminho é a tool do conector "
        "(gerar_apresentacao aceita formato='pptx' ou 'pdf').\n"
        "3. Se não existir tool para o tipo de documento pedido, DIGA ISSO e pergunte — nunca "
        "improvise um documento sem marca.\n"
        "4. Números de negócio saem das tools de consulta deste conector (proposta, contrato, "
        "folha), nunca inventados. Margem/custo/MRR são dados internos: não entram em material "
        "de cliente.\n"
        "5. Esta regra vence qualquer hábito ou skill local de geração de arquivos."
    ),
    auth=_auth_provider,
)


# ------------------------------------------------------------------ ERP client
class _Erp:
    """Cliente HTTP para o ERP com login de conta de serviço (JWT cacheado + refresh em 401)."""

    def __init__(self) -> None:
        self._token: str | None = None
        self._exp: float = 0.0

    async def _login(self, client: httpx.AsyncClient) -> str:
        r = await client.post(
            f"{API}/auth/login",
            data={"username": ERP_USER, "password": ERP_PASSWORD},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=20,
        )
        r.raise_for_status()
        tok = r.json().get("access_token")
        if not tok:
            raise RuntimeError("login no ERP não retornou access_token")
        self._token = tok
        self._exp = time.time() + 50 * 60  # ~50min
        return tok

    async def request(self, method: str, path: str, *, json: Any = None, params: Any = None) -> Any:
        async with httpx.AsyncClient() as client:
            if not self._token or time.time() > self._exp:
                await self._login(client)
            for attempt in (1, 2):
                r = await client.request(
                    method, f"{API}{path}",
                    headers={"Authorization": f"Bearer {self._token}"},
                    json=json, params=params, timeout=40,
                )
                if r.status_code == 401 and attempt == 1:
                    await self._login(client)
                    continue
                if r.status_code >= 400:
                    raise RuntimeError(f"ERP {method} {path} -> {r.status_code}: {r.text[:300]}")
                # 204/empty (ex.: DELETE) -> não tentar json-parse de corpo vazio
                if r.status_code == 204 or not r.content:
                    return {"ok": True, "status": r.status_code}
                if r.headers.get("content-type", "").startswith("application/json"):
                    return r.json()
                return r.text

    async def get(self, path, params=None):
        return await self.request("GET", path, params=params)

    async def post(self, path, json=None):
        return await self.request("POST", path, json=json)

    async def get_bytes(self, path: str) -> bytes:
        """GET que retorna bytes crus (ex.: PDF) — com refresh de token em 401."""
        async with httpx.AsyncClient() as client:
            if not self._token or time.time() > self._exp:
                await self._login(client)
            for attempt in (1, 2):
                r = await client.get(f"{API}{path}", headers={"Authorization": f"Bearer {self._token}"}, timeout=60)
                if r.status_code == 401 and attempt == 1:
                    await self._login(client)
                    continue
                r.raise_for_status()
                return r.content
        return b""

    async def post_bytes(self, path: str, json) -> bytes:
        """POST que retorna bytes crus (ex.: PDF gerado a partir de dados enviados)."""
        async with httpx.AsyncClient() as client:
            if not self._token or time.time() > self._exp:
                await self._login(client)
            for attempt in (1, 2):
                r = await client.post(f"{API}{path}", headers={"Authorization": f"Bearer {self._token}"},
                                      json=json, timeout=60)
                if r.status_code == 401 and attempt == 1:
                    await self._login(client)
                    continue
                if r.status_code >= 400:
                    raise RuntimeError(f"ERP POST {path} -> {r.status_code}: {r.text[:200]}")
                return r.content
        return b""


erp = _Erp()


def _brl(v: Any) -> str:
    try:
        return f"R$ {float(v or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return "R$ 0,00"


def _items(data: Any) -> list:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("items") or data.get("results") or []
    return []


# =================================================================== FERRAMENTAS

STAGE_LABEL = {
    "qualification": "Qualificação", "needs_analysis": "Análise", "proposal": "Proposta",
    "negotiation": "Negociação", "closed_won": "Ganho", "closed_lost": "Perdido",
}


async def _compute_pipeline() -> dict:
    """Lógica do pipeline reusável (por consultar_pipeline e resumo_comercial)."""
    data = await erp.get("/crm/opportunities/", params={"page_size": 100})
    deals = _items(data)
    by_stage: dict[str, dict] = {}
    total_open = 0.0
    for d in deals:
        stage = d.get("stage", "?")
        val = float(d.get("value") or 0)
        g = by_stage.setdefault(stage, {"estagio": STAGE_LABEL.get(stage, stage), "deals": 0, "valor": 0.0})
        g["deals"] += 1
        g["valor"] += val
        if stage not in ("closed_won", "closed_lost"):
            total_open += val
    for g in by_stage.values():
        g["valor_fmt"] = _brl(g["valor"])
    return {
        "total_deals": len(deals),
        "pipeline_aberto": _brl(total_open),
        "por_estagio": list(by_stage.values()),
    }


@mcp.tool
async def consultar_pipeline() -> dict:
    """Consulta o pipeline de vendas (oportunidades/deals) agrupado por estágio, com valores.
    Use para ter a visão do funil comercial: quantos deals e quanto R$ em cada etapa."""
    return await _compute_pipeline()


# mapa rótulo PT -> stage técnico (aceita os dois na busca)
_STAGE_FROM_LABEL = {v.lower(): k for k, v in STAGE_LABEL.items()}
_STAGE_FROM_LABEL.update({k: k for k in STAGE_LABEL})  # aceita o próprio stage técnico


@mcp.tool
async def listar_deals(estagio: str | None = None, limite: int = 50) -> dict:
    """Lista os deals (oportunidades) INDIVIDUAIS com nome do cliente, valor, estágio, probabilidade e dono.
    estagio (opcional): filtra por etapa — ex. 'Negociação', 'Proposta', 'Ganho' ou o nome técnico
    (negotiation, proposal, closed_won...). Use para drill-down do pipeline."""
    data = await erp.get("/crm/opportunities/", params={"page_size": 100})
    deals = _items(data)
    alvo = _STAGE_FROM_LABEL.get((estagio or "").strip().lower()) if estagio else None
    out = []
    for d in deals:
        if alvo and d.get("stage") != alvo:
            continue
        out.append({
            "cliente": d.get("company_name") or d.get("title") or "—",
            "titulo": d.get("title"),
            "valor": _brl(d.get("value")),
            "estagio": STAGE_LABEL.get(d.get("stage"), d.get("stage")),
            "probabilidade": f"{int((d.get('probability') or 0))}%",
            "dono_id": d.get("owner_id"),
            "id": d.get("id"),
        })
    out.sort(key=lambda x: float(str(x["valor"]).replace("R$", "").replace(".", "").replace(",", ".") or 0), reverse=True)
    return {"filtro": estagio or "todos", "total": len(out), "deals": out[:limite]}


@mcp.tool
async def atualizar_estagio_deal(deal_id: str, estagio: str, nota: str | None = None) -> dict:
    """Move um deal (oportunidade) entre estágios do pipeline.
    estagio: 'Qualificação', 'Análise', 'Proposta', 'Negociação', 'Ganho', 'Perdido'
    (ou técnico: qualification/needs_analysis/proposal/negotiation/closed_won/closed_lost)."""
    alvo = _STAGE_FROM_LABEL.get((estagio or "").strip().lower())
    if not alvo:
        return {"erro": f"estágio inválido: {estagio}", "validos": list(STAGE_LABEL.values())}
    r = await erp.request("PATCH", f"/crm/opportunities/{deal_id}/stage", json={"stage": alvo, "notes": nota})
    return {"movido": True, "deal_id": deal_id, "estagio": STAGE_LABEL.get(r.get("stage"), r.get("stage"))}


@mcp.tool
async def marcar_deal_perdido(deal_id: str, motivo: str) -> dict:
    """Marca um deal como Perdido (closed_lost) com o motivo — entra na taxa de conversão/forecast."""
    await erp.request("PATCH", f"/crm/opportunities/{deal_id}/stage",
                      json={"stage": "closed_lost", "notes": motivo})
    return {"perdido": True, "deal_id": deal_id, "motivo": motivo}


@mcp.tool
async def consultar_forecast() -> dict:
    """Previsão de vendas: pipeline ponderado por probabilidade de cada estágio, ganho no mês e meta."""
    return await erp.get("/crm/forecast")


@mcp.tool
async def consultar_funil() -> dict:
    """Funil UNIFICADO do primeiro contato ao fechamento (leads de conversa + deals): quantos e
    quanto R$ em cada etapa (novo→qualificando→visita→proposta→negociação→ganho/perdido), o GARGALO
    (etapa com mais gente) e QUEM está parado há mais tempo (nome, telefone, dias) para cutucar.
    Diferente do pipeline/forecast (só deals abertos): aqui entram também os leads que ainda nem
    viraram oportunidade. Use para ver onde os negócios estão travando e quem reativar."""
    return await erp.get("/crm/funil")


@mcp.tool
async def criar_proposta(
    titulo: str,
    cliente_nome: str,
    itens: list[dict],
    cliente_documento: str | None = None,
    cliente_email: str | None = None,
    condicoes_pagamento: str | None = None,
) -> dict:
    """Cria uma proposta/orçamento no CRM.

    itens: lista de {"nome": str, "quantidade": number, "preco_unitario": number}.
    Ex.: itens=[{"nome":"Cerca elétrica instalada","quantidade":1,"preco_unitario":11966.70}].
    O total é calculado pelo sistema. Retorna número e id da proposta."""
    payload = {
        "title": titulo,
        "client_name": cliente_nome,
        "items": [
            {"name": i.get("nome") or i.get("name"), "quantity": i.get("quantidade", i.get("quantity", 1)),
             "unit_price": i.get("preco_unitario", i.get("unit_price", 0))}
            for i in (itens or [])
        ],
    }
    if cliente_documento:
        payload["client_document"] = cliente_documento
    if cliente_email:
        payload["client_email"] = cliente_email
    if condicoes_pagamento:
        payload["payment_terms"] = condicoes_pagamento
    dup = await _proposta_duplicada(cliente_documento, titulo)
    if dup:
        return {"ja_existia": True, "numero": dup.get("number"), "id": dup.get("id"),
                "total": _brl(dup.get("total")), "status": dup.get("status")}
    r = await erp.post("/crm/proposals/", json=payload)
    return {"numero": r.get("number"), "id": r.get("id"), "total": _brl(r.get("total")), "status": r.get("status")}


async def _proposta_duplicada(client_doc: str | None, titulo: str) -> dict | None:
    """Idempotência: acha proposta ATIVA com mesmo CNPJ do cliente + mesmo título (evita duplicar
    em reprocessamento de lote). Retorna a proposta existente ou None."""
    if not titulo:
        return None
    digits = "".join(c for c in (client_doc or "") if c.isdigit())
    t = titulo.strip().lower()
    data = await erp.get("/crm/proposals/", params={"page_size": 100})
    for pr in _items(data):
        if (pr.get("title") or "").strip().lower() != t:
            continue
        pdoc = "".join(c for c in (pr.get("client_document") or "") if c.isdigit())
        if digits and pdoc and pdoc != digits:
            continue
        if not digits and (pr.get("client_name") or "").strip().lower() != "":
            # sem CNPJ: casa por nome do cliente também
            pass
        return pr
    return None


def _payload_proposta(p: dict) -> dict:
    """Monta o payload de uma proposta a partir de um dict em PT (aceita variações de chave)."""
    itens = p.get("itens") or p.get("items") or []
    payload = {
        "title": p.get("titulo") or p.get("title") or "Proposta",
        "client_name": p.get("cliente_nome") or p.get("client_name") or "Cliente",
        "items": [
            {"name": i.get("nome") or i.get("name"),
             "quantity": i.get("quantidade", i.get("quantity", 1)),
             "unit_price": i.get("preco_unitario", i.get("unit_price", 0))}
            for i in itens
        ],
    }
    for k_pt, k_en in (("cliente_documento", "client_document"), ("cliente_email", "client_email"),
                       ("condicoes_pagamento", "payment_terms")):
        if p.get(k_pt):
            payload[k_en] = p[k_pt]
    return payload


@mcp.tool
async def criar_propostas_lote(propostas: list[dict]) -> dict:
    """Cria VÁRIAS propostas no CRM de uma vez (importação em lote). Ideal para subir orçamentos
    redigidos no Cowork (portaria, portaria remota, controle de acesso, etc.).

    propostas: lista, cada item = {"titulo", "cliente_nome", "itens": [{"nome","quantidade","preco_unitario"}],
    "cliente_documento"?, "cliente_email"?, "condicoes_pagamento"?}.
    Retorna o resultado de cada uma (número/total) + erros, sem parar no primeiro problema."""
    criadas, erros = [], []
    for idx, p in enumerate(propostas or []):
        try:
            tit = p.get("titulo") or p.get("title") or ""
            dup = await _proposta_duplicada(p.get("cliente_documento") or p.get("client_document"), tit)
            if dup:
                criadas.append({"titulo": tit, "numero": dup.get("number"),
                                "total": _brl(dup.get("total")), "status": dup.get("status"), "ja_existia": True})
                continue
            r = await erp.post("/crm/proposals/", json=_payload_proposta(p))
            criadas.append({"titulo": tit, "numero": r.get("number"),
                            "total": _brl(r.get("total")), "status": r.get("status")})
        except Exception as exc:  # noqa: BLE001
            erros.append({"indice": idx, "titulo": p.get("titulo") or p.get("title"), "erro": str(exc)[:200]})
    return {"criadas": len(criadas), "falhas": len(erros), "propostas": criadas, "erros": erros}


@mcp.tool
async def atualizar_proposta(proposta_id: str, titulo: str | None = None, condicoes_pagamento: str | None = None,
                             observacoes: str | None = None, cliente_email: str | None = None) -> dict:
    """Atualiza campos de uma proposta SEM recriar (passe só o que quer mudar)."""
    payload: dict[str, Any] = {}
    if titulo is not None:
        payload["title"] = titulo
    if condicoes_pagamento is not None:
        payload["payment_terms"] = condicoes_pagamento
    if observacoes is not None:
        payload["notes"] = observacoes
    if cliente_email is not None:
        payload["client_email"] = cliente_email
    if not payload:
        return {"erro": "nada para atualizar — informe ao menos um campo"}
    r = await erp.request("PUT", f"/crm/proposals/{proposta_id}", json=payload)
    return {"atualizada": True, "numero": r.get("number"), "titulo": r.get("title"), "total": _brl(r.get("total"))}


@mcp.tool
async def baixar_proposta_pdf(proposta_id: str, salvar_no_drive: bool = False) -> dict:
    """Gera o PDF da proposta (SEM enviar ao cliente), REGISTRA no Conecta PRO e devolve o LINK de
    download (clicável). Use para conferir o layout/auditar antes de qualquer envio real."""
    return await _gerar_doc_get(f"/crm/proposals/{proposta_id}/pdf", drive=salvar_no_drive)


async def _pdf_b64(path: str) -> dict:
    import base64
    try:
        raw = await erp.get_bytes(path)
    except Exception as exc:  # noqa: BLE001
        return {"gerado": False, "erro": str(exc)[:200]}
    kb = round(len(raw) / 1024, 1)
    if len(raw) > 1_500_000:
        return {"gerado": True, "tamanho_kb": kb, "aviso": "PDF grande — não embutido."}
    return {"gerado": True, "tamanho_kb": kb, "mime": "application/pdf", "pdf_base64": base64.b64encode(raw).decode("ascii")}


@mcp.tool
async def baixar_contrato_pdf(contrato_id: str, salvar_no_drive: bool = False) -> dict:
    """Gera o PDF do CONTRATO no padrão Conecta Mais (com selo), em base64. contrato_id = número (CTR-...) ou id."""
    return await _gerar_doc_get(f"/crm/contracts/{contrato_id}/pdf", drive=salvar_no_drive)


@mcp.tool
async def baixar_relatorio_comercial_pdf(salvar_no_drive: bool = False) -> dict:
    """Gera o RELATÓRIO COMERCIAL em PDF (MRR, clientes, pipeline, top deals) no padrão Conecta Mais, em base64."""
    return await _gerar_doc_get("/crm/reports/comercial/pdf", drive=salvar_no_drive)


async def _pdf_post_b64(path: str, payload: dict) -> dict:
    import base64
    try:
        raw = await erp.post_bytes(path, payload)
    except Exception as exc:  # noqa: BLE001
        return {"gerado": False, "erro": str(exc)[:200]}
    return {"gerado": True, "tamanho_kb": round(len(raw) / 1024, 1), "mime": "application/pdf",
            "pdf_base64": base64.b64encode(raw).decode("ascii")}


async def _gerar_doc(path: str, payload: dict, teste: bool = True, drive: bool = False) -> dict:
    """Gera o documento (POST), REGISTRA no Conecta PRO e devolve o LINK público. drive=True: sobe pro Google Drive."""
    try:
        r = await erp.post(f"{path}?salvar=true&teste={'true' if teste else 'false'}&drive={'true' if drive else 'false'}", json=payload)
    except Exception as exc:  # noqa: BLE001
        return {"gerado": False, "erro": str(exc)[:200]}
    return {"gerado": True, "titulo": r.get("titulo"), "tamanho_kb": r.get("tamanho_kb"),
            "download_url": r.get("download_url"), "drive_url": r.get("drive_url"), "id": r.get("id"),
            "obs": "Registrado no Conecta PRO." + (f" Salvo no Drive: {r.get('drive_url')}" if r.get("drive_url") else " Abra o download_url para ver/baixar.")}


async def _gerar_doc_get(path: str, teste: bool = True, drive: bool = False) -> dict:
    """Idem (GET): gera doc de uma entidade existente (proposta/contrato/relatório), registra + link. drive=True: sobe pro Drive."""
    sep = "&" if "?" in path else "?"
    try:
        r = await erp.get(f"{path}{sep}salvar=true&teste={'true' if teste else 'false'}&drive={'true' if drive else 'false'}")
    except Exception as exc:  # noqa: BLE001
        return {"gerado": False, "erro": str(exc)[:200]}
    return {"gerado": True, "titulo": r.get("titulo"), "tamanho_kb": r.get("tamanho_kb"),
            "download_url": r.get("download_url"), "drive_url": r.get("drive_url"), "id": r.get("id"),
            "obs": "Registrado no Conecta PRO." + (f" Salvo no Drive: {r.get('drive_url')}" if r.get("drive_url") else " Abra o download_url para ver/baixar.")}


@mcp.tool
async def consultar_auditoria(limite: int = 30, metodo: str | None = None, busca: str | None = None) -> dict:
    """Log de auditoria das escritas no Conecta PRO (quem/quando/o quê/resultado).
    metodo: POST|PUT|PATCH|DELETE (opcional). busca: trecho do caminho (ex.: 'contracts')."""
    q = [f"limite={limite}"]
    if metodo:
        q.append(f"metodo={metodo}")
    if busca:
        q.append(f"busca={busca}")
    return await erp.get(f"/crm/audit?{'&'.join(q)}")


@mcp.tool
async def listar_precos_funcao() -> dict:
    """Tabela de PREÇOS por função (CCT 2026, Lucro Real, margem 15%): custo, preço, markup, adicionais.
    Funções com termos oficiais (AGP, ASG — nunca porteiro/vigia/faxineiro)."""
    return await erp.get("/crm/pricing/funcoes")


@mcp.tool
async def simular_preco(funcao: str | None = None, salario_base: float | None = None, jornada_dias: int = 15,
                        postos: int = 1, noturno: bool = False, hora_reduzida: bool = False, ronda: bool = False,
                        periculosidade: bool = False, insalubridade: bool = False, margem: float | None = None) -> dict:
    """Simula o preço de um posto (replica o simulador da planilha CCT 2026). Informe a função
    (ex.: 'AGP P1 Noturno') ou o salário base, e ative os adicionais. peric e insalub não acumulam."""
    return await erp.post("/crm/pricing/simular", json={
        "funcao": funcao, "salario_base": salario_base, "jornada_dias": jornada_dias, "postos": postos,
        "noturno": noturno, "hora_reduzida": hora_reduzida, "ronda": ronda,
        "periculosidade": periculosidade, "insalubridade": insalubridade, "margem": margem})


@mcp.tool
async def consultar_parametros_precificacao() -> dict:
    """Lê os parâmetros de precificação (encargos, tributos, margem, benefícios, adicionais)."""
    return await erp.get("/crm/pricing/parametros")


@mcp.tool
async def definir_parametros_precificacao(valores: dict) -> dict:
    """Atualiza parâmetros de precificação (sincronizar a planilha). valores = {chave: valor}.
    Ex.: {'ronda':0.05,'iss':0.05,'margem':0.15}. Chaves: encargos/tributos/benefícios/adicionais/margem."""
    return await erp.request("PUT", "/crm/pricing/parametros", json={"valores": valores})


@mcp.tool
async def listar_documentos(tipo: str | None = None, limite: int = 30) -> dict:
    """Lista os documentos gerados/registrados no Conecta PRO (com link de download).
    tipo (opcional): proposta|contrato|relatorio|recibo|ordem_servico|aditivo|atestado."""
    p = f"?tipo={tipo}&limite={limite}" if tipo else f"?limite={limite}"
    return await erp.get(f"/crm/docs{p}")


@mcp.tool
async def gerar_recibo_pdf(pagador: str, valor: float, referente: str, documento: str | None = None,
                           forma_pagamento: str | None = None, numero: str | None = None, salvar_no_drive: bool = False) -> dict:
    """Gera um RECIBO de pagamento em PDF (padrão Conecta Mais, com selo), em base64.
    Ex.: pagador='CONDOMINIO X', valor=6000, referente='portaria remota — junho/2026'."""
    return await _gerar_doc("/crm/docs/recibo/pdf", {
        "pagador": pagador, "valor": valor, "referente": referente,
        "documento": documento, "forma_pagamento": forma_pagamento, "numero": numero}, drive=salvar_no_drive)


@mcp.tool
async def gerar_aditivo_pdf(contrato_numero: str, tipo: str = "outro", objeto: str | None = None,
                            cliente: str | None = None, documento: str | None = None,
                            novo_valor: float | None = None, nova_vigencia_fim: str | None = None,
                            justificativa: str | None = None, numero: str | None = None, salvar_no_drive: bool = False) -> dict:
    """Gera um TERMO ADITIVO de contrato em PDF (padrão Conecta Mais, com selo), em base64.
    tipo: reajuste | prorrogacao | escopo | valor | outro. Enriquece cliente pelo contrato se omitido."""
    return await _gerar_doc("/crm/docs/aditivo/pdf", {
        "contrato_numero": contrato_numero, "tipo": tipo, "objeto": objeto, "cliente": cliente,
        "documento": documento, "novo_valor": novo_valor, "nova_vigencia_fim": nova_vigencia_fim,
        "justificativa": justificativa, "numero": numero}, drive=salvar_no_drive)


@mcp.tool
async def gerar_atestado_pdf(emitente: str, servico: str, periodo: str | None = None,
                             emitente_documento: str | None = None, emitente_responsavel: str | None = None,
                             emitente_cargo: str | None = None, valor: float | None = None,
                             cidade: str | None = None, observacoes: str | None = None,
                             numero: str | None = None, salvar_no_drive: bool = False) -> dict:
    """Gera um ATESTADO DE CAPACIDADE TÉCNICA em PDF (padrão Conecta Mais, com selo), em base64.
    emitente = cliente que atesta os serviços da Conecta Mais (usado em licitações)."""
    return await _gerar_doc("/crm/docs/atestado/pdf", {
        "emitente": emitente, "servico": servico, "periodo": periodo, "emitente_documento": emitente_documento,
        "emitente_responsavel": emitente_responsavel, "emitente_cargo": emitente_cargo, "valor": valor,
        "cidade": cidade, "observacoes": observacoes, "numero": numero}, drive=salvar_no_drive)


@mcp.tool
async def gerar_ordem_servico_pdf(cliente: str, servico: str, descricao: str | None = None,
                                  documento: str | None = None, endereco: str | None = None,
                                  responsavel: str | None = None, valor: float | None = None,
                                  prazo: str | None = None, observacoes: str | None = None,
                                  numero: str | None = None, salvar_no_drive: bool = False) -> dict:
    """Gera uma ORDEM DE SERVIÇO (OS) em PDF (padrão Conecta Mais, com selo), em base64."""
    return await _gerar_doc("/crm/docs/ordem-servico/pdf", {
        "cliente": cliente, "servico": servico, "descricao": descricao, "documento": documento,
        "endereco": endereco, "responsavel": responsavel, "valor": valor, "prazo": prazo,
        "observacoes": observacoes, "numero": numero}, drive=salvar_no_drive)


@mcp.tool
async def listar_propostas(limite: int = 20) -> dict:
    """Lista as propostas mais recentes (número, cliente, total, status)."""
    data = await erp.get("/crm/proposals/", params={"page_size": min(limite, 100)})
    return {"propostas": [
        {"numero": p.get("number"), "titulo": p.get("title"), "cliente": p.get("client_name"),
         "total": _brl(p.get("total")), "status": p.get("status")}
        for p in _items(data)[:limite]
    ]}


@mcp.tool
async def criar_lead(nome: str, email: str | None = None, telefone: str | None = None,
                     empresa: str | None = None, origem: str = "website") -> dict:
    """Cria um lead no CRM (dispara automações/scoring configurados). Retorna id do lead."""
    payload = {"name": nome, "source": origem, "status": "new"}
    if email:
        payload["email"] = email
    if telefone:
        payload["phone"] = telefone
    if empresa:
        payload["company"] = empresa
    r = await erp.post("/crm/leads", json=payload)
    return {"id": r.get("id"), "nome": r.get("name"), "status": r.get("status")}


@mcp.tool
async def listar_leads(limite: int = 20) -> dict:
    """Lista os leads mais recentes (nome, empresa, origem, status, score)."""
    data = await erp.get("/crm/leads", params={"page_size": min(limite, 100)})
    return {"leads": [
        {"id": l.get("id"), "nome": l.get("name"), "empresa": l.get("company"),
         "origem": l.get("source"), "status": l.get("status"), "score": l.get("score")}
        for l in _items(data)[:limite]
    ]}


@mcp.tool
async def listar_clientes(busca: str | None = None) -> dict:
    """Lista clientes cadastrados (código, nome, CNPJ, MRR). 'busca' filtra por nome (opcional)."""
    data = await erp.get("/crm/clients/")
    rows = _items(data)
    if busca:
        b = busca.lower()
        rows = [c for c in rows if b in (c.get("name", "") or "").lower()]
    return {"clientes": [
        {"codigo": c.get("code"), "nome": c.get("name"), "cnpj": c.get("cnpj") or c.get("document_number"),
         "mrr": _brl(c.get("mrr"))}
        for c in rows[:50]
    ]}


async def _buscar_cliente(cnpj: str) -> dict | None:
    """Acha um cliente pelo CNPJ/CPF (compara só dígitos). Retorna o registro ou None."""
    digits = "".join(c for c in (cnpj or "") if c.isdigit())
    if not digits:
        return None
    for c in _items(await erp.get("/crm/clients/")):
        cdoc = "".join(ch for ch in (c.get("cnpj") or c.get("document_number") or "") if ch.isdigit())
        if cdoc and cdoc == digits:
            return c
    return None


@mcp.tool
async def buscar_cliente_por_cnpj(cnpj: str) -> dict:
    """Verifica se um cliente já está cadastrado pelo CNPJ/CPF (use ANTES de criar, p/ não duplicar)."""
    c = await _buscar_cliente(cnpj)
    if c:
        return {"existe": True, "codigo": c.get("code"), "nome": c.get("name"),
                "cnpj": c.get("cnpj") or c.get("document_number"), "id": c.get("id"), "mrr": _brl(c.get("mrr"))}
    return {"existe": False, "cnpj": cnpj}


@mcp.tool
async def criar_cliente(nome: str, cnpj: str, email: str | None = None, telefone: str | None = None,
                        cidade: str | None = None) -> dict:
    """Cadastra um cliente com CNPJ. IDEMPOTENTE: se o CNPJ já existir, retorna o cliente existente
    (NUNCA duplica). Valida o CNPJ. Use ao alimentar o CRM com clientes reais."""
    existing = await _buscar_cliente(cnpj)
    if existing:
        return {"ja_existia": True, "codigo": existing.get("code"), "nome": existing.get("name"),
                "cnpj": existing.get("document_number"), "id": existing.get("id")}
    _digits = "".join(c for c in (cnpj or "") if c.isdigit())
    # clients.email é NOT NULL no banco. Se não informado, usa placeholder não-roteável (.invalid)
    # — claramente um "sem e-mail"; troque pelo real depois. Passe 'email' sempre que tiver.
    payload: dict[str, Any] = {
        "name": nome,
        "document_number": cnpj,
        "email": email or f"naoinformado-{_digits}@example.invalid",
    }
    if telefone:
        payload["phone"] = telefone
    if cidade:
        payload["address_city"] = cidade
    try:
        r = await erp.post("/clients", json=payload)
    except Exception as exc:  # noqa: BLE001 — CNPJ inválido ou duplicado (backstop)
        return {"criado": False, "erro": str(exc)[:200],
                "dica": "CNPJ pode estar inválido (dígitos verificadores) ou já cadastrado."}
    return {"criado": True, "codigo": r.get("code"),
            "nome": r.get("legal_name") or r.get("name"), "id": r.get("id")}


@mcp.tool
async def listar_contratos(limite: int = 20) -> dict:
    """Lista contratos (número, tipo, valor mensal, status)."""
    data = await erp.get("/crm/contracts", params={"page_size": min(limite, 100)})
    return {"contratos": [
        {"numero": c.get("contract_number"), "tipo": c.get("contract_type"),
         "mensal": _brl(c.get("monthly_value")), "status": c.get("status")}
        for c in _items(data)[:limite]
    ]}


@mcp.tool
async def listar_sequencias() -> dict:
    """Lista as sequências/cadências de follow-up disponíveis (id, nome, nº de passos)."""
    data = await erp.get("/crm/sequences")
    return {"sequencias": [
        {"id": s.get("id"), "nome": s.get("name"), "passos": len(s.get("steps") or []),
         "canal": s.get("channel"), "ativa": s.get("is_active")}
        for s in _items(data)
    ]}


@mcp.tool
async def inscrever_lead_em_sequencia(sequencia_id: str, lead_id: str) -> dict:
    """Inscreve um lead numa sequência de follow-up. Os envios saem automaticamente (Celery)."""
    r = await erp.post(f"/crm/sequences/{sequencia_id}/enroll", json={"lead_id": lead_id})
    return {"inscrito": bool(r.get("enrolled")), "enrollment_id": r.get("enrollment_id")}


@mcp.tool
async def resumo_comercial() -> dict:
    """Snapshot comercial: nº de clientes, MRR total, pipeline aberto e propostas recentes."""
    clientes = _items(await erp.get("/crm/clients/"))
    mrr = sum(float(c.get("mrr") or 0) for c in clientes)
    pipe = await _compute_pipeline()
    props = _items(await erp.get("/crm/proposals/", params={"page_size": 5}))
    return {
        "clientes": len(clientes),
        "mrr_total": _brl(mrr),
        "pipeline_aberto": pipe.get("pipeline_aberto"),
        "total_deals": pipe.get("total_deals"),
        "propostas_recentes": [{"numero": p.get("number"), "cliente": p.get("client_name"),
                                "total": _brl(p.get("total")), "status": p.get("status")} for p in props],
    }


# =================================================================== EDIÇÃO / GOVERNANÇA
@mcp.tool
async def definir_meta_mensal(valor: float, mes: int | None = None, ano: int | None = None,
                              vendedor: str | None = None) -> dict:
    """Define a META mensal de fechamento (destrava o atingimento no forecast).
    mes/ano: default = mês/ano atual. valor em R$."""
    hoje = date.today()
    payload = {"seller_name": vendedor or "Equipe", "period_year": ano or hoje.year,
               "period_month": mes or hoje.month, "target_value": valor}
    r = await erp.post("/crm/quotas", json=payload)
    return {"meta_definida": True, "periodo": f"{payload['period_month']:02d}/{payload['period_year']}",
            "valor": _brl(valor), "id": r.get("id")}


@mcp.tool
async def atualizar_cliente(cnpj_ou_id: str, nome: str | None = None, email: str | None = None,
                            telefone: str | None = None, cidade: str | None = None) -> dict:
    """Atualiza dados de um cliente (padronizar nome p/ CAIXA ALTA, corrigir contato).
    cnpj_ou_id: CNPJ (procura) ou o id do cliente. Passe só o que quer mudar."""
    cid = cnpj_ou_id
    if "-" not in cnpj_ou_id or len(cnpj_ou_id) < 30:  # parece CNPJ -> busca
        c = await _buscar_cliente(cnpj_ou_id)
        if not c:
            return {"erro": "cliente não encontrado pelo CNPJ", "cnpj": cnpj_ou_id}
        cid = c.get("id")
    payload: dict[str, Any] = {}
    if nome is not None:
        payload["name"] = nome
    if email is not None:
        payload["email"] = email
    if telefone is not None:
        payload["phone"] = telefone
    if cidade is not None:
        payload["address_city"] = cidade
    if not payload:
        return {"erro": "nada para atualizar"}
    r = await erp.request("PUT", f"/clients/{cid}", json=payload)
    return {"atualizado": True, "id": cid, "nome": r.get("legal_name") or r.get("name")}


@mcp.tool
async def excluir_proposta(proposta_id: str, confirmar: bool = False) -> dict:
    """Exclui (soft-delete) uma proposta — para rascunhos errados. Exige confirmar=true."""
    if not confirmar:
        return {"preview": True, "proposta_id": proposta_id,
                "aviso": "Isto exclui a proposta. Reenvie com confirmar=true."}
    await erp.request("DELETE", f"/crm/proposals/{proposta_id}")
    return {"excluida": True, "proposta_id": proposta_id}


@mcp.tool
async def arquivar_deal(deal_id: str, confirmar: bool = False) -> dict:
    """Arquiva (soft-delete) um deal/oportunidade — para remover deals de teste do funil.
    Exige confirmar=true."""
    if not confirmar:
        return {"preview": True, "deal_id": deal_id,
                "aviso": "Isto arquiva o deal (sai do funil). Reenvie com confirmar=true."}
    await erp.request("DELETE", f"/crm/opportunities/{deal_id}")
    return {"arquivado": True, "deal_id": deal_id}


@mcp.tool
async def arquivar_contrato(contrato_id: str, confirmar: bool = False) -> dict:
    """Arquiva (soft-delete) um contrato — para limpar contratos de teste. Exige confirmar=true."""
    if not confirmar:
        return {"preview": True, "contrato_id": contrato_id,
                "aviso": "Isto arquiva o contrato. Reenvie com confirmar=true."}
    await erp.request("DELETE", f"/crm/contracts/{contrato_id}")
    return {"arquivado": True, "contrato_id": contrato_id}


@mcp.tool
async def excluir_campanha(campanha_id: str, confirmar: bool = False) -> dict:
    """Exclui uma campanha de marketing (ex.: campanhas de teste). Exige confirmar=true."""
    if not confirmar:
        return {"preview": True, "campanha_id": campanha_id,
                "aviso": "Isto exclui a campanha. Reenvie com confirmar=true."}
    await erp.request("DELETE", f"/marketing/campaigns/{campanha_id}")
    return {"excluida": True, "campanha_id": campanha_id}


@mcp.tool
async def upload_asset(arquivo_base64: str, tipo: str = "logo", nome: str | None = None) -> dict:
    """Envia um asset (logo/selo) em base64 para o ERP — sem SSH. O logo comercial passa a ser usado
    no PDF automaticamente. tipo: logo | logo_transparente | logo_branco | selo. nome: opcional."""
    r = await erp.post("/crm/assets/upload", json={"tipo": tipo, "conteudo_base64": arquivo_base64, "nome": nome})
    return {"enviado": bool(r.get("ok")), "arquivo": r.get("arquivo"), "tamanho_kb": r.get("tamanho_kb")}


@mcp.tool
async def excluir_documento_crm(documento_id: str, confirmar: bool = False) -> dict:
    """Exclui (soft-delete) um documento gerado/registrado no CRM. Exige confirmar=true."""
    if not confirmar:
        return {"preview": True, "documento_id": documento_id,
                "aviso": "Isto exclui o documento. Reenvie com confirmar=true."}
    await erp.request("DELETE", f"/crm/docs/{documento_id}")
    return {"excluido": True, "documento_id": documento_id}


@mcp.tool
async def expurgar_documentos_teste(confirmar: bool = False) -> dict:
    """Arquiva TODOS os documentos de teste (teste=true). confirmar=false mostra a contagem; true executa."""
    return await erp.post(f"/crm/docs/expurgar-teste?confirmar={'true' if confirmar else 'false'}", json={})


@mcp.tool
async def definir_meta_contratos_mes(quantidade: int, mes: int | None = None, ano: int | None = None) -> dict:
    """Define a META por QUANTIDADE de contratos novos no mês (KPI '≥1 contrato novo/mês').
    Aparece no forecast como contratos_fechados_mes / meta_contratos_mes."""
    hoje = date.today()
    # target_value omitido de propósito: setar a meta por CONTAGEM não pode zerar a meta por VALOR
    # (o backend faz upsert independente — target_value None preserva o valor existente).
    r = await erp.post("/crm/quotas", json={"seller_name": "Equipe", "period_year": ano or hoje.year,
                                            "period_month": mes or hoje.month, "target_count": quantidade})
    return {"meta_contratos": quantidade, "periodo": f"{(mes or hoje.month):02d}/{ano or hoje.year}", "id": r.get("id")}


@mcp.tool
async def criar_contrato(cliente_documento: str, tipo: str = "recurring", valor_mensal: float = 0,
                         vigencia_inicio: str | None = None, vigencia_fim: str | None = None,
                         valor_total: float | None = None, nome: str | None = None,
                         deal_id: str | None = None) -> dict:
    """Cria um CONTRATO no CRM a partir do CNPJ do cliente (fecha deal→contrato). tipo: recurring | one_time.
    Depois use ativar_contrato para lançar no MRR (se recurring)."""
    c = await _buscar_cliente(cliente_documento)
    if not c:
        return {"erro": "cliente não encontrado pelo CNPJ", "cnpj": cliente_documento}
    payload: dict[str, Any] = {
        "client_id": c.get("id"), "contract_type": tipo, "monthly_value": valor_mensal,
        "name": nome or f"Contrato - {c.get('name')}", "start_date": vigencia_inicio or date.today().isoformat(),
    }
    if valor_total is not None:
        payload["total_value"] = valor_total
    if vigencia_fim:
        payload["end_date"] = vigencia_fim
    if deal_id:
        payload["opportunity_id"] = deal_id
    try:
        r = await erp.post("/crm/contracts", json=payload)
    except Exception as exc:  # noqa: BLE001
        return {"criado": False, "erro": str(exc)[:200]}
    return {"criado": True, "numero": r.get("contract_number"), "id": r.get("id"), "status": r.get("status")}


@mcp.tool
async def atualizar_contrato(contrato_id: str, valor_mensal: float | None = None, valor_total: float | None = None,
                             vigencia_fim: str | None = None, nome: str | None = None) -> dict:
    """Atualiza um contrato (valor/vigência/nome) sem recriar. Passe só o que muda."""
    payload: dict[str, Any] = {}
    if valor_mensal is not None:
        payload["monthly_value"] = valor_mensal
    if valor_total is not None:
        payload["total_value"] = valor_total
    if vigencia_fim:
        payload["end_date"] = vigencia_fim
    if nome:
        payload["name"] = nome
    if not payload:
        return {"erro": "nada para atualizar"}
    try:
        r = await erp.request("PUT", f"/crm/contracts/{contrato_id}", json=payload)
    except Exception as exc:  # noqa: BLE001
        return {"atualizado": False, "erro": str(exc)[:200]}
    return {"atualizado": True, "numero": r.get("contract_number"), "status": r.get("status")}


# =================================================================== CICLO DE VENDAS
# Envios reais ao cliente exigem confirmar=true (1ª chamada mostra preview, 2ª executa).

@mcp.tool
async def enviar_whatsapp(numero: str, mensagem: str, confirmar: bool = False) -> dict:
    """Envia mensagem de WhatsApp para um número. ENVIO REAL ao cliente.
    Chame primeiro com confirmar=false para ver o preview; depois confirmar=true para enviar."""
    if not confirmar:
        return {"preview": True, "para": numero, "mensagem": mensagem,
                "aviso": "Isto enviará um WhatsApp REAL. Reenvie com confirmar=true para disparar."}
    r = await erp.post("/whatsapp/send/custom", json={"phone": numero, "message": mensagem})
    return {"enviado": bool(r.get("success")), "status": r.get("status"), "para": r.get("phone")}


@mcp.tool
async def status_whatsapp() -> dict:
    """Status da conexão do WhatsApp (se está conectado e pronto para enviar)."""
    return await erp.get("/whatsapp/status")


@mcp.tool
async def gerar_copy(formato: str, briefing: str, objetivo: str | None = None,
                     publico: str | None = None, n_variacoes: int = 3) -> dict:
    """Gera RASCUNHOS de conteúdo de marketing na voz da marca (copywriter IA). Não publica.
    formato: ex. 'post_instagram', 'anuncio', 'email', 'whatsapp'. briefing: o que comunicar."""
    return await erp.post("/marketing/copywriter/generate", json={
        "formato": formato, "briefing": briefing, "objetivo": objetivo,
        "publico": publico, "n_variacoes": n_variacoes})


@mcp.tool
async def gerar_plano_estrategico(objetivo: str, periodo_dias: int = 30,
                                  orcamento: str | None = None, canais: str | None = None) -> dict:
    """Gera um plano de campanha + calendário editorial a partir de um objetivo (estrategista IA, rascunho)."""
    return await erp.post("/marketing/estrategista/plan", json={
        "objetivo": objetivo, "periodo_dias": periodo_dias,
        "orcamento": orcamento, "canais_preferidos": canais})


@mcp.tool
async def listar_campanhas() -> dict:
    """Lista as campanhas de marketing."""
    data = await erp.get("/marketing/campaigns/")
    return {"campanhas": _items(data)}


@mcp.tool
async def marcar_proposta_enviada(proposta: str) -> dict:
    """Marca uma proposta como JÁ ENVIADA, SEM reenviar ao cliente — quando o envio foi feito por
    fora do ciclo (WhatsApp/e-mail manual) e ela ainda consta como rascunho. Entra no painel +
    acompanhamento do José Luís. proposta = número (PROP-...) ou id."""
    pid = proposta
    if not (len(proposta) >= 32 and "-" in proposta and proposta.count("-") >= 4):
        # parece número de proposta -> resolve o id
        data = await erp.get("/crm/proposals/", params={"page_size": 200})
        for p in _items(data):
            if str(p.get("number", "")).upper() == proposta.upper() or str(p.get("id")) == proposta:
                pid = p.get("id")
                break
    return await erp.post(f"/crm/proposals/{pid}/marcar-enviada", json={})


@mcp.tool
async def enviar_proposta(proposta_id: str, confirmar: bool = False) -> dict:
    """Envia a proposta por e-mail ao cliente (com rastreio de abertura + link de assinatura).
    ENVIO REAL. Chame com confirmar=false para ver o preview; confirmar=true para enviar."""
    if not confirmar:
        p = await _one_proposal(proposta_id)
        return {"preview": True, "proposta": p,
                "aviso": "Isto enviará a proposta por e-mail ao cliente. Reenvie com confirmar=true."}
    r = await erp.post(f"/crm/proposals/{proposta_id}/send", json={})
    return {"enviada": True, "numero": r.get("number"), "status": r.get("status")}


@mcp.tool
async def ativar_contrato(contrato_id: str, confirmar: bool = False) -> dict:
    """Ativa um contrato (draft -> pending_signature -> active). Se for recorrente, LANÇA NO MRR.
    Ação financeira: chame com confirmar=false para ver o preview; confirmar=true para ativar."""
    if not confirmar:
        return {"preview": True, "contrato_id": contrato_id,
                "aviso": "Isto ativa o contrato (e lança MRR se recorrente). Reenvie com confirmar=true."}
    await erp.post(f"/crm/contracts/{contrato_id}/submit", json={})
    r = await erp.post(f"/crm/contracts/{contrato_id}/activate", json={})
    return {"ativado": True, "numero": r.get("contract_number"), "status": r.get("status"),
            "mensal": _brl(r.get("monthly_value"))}


@mcp.tool
async def criar_tarefa(titulo: str, descricao: str | None = None, vencimento_dias: int | None = None,
                       prioridade: str = "medium", lead_id: str | None = None) -> dict:
    """Cria uma tarefa/follow-up no CRM. vencimento_dias: vence em N dias a partir de hoje (opcional)."""
    payload: dict[str, Any] = {"title": titulo, "description": descricao, "priority": prioridade}
    if vencimento_dias is not None:
        payload["due_date"] = (date.today() + timedelta(days=vencimento_dias)).isoformat()
    if lead_id:
        payload["lead_id"] = lead_id
    r = await erp.post("/crm/tasks/", json=payload)
    return {"id": r.get("id"), "titulo": r.get("title"), "vencimento": r.get("due_date")}


async def _one_proposal(pid: str) -> dict:
    data = await erp.get("/crm/proposals/", params={"page_size": 100})
    for p in _items(data):
        if str(p.get("id")) == pid or p.get("number") == pid:
            return {"numero": p.get("number"), "cliente": p.get("client_name"),
                    "total": _brl(p.get("total")), "status": p.get("status")}
    return {"id": pid}


# =================================================================== FOLLOW-UP / WHATSAPP (José Luís)
# O José Luís acompanha e envia propostas por WhatsApp. Envios reais ao cliente exigem confirmar=true.

@mcp.tool
async def cadastrar_whatsapp_cliente(cnpj_ou_id: str, numero: str) -> dict:
    """Grava/normaliza (E.164 +55…) o WhatsApp de um cliente (por CNPJ ou id) ou lead (id).
    Pré-requisito para o José Luís enviar follow-up/proposta por WhatsApp."""
    return await erp.post("/crm/whatsapp/cadastrar", json={"cnpj_ou_id": cnpj_ou_id, "numero": numero}, drive=salvar_no_drive)


@mcp.tool
async def followup_whatsapp(mensagem: str, deal_id: str | None = None, cliente: str | None = None,
                            lead_id: str | None = None, proposta_id: str | None = None,
                            confirmar: bool = False) -> dict:
    """Toque MANUAL do José Luís por WhatsApp (acompanhamento). Resolve o número do alvo
    (deal/cliente por CNPJ/lead/proposta), respeita opt-out, horário comercial e anti-spam, e
    REGISTRA em crm_followups. ENVIO REAL: confirmar=false mostra preview; confirmar=true envia."""
    return await erp.post("/crm/followups", json={
        "deal_id": deal_id, "cliente": cliente, "lead_id": lead_id, "proposal_id": proposta_id,
        "mensagem": mensagem, "canal": "whatsapp", "confirmar": confirmar})


@mcp.tool
async def enviar_proposta_whatsapp(proposta_id: str, confirmar: bool = False) -> dict:
    """Envia a PROPOSTA pelo WhatsApp do José Luís: PDF + link de assinatura, com rastreio.
    ENVIO REAL ao cliente. confirmar=false mostra o preview (número + mensagem + link);
    confirmar=true envia de verdade e marca a proposta como enviada (move o deal)."""
    return await erp.post(f"/crm/proposals/{proposta_id}/send-whatsapp?confirmar={'true' if confirmar else 'false'}",
                          json={})


@mcp.tool
async def listar_followups_pendentes() -> dict:
    """Toques de follow-up agendados / a fazer (deal, cliente, canal, data)."""
    return await erp.get("/crm/followups/pendentes")


@mcp.tool
async def historico_followup(deal_id: str) -> dict:
    """Histórico de toques (enviados/agendados/cancelados) + respostas do cliente de um deal."""
    return await erp.get("/crm/followups/historico", params={"deal_id": deal_id})


@mcp.tool
async def registrar_resposta_followup(deal_id: str, status: str = "respondido",
                                      classificacao: str | None = None, nota: str | None = None) -> dict:
    """Registra o retorno do cliente no follow-up mais recente do deal.
    classificacao: interessado | duvida | recusou. status: respondido | recusou | cancelado."""
    return await erp.post("/crm/followups/resposta", json={
        "deal_id": deal_id, "status": status, "classificacao": classificacao, "nota": nota})


@mcp.tool
async def inscrever_em_sequencia(sequencia_id: str, lead_id: str) -> dict:
    """Inscreve um LEAD numa cadência (e-mail OU WhatsApp). Use a sequência
    'Follow-up Proposta — WhatsApp (José Luís)' (D+2/D+5/D+10) para acompanhamento automático.
    Veja os ids com listar_sequencias. (Garanta o telefone do lead para a cadência de WhatsApp.)"""
    r = await erp.post(f"/crm/sequences/{sequencia_id}/enroll", json={"lead_id": lead_id})
    return {"inscrito": bool(r.get("enrolled")), "enrollment_id": r.get("enrollment_id")}


@mcp.tool
async def registrar_optout_whatsapp(numero: str, motivo: str | None = None) -> dict:
    """Marca um número como opt-out (não receber mais follow-ups). Compliance/anti-spam."""
    return await erp.post("/crm/followups/optout", json={"numero": numero, "motivo": motivo})


@mcp.tool
async def enviar_proposta_completa(proposta_id: str, confirmar: bool = False) -> dict:
    """Envia a proposta por E-MAIL **e** WhatsApp de uma vez (o WhatsApp cita o e-mail), e o José Luís
    JÁ ASSUME o acompanhamento (follow-up D+2/D+5/D+10) te avisando no seu WhatsApp.
    ENVIO REAL. confirmar=false mostra o preview; confirmar=true envia."""
    return await erp.post(
        f"/crm/proposals/{proposta_id}/send-completo?confirmar={'true' if confirmar else 'false'}", json={})


@mcp.tool
async def painel_negociacoes() -> dict:
    """Panorama das negociações em aberto: cliente, proposta, quem conduz (José Luís/Jordan), última resposta."""
    return await erp.get("/crm/negociacoes")


@mcp.tool
async def negociacoes_pendentes() -> dict:
    """Propostas enviadas SEM resposta do cliente (com dias parados) — o que precisa de atenção."""
    return await erp.get("/crm/negociacoes/pendentes")


@mcp.tool
async def assumir_negociacao(cliente: str) -> dict:
    """Você (Jordan) assume a negociação — PAUSA o acompanhamento automático do José Luís para esse cliente."""
    return await erp.post("/crm/negociacoes/responsavel", json={"cliente": cliente, "responsavel": "jordan"})


@mcp.tool
async def devolver_negociacao(cliente: str) -> dict:
    """Devolve a negociação ao José Luís (ele volta a acompanhar/fazer follow-up automático)."""
    return await erp.post("/crm/negociacoes/responsavel", json={"cliente": cliente, "responsavel": "jose_luis"})


@mcp.tool
async def resumo_executivo() -> dict:
    """Retrato da casa num lugar só: pipeline (aberto/previsão/meta) + propostas + leads + contratos/MRR
    + pendências. Use para 'como tá a casa / como tão as vendas / panorama geral'."""
    return await erp.get("/crm/resumo-executivo")


@mcp.tool
async def relatorio_comercial() -> dict:
    """Raio-x de vendas: win/loss rate, conversão do funil (lead→oportunidade→ganho), motivos de perda,
    ROI por canal de origem, ranking de clientes por MRR e ciclo médio de venda."""
    return await erp.get("/crm/relatorio-comercial")


@mcp.tool
async def resumo_financeiro() -> dict:
    """Retrato financeiro: MRR, MRR anualizado, recebíveis previstos, inadimplência, caixa do mês
    (entradas/saídas/saldo) e faturamento NFS-e."""
    return await erp.get("/crm/financeiro")


@mcp.tool
async def simular_fechamento(deals: list[str] | None = None, estagio: str = "negotiation") -> dict:
    """What-if: 'se eu fechar estes deals (ou todos de um estágio), como fica meu ganho e a meta?'.
    Passe os ids dos deals OU um estágio (negotiation/proposal). Mostra ganho atual vs projetado e atingimento."""
    return await erp.post("/crm/simular-fechamento", json={"deals": deals, "estagio": estagio})


@mcp.tool
async def followup_em_lote(mensagem: str | None = None, confirmar: bool = False) -> dict:
    """Dá um toque (WhatsApp) em TODOS os clientes com proposta enviada sem resposta, de uma vez.
    confirmar=false mostra a lista (preview); confirmar=true o José Luís envia (respeita opt-out/horário)."""
    return await erp.post("/crm/followups/lote", json={"mensagem": mensagem, "confirmar": confirmar})


@mcp.tool
async def obter_deal(deal_id: str) -> dict:
    """Detalhe completo de uma oportunidade/deal pelo id."""
    return await erp.get(f"/crm/opportunities/{deal_id}")


@mcp.tool
async def obter_contrato(contrato_id: str) -> dict:
    """Detalhe completo de um contrato pelo id."""
    return await erp.get(f"/crm/contracts/{contrato_id}")


@mcp.tool
async def obter_cliente(cnpj_ou_id: str) -> dict:
    """Detalhe completo de um cliente (por CNPJ ou id)."""
    cid = cnpj_ou_id
    if "-" not in cnpj_ou_id or len(cnpj_ou_id) < 30:
        c = await _buscar_cliente(cnpj_ou_id)
        if not c:
            return {"erro": "cliente não encontrado", "busca": cnpj_ou_id}
        cid = c.get("id")
    return await erp.get(f"/clients/{cid}")


# =================================================================== VISITA TÉCNICA & COMERCIAL
# Fluxo: criar relatório → analisar mídia (você descreve os achados) → montar → PDF → lead + reunião.

@mcp.tool
async def criar_relatorio_visita(cliente_nome: str, panorama: str | None = None,
                                 data_visita: str | None = None) -> dict:
    """Inicia um relatório de visita técnica/comercial. panorama = contexto (porte, o que querem, etc.).
    Depois use adicionar_achados_visita (descrevendo o que você viu nas fotos/áudios) e montar_relatorio_visita."""
    return await erp.post("/crm/visitas", json={"cliente_nome": cliente_nome, "panorama": panorama,
                                                "data_visita": data_visita})


@mcp.tool
async def adicionar_achados_visita(ref: str, achados: list[dict]) -> dict:
    """Anexa achados ao relatório de visita. ref = id ou nome do cliente. achados = lista de
    {tipo, descricao} — ex.: {"tipo":"foto","descricao":"câmera da entrada embaçada"}."""
    return await erp.post("/crm/visitas/achados", json={"ref": ref, "achados": achados})


@mcp.tool
async def montar_relatorio_visita(ref: str, situacao_atual: str | None = None,
                                  diagnostico_tecnico: str | None = None,
                                  oportunidade_comercial: str | None = None,
                                  proximos_passos: str | None = None,
                                  conteudo_md: str | None = None) -> dict:
    """Grava o relatório de visita sintetizado (você redige com base nos achados; aqui persiste)."""
    return await erp.post("/crm/visitas/montar", json={
        "ref": ref, "situacao_atual": situacao_atual, "diagnostico_tecnico": diagnostico_tecnico,
        "oportunidade_comercial": oportunidade_comercial, "proximos_passos": proximos_passos,
        "conteudo_md": conteudo_md})


@mcp.tool
async def listar_relatorios_visita() -> dict:
    """Lista os relatórios de visita (cliente, status, nº de achados)."""
    return await erp.get("/crm/visitas")


@mcp.tool
async def obter_relatorio_visita(ref: str) -> dict:
    """Detalhe de um relatório de visita (por id ou nome do cliente)."""
    return await erp.get("/crm/visitas/detalhe", params={"ref": ref})


@mcp.tool
async def gerar_pdf_visita(ref: str) -> dict:
    """Gera o PDF do relatório de visita (com selo Conecta Mais), registra e devolve link de download."""
    return await erp.post("/crm/visitas/pdf", json={"ref": ref, "salvar": True})


@mcp.tool
async def registrar_lead_da_visita(ref: str, telefone: str | None = None, cnpj: str | None = None,
                                   valor_estimado: float | None = None) -> dict:
    """Cria/atualiza lead + oportunidade no CRM a partir do relatório de visita."""
    return await erp.post("/crm/visitas/registrar-lead", json={
        "ref": ref, "telefone": telefone, "cnpj": cnpj, "valor_estimado": valor_estimado})


@mcp.tool
async def sugerir_reuniao(titulo: str, quando_iso: str, cliente_nome: str | None = None,
                          local: str | None = None, tipo: str = "reuniao",
                          visit_report_id: str | None = None) -> dict:
    """Agenda (sugere) uma reunião. quando_iso = YYYY-MM-DDTHH:MM. tipo: visita_tecnica|comercial|apresentacao|reuniao.
    Fica como 'sugerido' até confirmar_reuniao. Lembrete pré-reunião é enviado automaticamente."""
    return await erp.post("/crm/reunioes", json={"titulo": titulo, "quando_iso": quando_iso,
                          "cliente_nome": cliente_nome, "local": local, "tipo": tipo,
                          "visit_report_id": visit_report_id})


@mcp.tool
async def confirmar_reuniao(meeting_id: str) -> dict:
    """Confirma uma reunião sugerida."""
    return await erp.post("/crm/reunioes/confirmar", json={"meeting_id": meeting_id})


@mcp.tool
async def listar_reunioes(futuras: bool = True) -> dict:
    """Lista as reuniões (futuras por padrão)."""
    return await erp.get("/crm/reunioes", params={"futuras": futuras})


@mcp.tool
async def sugerir_cross_sell(cliente: str) -> dict:
    """A partir dos contratos REAIS de um cliente, sugere o serviço complementar que falta
    (ex.: tem portaria mas não tem CFTV). cliente = CNPJ, nome ou id."""
    return await erp.get("/crm/cross-sell", params={"cliente": cliente})


@mcp.tool
async def leads_frios(dias: int = 14) -> dict:
    """Leads que esfriaram (sem interação há >= N dias, ainda abertos). Para reengajar."""
    return await erp.get("/crm/leads-frios", params={"dias": dias})


@mcp.tool
async def reativar_lead(ref: str, mensagem: str | None = None, confirmar: bool = False) -> dict:
    """Reengaja um lead frio por WhatsApp (José Luís manda um toque). ref = id ou nome.
    confirmar=false mostra o preview; confirmar=true envia de verdade."""
    return await erp.post("/crm/reativar-lead", json={"ref": ref, "mensagem": mensagem, "confirmar": confirmar})


@mcp.tool
async def enviar_nps(ref: str, confirmar: bool = False) -> dict:
    """Envia uma pesquisa NPS (0–10) a um cliente por WhatsApp. A resposta é capturada automaticamente.
    ref = CNPJ, nome ou id. confirmar=false mostra o preview; confirmar=true envia."""
    return await erp.post("/crm/nps/enviar", json={"ref": ref, "confirmar": confirmar})


@mcp.tool
async def resumo_nps() -> dict:
    """Resumo do NPS: respostas, média, promotores/neutros/detratores e o NPS (-100 a +100)."""
    return await erp.get("/crm/nps")


@mcp.tool
async def diagnostico_ciclo() -> dict:
    """Saúde do ciclo Cowork↔Conecta PRO↔WhatsApp: WhatsApp online, agente ligado, webhook recebendo,
    cadência. Use para 'o ciclo tá saudável / o José Luís tá funcionando / tá tudo no ar'."""
    return await erp.get("/crm/ciclo/diagnostico")


@mcp.tool
async def metricas_jose_luis() -> dict:
    """Funil/desempenho do José Luís: leads captados no WhatsApp, follow-ups enviados/respondidos +
    taxa, visitas registradas, negociações por responsável e NPS."""
    return await erp.get("/crm/ciclo/metricas")


@mcp.tool
async def anotar_cliente(cliente: str, nota: str) -> dict:
    """Adiciona uma anotação à FICHA VIVA do cliente (compartilhada com o José Luís — ele lê no
    atendimento). cliente = CNPJ, nome ou id."""
    return await erp.post("/crm/clientes/anotar", json={"ref": cliente, "nota": nota})


@mcp.tool
async def ver_ficha_cliente(cliente: str) -> dict:
    """Ficha viva do cliente: dados + anotações (suas e do José Luís) + último status de negociação."""
    return await erp.get("/crm/clientes/ficha", params={"ref": cliente})


# =================================================================== GED / Kits
# Ferramentas do GED (montagem dos kits documentais mensais por condomínio).
# Tudo chama os mesmos endpoints /gedeon/kits/* do ERP (determinístico, sem inventar).
import asyncio as _asyncio

_GED_CONDS = ["IDEAL FLORES", "MICHELANGELO", "MIRANTE", "VILLA PÁSSAROS",
              "VILLA DEI FIORI", "LARANJEIRAS", "PRIME ARENA"]
# tipo de documento (como a pessoa fala) -> bloco do robô
_GED_BLOCOS = {
    "folha": "folha", "contracheque": "folha", "contracheques": "folha",
    "salario": "pagamentos", "salarios": "pagamentos", "salário": "pagamentos",
    "inss": "pagamentos", "pagamentos": "pagamentos", "comprovante": "pagamentos",
    "vt": "vavt", "vr": "vavt", "vale": "vavt", "vavt": "vavt", "va": "vavt",
    "vale transporte": "vavt", "vale alimentacao": "vavt", "vale alimentação": "vavt",
    "guia": "guias", "guias": "guias", "impostos": "guias", "fgts": "guias", "dctfweb": "guias",
    "rescisao": "rescisao", "rescisão": "rescisao", "rescisoes": "rescisao", "trct": "rescisao",
    "cnd": "cnds", "cnds": "cnds", "certidao": "cnds", "certidão": "cnds", "certidoes": "cnds",
    "nfse": "nfse", "nota": "nfse", "notas": "nfse", "nota fiscal": "nfse", "boleto": "nfse",
    "ponto": "ponto", "assinados": "ponto", "assinado": "ponto", "folha de ponto": "ponto",
}


def _ged_cond(nome: str) -> str:
    """Resolve o nome falado ('ideal flores', 'michelangelo') para o canônico do kit."""
    import unicodedata
    def n(s):
        s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
        return s.upper().strip()
    alvo = set(n(nome).split())
    for c in _GED_CONDS:
        ct = set(n(c).split())
        if ct <= alvo or alvo <= ct or (alvo & ct):
            return c
    return nome


@mcp.tool
async def consultar_kits(competencia: str | None = None) -> dict:
    """Status dos kits documentais dos 7 condomínios no mês: % de completude, completos/pendentes
    e o que falta em cada um. `competencia` opcional (MM.YYYY); sem ela usa o mês corrente do kit."""
    params = {"competencia": competencia} if competencia else {}
    d = await erp.get("/gedeon/kits/completude", params=params)
    kits = [{
        "condominio": k["condominio"], "completude": f"{k['completion_percentage']}%",
        "status": k["status"], "docs": k["total"],
        "falta": [i["label"] for i in k.get("checklist", []) if not i["presente"]],
    } for k in d.get("kits", [])]
    return {"mes_kit": d.get("mes_kit"), "competencia": d.get("competencia"),
            "media": f"{d.get('media_completude')}%",
            "completos": d.get("kits_completos"), "total": d.get("total_kits"), "kits": kits}


@mcp.tool
async def consultar_kit(condominio: str, competencia: str | None = None) -> dict:
    """Ficha completa do kit de UM condomínio: completude, checklist de documentos (presente/falta),
    eventos do mês (contratações, demissões, férias) e a lista de arquivos no Drive (com id p/ excluir)."""
    cond = _ged_cond(condominio)
    params = {"condominio": cond, **({"competencia": competencia} if competencia else {})}
    d = await erp.get("/gedeon/kits/ficha", params=params)
    arquivos = []
    for sp in d.get("subpastas", []):
        for a in sp.get("arquivos", []):
            arquivos.append({"subpasta": sp["nome"], "nome": a["name"], "id": a.get("id")})
    return {
        "condominio": d.get("condominio"), "competencia": d.get("competencia"),
        "completude": f"{d.get('completude')}%", "docs": d.get("total_docs"),
        "falta": [i["label"] for i in d.get("checklist", []) if not i["presente"]],
        "eventos": [{"tipo": e["tipo"], "funcionario": e.get("funcionario"), "descricao": e["descricao"]}
                    for e in (d.get("eventos", {}).get("auto", []) + d.get("eventos", {}).get("manuais", []))],
        "arquivos": arquivos,
    }


@mcp.tool
async def cronograma_kit(competencia: str | None = None) -> dict:
    """Cronograma do mês: quando cada documento deve estar pronto (salário 5º dia útil, VT/VR dia 16,
    prazos de assinatura 48h...). Ajuda a saber o que já dá pra coletar."""
    params = {"competencia": competencia} if competencia else {}
    d = await erp.get("/gedeon/kits/cronograma", params=params)
    return {"mes_entrega": d.get("mes_entrega"), "etapas": [
        {"o_que": e["titulo"], "quando": e.get("data"), "prazo": e.get("prazo"), "obs": e.get("obs")}
        for e in d.get("etapas", [])]}


@mcp.tool
async def buscar_documento(condominio: str, tipo: str, competencia: str | None = None) -> dict:
    """Manda o robô COLETAR um tipo de documento só deste condomínio (folha, salários, VT/VR, guias,
    rescisões, CNDs, notas fiscais, assinados/ponto). Acompanha até concluir e diz quantos docs entraram.
    Ex.: buscar_documento('Ideal Flores', 'VT/VR')."""
    cond = _ged_cond(condominio)
    bloco = _GED_BLOCOS.get((tipo or "").strip().lower())
    if not bloco:
        return {"erro": f"tipo '{tipo}' não reconhecido",
                "tipos_validos": sorted(set(_GED_BLOCOS.values()))}
    r = await erp.post("/gedeon/kits/montagem", json={
        "competencia": competencia, "blocos": [bloco], "condominios": [cond]})
    tid = r.get("task_id")
    # acompanha até concluir (blocos por 1 condomínio são rápidos)
    for _ in range(20):
        await _asyncio.sleep(4)
        st = await erp.get(f"/gedeon/kits/montagem/{tid}")
        ponto_ok = (st.get("ponto", {}).get("state") in ("done", "error")) if bloco == "ponto" else True
        if st.get("state") == "SUCCESS" and ponto_ok:
            etapas = st.get("etapas", {})
            return {"condominio": cond, "tipo": tipo, "status": "coletado",
                    "etapas": {k: ("ok" if v.get("ok") else "falha") for k, v in etapas.items()}}
        if st.get("state") == "FAILURE":
            return {"condominio": cond, "tipo": tipo, "status": "falhou", "erro": st.get("erro")}
    return {"condominio": cond, "tipo": tipo, "status": "ainda coletando",
            "task_id": tid, "dica": "use status_coleta(task_id) para acompanhar"}


@mcp.tool
async def status_coleta(task_id: str) -> dict:
    """Acompanha uma coleta/montagem em andamento pelo task_id."""
    st = await erp.get(f"/gedeon/kits/montagem/{task_id}")
    return {"estado": st.get("state"), "resumo": st.get("resumo"),
            "etapas": {k: ("ok" if v.get("ok") else "falha") for k, v in (st.get("etapas") or {}).items()},
            "ponto": st.get("ponto", {}).get("state")}


@mcp.tool
async def montar_kit_completo(condominio: str | None = None, competencia: str | None = None) -> dict:
    """Dispara a montagem COMPLETA (todos os documentos) — de um condomínio ou de todos (sem condomínio).
    Leva ~3 min. Retorna o task_id; acompanhe com status_coleta."""
    payload: dict = {"competencia": competencia}
    if condominio:
        payload["condominios"] = [_ged_cond(condominio)]
    r = await erp.post("/gedeon/kits/montagem", json=payload)
    return {"status": "montagem iniciada (~3 min)", "task_id": r.get("task_id"),
            "competencia": r.get("competencia"),
            "dica": "use status_coleta(task_id) para acompanhar"}


@mcp.tool
async def excluir_documento(condominio: str, file_id: str, nome: str | None = None,
                            competencia: str | None = None) -> dict:
    """Exclui um documento do kit (vai pra LIXEIRA do Drive, recuperável). Pegue o `file_id` em
    consultar_kit. Use quando o robô coletou errado ou alguém anexou o arquivo trocado."""
    cond = _ged_cond(condominio)
    params = {"condominio": cond, "file_id": file_id,
              **({"nome": nome} if nome else {}), **({"competencia": competencia} if competencia else {})}
    r = await erp.request("DELETE", "/gedeon/kits/arquivo", params=params)
    return {"excluido": bool(r.get("ok")), "arquivo": r.get("arquivo"), "condominio": cond}


@mcp.tool
async def registrar_evento_kit(condominio: str, tipo: str, descricao: str,
                               funcionario: str | None = None, competencia: str | None = None) -> dict:
    """Registra um evento no checklist do kit (contratacao, demissao, ferias, migracao_posto,
    atestado, afastamento, observacao) — pra conferência ponto a ponto."""
    cond = _ged_cond(condominio)
    r = await erp.post("/gedeon/kits/checklist", json={
        "condominio": cond, "competencia": competencia, "tipo": tipo,
        "descricao": descricao, "funcionario": funcionario})
    return {"registrado": True, "id": r.get("id"), "tipo": r.get("tipo"), "condominio": cond}


@mcp.tool
async def status_certidoes() -> dict:
    """Status das certidões da empresa (CNDs): Federal, FGTS, Estadual, Municipal, Trabalhista —
    situação e validade. Use para saber quais estão OK/vencendo."""
    d = await erp.get("/gedeon/cnd/status")
    return {"certidoes": [{
        "tipo": c["document_type"].replace("certidao_negativa_", ""),
        "situacao": c.get("situacao"), "validade": c.get("validade"),
        "alerta": c.get("alerta"),
    } for c in d.get("certidoes", [])]}


# ============================ CFO / Financeiro / Diárias / DET (recursos novos 2026-07) ========

@mcp.tool
async def cfo_panorama() -> dict:
    """Fotografia financeira REAL da empresa agora: saldo do Banco Inter AO VIVO, MRR, folha, margem,
    runway, contas a pagar/receber, e visão cross-módulo (pipeline comercial, contingências jurídicas,
    diaristas a pagar). Use para saber a saúde financeira atual."""
    return await erp.get("/financial/cfo/panorama")


@mcp.tool
async def cfo_perguntar(pergunta: str, area: str = "fluxo_caixa") -> dict:
    """Pergunta ao CFO IA (diretor financeiro), ancorado nos números reais do ERP. Nunca inventa número.
    area: fluxo_caixa | resultado | tributos | estrategico. Ex.: 'Meu caixa cobre a folha deste mês?'."""
    return await erp.post("/financial/cfo/perguntar", json={"area": area, "pergunta": pergunta})


@mcp.tool
async def previsao_custos_mensais() -> dict:
    """Previsibilidade de custos mensais: folha, FGTS, ISS, diaristas (VT+VR diário e diárias do dia 15),
    fornecedores, reembolsos, e os parcelamentos/acordos/custos fixos registrados. Cada valor traz a fonte."""
    return await erp.get("/financial/cfo/previsao-custos")


@mcp.tool
async def registrar_custo_recorrente(categoria: str, descricao: str, valor: float,
                                     dia_vencimento: int | None = None,
                                     parcelas_total: int | None = None,
                                     parcelas_pagas: int = 0) -> dict:
    """Registra um custo recorrente para entrar na previsão. categoria: tributo | parcelamento | acordo | fixo | fornecedor.
    Ex.: parcelamento (valor da parcela + parcelas_total + parcelas_pagas); aluguel/contador (fixo)."""
    return await erp.post("/financial/cfo/custos-recorrentes", json={
        "categoria": categoria, "descricao": descricao, "valor": valor,
        "dia_vencimento": dia_vencimento, "parcelas_total": parcelas_total, "parcelas_pagas": parcelas_pagas})


@mcp.tool
async def diarias_cadastros() -> dict:
    """Listas para lançar diárias: diaristas, funções, postos/condomínios, turnos e a tabela de preços (Função|Turno→valor)."""
    return await erp.get("/operacional/diarias/cadastros")


@mcp.tool
async def lancar_diaria(diarista_id: int, funcao: str, posto: str, data: str, turno: str | None = None) -> dict:
    """Lança uma diária trabalhada — o valor sai AUTOMÁTICO pela função/turno. data = AAAA-MM-DD.
    turno (só p/ Agente de Portaria): DIURNO | NOTURNO | MEIO PERÍODO. Use diarias_cadastros() para os ids/opções."""
    return await erp.post("/operacional/diarias/lancar", json={
        "diarista_id": diarista_id, "funcao": funcao, "posto": posto, "data": data, "turno": turno})


@mcp.tool
async def resumo_diarias(mes: int, ano: int) -> dict:
    """Resumo das diárias trabalhadas por diarista no mês — a lista que o Financeiro paga no dia 15."""
    return await erp.get("/operacional/diarias/resumo-diarista", params={"mes": mes, "ano": ano})


@mcp.tool
async def gerar_lote_diarias_mes(ano: int, mes: int) -> dict:
    """Gera o lote de pagamento do dia 15 a partir das diárias trabalhadas do mês (fila para o Financeiro pagar)."""
    return await erp.post(f"/financial/pagamentos-diaristas/programar-diarias-mensais/{ano}/{mes}")


@mcp.tool
async def lote_diaristas(data: str | None = None) -> dict:
    """Lote de pagamentos de diaristas a revisar (VT+VR diário e diárias do dia 15). data opcional AAAA-MM-DD.
    O pagamento em lote em si é feito na tela do Financeiro (dinheiro que sai exige aprovação do gestor)."""
    return await erp.get("/financial/pagamentos-diaristas/lote", params=({"data": data} if data else None))


@mcp.tool
async def diaristas_a_cadastrar() -> dict:
    """Diaristas que aparecem no histórico de pagamentos (PIX de R$32 = VT+VR) e ainda NÃO estão cadastrados,
    por frequência. Cada um precisa de CPF (obrigatório) + chave PIX no cadastro do Operacional."""
    return await erp.get("/financial/pagamentos-diaristas/sugestoes-cadastro")


@mcp.tool
async def det_comunicacoes() -> dict:
    """Comunicações do DET (Domicílio Eletrônico Trabalhista) coletadas pelo robô: notificações de
    fiscalização (FGTS/INSS), intimações e avisos. Sinaliza as que exigem ação/escalonamento ao CQB."""
    return await erp.get("/juridico/det/comunicacoes")


@mcp.tool
async def gerar_apresentacao(
    titulo: str,
    slides: list[dict],
    subtitulo: str | None = None,
    cliente: str | None = None,
    local: str | None = None,
    data: str | None = None,
    formato: str = "pdf",
    salvar_no_drive: bool = False,
) -> dict:
    """Gera uma APRESENTAÇÃO no padrão visual Conecta PRO — a MESMA identidade dos documentos
    (capa azul-marinho com faixa laranja + logo, títulos com barra laranja, cards, selos com números
    laranja, rodapé de marca fixo com CNPJ/0800/site, fechamento assinado pelo CEO). Use SEMPRE esta
    ferramenta para montar apresentações/propostas em slides — nunca gere slides fora deste padrão.

    Monte `slides` como uma lista de blocos (a CAPA e o CONTATO são adicionados automaticamente do
    titulo/cliente/local/data e do CEO). Tipos de bloco:
    - {"tipo":"sobre"}  → 4 selos padrão (+12 anos, 100% equipe própria, 24/7, Sentinela IA); customize com "selos":[{"valor","label"}]
    - {"tipo":"problema","titulo":"O Desafio","subtitulo":"...","itens":[{"titulo","desc"}]}  (cards numerados)
    - {"tipo":"solucao"|"escopo"|"diferenciais"|"cards","titulo":"...","subtitulo":"...","cards":[{"titulo","desc"}]}
    - {"tipo":"passos","titulo":"Como Funciona","passos":[{"titulo","desc"}]}  (fluxo numerado)
    - {"tipo":"kpis","titulo":"...","kpis":[{"valor":"+12","label":"anos"}]}
    - {"tipo":"investimento","titulo":"...","opcoes":[{"nome","valor","destaque":true,"itens":["..."]}],"observacao":"..."}
    - {"tipo":"imagem","titulo":"...","legenda":"...","imagem_path":"/caminho.png"}
    - {"tipo":"secao","titulo":"...","subtitulo":"..."}  (divisória de seção)
    - {"tipo":"contato","cta":"Vamos proteger seu pátio?"}
    formato: "pdf" (retorna download_url clicável para enviar ao cliente) ou "pptx" (arquivo editável em base64)."""
    import base64

    payload = {"titulo": titulo, "subtitulo": subtitulo, "cliente": cliente,
               "local": local, "data": data, "slides": slides}
    if (formato or "pdf").lower() == "pptx":
        try:
            raw = await erp.post_bytes("/crm/apresentacoes/gerar?formato=pptx", payload)
        except Exception as exc:  # noqa: BLE001
            return {"gerado": False, "erro": str(exc)[:200]}
        return {"gerado": True, "formato": "pptx", "tamanho_kb": round(len(raw) / 1024, 1),
                "pptx_base64": base64.b64encode(raw).decode("ascii"),
                "obs": "Apresentação editável (PowerPoint) no padrão Conecta PRO."}
    try:
        r = await erp.post(f"/crm/apresentacoes/gerar?formato=pdf&salvar=true&teste=false&drive={'true' if salvar_no_drive else 'false'}", json=payload)
    except Exception as exc:  # noqa: BLE001
        return {"gerado": False, "erro": str(exc)[:200]}
    return {"gerado": True, "formato": "pdf", "titulo": r.get("titulo"), "tamanho_kb": r.get("tamanho_kb"),
            "download_url": r.get("download_url"), "drive_url": r.get("drive_url"), "id": r.get("id"),
            "obs": "Apresentação no padrão Conecta PRO." + (f" Salva no Drive: {r.get('drive_url')}" if r.get("drive_url") else " Abra o download_url para ver/enviar.")}


@mcp.tool
async def gerar_orcamento(
    cliente: str,
    itens: list[dict],
    documento: str | None = None,
    cidade: str | None = None,
    objeto: str | None = None,
    desconto_avista_pct: float | None = None,
    parcelas: int | None = None,
    entrada: float | None = None,
    validade_dias: int | None = None,
    garantia: str | None = None,
    prazo: str | None = None,
    observacao: str | None = None,
    numero: str | None = None,
    salvar_no_drive: bool = False,
) -> dict:
    """Gera um ORÇAMENTO / proposta de PAGAMENTO ÚNICO no padrão-ouro Conecta PRO — para MATERIAL,
    SERVIÇO ou ambos (misto), SEM recorrência mensal. É a opção certa para venda de material,
    serviço avulso ou fornecimento+instalação (diferente da proposta de serviço mensal recorrente).

    `itens`: lista de {"descricao","valor_unit","qtd"(=1),"unidade"("un"),"tipo"("material"|"servico")}.
    Ex.: [{"descricao":"BARREIRA LED CLASS 4,30M","qtd":2,"unidade":"un","valor_unit":750,"tipo":"material"}].
    Pagamento (combine à vontade):
      - desconto_avista_pct: ex. 5  → mostra "À vista com 5% de desconto".
      - parcelas (+ entrada opcional): ex. parcelas=3 → "3x de R$ X (sem juros)".
    documento = CNPJ/CPF do cliente. objeto = 1 linha resumindo o fornecimento (opcional).
    validade_dias (15), garantia (material), prazo — vão no bloco Condições.
    Retorna download_url (link clicável para enviar/imprimir). Assinatura: cliente + CEO."""
    condicoes = {}
    if validade_dias is not None:
        condicoes["validade_dias"] = validade_dias
    if garantia:
        condicoes["garantia"] = garantia
    if prazo:
        condicoes["prazo"] = prazo
    payload = {
        "cliente": cliente, "itens": itens, "documento": documento, "cidade": cidade,
        "objeto": objeto, "desconto_avista_pct": desconto_avista_pct, "parcelas": parcelas,
        "entrada": entrada, "observacao": observacao, "numero": numero,
        "condicoes": condicoes or None,
    }
    return await _gerar_doc("/crm/docs/orcamento/pdf", payload, drive=salvar_no_drive)


# =================================================================== JURÍDICO


@mcp.tool
async def consultar_juridico(area: str, pergunta: str) -> dict:
    """Pergunta ao CONSULTOR JURÍDICO IA do Conecta PRO (fundamentado, com contexto REAL do ERP).
    area: 'trabalhista' | 'civel' | 'tributaria'. Ex.: pergunta='Posso descontar aviso prévio não cumprido?'.
    Retorna resposta estruturada (fundamentos, riscos, recomendação). READ-ONLY, não altera nada."""
    try:
        return await erp.post("/juridico/consultor/perguntar", json={"area": area, "pergunta": pergunta})
    except Exception as exc:  # noqa: BLE001
        return {"erro": str(exc)[:200]}


@mcp.tool
async def analisar_processo_juridico(
    texto: str, numero: str | None = None, tipo: str | None = None, employee_id: str | None = None
) -> dict:
    """Analisa um PROCESSO/notificação a partir do texto colado: extrai pedidos, monta dossiê com dado
    REAL do ERP (funcionário/contrato) e gera linha de defesa IA (com 'como obter' as provas).
    tipo ex.: 'trabalhista'. employee_id: dica de qual funcionário, se souber."""
    payload = {"texto": texto, "numero": numero, "tipo": tipo, "employee_id": employee_id}
    try:
        return await erp.post("/juridico/processos", json=payload)
    except Exception as exc:  # noqa: BLE001
        return {"erro": str(exc)[:200]}


@mcp.tool
async def gerar_parecer_juridico(area: str, titulo: str, contexto: str) -> dict:
    """Gera um PARECER JURÍDICO (rascunho IA) sobre um tema. area: trabalhista|civel|tributaria.
    contexto = situação/fatos a analisar. Retorna o parecer estruturado (registrado no ERP)."""
    try:
        return await erp.post("/juridico/pareceres", json={"area": area, "titulo": titulo, "contexto": contexto})
    except Exception as exc:  # noqa: BLE001
        return {"erro": str(exc)[:200]}


@mcp.tool
async def dossie_juridico(tipo: str, identificador: str | None = None) -> dict:
    """Dossiê jurídico READ-ONLY cross-módulo do Conecta PRO. tipo:
    - 'panorama'   → visão geral (passivos, contratos, riscos).
    - 'funcionario'→ identificador = nome/CPF/id do funcionário (histórico, ponto, advertências, folha).
    - 'contrato'   → identificador = número/id do contrato.
    - 'cliente'    → identificador = id do cliente.
    Reúne o contexto real para embasar defesa/consulta — não inventa nada."""
    t = (tipo or "").strip().lower()
    try:
        if t == "panorama":
            return await erp.get("/juridico/contexto/panorama")
        if t in ("funcionario", "funcionário", "pessoa"):
            return await erp.get(f"/juridico/contexto/funcionario/{identificador}")
        if t == "contrato":
            return await erp.get(f"/juridico/contexto/contrato/{identificador}")
        if t == "cliente":
            return await erp.get(f"/juridico/contexto/cliente/{identificador}")
        return {"erro": f"tipo inválido '{tipo}'. Use: panorama | funcionario | contrato | cliente."}
    except Exception as exc:  # noqa: BLE001
        return {"erro": str(exc)[:200]}


@mcp.tool
async def painel_juridico() -> dict:
    """Painel do Jurídico: dashboard consolidado (dado real) + prazos/compliance vencendo (≤7/≤15/≤30
    dias e atrasados). Use para saber a situação jurídica e o que está prestes a vencer."""
    out: dict = {}
    try:
        out["dashboard"] = await erp.get("/juridico/dashboard")
    except Exception as exc:  # noqa: BLE001
        out["dashboard_erro"] = str(exc)[:150]
    try:
        out["prazos_alertas"] = await erp.get("/juridico/prazos/alertas")
    except Exception as exc:  # noqa: BLE001
        out["prazos_erro"] = str(exc)[:150]
    return out



# =================================================================== DP / PEOPLE-MANAGEMENT (Pyetra)


# ---- Funcionários ----
@mcp.tool
async def listar_funcionarios(busca: str | None = None, page: int = 1, page_size: int = 30) -> dict:
    """Lista funcionários (DP). busca = nome/CPF/matrícula. Paginação page/page_size."""
    params = {"page": page, "page_size": page_size}
    if busca:
        params["search"] = busca
    return await erp.get("/people-management/hr/employees", params=params)


@mcp.tool
async def buscar_funcionario(busca: str) -> dict:
    """Busca rápida de funcionário por nome/CPF/matrícula (retorna os que casam)."""
    return await erp.get("/people-management/hr/employees/search", params={"q": busca, "search": busca})


@mcp.tool
async def obter_funcionario(employee_id: str) -> dict:
    """Dados cadastrais de um funcionário pelo id."""
    return await erp.get(f"/people-management/hr/employees/{employee_id}")


@mcp.tool
async def buscar_funcionario_por_cpf(cpf: str) -> dict:
    """Localiza um funcionário pelo CPF (só dígitos ou formatado)."""
    return await erp.get(f"/people-management/hr/employees/cpf/{cpf}")


@mcp.tool
async def ficha_funcionario(employee_id: str) -> dict:
    """Ficha/perfil completo do funcionário (dados + vínculos)."""
    return await erp.get(f"/people-management/hr/employees/{employee_id}/profile")


@mcp.tool
async def estatisticas_funcionarios() -> dict:
    """Estatísticas de pessoal (headcount, por cargo/status)."""
    return await erp.get("/people-management/hr/employees/stats")


# ---- Folha de pagamento ----
@mcp.tool
async def folha_dashboard(mes: int, ano: int) -> dict:
    """Dashboard da FOLHA do mês (total colaboradores, proventos, descontos, líquido, FGTS, INSS, fonte)."""
    return await erp.get("/people-management/folha/dashboard", params={"mes": mes, "ano": ano})


@mcp.tool
async def resumo_folha(mes: int, ano: int) -> dict:
    """Resumo consolidado da folha de uma competência (mes/ano)."""
    return await erp.get(f"/people-management/folha/resumo/{mes}/{ano}")


@mcp.tool
async def calcular_holerite(employee_id: str, mes: int, ano: int) -> dict:
    """Calcula o holerite completo (CCT 2026) de um funcionário na competência mes/ano."""
    return await erp.get(f"/people-management/folha/calcular/{employee_id}/{mes}/{ano}")


@mcp.tool
async def baixar_holerite_pdf(employee_id: str, mes: int, ano: int) -> dict:
    """Gera o HOLERITE em PDF (padrão-ouro, só assinatura do funcionário) — retorna base64."""
    return await _pdf_b64(f"/people-management/folha/holerite/{employee_id}/{mes}/{ano}/pdf")


@mcp.tool
async def baixar_recibo_vt_vr_pdf(employee_id: str, mes: int, ano: int) -> dict:
    """Gera o recibo de VT/VR em PDF (só assinatura do funcionário) — retorna base64."""
    return await _pdf_b64(f"/people-management/folha/recibo-vt-vr/{employee_id}/{mes}/{ano}/pdf")


@mcp.tool
async def listar_rubricas_folha() -> dict:
    """Lista as rubricas da folha (proventos/descontos cadastrados)."""
    return await erp.get("/people-management/folha/rubricas")


@mcp.tool
async def calcular_folha_todos(mes: int, ano: int) -> dict:
    """Calcula a folha do mês para TODOS os funcionários ativos (lote)."""
    return await erp.post(f"/people-management/folha/calcular/todos/{mes}/{ano}", json={})


@mcp.tool
async def fechar_folha(mes: int, ano: int) -> dict:
    """FECHA a folha de uma competência (mes/ano). Ação de gestão — confirme antes."""
    return await erp.post(f"/people-management/folha/fechar/{mes}/{ano}", json={})


# ---- Ponto eletrônico ----
@mcp.tool
async def ponto_dashboard(mes: int, ano: int) -> dict:
    """Dashboard do PONTO do mês (batidas, inconsistências, banco de horas consolidado)."""
    return await erp.get("/people-management/ponto/dashboard", params={"mes": mes, "ano": ano})


@mcp.tool
async def espelho_ponto(employee_id: str, mes: int, ano: int) -> dict:
    """Espelho de ponto mensal de um funcionário (escala, horas esperadas/trabalhadas, saldo)."""
    return await erp.get(f"/people-management/ponto/espelho/{employee_id}", params={"month": mes, "year": ano})


@mcp.tool
async def banco_horas(employee_id: str, mes: int | None = None, ano: int | None = None) -> dict:
    """Saldo de banco de horas de um funcionário (12x36→180h; 44h→220h)."""
    params = {}
    if mes:
        params["mes"] = mes
    if ano:
        params["ano"] = ano
    return await erp.get(f"/people-management/ponto/banco-horas/{employee_id}", params=params or None)


@mcp.tool
async def colaboradores_sem_escala() -> dict:
    """Lista funcionários ativos SEM escala cadastrada (precisam de definição no DP)."""
    return await erp.get("/people-management/ponto/colaboradores-sem-escala")


@mcp.tool
async def justificativas_ponto_pendentes() -> dict:
    """Lista as justificativas de ponto aguardando revisão do DP."""
    return await erp.get("/people-management/ponto/justificativas/pendentes")


@mcp.tool
async def revisar_justificativa_ponto(justification_id: str, aprovar: bool, observacao: str | None = None) -> dict:
    """Aprova (aprovar=True) ou rejeita uma justificativa de ponto."""
    return await erp.request("PUT", f"/people-management/ponto/justificativa/{justification_id}/revisar",
                             json={"aprovar": aprovar, "aprovada": aprovar, "observacao": observacao})


@mcp.tool
async def status_fechamento_ponto(mes: int, ano: int) -> dict:
    """Estado real do fechamento do ponto por competência (quantos fechados/pendentes)."""
    return await erp.get("/people-management/ponto/fechamento/status", params={"month": mes, "year": ano})


@mcp.tool
async def fechar_mes_ponto(mes: int, ano: int) -> dict:
    """FECHA o mês do ponto para todos (idempotente). Ação de gestão — confirme antes."""
    return await erp.post("/people-management/ponto/fechamento-mes", json={"mes": mes, "ano": ano})


# ---- Férias ----
@mcp.tool
async def listar_ferias(status: str | None = None, page: int = 1, page_size: int = 30) -> dict:
    """Lista solicitações de férias (todos). status opcional (ex.: 'aprovado','solicitado')."""
    params = {"page": page, "page_size": page_size}
    if status:
        params["status"] = status
    return await erp.get("/people-management/hr/vacations", params=params)


@mcp.tool
async def ferias_funcionario(employee_id: str) -> dict:
    """Férias de um funcionário específico."""
    return await erp.get(f"/people-management/hr/vacations/employee/{employee_id}")


@mcp.tool
async def saldo_ferias(employee_id: str) -> dict:
    """Saldo e período aquisitivo de férias de um funcionário (alerta de vencidas)."""
    return await erp.get(f"/people-management/hr/vacations/employee/{employee_id}/balance")


@mcp.tool
async def solicitar_ferias(employee_id: str, data_inicio: str, dias: int = 30, observacao: str | None = None) -> dict:
    """Cria uma solicitação de férias. data_inicio no formato YYYY-MM-DD; dias (ex.: 30)."""
    return await erp.post("/people-management/hr/vacations", json={
        "employee_id": employee_id, "data_inicio": data_inicio, "start_date": data_inicio,
        "dias": dias, "days": dias, "observacao": observacao})


@mcp.tool
async def aprovar_ferias(vacation_id: str, observacao: str | None = None) -> dict:
    """Aprova uma solicitação de férias."""
    return await erp.post(f"/people-management/hr/vacations/{vacation_id}/approve",
                          json={"observacao": observacao})


# ---- Admissão ----
@mcp.tool
async def listar_admissoes(status: str | None = None) -> dict:
    """Lista processos de admissão em andamento."""
    return await erp.get("/people-management/hr/admissions", params={"status": status} if status else None)


@mcp.tool
async def concluir_admissao(admission_id: str) -> dict:
    """Finaliza uma admissão (gera o funcionário efetivo). Confirme os documentos antes."""
    return await erp.post(f"/people-management/hr/admissions/{admission_id}/complete", json={})


# ---- Rescisão ----
@mcp.tool
async def listar_rescisoes(status: str | None = None) -> dict:
    """Lista processos de rescisão."""
    return await erp.get("/people-management/hr/terminations", params={"status": status} if status else None)


@mcp.tool
async def calcular_verbas_rescisorias(termination_id: str) -> dict:
    """Calcula as verbas rescisórias de um processo de rescisão."""
    return await erp.post(f"/people-management/hr/terminations/{termination_id}/calculate", json={})


# ---- Benefícios ----
@mcp.tool
async def listar_beneficios_funcionario(employee_id: str) -> dict:
    """Benefícios (VT/VR/plano) de um funcionário."""
    return await erp.get(f"/people-management/hr/benefits/employee/{employee_id}")


# ---- SST (saúde ocupacional) ----
@mcp.tool
async def sst_dashboard() -> dict:
    """Dashboard de SST (ASOs, EPIs, PCMSO, PPRA, acidentes)."""
    return await erp.get("/people-management/sst/dashboard")


@mcp.tool
async def asos_vencendo(dias: int = 30) -> dict:
    """ASOs (exames ocupacionais) vencendo nos próximos N dias."""
    return await erp.get("/people-management/sst/asos/vencendo", params={"dias": dias})


@mcp.tool
async def funcionarios_sem_aso() -> dict:
    """Funcionários sem ASO válido (pendência de saúde ocupacional)."""
    return await erp.get("/people-management/sst/asos/sem-aso")




# =================================================================== FISCAL / CONTÁBIL


# ---- NFS-e ----
@mcp.tool
async def listar_nfse(competencia: str | None = None, limit: int = 50) -> dict:
    """Lista NFS-e emitidas (fonte real gov.br, só cStat 100). competencia='YYYY-MM' opcional."""
    params = {"limit": limit}
    if competencia:
        params["competencia"] = competencia
    return await erp.get("/financial/nfse", params=params)


@mcp.tool
async def dashboard_nfse() -> dict:
    """Painel de faturamento por NFS-e: total de notas, valor, ISS, por competência e por cliente."""
    return await erp.get("/financial/nfse/dashboard")


@mcp.tool
async def listar_nfse_entrada() -> dict:
    """Lista NFS-e de ENTRADA (tomadas contra o CNPJ) — custos/fornecedores."""
    return await erp.get("/financial/nfse-entrada")


@mcp.tool
async def resumo_nfse_entrada() -> dict:
    """Resumo fiscal das NFS-e de entrada (retenções, tributos)."""
    return await erp.get("/financial/nfse-entrada/resumo-fiscal")


# ---- Dashboards fiscais ----
@mcp.tool
async def dashboard_fiscal() -> dict:
    """Painel fiscal consolidado (NFS-e, tributos, obrigações, INSS/FGTS)."""
    return await erp.get("/financial/fiscal/dashboard")


@mcp.tool
async def dashboard_fiscal_grupo(mes: int | None = None, ano: int | None = None) -> dict:
    """Painel fiscal do GRUPO (multi-empresa): receita/impostos por CNPJ na competência."""
    params = {}
    if mes:
        params["mes"] = mes
    if ano:
        params["ano"] = ano
    return await erp.get("/empresas/dashboard/fiscal/grupo", params=params or None)


@mcp.tool
async def rentabilidade_grupo() -> dict:
    """Rentabilidade/margem comparada entre as empresas do grupo."""
    return await erp.get("/empresas/dashboard/rentabilidade/grupo")


@mcp.tool
async def contabil_grupo() -> dict:
    """Painel contábil consolidado do grupo."""
    return await erp.get("/empresas/dashboard/contabil/grupo")


@mcp.tool
async def monitor_integracoes_gov() -> dict:
    """Monitoramento das integrações gov (SEFAZ/eSocial/e-CAC/etc.): online/degraded."""
    return await erp.get("/government/dashboard/")


@mcp.tool
async def alertas_certificados() -> dict:
    """Alertas de vencimento de certificados digitais A1/A3."""
    return await erp.get("/government/dashboard/certificados/alertas")


# ---- DAS / Simples ----
@mcp.tool
async def status_simples_nacional() -> dict:
    """Situação/opção no Simples Nacional (anexo, sublimite, pendências)."""
    return await erp.get("/government/simples-nacional/status")


@mcp.tool
async def pendencias_simples() -> dict:
    """Pendências no Simples Nacional."""
    return await erp.get("/government/simples-nacional/pendencias")


# ---- Obrigações ----
@mcp.tool
async def alertas_obrigacoes() -> dict:
    """Alertas de obrigações acessórias vencendo/vencidas (grupo)."""
    return await erp.get("/empresas/obrigacoes/alertas")


@mcp.tool
async def calendario_obrigacoes() -> dict:
    """Calendário de obrigações fiscais do grupo (multi-empresa)."""
    return await erp.get("/empresas/obrigacoes/calendario/grupo")


# ---- Certidões / e-CAC ----
@mcp.tool
async def listar_certidoes() -> dict:
    """Lista certidões (CND, FGTS, trabalhista) e validade."""
    return await erp.get("/ged/certidoes")


@mcp.tool
async def situacao_fiscal_ecac() -> dict:
    """Situação fiscal no e-CAC (regularidade)."""
    return await erp.get("/government/ecac/situacao-fiscal")


@mcp.tool
async def debitos_ecac() -> dict:
    """Débitos no e-CAC."""
    return await erp.get("/government/ecac/debitos")


@mcp.tool
async def resumo_ecac() -> dict:
    """Resumo/status do e-CAC (situação, declarações, parcelamentos)."""
    return await erp.get("/government/ecac/status")


# ---- eSocial / FGTS / DCTFWeb ----
@mcp.tool
async def listar_eventos_esocial() -> dict:
    """Lista eventos do eSocial registrados (só transmissões reais)."""
    return await erp.get("/government/esocial/eventos")


@mcp.tool
async def gaps_esocial() -> dict:
    """Funcionários com pendências/faltando eventos no eSocial."""
    return await erp.get("/government/esocial/gaps-funcionarios")


@mcp.tool
async def status_dctfweb() -> dict:
    """Status/configuração da DCTFWeb."""
    return await erp.get("/government/dctfweb/status")


@mcp.tool
async def status_fgts_digital() -> dict:
    """Status do FGTS Digital."""
    return await erp.get("/government/fgts-digital/status")


@mcp.tool
async def guias_fgts() -> dict:
    """Lista/gera guias de FGTS."""
    return await erp.get("/government/fgts/guias")


# ---- Empresas ----
@mcp.tool
async def listar_empresas() -> dict:
    """Lista as empresas/CNPJs do grupo econômico."""
    return await erp.get("/empresas/")




# =================================================================== OPERACIONAL / CAMPO


@mcp.tool
async def dashboard_operacional() -> dict:
    """Painel operacional: postos ativos, colaboradores, alocações, turnos hoje, ocorrências, cobertura."""
    return await erp.get("/operacional/dashboard/")


@mcp.tool
async def listar_postos(status: str | None = None, busca: str | None = None, page: int = 1, page_size: int = 30) -> dict:
    """Lista POSTOS de trabalho (com filtros de status/busca)."""
    params = {"page": page, "page_size": page_size}
    if status:
        params["status"] = status
    if busca:
        params["search"] = busca
    return await erp.get("/operacional/posts/", params=params)


@mcp.tool
async def estatisticas_postos() -> dict:
    """KPIs de postos (total, ativos, com/sem vaga)."""
    return await erp.get("/operacional/posts/stats")


@mcp.tool
async def listar_escalas(mes: int | None = None, ano: int | None = None, page: int = 1, page_size: int = 30) -> dict:
    """Lista ESCALAS (12x36, 44h etc.), com filtro por mês/ano."""
    params = {"page": page, "page_size": page_size}
    if mes:
        params["month"] = mes
    if ano:
        params["year"] = ano
    return await erp.get("/operacional/scales/", params=params)


@mcp.tool
async def listar_alocacoes(post_id: str | None = None, employee_id: str | None = None, page: int = 1) -> dict:
    """Lista ALOCAÇÕES (funcionário↔posto). Filtra por post_id/employee_id."""
    params = {"page": page, "page_size": 30}
    if post_id:
        params["post_id"] = post_id
    if employee_id:
        params["employee_id"] = employee_id
    return await erp.get("/operacional/allocations/", params=params)


@mcp.tool
async def alocacoes_vigentes(post_id: str | None = None) -> dict:
    """Alocações ativas no momento (opcional: de um posto específico)."""
    return await erp.get("/operacional/allocations/current", params={"post_id": post_id} if post_id else None)


@mcp.tool
async def funcionarios_disponiveis_posto(post_id: str) -> dict:
    """Funcionários livres para alocar num posto (post_id obrigatório)."""
    return await erp.get("/operacional/allocations/available-employees", params={"post_id": post_id})


@mcp.tool
async def listar_ocorrencias(status: str | None = None, severity: str | None = None, page: int = 1) -> dict:
    """Lista OCORRÊNCIAS operacionais (filtra por status/severidade)."""
    params = {"page": page, "page_size": 30}
    if status:
        params["status"] = status
    if severity:
        params["severity"] = severity
    return await erp.get("/operacional/occurrences/", params=params)


@mcp.tool
async def relatorio_cobertura(start_date: str | None = None, end_date: str | None = None) -> dict:
    """Relatório de cobertura (postos × alocações, taxa de cobertura). Datas YYYY-MM-DD."""
    params = {}
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    return await erp.get("/operacional/reports/coverage", params=params or None)


@mcp.tool
async def listar_ordens_servico(status: str | None = None, page: int = 1, page_size: int = 30) -> dict:
    """Lista ORDENS DE SERVIÇO de campo (instalação/manutenção)."""
    params = {"page": page, "page_size": page_size}
    if status:
        params["status"] = status
    return await erp.get("/campo/os/", params=params)


@mcp.tool
async def dashboard_ordens_servico() -> dict:
    """Estatísticas de OS de campo (abertas, atrasadas, por técnico)."""
    return await erp.get("/campo/os/dashboard")


@mcp.tool
async def listar_visitas_campo(status: str | None = None, page: int = 1) -> dict:
    """Lista VISITAS de campo (técnicas/comerciais agendadas)."""
    params = {"page": page, "page_size": 30}
    if status:
        params["status"] = status
    return await erp.get("/campo/visitas/", params=params)


@mcp.tool
async def dashboard_campo() -> dict:
    """Painel do módulo de campo (OS + visitas + técnicos)."""
    return await erp.get("/campo/dashboard")


# =================================================================== RH / SST / CCT / REEMBOLSO


@mcp.tool
async def listar_vagas(status: str | None = None) -> dict:
    """Lista VAGAS de recrutamento (status opcional)."""
    return await erp.get("/recruitment/job-positions", params={"status": status} if status else None)


@mcp.tool
async def vagas_abertas() -> dict:
    """Lista só as vagas ABERTAS (em recrutamento)."""
    return await erp.get("/recruitment/job-positions/open")


@mcp.tool
async def listar_candidatos(busca: str | None = None, page: int = 1) -> dict:
    """Lista CANDIDATOS do recrutamento (busca opcional)."""
    params = {"page": page, "page_size": 30}
    if busca:
        params["q"] = busca
    return await erp.get("/recruitment/candidates", params=params)


@mcp.tool
async def listar_entrevistas() -> dict:
    """Lista ENTREVISTAS agendadas do recrutamento."""
    return await erp.get("/recruitment/interviews")


@mcp.tool
async def estoque_epi() -> dict:
    """Estoque de EPIs (equipamentos de proteção — NR-6)."""
    return await erp.get("/health-occupational/epi/estoque")


@mcp.tool
async def status_pcmso() -> dict:
    """Estatísticas/status do PCMSO (exames ocupacionais — NR-7)."""
    return await erp.get("/health-occupational/pcmso/estatisticas")


@mcp.tool
async def status_ppra() -> dict:
    """Estatísticas do PPRA/PGR (riscos ocupacionais — NR-9)."""
    return await erp.get("/health-occupational/ppra/estatisticas")


@mcp.tool
async def listar_reembolsos(status: str | None = None) -> dict:
    """Lista solicitações de REEMBOLSO (status opcional)."""
    return await erp.get("/reimbursements/", params={"status": status} if status else None)


@mcp.tool
async def reembolsos_pendentes_aprovacao() -> dict:
    """Reembolsos aguardando aprovação."""
    return await erp.get("/reimbursements/approvals/pending")


@mcp.tool
async def reembolsos_prontos_pagamento() -> dict:
    """Reembolsos aprovados e prontos para pagamento."""
    return await erp.get("/reimbursements/ready-for-payment")


@mcp.tool
async def tabela_salarial_cct() -> dict:
    """Tabela salarial completa da CCT SINDECOMPRESTS 2026 (pisos por cargo)."""
    return await erp.get("/cct/salarios/tabela")


@mcp.tool
async def beneficios_cct(cargo: str | None = None) -> dict:
    """Benefícios previstos na CCT (VT/VR/cesta) — opcional por cargo."""
    return await erp.get("/cct/beneficios", params={"cargo": cargo} if cargo else None)


@mcp.tool
async def dashboard_clima() -> dict:
    """Indicadores da pesquisa de clima organizacional."""
    return await erp.get("/retention/climate/dashboard")



# =================================================================== ASGI app
# ============================================================================
# ATUALIZAÇÃO 2026-07-16 — recursos novos (tudo READ-ONLY; dinheiro que sai
# continua SÓ pela tela com gate OTP humano — o conector não executa pagamento)
# ============================================================================

@mcp.tool
async def inter_saldo() -> dict:
    """Saldo atual da conta Banco Inter (leitura, tempo real)."""
    return await erp.get("/financeiro/inter/saldo")


@mcp.tool
async def inter_extrato_resumo() -> dict:
    """Resumo do extrato Inter (entradas/saídas recentes, conciliação)."""
    return await erp.get("/financeiro/inter/extrato/resumo")


@mcp.tool
async def listar_pagamentos_inter(page_size: int = 20) -> dict:
    """Pagamentos feitos pelo Inter (PIX/boleto/DARF): valor, status, categoria, datas."""
    return await erp.get("/financeiro/inter/payments", params={"page_size": page_size})


@mcp.tool
async def baixar_comprovante_pagamento_pdf(payment_id: str) -> dict:
    """Comprovante em PDF (padrão-ouro) de um pagamento Inter CONCLUÍDO — retorna base64."""
    return await _pdf_b64(f"/financeiro/inter/payments/{payment_id}/comprovante")


@mcp.tool
async def teto_diario_pagamentos() -> dict:
    """Teto diário de pagamentos (CONECTA_LIMITE_DIARIO) vs quanto já saiu hoje."""
    return await erp.get("/financeiro/inter/payments/saldo-limite")


@mcp.tool
async def divergencias_folha_pagamentos() -> dict:
    """Divergências entre a folha calculada e os pagamentos Inter (antes de pagar)."""
    return await erp.get("/financeiro/inter/payroll/divergencias")


@mcp.tool
async def pix_recebidos() -> dict:
    """PIX recebidos na conta Inter (entradas identificadas)."""
    return await erp.get("/financeiro/inter/pix/recebidos")


@mcp.tool
async def listar_cobrancas_inter() -> dict:
    """Cobranças/boletos emitidos pelo Inter e seus status."""
    return await erp.get("/financeiro/inter/cobrancas")


@mcp.tool
async def listar_beneficiarios_pix() -> dict:
    """Agenda de beneficiários PIX (nome → chave salva; employees usam pix_key)."""
    return await erp.get("/financial/beneficiarios")


@mcp.tool
async def status_dominio() -> dict:
    """Status da integração com a contabilidade Domínio (plano de contas, conexão)."""
    return await erp.get("/empresas/dominio/status")


@mcp.tool
async def exportar_folha_dominio(competencia: str) -> dict:
    """Export da folha no layout Domínio (motor read-only — NÃO fecha a folha). competencia: 'YYYY-MM'."""
    return await erp.get(f"/people-management/hr/payroll-export/dominio/{competencia}")


@mcp.tool
async def esocial_espelho_resumo() -> dict:
    """Espelho eSocial: resumo dos eventos transmitidos vs pendentes por funcionário."""
    return await erp.get("/government/esocial/espelho/resumo")


@mcp.tool
async def esocial_timeline_funcionario(employee_id: str) -> dict:
    """Linha do tempo eSocial de um funcionário (S-2200/2230/2299 e protocolos)."""
    return await erp.get(f"/government/esocial/espelho/timeline/{employee_id}")


@mcp.tool
async def presenca_ao_vivo() -> dict:
    """PRESENÇA AO VIVO de hoje: escala × batidas por posto (TZ Manaus), faltas e atrasos."""
    return await erp.get("/operacional/presenca/hoje")


@mcp.tool
async def substitutos_disponiveis(posto_id: str) -> dict:
    """Substitutos disponíveis para cobrir falta num posto (mesmo cargo, sem conflito de escala)."""
    return await erp.get(f"/operacional/presenca/substitutos/{posto_id}")


@mcp.tool
async def substituicoes_pendentes() -> dict:
    """Faltas com substituição ainda pendente de resolução."""
    return await erp.get("/operacional/substitutions/pending")


@mcp.tool
async def listar_substituicoes(data: str | None = None) -> dict:
    """Substituições registradas (falta → substituto). data opcional 'YYYY-MM-DD'."""
    if data:
        return await erp.get(f"/operacional/substitutions/by-date/{data}")
    return await erp.get("/operacional/substitutions")


@mcp.tool
async def grade_postos() -> dict:
    """Grade de escala por posto (visão geral: quem cobre o quê, 12x36/comercial)."""
    return await erp.get("/operacional/grade/postos")


@mcp.tool
async def grade_do_posto(posto_id: str) -> dict:
    """Grade de escala POR PESSOA de um posto (leitura; edição é só na tela, pelo Jordan/Gonzaga/Paiva)."""
    return await erp.get(f"/operacional/grade/{posto_id}")


@mcp.tool
async def listar_comunicados() -> dict:
    """Comunicados internos publicados (sino do ERP)."""
    return await erp.get("/operacional/comunicados")


@mcp.tool
async def comunicados_nao_lidos() -> dict:
    """Comunicados internos ainda não lidos pelos destinatários (cobrança de leitura)."""
    return await erp.get("/operacional/comunicados/nao-lidos")


@mcp.tool
async def painel_espelho_ponto(mes: int, ano: int) -> dict:
    """Painel do espelho de ponto da competência: todos os funcionários, horas e pendências."""
    return await erp.get(f"/people-management/hr/ponto/espelho/painel/{mes}/{ano}")


@mcp.tool
async def baixar_espelho_ponto_pdf(employee_id: str, mes: int, ano: int) -> dict:
    """Espelho de ponto mensal de um funcionário em PDF (padrão-ouro) — retorna base64."""
    return await _pdf_b64(f"/people-management/hr/ponto/espelho/{employee_id}/{mes}/{ano}/pdf")


_ORIGENS = ("ceo", "cfo", "fiscal", "rh", "juridico", "comercial", "operacional", "ged")


async def _consultar(origem: str, pergunta: str) -> dict:
    return await erp.post(f"/consultores/mcp/{origem}/consultar", json={"pergunta": pergunta})


@mcp.tool
async def consultor_ceo(pergunta: str) -> dict:
    """Consultor executivo (CEO): visão estratégica, runway, decisão. Único que cruza dinheiro+legal+gente por cliente (gated). READ."""
    return await _consultar("ceo", pergunta)


@mcp.tool
async def consultor_cfo(pergunta: str) -> dict:
    """Consultor financeiro (CFO): caixa, aging, o que vence, saúde financeira. READ."""
    return await _consultar("cfo", pergunta)


@mcp.tool
async def consultor_fiscal(pergunta: str) -> dict:
    """Consultor fiscal/contábil: notas, guias, regime, obrigações. READ."""
    return await _consultar("fiscal", pergunta)


@mcp.tool
async def consultor_dp(pergunta: str) -> dict:
    """Consultor de DP/RH: folha, ponto, colaboradores, CCT. READ."""
    return await _consultar("rh", pergunta)


@mcp.tool
async def consultor_juridico(pergunta: str) -> dict:
    """Consultor jurídico (READ-ONLY): processos, dossiê. Aconselha, nunca protocola. READ."""
    return await _consultar("juridico", pergunta)


@mcp.tool
async def consultor_comercial(pergunta: str) -> dict:
    """Consultor comercial/CRM: funil, propostas, clientes. READ."""
    return await _consultar("comercial", pergunta)


@mcp.tool
async def consultor_operacional(pergunta: str) -> dict:
    """Consultor operacional (READ-ONLY): postos, escalas, presença. Nunca altera escala. READ."""
    return await _consultar("operacional", pergunta)


@mcp.tool
async def consultor_ged(pergunta: str) -> dict:
    """Consultor de GED/documentos: kits, panorama documental. READ."""
    return await _consultar("ged", pergunta)


@mcp.tool
async def registrar_feedback(origem: str, correcao: str, consulta_id: int | None = None) -> dict:
    """🔵 Registra uma correção do gestor como memória permanente do consultor (realimenta o ERP). origem ∈ ceo/cfo/fiscal/rh/juridico/comercial/operacional/ged."""
    return await erp.post("/consultores/mcp/feedback", json={"origem": origem, "correcao": correcao, "consulta_id": consulta_id})


@mcp.tool
async def propor_pagamento(valor: float, pix_key: str, descricao: str = "") -> dict:
    """🟡 PROPÕE um pagamento PIX — grava PENDENTE ('preparado'). NÃO executa: requer aprovação humana + OTP. Nunca move dinheiro sozinho."""
    return await erp.post("/consultores/mcp/propor-pagamento", json={"valor": valor, "pix_key": pix_key, "descricao": descricao})


@mcp.tool
async def propor_comunicado(titulo: str, corpo: str) -> dict:
    """🟡 PROPÕE um comunicado — grava RASCUNHO. NÃO publica/envia: requer aprovação humana."""
    return await erp.post("/consultores/mcp/propor-comunicado", json={"titulo": titulo, "corpo": corpo})


# ------------------------------------------- Fase 5.2a.4: quick-wins executivos (🟢 read)
@mcp.tool
async def consultar_viabilidade_contratacao(qtd: int, cargo: str) -> dict:
    """🟢 "Posso contratar N do cargo X?" — cruza caixa/runway (CFO) + postos descobertos (COO)
    + custo de folha (qtd × piso CCT + encargos). Cada número com proveniência; síntese ancorada
    (groundedness). Só LEITURA — não contrata, não move dinheiro. READ."""
    return await erp.post("/consultores/mcp/executivo/viabilidade-contratacao",
                          json={"qtd": qtd, "cargo": cargo})


@mcp.tool
async def briefing_executivo() -> dict:
    """🟢 1-card executivo do dia: caixa (saldo Inter), postos descobertos, certidões vencendo,
    deals quentes. Cada número com source; o que não tiver lastro vem 'aguardando dado'. READ."""
    return await erp.get("/consultores/mcp/executivo/briefing")


@mcp.tool
async def runway_ao_vivo() -> dict:
    """🟢 Runway de caixa AO VIVO: saldo Inter vivo ÷ folha mensal = meses, com as_of
    (corrige o KPI de cache velho). READ."""
    return await erp.get("/consultores/mcp/executivo/runway")


@mcp.tool
async def margem_por_condominio() -> dict:
    """🟢 Margem por contrato: receita (contrato) − folha alocada (best-effort). Onde o
    cruzamento não fecha, a folha vem 'aguardando dado' — nunca estimada. READ."""
    return await erp.get("/consultores/mcp/executivo/margem-condominio")


_mcp_app = mcp.http_app(path="/mcp")


async def _healthz(_request):
    return JSONResponse({"ok": True, "service": "conecta-pro-mcp"})


_base = Starlette(
    routes=[Route("/healthz", _healthz), Mount("/", app=_mcp_app)],
    lifespan=_mcp_app.lifespan,
)


class _BearerASGI:
    """Auth de entrada por Bearer token (pura ASGI — não quebra streaming/SSE do MCP)."""

    def __init__(self, app, token: str):
        self.app = app
        self.token = token

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and self.token:
            if scope.get("path") != "/healthz":
                headers = dict(scope.get("headers") or [])
                if headers.get(b"authorization", b"").decode() != f"Bearer {self.token}":
                    await JSONResponse({"error": "unauthorized"}, status_code=401)(scope, receive, send)
                    return
        await self.app(scope, receive, send)


if AUTH_MODE == "google":
    # FastMCP + GoogleProvider já protegem o /mcp (OAuth). Não envolve no Bearer.
    app = _base
else:
    app = _BearerASGI(_base, MCP_AUTH_TOKEN)

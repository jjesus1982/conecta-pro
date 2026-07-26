"""Controller MCP dos consultores — superfície 🟢🔵🟡 que o conector chama.
Cada endpoint é a contraparte de uma tool MCP em mcp-server/server.py.

Task 3 (Fase 5.1) implementa só o endpoint de consulta unificado (🟢, read):
POST /consultores/mcp/{origem}/consultar. Tasks 4/5/6 adicionam feedback/
propor-pagamento/propor-comunicado neste mesmo router — mantenha extensível.
"""
import json
import os
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_active_user
from core.database import get_db
from modules.ai.conversation.services import consultor_hub as _hub
from modules.ai.conversation.services.consultor_hub import TABELAS_CONSULTAS  # origem -> (tabela, rótulo)
from modules.operacional.communication.models.announcement import Announcement, AnnouncementStatus

router = APIRouter(prefix="/consultores/mcp", tags=["Consultores MCP"])

_DISCLAIMER = "Resposta gerada por consultor de IA — confira antes de agir."

# 8 personas (origem -> system prompt curto). Enriquecer depois; suficiente p/ 5.1.
PERSONAS = {
    "ceo": "Você é o consultor executivo (CEO) da Conecta PRO. Visão estratégica, runway, decisão. Nunca fabrique dado; se faltar, diga 'aguardando dado'.",
    "cfo": "Você é o CFO da Conecta PRO. Caixa, aging, o que vence, saúde financeira. Nunca fabrique dado.",
    "fiscal": "Você é o consultor fiscal/contábil. Notas, guias, regime, obrigações. Nunca fabrique dado.",
    "rh": "Você é o consultor de DP/RH. Folha, ponto, colaboradores, CCT. Nunca fabrique dado.",
    "juridico": "Você é o consultor jurídico (READ-ONLY). Processos, dossiê. Aconselha, nunca protocola. Nunca fabrique dado.",
    "comercial": "Você é o consultor comercial/CRM. Funil, propostas, clientes. Nunca fabrique dado.",
    "operacional": "Você é o consultor operacional (READ-ONLY). Postos, escalas, presença. Nunca altera escala. Nunca fabrique dado.",
    "ged": "Você é o consultor de GED/documentos. Kits, panorama documental. Nunca fabrique dado.",
}


class ConsultaIn(BaseModel):
    pergunta: str


class FeedbackIn(BaseModel):
    origem: str
    correcao: str
    consulta_id: int | None = None


class ProporPagamentoIn(BaseModel):
    valor: float
    pix_key: str
    descricao: str = ""


class ProporComunicadoIn(BaseModel):
    titulo: str
    corpo: str   # entrada da API; mapeia p/ a coluna `conteudo` do model Announcement


def _tenant_id_de(user) -> str:
    """Mesma convenção do announcement_controller.py (_get_tenant_id): usa user.tenant_id
    se existir; senão cai no id do próprio usuário — confirmado batendo com os 10 comunicados
    reais em produção (tenant_id == id de jjesus@conectamais.pro)."""
    return str(getattr(user, "tenant_id", None) or user.id)


async def _persistir_consulta(db: AsyncSession, origem: str, pergunta: str, resposta: str, user) -> int | None:
    """Persiste na tabela de consultas da Fase −1 (via TABELAS_CONSULTAS) e devolve o id.
    Se a origem não tiver tabela mapeada, devolve None (feedback aceita consulta_id=None)."""
    entry = TABELAS_CONSULTAS.get(origem)
    if not entry:
        return None
    tabela = entry[0]
    # shape base comum (confirmado em fase_menos1_consultas_baseline + cfo_service.py:~760)
    row = await db.execute(
        text(f"""INSERT INTO {tabela}
                 (area, pergunta, resposta, escalonar, disclaimer, contexto_usado, created_by)
                 VALUES (:a, :p, :r, false, :d, CAST(:c AS jsonb), :u) RETURNING id"""),
        {"a": origem[:20], "p": pergunta, "r": resposta, "d": _DISCLAIMER,
         "c": json.dumps({"via": "mcp"}), "u": str(getattr(user, "id", "")) or None},
    )
    await db.commit()
    return int(row.scalar())


@router.post("/{origem}/consultar")
async def consultar(
    payload: ConsultaIn,
    origem: str = Path(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_active_user),
):
    if origem not in PERSONAS:
        raise HTTPException(status_code=422, detail=f"origem inválida: {origem}")
    extra = await _hub.contexto_compartilhado(db, origem, payload.pergunta)  # retrato de entidade só p/ 'ceo' (LGPD)
    system_prompt = PERSONAS[origem] + "\n\n" + extra
    # direct=True — guard de re-entrância (Fase 5.2a.2): esta rota é a que o Hermes chama
    # via tool consultor_*; mesmo se origem vier 'executivo' um dia, NUNCA re-roteia pro
    # Hermes aqui (evitaria loop infinito Hermes→tool→gerar→Hermes→...).
    resposta, _meta = await _hub.gerar(
        messages=[{"role": "user", "content": payload.pergunta}],
        system_prompt=system_prompt,
        origem=origem,
        direct=True,
    )
    consulta_id = None
    try:
        consulta_id = await _persistir_consulta(db, origem, payload.pergunta, resposta, user)
    except Exception:
        pass  # persistência é best-effort; não quebra a resposta
    return {"resposta": resposta, "consulta_id": consulta_id, "origem": origem}


@router.post("/feedback")
async def feedback(payload: FeedbackIn, db: AsyncSession = Depends(get_db)):
    """Registra a correção do gestor como memória permanente (realimenta a Fase 4).
    consulta_id=0 (quando None) é seguro: registrar_feedback só faz um UPDATE...WHERE id=:id
    que afeta 0 linhas, e mesmo assim insere a memória em consultor_memorias
    (fonte='feedback_gestor'; não é FK — confirmado consultor_hub.py:310-341)."""
    if payload.origem not in PERSONAS:
        raise HTTPException(status_code=422, detail=f"origem inválida: {payload.origem}")
    res = await _hub.registrar_feedback(
        db, payload.origem, payload.consulta_id or 0, util=False, correcao=payload.correcao,
    )
    return {"ok": bool(res.get("ok")), "resultado": res}


@router.post("/propor-pagamento")
async def propor_pagamento(
    payload: ProporPagamentoIn,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_active_user),
):
    """🟡 PROPOR (gated): grava PENDENTE (status='preparado' via server_default).
    NUNCA aprova, NUNCA executa, NUNCA chama a API do Inter. O gate OTP humano
    fica downstream (payment_controller.py:115). 'id' e 'status' vêm de
    server_default — não os setamos aqui, garantindo que nasce 'preparado'."""
    if payload.valor <= 0:
        raise HTTPException(status_code=422, detail="valor deve ser > 0")
    # teto de PROPOSTA = mesmo teto diário do Inter (CONECTA_LIMITE_DIARIO_PAGAMENTOS, R$100k).
    # Defesa em profundidade: rejeita já na proposta valores acima do teto (o gate OTP + a trava
    # real ficam downstream, mas uma proposta acima do teto nunca aprovaria — melhor recusar cedo).
    _teto = float(os.environ.get("CONECTA_LIMITE_DIARIO_PAGAMENTOS") or "100000")
    if payload.valor > _teto:
        raise HTTPException(
            status_code=422,
            detail=f"valor acima do teto de proposta (R$ {_teto:,.2f}); use o fluxo manual/OTP",
        )
    # colunas obrigatórias sem default (confirmado sprint87_d7_payments.py):
    #   payment_type, destinatario, valor, data_pagamento, prepared_by (FK users.id NOT NULL).
    row = await db.execute(text("""
        INSERT INTO inter_payments (payment_type, destinatario, valor, data_pagamento, prepared_by, observacoes)
        VALUES ('pix', CAST(:dest AS jsonb), :valor, :dt, :prep, :obs)
        RETURNING id, status
    """), {
        "dest": json.dumps({"pix_key": payload.pix_key}),
        "valor": payload.valor,
        "dt": date.today(),
        "prep": str(user.id),   # prepared_by = quem propôs (conta de serviço MCP / diretoria)
        "obs": f"proposta via consultor MCP — requer aprovação humana + OTP. {payload.descricao}",
    })
    await db.commit()
    rec = row.first()
    return {"payment_id": str(rec[0]), "status": rec[1]}  # status = 'preparado' (server_default)


class ProporEsocialSSTIn(BaseModel):
    tipo_evento: str          # "S-2220" | "S-2230" | "S-2240" (SST)
    referencia: str           # id da fonte (chave de idempotência junto com tipo_evento)
    empresa_id: str           # UUID da empresa (Eletrônica/Patrimonial)
    employee_id: str | None = None
    payload: dict | None = None


@router.post("/propor-esocial-sst")
async def propor_esocial_sst(
    body: ProporEsocialSSTIn,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_active_user),
):
    """🔴 PROPOR (gated) a transmissão de um evento SST ao eSocial. Grava proposta 'proposto' na
    fila do sino p/ aprovação humana (Fase 5.4, aprovador ROLES_MONEY); a assinatura + transmissão
    real ao governo continua 100% HUMANA no fluxo SST. O agente/botão NUNCA transmite. Hook do T1
    p/ o botão eSocial do DP redesign (Task 9 do T2)."""
    from modules.ai.conversation.services.orquestrador.acoes.onda_c import _propor_esocial
    from modules.ai.conversation.services.orquestrador.engine import OrqScope

    scope = OrqScope(tier="gestor", is_manager=True)
    r = await _propor_esocial(
        db, user, scope, tipo_evento=body.tipo_evento, referencia=body.referencia,
        empresa_id=body.empresa_id, employee_id=body.employee_id, payload=body.payload or {},
    )
    if isinstance(r, dict) and r.get("erro"):
        raise HTTPException(status_code=422, detail=r["erro"])
    proposta_id = r if isinstance(r, str) else (r.get("id") or r.get("proposta_id") if isinstance(r, dict) else None)
    return {
        "ok": True, "proposta_id": proposta_id,
        "message": "Proposta enviada ao sino — aguardando aprovação humana + transmissão no fluxo SST. "
                   "Nada foi transmitido ao governo.",
    }


@router.post("/propor-comunicado")
async def propor_comunicado(
    payload: ProporComunicadoIn,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_active_user),
):
    """🟡 PROPOR (gated): grava RASCUNHO pendente de aprovação humana.
    NUNCA publica, NUNCA envia (push/email ficam False). O gate de aprovação +
    disparo real fica no announcement_controller.py (fluxo humano existente)."""
    ann = Announcement(
        tenant_id=_tenant_id_de(user),
        titulo=payload.titulo,
        conteudo=payload.corpo,
        created_by=str(user.id),
        status=AnnouncementStatus.RASCUNHO.value,
        enviar_push=False,
        enviar_email=False,
    )
    db.add(ann)
    await db.commit()
    await db.refresh(ann)
    return {"announcement_id": str(ann.id), "status": ann.status}

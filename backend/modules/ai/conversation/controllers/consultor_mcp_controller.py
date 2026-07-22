"""Controller MCP dos consultores — superfície 🟢🔵🟡 que o conector chama.
Cada endpoint é a contraparte de uma tool MCP em mcp-server/server.py.

Task 3 (Fase 5.1) implementa só o endpoint de consulta unificado (🟢, read):
POST /consultores/mcp/{origem}/consultar. Tasks 4/5/6 adicionam feedback/
propor-pagamento/propor-comunicado neste mesmo router — mantenha extensível.
"""
import json

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_active_user
from core.database import get_db
from modules.ai.conversation.services import consultor_hub as _hub
from modules.ai.conversation.services.consultor_hub import TABELAS_CONSULTAS  # origem -> (tabela, rótulo)

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
    resposta, _meta = await _hub.gerar(
        messages=[{"role": "user", "content": payload.pergunta}],
        system_prompt=system_prompt,
    )
    consulta_id = None
    try:
        consulta_id = await _persistir_consulta(db, origem, payload.pergunta, resposta, user)
    except Exception:
        pass  # persistência é best-effort; não quebra a resposta
    return {"resposta": resposta, "consulta_id": consulta_id, "origem": origem}

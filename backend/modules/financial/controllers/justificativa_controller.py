"""Controller de Justificativas — Saídas Sem Nota Fiscal (Lucro Real)"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.auth.dependencies import get_current_user

router = APIRouter(prefix="/justificativa", tags=["Justificativas Fiscais"])


class JustificativaRequest(BaseModel):
    transacao_id: str
    categoria: str
    descricao: str
    responsavel: str | None = "Jordan Jesus"


@router.post(
    "/registrar",
    summary="Registrar justificativa para saída sem nota fiscal",
)
async def registrar_justificativa(
    req: JustificativaRequest,
    _user=Depends(get_current_user),
):
    """
    Registra justificativa para transação bancária sem nota fiscal.
    Obrigatório para conformidade Lucro Real.

    Categorias: salario, adiantamento, reembolso, taxa_bancaria,
    imposto, servico_sem_nf, transferencia_interna, outros
    """
    from modules.financial.services.justificativa_service import (
        registrar_justificativa as _svc,
    )

    resultado = _svc(req.transacao_id, req.categoria, req.descricao, req.responsavel)
    if "erro" in resultado:
        raise HTTPException(status_code=400, detail=resultado["erro"])
    return resultado


@router.post(
    "/alertar",
    summary="Disparar alerta Telegram sobre pendências",
)
async def alertar_pendentes(_user=Depends(get_current_user)):
    """Envia alerta Telegram sobre saídas sem justificativa."""
    from modules.financial.services.justificativa_service import alertar_pendentes

    return alertar_pendentes()


@router.post(
    "/classificar-auto",
    summary="Classificar automaticamente saídas por categoria Lucro Real",
)
async def classificar_auto(
    aplicar: bool = False,
    apenas_sem_categoria: bool = True,
    responsavel: str = "Sistema — Lucro Real Auto",
    _user=Depends(get_current_user),
):
    """
    Classifica automaticamente débitos bancários por categoria fiscal.

    - **preview** (aplicar=false): mostra distribuição sem salvar — padrão seguro
    - **aplicar=true**: persiste categorias no banco (irreversível sem log)
    - **apenas_sem_categoria=true**: só processa transações sem categoria ou mal-classificadas
    - **apenas_sem_categoria=false**: reclassifica tudo (use com cuidado)

    Regras: CNPJ de instituições conhecidas (CEF/FGTS, SOLIDES) + regex sobre descrição.
    """
    from modules.financial.services.lucro_real_justificativa_service import (
        classificar_automatico,
    )

    return classificar_automatico(
        preview=not aplicar,
        apenas_sem_categoria=apenas_sem_categoria,
        responsavel=responsavel,
    )



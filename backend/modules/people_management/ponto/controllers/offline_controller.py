"""Sincronização da batida feita SEM SINAL — sobe como pendente e o servidor reconfere o rosto.

Frente 2 (13/09/2026). A DGX anuncia no Cronos 3.61.9 "reconhecimento facial offline automático em
caso de instabilidade na conexão online". O que falta no anúncio é a metade que importa: offline
quem compara o rosto é o aparelho, e aparelho é do porteiro.

O desenho, decidido antes de escrever uma linha:

1. **A batida offline NUNCA nasce definitiva.** Ela entra `pendente_de_conferencia` e, na mesma
   transação da sincronização, o SERVIDOR recompara o descriptor contra `employees.face_descriptor`
   com o mesmo limiar do fluxo online (lido de `system_configs`). Passou → definitiva (`pending`,
   o mesmo ciclo de qualquer batida). Não passou, ou não deu para comparar → fica pendente e o DP
   recebe a pendência com a foto.
2. **As duas horas, sempre.** `punch_timestamp` é a hora do APARELHO (que é a hora do fato) e
   `server_timestamp` a do servidor; `divergencia_relogio_seg` é a diferença. Relógio de celular é
   editável — a defesa não é recusar a batida, é ter o número e olhar para ele. Divergência acima
   do limite manda a batida para a conferência do DP; ela não é apagada nem alterada.
3. **Idempotência por (pessoa, minuto do aparelho, aparelho).** `chave_idempotente` é UNIQUE no
   banco. A retentativa do service worker manda o mesmo lote de novo e a segunda passagem devolve
   `duplicada` sem inserir nada. Verificar-e-depois-inserir sem trava é promessa, não trava: foi
   assim que 1.375 jornadas duplicaram em 11/09 e que três batidas do GERNANES caíram no mesmo
   segundo em 08/09.
4. **A falha offline sobe junto.** `tentativas_offline` guarda o que falhou no aparelho enquanto
   não havia sinal (`nao_detectou` / `nao_bateu`). Sem isso a estatística de falha de
   reconhecimento desaparece justamente quando mais importa — o buraco que fez a ERIKA aparecer
   com zero falhas em 32 tentativas.
5. **Pendente não entra no AFD.** O AFD é memória inalterável de marcação (frente 1). A batida só
   ganha linha AFD quando vira definitiva; a varredura `gerar_afd_desde_corte` foi ensinada a
   pular `pendente_de_conferencia`.
"""

from __future__ import annotations

import logging
import uuid as _uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_active_user
from core.database.session import get_db

from ..services import reconferencia_facial as _rf

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/offline", tags=["Ponto Eletronico — offline"])

#: Manaus não tem horário de verão — offset fixo, sem ZoneInfo no caminho quente.
_MANAUS = timezone(timedelta(hours=-4))

#: Status da batida que espera conferência do DP. Não é batida final e não entra no AFD.
PENDENTE = "pendente_de_conferencia"
#: Status da batida que passou na reconferência — o mesmo em que nasce qualquer batida online.
DEFINITIVA = "pending"

#: Teto do lote. O service worker já manda de 20 em 20; o teto existe para um cliente com defeito
#: não derrubar o processo com um lote de 10 mil.
LOTE_MAX = 50


class TentativaOffline(BaseModel):
    """Uma tentativa de reconhecimento que falhou NO APARELHO, sem sinal."""

    motivo: str = Field(..., max_length=40)  # nao_detectou | nao_bateu | camera_nao_abriu
    quando: str | None = None
    distancia: float | None = None
    confianca: float | None = None


class BatidaOffline(BaseModel):
    punch_type: str = Field(..., max_length=20)
    #: hora do APARELHO, ISO. É a hora do fato — o servidor grava e mede a diferença, não corrige.
    hora_aparelho: str
    #: identificador estável do aparelho (parte da chave idempotente).
    device_id: str = Field(..., min_length=3, max_length=64)
    #: descriptor de 128 floats capturado offline — o servidor recompara com a referência.
    descriptor: list[float] = Field(default_factory=list, max_length=512)
    foto_base64: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    accuracy: float | None = None
    #: distância/confiança que o APARELHO calculou. Guardadas para auditoria; não decidem nada.
    distancia_aparelho: float | None = None
    tentativas_offline: list[TentativaOffline] = Field(default_factory=list, max_length=50)


class LoteOffline(BaseModel):
    batidas: list[BatidaOffline] = Field(..., min_length=1, max_length=LOTE_MAX)


def _employee_id(current_user) -> str:
    if not getattr(current_user, "employee_id", None):
        raise HTTPException(
            status_code=400,
            detail="Sua conta não está vinculada a um funcionário (employee_id ausente).",
        )
    return str(current_user.employee_id)


def _manaus_naive(iso: str) -> datetime:
    """Hora do aparelho → hora de parede de Manaus, naive (convenção da coluna).

    ISO com offset é convertido; ISO sem offset é aceito como já sendo hora local de Manaus, que é
    o que o app manda. Converter duas vezes é o erro de fuso que custou 180 turnos em 11/09.
    """
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return dt.replace(tzinfo=None) if dt.tzinfo is None else dt.astimezone(_MANAUS).replace(tzinfo=None)


def _chave(employee_id: str, hora: datetime, device_id: str) -> str:
    """(pessoa, MINUTO da hora do aparelho, aparelho). Segundos fora de propósito: a retentativa
    do SW pode reenviar com o mesmo carimbo e um clique duplo cai no mesmo minuto."""
    return f"{employee_id}:{hora.strftime('%Y-%m-%dT%H:%M')}:{device_id}"


@router.get("/config")
async def config_offline(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
) -> dict[str, Any]:
    """Parâmetros que o aparelho precisa saber ANTES de perder o sinal.

    O limiar sai daqui em vez de ficar chumbado no `.tsx`: se o servidor aperta a régua, o aparelho
    aperta junto no próximo carregamento — duas réguas divergentes são o defeito, não a
    redundância. A validade do cache é a política de LGPD do descriptor no aparelho.
    """
    p = await _rf.parametros(db)
    return {
        "limiar_distancia": p["ponto.facial.limiar_distancia"],
        "validade_cache_horas": int(p["ponto.offline.validade_cache_horas"]),
        "divergencia_relogio_max_seg": int(p["ponto.offline.divergencia_relogio_max_seg"]),
        "janela_idempotencia_min": int(p["ponto.offline.janela_idempotencia_min"]),
        "servidor_agora": datetime.now(_MANAUS).replace(tzinfo=None).isoformat(),
    }


@router.post("/sync", status_code=200)
async def sincronizar_offline(  # noqa: C901, PLR0912, PLR0915
    lote: LoteOffline,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
) -> dict[str, Any]:
    """Recebe a fila do aparelho, reconfere cada batida no servidor e devolve item a item.

    Nunca 500 por causa de UMA batida: cada item tem savepoint próprio. Perder o lote inteiro
    porque uma linha veio torta é como se perde a jornada de quem estava na guarita.
    """
    import json as _json

    emp = _employee_id(current_user)
    par = await _rf.parametros(db)
    limiar = par["ponto.facial.limiar_distancia"]
    diverg_max = int(par["ponto.offline.divergencia_relogio_max_seg"])

    agora = datetime.now(_MANAUS).replace(tzinfo=None)
    resultados: list[dict[str, Any]] = []
    virou_definitiva = False

    for b in lote.batidas:
        try:
            hora_ap = _manaus_naive(b.hora_aparelho)
        except (ValueError, TypeError):
            resultados.append({"hora_aparelho": b.hora_aparelho, "resultado": "erro",
                               "detalhe": "hora do aparelho ilegível"})
            continue

        chave = _chave(emp, hora_ap, b.device_id)

        # Idempotência lida ANTES, e garantida pelo UNIQUE depois. A leitura evita trabalho; quem
        # impede a duplicata de fato é o índice — é o que faltava no importador do Tangerino.
        ja = (
            await db.execute(
                text("SELECT punch_id, status FROM gp_clock_punches WHERE chave_idempotente = :k"),
                {"k": chave},
            )
        ).fetchone()
        if ja:
            resultados.append({"chave": chave, "resultado": "duplicada", "punch_id": ja[0],
                               "status": ja[1]})
            continue

        conf = await _rf.reconferir(db, emp, b.descriptor, limiar)
        divergencia = int((agora - hora_ap).total_seconds())
        relogio_suspeito = abs(divergencia) > diverg_max

        # Quem decide o status: o SERVIDOR. match None (não deu para comparar) é tratado como
        # bloqueio — sensível é o default, dado ausente nunca vira permissão.
        if conf["match"] is True and not relogio_suspeito:
            status, motivo = DEFINITIVA, None
        else:
            status = PENDENTE
            motivo = ("relogio_divergente" if relogio_suspeito and conf["match"] is True
                      else conf.get("motivo") or "nao_bateu")

        punch_id = str(_uuid.uuid4())
        foto_url = None
        if b.foto_base64:
            # reusa o mesmo gravador de selfie do ponto (uploads/ponto/<punch_id>.jpg) —
            # a foto é o que permite ao DP conferir quem bateu quando o rosto não passou
            try:
                from modules.people_management.hr.services.time_record_service import (
                    _salvar_selfie_ponto,
                )

                foto_url = _salvar_selfie_ponto(punch_id, b.foto_base64)
            except Exception as exc:  # noqa: BLE001
                logger.warning("offline: selfie de %s não salva: %s", punch_id, exc)

        try:
            async with db.begin_nested():  # savepoint por batida
                await db.execute(
                    text(
                        "INSERT INTO gp_clock_punches (punch_id, employee_id, punch_type, "
                        " punch_timestamp, server_timestamp, status, facial_match, "
                        " facial_confidence, facial_liveness, foto_capturada_url, latitude, "
                        " longitude, accuracy, device_type, is_offline, synced_at, sync_attempts, "
                        " chave_idempotente, divergencia_relogio_seg, tentativas_offline, "
                        " device_id, created_at, updated_at) "
                        "VALUES (:pid, CAST(:e AS uuid), :tipo, :ta, :ts, :st, :fm, :fc, NULL, "
                        " :foto, :lat, :lon, :acc, 'mobile', true, :ts, 1, :chave, :dv, "
                        " CAST(:tent AS jsonb), :dev, now(), now())"
                    ),
                    {
                        "pid": punch_id, "e": emp, "tipo": b.punch_type,
                        "ta": hora_ap, "ts": agora, "st": status,
                        "fm": conf["match"], "fc": conf.get("confianca"),
                        "foto": foto_url,
                        "lat": b.latitude, "lon": b.longitude,
                        # 0 vira NULO: gravar zero afirmaria precisão PERFEITA, o oposto do dado
                        "acc": (b.accuracy or None),
                        "chave": chave, "dv": divergencia,
                        "tent": _json.dumps(
                            {"tentativas": [t.model_dump() for t in b.tentativas_offline],
                             "distancia_aparelho": b.distancia_aparelho,
                             "distancia_servidor": conf.get("distancia"),
                             "limiar": limiar},
                        ),
                        "dev": b.device_id,
                    },
                )
        except Exception as exc:  # noqa: BLE001
            # UNIQUE violado = outra sincronização chegou antes. Isso é sucesso, não erro.
            msg = str(exc)
            if "ux_gp_punch_chave_idem" in msg or "chave_idempotente" in msg:
                resultados.append({"chave": chave, "resultado": "duplicada",
                                   "detalhe": "corrida de sincronização — a primeira venceu"})
            else:
                logger.error("offline: batida %s não gravada: %s", chave, exc)
                resultados.append({"chave": chave, "resultado": "erro", "detalhe": msg[:200]})
            continue

        if status == DEFINITIVA:
            virou_definitiva = True
        else:
            await _pendencia_dp(db, emp, punch_id, hora_ap, motivo, conf, divergencia, foto_url)

        resultados.append({
            "chave": chave, "punch_id": punch_id, "status": status,
            "resultado": "definitiva" if status == DEFINITIVA else "pendente_de_conferencia",
            "facial_match": conf["match"], "distancia_servidor": conf.get("distancia"),
            "limiar": limiar, "divergencia_relogio_seg": divergencia,
            "relogio_suspeito": relogio_suspeito, "motivo": motivo,
            "hora_aparelho": hora_ap.isoformat(), "hora_servidor": agora.isoformat(),
        })

    # A linha AFD só é gerada para o que virou DEFINITIVO — e a varredura da frente 1 já pula
    # `pendente_de_conferencia`. Falha aqui não derruba a sincronização: vira dívida contada.
    if virou_definitiva:
        try:
            from modules.hr.rep_integration.services.rep_p import gerar_afd_desde_corte

            async with db.begin_nested():
                await gerar_afd_desde_corte(db, commit=False)
        except Exception as exc:  # noqa: BLE001
            logger.error("offline: AFD não gerado para o lote de %s: %s", emp, exc)

    await db.commit()
    return {
        "recebidas": len(lote.batidas),
        "definitivas": sum(1 for r in resultados if r.get("resultado") == "definitiva"),
        "pendentes": sum(1 for r in resultados if r.get("resultado") == "pendente_de_conferencia"),
        "duplicadas": sum(1 for r in resultados if r.get("resultado") == "duplicada"),
        "erros": sum(1 for r in resultados if r.get("resultado") == "erro"),
        "itens": resultados,
    }


async def _pendencia_dp(db, emp: str, punch_id: str, hora: datetime, motivo: str | None,
                        conf: dict, divergencia: int, foto_url: str | None) -> None:
    """Abre a pendência para o DP conferir — com a foto, a distância e as duas horas.

    Usa o mesmo mecanismo de rascunho que a casa já usa para tudo que espera um humano
    (`pendencia_dp.abrir` → `agent_drafts`), então a batida aparece na mesma Central onde o DP já
    decide. NUNCA valida a batida sozinha: ponto é registro de fato e a conferência é ato do DP.
    """
    try:
        from .. import pendencia_dp

        nome = (
            await db.execute(
                text("SELECT nome FROM employees WHERE id = CAST(:e AS uuid)"), {"e": emp}
            )
        ).scalar() or "Funcionário"
        explica = {
            "nao_bateu": "o rosto enviado não casou com a referência na reconferência do servidor",
            "sem_rosto_cadastrado": "a pessoa não tem rosto de referência cadastrado",
            "descriptor_incomparavel": "o aparelho não mandou um rosto comparável",
            "relogio_divergente": "o rosto casou, mas o relógio do aparelho está fora do limite",
        }.get(motivo or "", "a batida offline não passou na reconferência")
        await pendencia_dp.abrir(
            db,
            employee_id=emp,
            nome=nome,
            assunto="validar_batida",
            relato=(
                f"Batida OFFLINE de {hora.strftime('%d/%m/%Y %H:%M')} (hora do aparelho) aguardando "
                f"conferência: {explica}. Distância medida no servidor: {conf.get('distancia')} "
                f"(limiar {conf.get('limiar')}). Diferença entre o relógio do aparelho e o do "
                f"servidor: {divergencia}s. Foto: {foto_url or 'não enviada'}. "
                f"punch_id {punch_id}. A batida NÃO foi validada e NÃO entrou no AFD."
            ),
        )
    except Exception as exc:  # noqa: BLE001
        # Pendência que falha não pode derrubar a sincronização — a batida já está gravada e
        # pendente, que é o estado seguro. O caçador conta o que ficou sem dono.
        logger.error("offline: pendência do DP não aberta para %s: %s", punch_id, exc)

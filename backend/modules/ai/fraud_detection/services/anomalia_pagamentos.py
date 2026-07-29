"""
Detector de anomalia de pagamento — Fase 5.6a (LEAN, pivot).

CONTEXTO DO PIVOT: a casca CRUD de `modules/ai/fraud_detection` (controllers/
repositories/models antigos, sprint45) está com ~13 mismatches de assinatura
controller<->repository<->model e, pior, `fraud_alerts` sofre COLISÃO de
schema — a tabela VIVA no banco não é a do model
`modules/ai/fraud_detection/models/fraud_alert.py` (esse é de outro módulo/
sprint, nunca migrado); é a tabela do módulo "analytics" (sprint04,
sklearn IsolationForest). Ressuscitar a casca é inviável sem reescrever tudo.

Este arquivo é um serviço NOVO, ASSÍNCRONO, INDEPENDENTE da casca quebrada.
Ele:
  1) Lê (SOMENTE SELECT, nunca UPDATE/DELETE/INSERT) pagamentos recentes em
     `inter_payments` (dinheiro que SAI real: PIX/boleto/TED/DARF/GPS).
  2) REUSA as FÓRMULAS PURAS de detecção do módulo dormente — não a "cola"
     acoplada ao repositório síncrono quebrado:
       - z-score de valor vs. histórico do MESMO beneficiário
         (`services/pattern_analyzer.py::_analyze_amount_pattern`, ~L299-345:
         `statistics.mean`/`statistics.stdev`, limiar 3.0 desvios-padrão,
         fallback "3x a média" quando o histórico é curto).
       - velocity: N pagamentos ao mesmo beneficiário numa janela curta
         (`pattern_analyzer.py::_analyze_velocity` + constantes
         `DEFAULT_VELOCITY_THRESHOLD=5` / `DEFAULT_VELOCITY_PERIOD_MINUTES=60`,
         ~L29-30).
       - horário atípico, TZ Manaus (espírito de
         `pattern_analyzer.py::_analyze_time_pattern` + `DEFAULT_TIME_ANOMALY_HOURS`,
         ~L32, ampliado para qualquer hora fora do comercial + fim de semana).
       - teto: valor acima de `CONECTA_LIMITE_DIARIO_PAGAMENTOS` OU multiplo
         alto da média do beneficiário.
       - score ponderado 0-100 combinando os 4 sinais acima (pesos inspirados
         em `services/risk_scorer.py::COMPONENT_WEIGHTS`, ~L29-36, e faixas de
         severidade em `_determine_risk_level`, ~L495-506).
  3) Escreve (SOMENTE INSERT) um alerta de SUSPEITA em `fraud_alerts`, usando
     as COLUNAS REAIS da tabela viva (confirmadas via `\\d fraud_alerts` no
     Postgres do container `conecta-pro-postgres`, NÃO as do model antigo).

INVIOLÁVEIS (fase 5.6a):
  - Read-only sobre `inter_payments`: este módulo NUNCA executa UPDATE/DELETE/
    INSERT nela. Só SELECT.
  - Só ALERTA, nunca AGE sobre dinheiro (não cancela, não aprova, não bloqueia
    pagamento nenhum).
  - Status do alerta é SEMPRE o estado inicial "aguardando revisão humana"
    (ver nota sobre `status` abaixo) — NUNCA um estado de fato confirmado.
    Confirmar/descartar é ação humana, fora deste arquivo.
  - `risk_score`/`confidence_score` são HIPÓTESE NÃO CALIBRADA (sem ML/
    treino) — rotulado explicitamente no `summary` do alerta.
  - Nunca fabrica dado: todo sinal vem de uma query real sobre
    `inter_payments`; se o histórico do beneficiário é insuficiente pra um
    sinal, o sinal simplesmente não dispara (não se inventa baseline).
  - TZ Manaus (America/Manaus) para classificar "horário atípico".

NOTA SCHEMA-DRIFT (ver `\\d fraud_alerts` real, 2026-07-28):
  O enum `alertstatus` vivo é `pending|investigating|confirmed|false_positive|
  resolved|escalated|closed|active` — NÃO tem o valor `new` que o design doc
  da 5.6a menciona. Usamos `pending` como o estado "acabou de nascer, ninguém
  revisou ainda" (o equivalente vivo de NEW) — nunca `confirmed`. O enum
  `fraudcategory` vivo tem `payment` (não tem `transaction`) — usado aqui.
  `alertseverity` vivo é `low|medium|high|critical` (bate com o que geramos).
"""

from __future__ import annotations

import logging
import os
import statistics
import uuid
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ── Constantes reusadas dos algoritmos reais (ver docstring acima p/ origem) ──

TZ_MANAUS = ZoneInfo("America/Manaus")

# pattern_analyzer.py DEFAULT_AMOUNT_DEVIATION_THRESHOLD (~L31)
Z_SCORE_LIMIAR = 3.0
# pattern_analyzer.py::_analyze_amount_pattern exige >=5 pontos p/ z-score real (~L318)
Z_SCORE_MIN_AMOSTRAS = 5
# pattern_analyzer.py::_analyze_amount_pattern fallback quando baseline curto (~L335-340)
MEDIA_FALLBACK_MULTIPLICADOR = 3.0

# pattern_analyzer.py DEFAULT_VELOCITY_THRESHOLD / DEFAULT_VELOCITY_PERIOD_MINUTES (~L29-30)
VELOCITY_LIMIAR = 5
VELOCITY_JANELA_MINUTOS = 60

# horário comercial (fora disso = atípico); espírito de DEFAULT_TIME_ANOMALY_HOURS (~L32)
HORARIO_COMERCIAL_INICIO = 6
HORARIO_COMERCIAL_FIM = 22

# teto absoluto — mesma env var do gate OTP real (payment_service.py::LIMITE_DIARIO, ~L28)
LIMITE_DIARIO_PAGAMENTOS = float(os.getenv("CONECTA_LIMITE_DIARIO_PAGAMENTOS", "5000.00"))
# teto relativo: multiplo alto da média do próprio beneficiário
TETO_MULTIPLICADOR_MEDIA = 5.0

# pesos do score ponderado — inspirado em risk_scorer.py COMPONENT_WEIGHTS (~L29-36),
# adaptado aos 4 sinais que existem sobre inter_payments hoje. Soma = 1.0.
PESOS_SINAIS: dict[str, float] = {
    "valor": 0.35,
    "teto": 0.30,
    "velocity": 0.20,
    "horario": 0.15,
}

# faixas de severidade — mesmos cortes de risk_scorer.py::_determine_risk_level (~L495-506),
# colapsando MINIMAL em LOW (o enum vivo de fraud_alerts só tem 4 níveis).
SEVERIDADES_LIMIAR: tuple[tuple[float, str], ...] = (
    (80.0, "critical"),
    (60.0, "high"),
    (40.0, "medium"),
)
SEVERIDADE_PADRAO = "low"

# status inicial do alerta na tabela viva — ver "NOTA SCHEMA-DRIFT" na docstring.
STATUS_ALERTA_INICIAL = "pending"
CATEGORIA_ALERTA = "payment"

# beneficiário: mesma convenção já usada em redesign_builders/_fin_pagar.py e
# financial/beneficiarios_service.py (coalesce chave > codigo_barras > nome_recebedor),
# estendida aqui p/ darf/gps (sem "beneficiário" tradicional, mas com um destino fixo
# identificável por código de receita/pagamento) para não bucketar tudo junto sob None.
_SQL_BENEFICIARIO_KEY = """
    COALESCE(
        NULLIF(p.destinatario->>'chave', ''),
        NULLIF(p.destinatario->>'codigo_barras', ''),
        NULLIF(p.destinatario->>'codigo_receita', ''),
        NULLIF(p.destinatario->>'codigo_pagamento', ''),
        NULLIF(lower(trim(p.destinatario->>'nome_recebedor')), ''),
        p.payment_type
    )
"""
_SQL_BENEFICIARIO_NOME = """
    COALESCE(
        NULLIF(p.destinatario->>'nome_recebedor', ''),
        NULLIF(p.destinatario->>'chave', ''),
        NULLIF(left(p.destinatario->>'codigo_barras', 22), ''),
        CASE WHEN p.payment_type IN ('darf', 'gps')
             THEN upper(p.payment_type) || ' - ' ||
                  COALESCE(p.destinatario->>'codigo_receita', p.destinatario->>'codigo_pagamento', '?')
             ELSE p.payment_type
        END
    )
"""


class AnomaliaPagamentosDetector:
    """
    Detector de anomalia de pagamento sobre `inter_payments` (dinheiro que SAI).

    Read-only sobre `inter_payments`. Escreve SOMENTE INSERT em `fraud_alerts`
    (nunca UPDATE/DELETE, nunca em `inter_payments`). Idempotente por
    `transaction_id` (não duplica alerta pro mesmo pagamento).
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── orquestração ─────────────────────────────────────────────────────

    async def detectar(
        self,
        *,
        janela_horas: int = 24,
        apenas_pagamento_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Varre pagamentos candidatos e gera alerta de SUSPEITA para os anômalos.

        Args:
            janela_horas: janela de "pagamentos recentes" a considerar quando
                `apenas_pagamento_ids` não é passado (uso em produção/beat).
            apenas_pagamento_ids: se passado, restringe a varredura a esses IDs
                (uso em teste/bancada — nunca escaneia a tabela toda).

        Returns:
            Lista de alertas criados nesta chamada (vazia se nada anômalo ou
            se os candidatos já tinham alerta — idempotência via NOT EXISTS
            na própria query de candidatos).
        """
        candidatos = await self._buscar_candidatos(
            janela_horas=janela_horas,
            apenas_pagamento_ids=apenas_pagamento_ids,
        )

        alertas_criados: list[dict[str, Any]] = []
        for pagamento in candidatos:
            try:
                sinais = await self._calcular_sinais(pagamento)
                score, severidade, indicadores = self._calcular_score(sinais)

                if score <= 0:
                    # nenhum sinal disparou — pagamento dentro do padrão, sem alerta.
                    continue

                alerta = await self._inserir_alerta(
                    pagamento=pagamento,
                    score=score,
                    severidade=severidade,
                    indicadores=indicadores,
                )
                alertas_criados.append(alerta)
            except Exception:
                logger.exception(
                    "anomalia_pagamentos: falha ao processar payment_id=%s (pulando, não propaga)",
                    pagamento.get("id"),
                )

        if alertas_criados:
            await self.db.commit()

        return alertas_criados

    # ── leitura (read-only sobre inter_payments) ────────────────────────

    async def _buscar_candidatos(
        self,
        *,
        janela_horas: int,
        apenas_pagamento_ids: list[str] | None,
    ) -> list[dict[str, Any]]:
        """SELECT puro. Nunca altera inter_payments. Exclui via NOT EXISTS os
        pagamentos que já têm alerta (idempotência: 2ª rodada = 0 candidatos)."""
        where_extra = ""
        params: dict[str, Any] = {}

        if apenas_pagamento_ids:
            where_extra = "AND p.id = ANY(:ids)"
            params["ids"] = apenas_pagamento_ids
        else:
            where_extra = "AND p.created_at >= NOW() - make_interval(hours => :janela_horas)"
            params["janela_horas"] = janela_horas

        rows = (
            (
                await self.db.execute(
                    text(f"""
                        SELECT
                            p.id,
                            p.payment_type,
                            p.valor,
                            p.status,
                            p.created_at,
                            {_SQL_BENEFICIARIO_KEY} AS beneficiario_key,
                            {_SQL_BENEFICIARIO_NOME} AS beneficiario_nome
                        FROM inter_payments p
                        WHERE p.status <> 'cancelado'
                          {where_extra}
                          AND NOT EXISTS (
                              SELECT 1 FROM fraud_alerts fa WHERE fa.transaction_id = p.id
                          )
                        ORDER BY p.created_at ASC
                    """),
                    params,
                )
            )
            .mappings()
            .all()
        )
        return [dict(r) for r in rows]

    async def _historico_beneficiario(
        self, *, payment_id: str, beneficiario_key: str
    ) -> list[float]:
        """SELECT puro: valores anteriores do MESMO beneficiário (exclui o próprio
        pagamento em análise). Base do z-score. Nunca altera inter_payments."""
        rows = (
            await self.db.execute(
                text(f"""
                    SELECT p.valor
                    FROM inter_payments p
                    WHERE p.status <> 'cancelado'
                      AND p.id <> :payment_id
                      AND {_SQL_BENEFICIARIO_KEY} = :beneficiario_key
                    ORDER BY p.created_at DESC
                    LIMIT 200
                """),
                {"payment_id": payment_id, "beneficiario_key": beneficiario_key},
            )
        ).scalars().all()
        return [float(v) for v in rows]

    async def _velocity_beneficiario(
        self,
        *,
        payment_id: str,
        beneficiario_key: str,
        referencia: datetime,
    ) -> int:
        """SELECT puro: quantos outros pagamentos ao MESMO beneficiário caíram na
        janela curta que termina no created_at do pagamento em análise."""
        count = (
            await self.db.execute(
                text(f"""
                    SELECT count(*)
                    FROM inter_payments p
                    WHERE p.status <> 'cancelado'
                      AND p.id <> :payment_id
                      AND {_SQL_BENEFICIARIO_KEY} = :beneficiario_key
                      AND p.created_at >= (CAST(:referencia AS timestamptz) - make_interval(mins => :janela_min))
                      AND p.created_at <= CAST(:referencia AS timestamptz)
                """),
                {
                    "payment_id": payment_id,
                    "beneficiario_key": beneficiario_key,
                    "referencia": referencia,
                    "janela_min": VELOCITY_JANELA_MINUTOS,
                },
            )
        ).scalar()
        return int(count or 0)

    # ── cálculo (puro, sem I/O exceto as 2 queries read-only acima) ────────

    async def _calcular_sinais(self, pagamento: dict[str, Any]) -> dict[str, Any]:
        payment_id = str(pagamento["id"])
        beneficiario_key = pagamento["beneficiario_key"]
        valor = float(pagamento["valor"])
        created_at: datetime = pagamento["created_at"]

        historico = await self._historico_beneficiario(
            payment_id=payment_id, beneficiario_key=beneficiario_key
        )
        velocidade = await self._velocity_beneficiario(
            payment_id=payment_id,
            beneficiario_key=beneficiario_key,
            referencia=created_at,
        )

        return {
            "valor": valor,
            "historico": historico,
            "velocidade_contagem": velocidade,
            "created_at": created_at,
        }

    def _sinal_valor(self, sinais: dict[str, Any]) -> dict[str, Any]:
        """z-score do valor vs. histórico do beneficiário (pattern_analyzer.py
        ~L299-345). Com histórico curto, cai no fallback "3x a média" — nunca
        fabrica um baseline que não existe."""
        valor = sinais["valor"]
        historico = sinais["historico"]
        base: dict[str, Any] = {
            "sinal": "valor_atipico",
            "disparado": False,
            "confianca": 0.0,
            "amostras_baseline": len(historico),
            "detalhe": "baseline insuficiente ou valor dentro do padrão do beneficiário",
        }

        if len(historico) >= Z_SCORE_MIN_AMOSTRAS:
            media = statistics.mean(historico)
            desvio = statistics.stdev(historico) if len(historico) > 1 else media * 0.2
            base["media_beneficiario"] = round(media, 2)
            base["desvio_padrao_beneficiario"] = round(desvio, 2)
            if desvio > 0:
                z = abs(valor - media) / desvio
                base["z_score"] = round(z, 2)
                if z > Z_SCORE_LIMIAR:
                    base["disparado"] = True
                    base["confianca"] = min(1.0, z / 5)
                    base["detalhe"] = (
                        f"valor R${valor:.2f} é {z:.1f} desvios-padrão da média do "
                        f"beneficiário (R${media:.2f} ± R${desvio:.2f}, n={len(historico)})"
                    )
        elif historico:
            media = statistics.mean(historico)
            base["media_beneficiario"] = round(media, 2)
            if media > 0 and valor > media * MEDIA_FALLBACK_MULTIPLICADOR:
                base["disparado"] = True
                base["confianca"] = 0.6
                base["detalhe"] = (
                    f"valor R${valor:.2f} é {MEDIA_FALLBACK_MULTIPLICADOR:.0f}x+ a média do "
                    f"beneficiário (R${media:.2f}) — baseline curto (n={len(historico)}), "
                    "sinal fallback"
                )

        return base

    def _sinal_teto(self, sinais: dict[str, Any]) -> dict[str, Any]:
        """Valor acima do teto diário absoluto (mesma env do gate OTP real) ou
        múltiplo alto da média do beneficiário."""
        valor = sinais["valor"]
        historico = sinais["historico"]
        media = statistics.mean(historico) if historico else 0.0

        acima_absoluto = valor > LIMITE_DIARIO_PAGAMENTOS
        acima_relativo = media > 0 and valor > media * TETO_MULTIPLICADOR_MEDIA
        disparado = acima_absoluto or acima_relativo

        detalhes = []
        if acima_absoluto:
            detalhes.append(f"valor R${valor:.2f} > teto diário R${LIMITE_DIARIO_PAGAMENTOS:.2f}")
        if acima_relativo:
            detalhes.append(
                f"valor R${valor:.2f} > {TETO_MULTIPLICADOR_MEDIA:.0f}x a média do "
                f"beneficiário (R${media:.2f})"
            )

        return {
            "sinal": "acima_do_teto",
            "disparado": disparado,
            "confianca": 1.0 if acima_absoluto else (0.7 if acima_relativo else 0.0),
            "detalhe": "; ".join(detalhes) if detalhes else "valor dentro dos limites",
        }

    def _sinal_velocity(self, sinais: dict[str, Any]) -> dict[str, Any]:
        """N pagamentos ao mesmo beneficiário numa janela curta
        (pattern_analyzer.py::_analyze_velocity, ~L263-297)."""
        contagem = sinais["velocidade_contagem"]
        disparado = contagem >= VELOCITY_LIMIAR
        return {
            "sinal": "velocity_alta",
            "disparado": disparado,
            "confianca": min(1.0, contagem / (VELOCITY_LIMIAR * 2)) if disparado else 0.0,
            "detalhe": (
                f"{contagem} outros pagamentos ao mesmo beneficiário em "
                f"{VELOCITY_JANELA_MINUTOS}min"
                if disparado
                else f"{contagem} pagamentos ao beneficiário na janela — normal"
            ),
        }

    def _sinal_horario(self, sinais: dict[str, Any]) -> dict[str, Any]:
        """Horário atípico (madrugada/fim de semana), TZ Manaus (espírito de
        pattern_analyzer.py::_analyze_time_pattern, ~L347-376)."""
        created_at: datetime = sinais["created_at"]
        local = created_at.astimezone(TZ_MANAUS)
        fora_do_horario = not (HORARIO_COMERCIAL_INICIO <= local.hour < HORARIO_COMERCIAL_FIM)
        fim_de_semana = local.weekday() >= 5  # 5=sábado, 6=domingo
        disparado = fora_do_horario or fim_de_semana

        return {
            "sinal": "horario_atipico",
            "disparado": disparado,
            "confianca": 0.5 if disparado else 0.0,
            "detalhe": (
                f"pagamento preparado às {local:%Y-%m-%d %H:%M} (Manaus), "
                f"{'fora do horário comercial' if fora_do_horario else ''}"
                f"{' + ' if fora_do_horario and fim_de_semana else ''}"
                f"{'fim de semana' if fim_de_semana else ''}"
                if disparado
                else f"horário comercial ({local:%H:%M} Manaus)"
            ),
        }

    def _calcular_score(
        self, sinais: dict[str, Any]
    ) -> tuple[float, str, list[dict[str, Any]]]:
        """Score ponderado 0-100 (HIPÓTESE não-calibrada — não é ML, é
        combinação determinística dos 4 sinais). Score=0 (nenhum sinal
        disparado) => sem alerta."""
        indicadores = [
            self._sinal_valor(sinais),
            self._sinal_teto(sinais),
            self._sinal_velocity(sinais),
            self._sinal_horario(sinais),
        ]

        nome_peso = {
            "valor_atipico": "valor",
            "acima_do_teto": "teto",
            "velocity_alta": "velocity",
            "horario_atipico": "horario",
        }

        score = 0.0
        for ind in indicadores:
            if ind["disparado"]:
                peso = PESOS_SINAIS[nome_peso[ind["sinal"]]]
                confianca = ind["confianca"] or 1.0
                score += peso * 100 * confianca

        score = round(min(100.0, max(0.0, score)), 2)

        severidade = SEVERIDADE_PADRAO
        for limiar, nivel in SEVERIDADES_LIMIAR:
            if score >= limiar:
                severidade = nivel
                break

        return score, severidade, indicadores

    # ── escrita (SOMENTE INSERT em fraud_alerts; NUNCA toca inter_payments) ─

    async def _gerar_alert_number(self, referencia: datetime) -> str:
        local = referencia.astimezone(TZ_MANAUS)
        prefixo = f"FRD-{local:%Y%m%d}-"
        total = (
            await self.db.execute(
                text("SELECT count(*) FROM fraud_alerts WHERE alert_number LIKE :p"),
                {"p": f"{prefixo}%"},
            )
        ).scalar()
        seq = int(total or 0) + 1
        return f"{prefixo}{seq:04d}"

    async def _inserir_alerta(
        self,
        *,
        pagamento: dict[str, Any],
        score: float,
        severidade: str,
        indicadores: list[dict[str, Any]],
    ) -> dict[str, Any]:
        import json as _json

        beneficiario_key = pagamento["beneficiario_key"]
        beneficiario_nome = pagamento["beneficiario_nome"]
        payment_id = pagamento["id"]
        valor = float(pagamento["valor"])
        payment_type = pagamento["payment_type"]
        created_at: datetime = pagamento["created_at"]

        entity_id = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"conecta-pro:beneficiario-pagamento:{beneficiario_key}",
        )
        sinais_disparados = [i["sinal"] for i in indicadores if i["disparado"]]
        confidence_score = round(
            min(100.0, 100.0 * len(sinais_disparados) / len(PESOS_SINAIS)), 2
        )

        summary = (
            "SUSPEITA de anomalia estatística em pagamento — pendente de revisão "
            "humana. NÃO é fraude confirmada. Score é hipótese não-calibrada "
            "(regra determinística, sem ML/treino). Sinais disparados: "
            f"{', '.join(sinais_disparados)}."
        )

        # retry curto p/ colisão de alert_number sob concorrência (bancada c/
        # múltiplas sessões podem rodar em paralelo — ver memória operacional).
        ultima_excecao: Exception | None = None
        for _tentativa in range(3):
            alert_number = await self._gerar_alert_number(created_at)
            alert_id = uuid.uuid4()
            try:
                await self.db.execute(
                    text("""
                        INSERT INTO fraud_alerts (
                            id, alert_number, category, severity, status,
                            title, summary,
                            entity_type, entity_id, entity_name,
                            transaction_id, transaction_type, transaction_value,
                            risk_score, confidence_score,
                            indicators,
                            is_active, requires_immediate_action,
                            detected_at, created_at
                        ) VALUES (
                            :id, :alert_number, :category, :severity, :status,
                            :title, :summary,
                            :entity_type, :entity_id, :entity_name,
                            :transaction_id, :transaction_type, :transaction_value,
                            :risk_score, :confidence_score,
                            cast(:indicators as jsonb),
                            :is_active, :requires_immediate_action,
                            :detected_at, :created_at
                        )
                    """),
                    {
                        "id": alert_id,
                        "alert_number": alert_number,
                        "category": CATEGORIA_ALERTA,
                        "severity": severidade,
                        "status": STATUS_ALERTA_INICIAL,
                        "title": f"Suspeita de anomalia em pagamento — {beneficiario_nome}",
                        "summary": summary,
                        "entity_type": "beneficiario_pagamento",
                        "entity_id": entity_id,
                        "entity_name": beneficiario_nome[:255] if beneficiario_nome else None,
                        "transaction_id": payment_id,
                        "transaction_type": payment_type,
                        "transaction_value": valor,
                        "risk_score": score,
                        "confidence_score": confidence_score,
                        "indicators": _json.dumps(indicadores),
                        "is_active": True,
                        "requires_immediate_action": severidade in ("high", "critical"),
                        "detected_at": datetime.utcnow(),
                        "created_at": datetime.utcnow(),
                    },
                )
                logger.warning(
                    "anomalia_pagamentos: SUSPEITA registrada %s payment_id=%s "
                    "score=%.2f severidade=%s sinais=%s (status=%s, pendente revisão humana)",
                    alert_number,
                    payment_id,
                    score,
                    severidade,
                    sinais_disparados,
                    STATUS_ALERTA_INICIAL,
                )
                return {
                    "alert_id": str(alert_id),
                    "alert_number": alert_number,
                    "payment_id": str(payment_id),
                    "beneficiario": beneficiario_nome,
                    "valor": valor,
                    "risk_score": score,
                    "severity": severidade,
                    "status": STATUS_ALERTA_INICIAL,
                    "sinais_disparados": sinais_disparados,
                }
            except Exception as exc:  # colisão de alert_number único: tenta de novo
                ultima_excecao = exc
                await self.db.rollback()
                continue

        raise RuntimeError(
            f"anomalia_pagamentos: falha ao inserir alerta para payment_id={payment_id} "
            f"após 3 tentativas: {ultima_excecao}"
        )


async def detectar_anomalias_pagamentos(
    db: AsyncSession,
    *,
    janela_horas: int = 24,
    apenas_pagamento_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Ponto de entrada funcional (uso em beat/task/teste). Ver
    `AnomaliaPagamentosDetector.detectar` para o contrato completo."""
    detector = AnomaliaPagamentosDetector(db)
    return await detector.detectar(
        janela_horas=janela_horas,
        apenas_pagamento_ids=apenas_pagamento_ids,
    )

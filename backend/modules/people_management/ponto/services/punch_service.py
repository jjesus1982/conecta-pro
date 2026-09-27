"""Service de batida de ponto — persiste no PostgreSQL.

Usa ClockPunchModel, JustificationModel e MonthlyClosingModel
para INSERT/SELECT/UPDATE na tabela gp_clock_punches.
Valida geofence via coordenadas do posto (Haversine).
"""

import logging
import math
import os
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import String, cast, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.people_management.hr.services.time_record_service import _salvar_selfie_ponto

from ..models.clock_punch import ClockPunchModel
from ..models.justification import JustificationModel
from ..models.monthly_closing import MonthlyClosingModel
from ..schemas.punch_schemas import JustificationCreate, PunchCreate

logger = logging.getLogger(__name__)

_MANAUS_TZ = timezone(timedelta(hours=-4))  # Manaus UTC-4, sem DST


def _ts_local(col):
    """punch_timestamp já é gravado em hora LOCAL de Manaus (naive) → leitura direta."""
    return col


# Raio padrao de geofence em metros
GEOFENCE_RADIUS_METERS = 200.0


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calcula distancia em metros entre dois pontos via formula Haversine.

    Args:
        lat1, lon1: Coordenadas do ponto 1 (graus decimais).
        lat2, lon2: Coordenadas do ponto 2 (graus decimais).

    Returns:
        Distancia em metros.
    """
    r = 6_371_000  # raio da Terra em metros
    p = math.pi / 180
    a = (
        0.5
        - math.cos((lat2 - lat1) * p) / 2
        + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lon2 - lon1) * p)) / 2
    )
    return 2 * r * math.asin(math.sqrt(a))


class PunchService:
    """Service para operacoes de ponto eletronico com persistencia no banco."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def registrar_batida(
        self,
        data: PunchCreate,
        autor_user_id: str | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        """Registra uma batida de ponto no banco de dados.

        Args:
            data: Dados da batida (employee_id, tipo, facial, geo, etc.)

        Returns:
            Dicionario com os dados da batida registrada.
        """
        punch_id = str(uuid4())
        # CONVENÇÃO CANÔNICA DA COLUNA: hora LOCAL de Manaus (naive) — igual ao acervo do
        # sync Tangerino (datetime.fromtimestamp num servidor America/Manaus). datetime.now()
        # já devolve Manaus local; os LEITORES leem o valor como está (sem conversão de fuso).
        now = datetime.now()
        if data.timestamp:
            # timestamp do device (offline/app) chega em hora LOCAL Manaus → grava como está.
            ts_local = datetime.fromisoformat(str(data.timestamp))
            timestamp = (
                ts_local.replace(tzinfo=None).isoformat()
                if ts_local.tzinfo is None
                else ts_local.astimezone(_MANAUS_TZ).replace(tzinfo=None).isoformat()
            )
        else:
            timestamp = now.isoformat()

        # ⭐ NÃO SE BATE ANTES DA HORA — regra do Jordan, 27/09/2026:
        #
        #   *"eles não podem bater o ponto antes do horário previsto, porque senão gera hora
        #    extra pra eles; tem que bater no horário certinho e o sistema cobrar o atraso, mas
        #    bater antes não pode. Se o funcionário tentar, o sistema deve avisar para ele
        #    aguardar a quantidade de minutos que faltam."*
        #
        # ⚠️ VALE PARA TODOS e SÓ PARA A ENTRADA. Atraso continua permitido e cobrado (é o que
        # a escalada de +10 e +25 faz). Saída antes da hora NÃO gera hora extra — gera hora a
        # menos — e barrar isso impediria alguém autorizado a sair mais cedo de registrar a
        # saída, trocando um problema visível por um invisível.
        #
        # ⚠️ TOLERÂNCIA DE 5 MINUTOS, e ela não é minha invenção: é o **art. 58 §1 da CLT**, que
        # não considera como jornada extraordinária as variações de até 5 minutos por marcação,
        # limitadas a 10 no dia. Barrar alguém por 47 segundos (o JONHATA bateu 05:59:13 hoje)
        # faria o app parecer quebrado e jogaria a batida para contingência — trocando hora
        # extra por trabalho manual do DP. Ajustável por `PONTO_TOLERANCIA_ANTES_MIN`.
        #
        # Medido em 26/09: 5 batidas em 14 dias com mais de 1h de antecedência, a maior com
        # **239 minutos** — 4 horas de hora extra que ninguém pediu.
        if (data.punch_type or "entrada") == "entrada":
            _tol = int(os.getenv("PONTO_TOLERANCIA_ANTES_MIN", "5"))
            _ts = datetime.fromisoformat(timestamp)
            _prox = (await self.db.execute(
                text(
                    # o PRÓXIMO início de turno dela a partir desta batida, olhando hoje e
                    # amanhã (turno noturno que começa 19:00 é do mesmo dia; quem bate 23:50
                    # para um turno de 00:00 cai no dia seguinte)
                    "SELECT (s.shift_date + s.planned_start_time) AS inicio, s.planned_start_time "
                    "  FROM shifts s "
                    " WHERE s.employee_id = CAST(:e AS uuid) AND s.is_active "
                    "   AND coalesce(s.status,'') NOT IN ('cancelled','cancelado','cancelada') "
                    "   AND s.shift_date BETWEEN CAST(CAST(:d AS text) AS date) "
                    "                        AND CAST(CAST(:d AS text) AS date) + 1 "
                    "   AND (s.shift_date + s.planned_start_time) > CAST(CAST(:ts AS text) AS timestamp) "
                    " ORDER BY (s.shift_date + s.planned_start_time) LIMIT 1"
                ),
                {"e": str(data.employee_id), "d": _ts.date().isoformat(), "ts": timestamp},
            )).mappings().first()
            if _prox:
                _faltam = int((_prox["inicio"] - _ts).total_seconds() // 60)
                # ⚠️ TETO DE 4 HORAS: sem ele, quem bate a SAÍDA de um noturno às 06:00 seria
                # comparado com o turno da noite seguinte e barrado. A janela olha só o turno
                # que está de fato começando.
                if _tol < _faltam <= 240:
                    logger.warning(
                        "ponto: batida ANTES da hora recusada — employee=%s faltam %dmin para o "
                        "turno de %s (tolerância %dmin)",
                        data.employee_id, _faltam, _prox["planned_start_time"], _tol)
                    raise HTTPException(
                        # ⚠️ 409 literal, NÃO `status.HTTP_409_CONFLICT`: este serviço tem
                        # uma variável local `status = "pending"` mais abaixo, e ela
                        # SOMBREIA o módulo do FastAPI em toda a função — a referência
                        # antes da atribuição dá UnboundLocalError. Peguei isso na prova.
                        status_code=409,
                        detail=(
                            f"Ainda não está na hora de bater. Seu turno começa às "
                            f"{str(_prox['planned_start_time'])[:5]} e faltam *{_faltam} "
                            f"minuto(s)*. Aguarde e bata no horário — bater antes gera hora "
                            f"extra indevida. Se você chegou mais cedo, tudo bem: é só esperar "
                            f"o horário para registrar."
                        ),
                    )

        # ⭐ BATIDA FORA DO HORÁRIO SÓ FECHA COM JUSTIFICATIVA — Jordan, 27/09/2026:
        #
        #   *"ao sair depois do horário programado, abrir o campo de justificativa, por que o
        #    funcionário está batendo o ponto de entrada ou de saída fora do horário programado.
        #    Essa justificativa já retira o trabalho do DP de ter que justificar. Nesse caso o
        #    sistema só finaliza a batida de ponto APÓS a justificativa."*
        #
        # ⭐ O GANHO É DE QUEM SABE O MOTIVO. Hoje o DP justifica o atraso de outra pessoa,
        # adivinhando por quê — e quem sabe é quem chegou atrasado. A justificativa nasce com a
        # pessoa e vai para aprovação de quem supervisiona.
        #
        # ⚠️ Vale para ENTRADA e para SAÍDA, e para TODOS. Mesma tolerância de 5 minutos do
        # art. 58 §1 da CLT usada na guarda de cima — pedir justificativa por 40 segundos de
        # atraso ensinaria todo mundo a escrever "trânsito" sem ler a pergunta.
        _justif_para_criar: dict[str, Any] | None = None
        _tipo = (data.punch_type or "entrada")
        # 🔴 27/09/2026, 07:08 — A DIREÇÃO DA FALHA, APRENDIDA COM GENTE NO POSTO.
        #
        # Esta regra subiu antes de existir o campo na tela, e o log conta o resto: o ANILSON
        # tentou a saída **cinco vezes** entre 07:08 e 07:12, o MATHEUS a entrada **três vezes**
        # às 07:10, cada uma recusada com 409 pedindo um motivo que a tela não sabia perguntar.
        # Os dois recorreram ao José Luís no WhatsApp e ele salvou as batidas por contingência.
        #
        # ⭐ Batida ADIANTADA pode falhar fechado — a pessoa está no posto, espera e bate.
        #    Batida ATRASADA **não pode**: recusar não desfaz o atraso, só apaga o registro de
        #    quem já está trabalhando. Por isso o 409 só sai quando o cliente DECLARA que sabe
        #    abrir o campo; sem isso a batida entra e o motivo é cobrado depois, pelo agente.
        _pede_na_tela = bool(getattr(data, "pede_justificativa_na_tela", False))

        # ⭐ RETORNO DO ALMOÇO — Jordan, 27/09/2026: a tolerância de 5 minutos vale para os
        # QUATRO marcos. Aqui a referência não vem da escala: vem da própria saída de almoço
        # **mais** `planned_break_minutes`.
        #
        # ⚠️ E voltar ANTES do fim do intervalo gera hora extra pela mesma lógica da entrada
        # antecipada: a pessoa passa a trabalhar antes do previsto. Voltar DEPOIS exige
        # justificativa, como a entrada atrasada.
        #
        # ⚠️ NÃO consigo aplicar a regra à SAÍDA para almoço: `shifts` tem a DURAÇÃO do intervalo
        # (`planned_break_minutes`) e **nenhuma hora prevista** para ele — e as batidas de almoço
        # da casa vão de 00:00 a 23:55, porque o noturno almoça de madrugada. Sem horário
        # previsto não há "5 minutos antes" que signifique algo, e eu não vou inventar um.
        if _tipo == "retorno_almoco":
            _tol = int(os.getenv("PONTO_TOLERANCIA_ANTES_MIN", "5"))
            _ts = datetime.fromisoformat(timestamp)
            _ref_alm = (await self.db.execute(
                text(
                    "SELECT g.punch_timestamp AS saiu, coalesce(s.planned_break_minutes, 60) AS dur "
                    "  FROM gp_clock_punches g "
                    "  LEFT JOIN shifts s ON s.employee_id = g.employee_id "
                    "       AND s.shift_date = g.punch_timestamp::date AND s.is_active "
                    " WHERE g.employee_id = CAST(:e AS uuid) AND g.punch_type = 'saida_almoco' "
                    "   AND g.punch_timestamp < CAST(CAST(:ts AS text) AS timestamp) "
                    "   AND g.punch_timestamp > CAST(CAST(:ts AS text) AS timestamp) "
                    "                           - INTERVAL '6 hours' "
                    " ORDER BY g.punch_timestamp DESC LIMIT 1"
                ),
                {"e": str(data.employee_id), "ts": timestamp},
            )).mappings().first()
            if _ref_alm and _ref_alm["dur"]:
                _fim_alm = _ref_alm["saiu"] + timedelta(minutes=int(_ref_alm["dur"]))
                _dif = int((_ts - _fim_alm).total_seconds() // 60)
                if _dif < -_tol:
                    _faltam = -_dif
                    logger.warning("ponto: retorno de almoço ANTES da hora recusado — "
                                   "employee=%s faltam %dmin", data.employee_id, _faltam)
                    raise HTTPException(
                        status_code=409,
                        detail=(f"Seu intervalo é de {int(_ref_alm['dur'])} minutos e ainda "
                                f"faltam *{_faltam} minuto(s)* para terminar. Aguarde e bata no "
                                f"horário — voltar antes gera hora extra indevida."),
                    )
                if _dif > _tol:
                    if not (data.justificativa or "").strip() and _pede_na_tela:
                        raise HTTPException(
                            status_code=409,
                            detail={
                                "precisa_justificativa": True, "punch_type": _tipo,
                                "atraso_min": _dif,
                                "horario_previsto": _fim_alm.strftime("%H:%M"),
                                "message": (
                                    f"Seu intervalo de {int(_ref_alm['dur'])} minutos terminava "
                                    f"às {_fim_alm.strftime('%H:%M')} e você está voltando "
                                    f"{_dif} minuto(s) depois. *Escreva o motivo* para finalizar "
                                    f"a batida — a sua justificativa vai para aprovação da "
                                    f"supervisão."
                                ),
                            },
                        )
                    _justif_para_criar = {
                        "tipo": "retorno_almoco_atrasado", "atraso_min": _dif,
                        "hora_prevista": _fim_alm.strftime("%H:%M"),
                        "motivo": (data.justificativa or "").strip()[:2000],
                    }
        if _tipo in ("entrada", "saida"):
            _tol = int(os.getenv("PONTO_TOLERANCIA_ANTES_MIN", "5"))
            _ts = datetime.fromisoformat(timestamp)
            _ref = (await self.db.execute(
                text(
                    "SELECT s.planned_start_time, s.planned_end_time, "
                    "       (s.shift_date + s.planned_start_time) AS inicio, "
                    "       (s.shift_date + s.planned_end_time "
                    "        + CASE WHEN s.planned_end_time <= s.planned_start_time "
                    "               THEN INTERVAL '1 day' ELSE INTERVAL '0' END) AS fim "
                    "  FROM shifts s "
                    " WHERE s.employee_id = CAST(:e AS uuid) AND s.is_active "
                    "   AND coalesce(s.status,'') NOT IN ('cancelled','cancelado','cancelada') "
                    "   AND s.shift_date BETWEEN CAST(CAST(:d AS text) AS date) - 1 "
                    "                        AND CAST(CAST(:d AS text) AS date) "
                    # o turno cujo marco (início p/ entrada, fim p/ saída) está mais PRÓXIMO
                    # desta batida — é o que evita comparar com o turno de outro dia
                    " ORDER BY abs(EXTRACT(EPOCH FROM ("
                    "     CASE WHEN :tp = 'entrada' THEN (s.shift_date + s.planned_start_time) "
                    "          ELSE (s.shift_date + s.planned_end_time "
                    "                + CASE WHEN s.planned_end_time <= s.planned_start_time "
                    "                       THEN INTERVAL '1 day' ELSE INTERVAL '0' END) END "
                    "     - CAST(CAST(:ts AS text) AS timestamp)))) LIMIT 1"
                ),
                {"e": str(data.employee_id), "d": _ts.date().isoformat(), "ts": timestamp,
                 "tp": _tipo},
            )).mappings().first()
            if _ref:
                _marco = _ref["inicio"] if _tipo == "entrada" else _ref["fim"]
                _atraso = int((_ts - _marco).total_seconds() // 60)
                # ⚠️ TETO DE 4 HORAS: acima disso não é atraso desta batida, é outro turno.
                if _tol < _atraso <= 240:
                    _hora_prev = str(_ref["planned_start_time" if _tipo == "entrada"
                                         else "planned_end_time"])[:5]
                    if not (data.justificativa or "").strip() and _pede_na_tela:
                        logger.info("ponto: batida %s de %s atrasada %dmin — pedindo justificativa",
                                    _tipo, data.employee_id, _atraso)
                        raise HTTPException(
                            status_code=409,
                            detail={
                                "precisa_justificativa": True,
                                "punch_type": _tipo,
                                "atraso_min": _atraso,
                                "horario_previsto": _hora_prev,
                                "message": (
                                    f"Sua {'entrada' if _tipo == 'entrada' else 'saída'} estava "
                                    f"prevista para {_hora_prev} e você está batendo "
                                    f"{_atraso} minuto(s) depois. *Escreva o motivo* para "
                                    f"finalizar a batida — sem isso ela não é registrada. "
                                    f"A sua justificativa vai para aprovação da supervisão."
                                ),
                            },
                        )
                    _justif_para_criar = {
                        "tipo": "atraso" if _tipo == "entrada" else "saida_fora_horario",
                        "atraso_min": _atraso, "hora_prevista": _hora_prev,
                        "motivo": (data.justificativa or "").strip()[:2000],
                    }

        # Determinar status — vocabulário REAL do ciclo de vida do ponto: uma batida
        # nova nasce 'pending' (aguardando aprovação) e vira 'approved' na conferência.
        # (99,8% do banco usa pending/approved; 'normal'/'regular' eram seed legado.)
        # 'offline'/'fora_local' são marcadores de exceção sobre esse ciclo.
        status = "pending"
        if data.is_offline:
            status = "offline"

        # Geofence check — validacao real via coordenadas do posto
        dentro_geofence = None
        distancia_metros = None
        posto_id = data.posto_id
        posto_nome = None

        if data.location and data.location.latitude and data.location.longitude:
            geofence = await self._validar_geofence(
                employee_id=data.employee_id,
                lat=data.location.latitude,
                lon=data.location.longitude,
                posto_id=posto_id,
            )
            dentro_geofence = geofence["dentro"]
            distancia_metros = geofence["distancia_metros"]
            posto_id = geofence.get("posto_id") or posto_id
            posto_nome = geofence.get("posto_nome")

            # Só marca fora_local quando o geofence confirmou que está FORA (False).
            # dentro=None = posto sem coordenadas/geofence → não há o que validar,
            # registra normal (ex.: Conecta Base, postos sem geofence configurado).
            if dentro_geofence is False:
                status = "fora_local"
                # 🔴 GPS RUIM NÃO É "FORA DO POSTO". A precisão que o aparelho informa é o
                # raio de incerteza da posição: com accuracy de 2.000m, o celular está
                # dizendo "estou em algum lugar num círculo de 2km" — e acusar a pessoa de
                # estar fora do posto com esse dado é afirmar o que não se sabe.
                #
                # Medido em 23/08/2026 no Mirante das Flores: um TERÇO das batidas cai fora
                # do raio, sempre por volta de 1.300m, de todo mundo — Telma 14 de 40,
                # Vanderlice 12 de 38, Paulo 2 de 24. Tem cara de celular pegando torre em
                # vez de satélite. O EDIWILSON bateu a 4.123m estando no condomínio, e o
                # Jordan confirmou pelo mapa que o posto está cadastrado certo (40m do
                # ponto real).
                #
                # Quando a incerteza do GPS é maior que a distância medida, a batida fica
                # `pending`: vai para conferência do DP como qualquer outra, mas SEM a
                # afirmação de que a pessoa estava fora. Ela pode estar dentro — o aparelho
                # é que não soube dizer.
                _acc = getattr(data.location, "accuracy", None)
                if _acc and distancia_metros and float(_acc) >= float(distancia_metros):
                    status = "pending"
                    dentro_geofence = None

        # Anti-fraude facial: match NEGATIVO (selfie de outra pessoa) marca a batida p/
        # REVISÃO do DP — não pode entrar como válida só porque o geofence passou. Hoje
        # latente (facial na fase 1), mas o resultado deixa de ser só persistido e ignorado.
        if data.facial is not None and data.facial.match is False:
            status = "facial_reprovado"

        # Criar model e persistir
        punch = ClockPunchModel(
            punch_id=punch_id,
            employee_id=data.employee_id,
            punch_type=data.punch_type,
            punch_timestamp=datetime.fromisoformat(str(timestamp)),
            server_timestamp=now,
            status=status,
            facial_match=data.facial.match if data.facial else None,
            facial_confidence=data.facial.confidence if data.facial else None,
            latitude=data.location.latitude if data.location else None,
            longitude=data.location.longitude if data.location else None,
            # 🔴 A PRECISAO PRECISA SER GRAVADA, e nao era. A coluna existe, o schema
            # aceita e o app manda — mas o model nunca recebia o campo, entao 836 batidas
            # ficaram com accuracy NULO. Sem esse numero ninguem consegue, depois,
            # distinguir "estava longe do posto" de "o aparelho nao sabia onde estava" —
            # que e justamente a duvida que decide se a pessoa levou falta injusta.
            # 0 vira NULO de proposito: cliente antigo manda 0 fixo, e gravar zero seria
            # afirmar precisao PERFEITA, o oposto do que o dado significa.
            accuracy=(data.location.accuracy or None) if data.location else None,
            dentro_geofence=dentro_geofence,
            distancia_posto_metros=distancia_metros,
            # 🔴 A FOTO PRECISA SER GRAVADA, e não era — mesmo defeito do `accuracy` logo
            # acima, no mesmo construtor. O app TIRA a selfie, manda em `facial.foto_base64`,
            # o schema aceita… e o model nunca recebia o campo. Medido em 14/09/2026: 829
            # batidas de setembro com facial conferido e GPS, e ZERO com foto.
            #
            # Sem a foto não dá para ver farda, barba, crachá nem se a pessoa está mesmo no
            # posto — que é exatamente o que o DP olha no Sólides. O rosto foi CONFERIDO
            # (facial_match), mas a evidência foi descartada logo depois de validada.
            #
            # `_salvar_selfie_ponto` já existia em time_record_service e grava em
            # /app/uploads/ponto/{punch_id}.jpg. Falha ao salvar devolve None e NUNCA
            # derruba a batida: registro de jornada não se perde por causa de imagem.
            foto_capturada_url=_salvar_selfie_ponto(
                punch_id, getattr(data.facial, "foto_base64", None) if data.facial else None
            ),
            device_type=data.device_type or "web",
            is_offline=data.is_offline or False,
            posto_id=str(posto_id) if posto_id else None,
            posto_nome=str(posto_nome) if posto_nome else None,
            # 🔴 QUEM BATEU precisa ficar registrado, e não ficava. Medido em 17/09/2026:
            # das 1.372 batidas dos 15 dias anteriores, ZERO tinham created_by, device_id,
            # ip_address ou user_agent — as quatro colunas existem e nada as preenchia.
            #
            # Sem isto não há como responder «quem bateu o ponto de quem». O Antônio Carlos
            # apareceu com o app logado na conta da Graciene e bateu a entrada dela às 08:05;
            # a única prova foi o print que ele mesmo mandou. O banco não sabia de nada.
            created_by=autor_user_id,
            # 🔴 DE ONDE veio a batida. Sem isto não há como descobrir que DUAS pessoas usam a
            # MESMA conta — que foi o caso do Antônio com a conta da Graciene: ele bate no posto
            # DELA, com o login DELA, e nenhuma conferência de posto ou de autor acusa nada.
            # O aparelho é o único sinal que separa as duas.
            ip_address=ip,
            user_agent=(user_agent or "")[:400] or None,
        )
        self.db.add(punch)
        await self.db.flush()

        # frente 01 — REP-P: a batida ganha linha AFD (NSR + hash) na mesma transação. Savepoint:
        # falha aqui NUNCA derruba a batida — vira dívida contada por checar_ponto_sem_instrumento.py.
        try:
            from modules.hr.rep_integration.services.rep_p import gerar_afd_desde_corte

            async with self.db.begin_nested():
                await gerar_afd_desde_corte(self.db, commit=False)
        except Exception as exc:  # noqa: BLE001
            logger.error("REP-P: batida %s sem linha AFD: %s", punch_id, exc)

        # Push bidirecional para Sólides (não bloqueia se falhar)
        await self._push_punch_to_solides(
            data.employee_id, data.punch_type, str(timestamp), status, data.device_type or "web"
        )

        # ⭐ A JUSTIFICATIVA NASCE JUNTO E VAI PARA APROVAÇÃO — Jordan, 27/09/2026: *"essa
        # justificativa do funcionário vai para uma lista de aprovação onde Pyetra ou Orlailson
        # aprovam ou reprovam"*.
        #
        # ⚠️ DEPOIS do flush, porque a justificativa referencia `punch_id`. E em savepoint: se a
        # criação falhar, a BATIDA NÃO CAI — ela já é fato, e perder a batida para salvar a
        # anotação seria trocar o registro de jornada por papelada. A falha vira log e o DP
        # justifica à mão, que é o mundo de antes.
        #
        # ⚠️ `roles_aprovador=("admin","gerente_operacional")` alcança exatamente os dois que o
        # Jordan nomeou: medido — Pyetra é `admin` e Orlailson é `gerente_operacional`.
        if _justif_para_criar:
            try:
                async with self.db.begin_nested():
                    _jid = str(uuid4())
                    await self.db.execute(
                        text(
                            "INSERT INTO gp_justifications (justification_id, punch_id, "
                            "  employee_id, justification_type, reason, category, status, "
                            "  source, source_id, data_fato, created_at, updated_at) "
                            "VALUES (:jid, :pid, :eid, :tp, :motivo, 'ponto', 'pendente', "
                            "        'app_funcionario', :pid, CAST(CAST(:dia AS text) AS date), "
                            "        now(), now())"
                        ),
                        {"jid": _jid[:36], "pid": punch_id, "eid": str(data.employee_id),
                         "tp": _justif_para_criar["tipo"],
                         "motivo": _justif_para_criar["motivo"],
                         "dia": datetime.fromisoformat(timestamp).date().isoformat()},
                    )
                    # e vai para a Central de Aprovações, onde o executor `justificar_ponto` já
                    # existe e chama `revisar_justificativa` — o serviço oficial.
                    from modules.ai.conversation.services.orquestrador.acoes.rascunho import (
                        criar_rascunho,
                    )

                    _nome = (await self.db.execute(
                        text("SELECT nome FROM employees WHERE id = CAST(:e AS uuid)"),
                        {"e": str(data.employee_id)})).scalar() or "(sem nome)"
                    _t = _justif_para_criar
                    await criar_rascunho(
                        self.db, None,
                        tipo="justificar_ponto", modulo="ponto",
                        titulo=(f"{_nome}: {_t['tipo'].replace('_', ' ')} de {_t['atraso_min']}min "
                                f"(previsto {_t['hora_prevista']})")[:180],
                        # ⚠️ Sem motivo, o resumo DIZ que está sem motivo. Escrever
                        # "justificou com as próprias palavras: « »" seria fabricar uma
                        # justificativa vazia e pedir que a supervisão aprovasse o nada.
                        resumo=(f"{_nome} bateu {data.punch_type} {_t['atraso_min']} minuto(s) "
                                f"depois do previsto ({_t['hora_prevista']}) e justificou com as "
                                f"próprias palavras:\n\n« {_t['motivo']} »\n\n"
                                f"Aprovar = justificativa ACEITA. Rejeitar = atraso segue sem "
                                f"justificativa válida."
                                if _t["motivo"] else
                                f"{_nome} bateu {data.punch_type} {_t['atraso_min']} minuto(s) "
                                f"depois do previsto ({_t['hora_prevista']}) e **ainda não "
                                f"informou o motivo** — a tela dele não tem o campo. O José Luís "
                                f"já pediu o motivo no WhatsApp; quando ele responder, entra "
                                f"aqui.\n\nNÃO aprove ainda: aprovar agora é aceitar uma "
                                f"justificativa que não existe."),
                        payload={"justification_id": _jid[:36], "decisao": "aprovar",
                                 "employee_id": str(data.employee_id), "punch_id": punch_id,
                                 "notas": f"aprovado na Central — {_t['atraso_min']}min"},
                        gate="🟡", requires_otp=False,
                        roles_aprovador=("admin", "gerente_operacional"),
                        idempotency_key=f"justif_ponto:{punch_id}",
                    )
                logger.info("ponto: justificativa %s criada e enviada para aprovação (batida %s)",
                            _jid[:36], punch_id)
            except Exception as exc:  # noqa: BLE001
                logger.error("ponto: batida %s registrada mas a JUSTIFICATIVA não nasceu — %s",
                             punch_id, exc, exc_info=True)

            # ⭐ SEM MOTIVO NA TELA, O AGENTE PEDE O MOTIVO. É isto que fecha a regra do Jordan
            # — *"essa justificativa já retira o trabalho do dp de ter que justificar"* — sem
            # depender de um campo que ainda não existe. O DP não adivinha; quem sabe responde.
            #
            # ⚠️ `destinatario.mandar` é a PORTA ÚNICA: o telefone sai do cadastro e aqui não há
            # como digitar um número. Foi assim que o guia do Jair chegou ao Antonio Carlos.
            # best-effort: WhatsApp fora do ar não pode desfazer uma batida já gravada.
            if not _justif_para_criar["motivo"]:
                try:
                    from modules.integrations.connectors.whatsapp.destinatario import mandar

                    _t = _justif_para_criar
                    await mandar(
                        self.db,
                        quem=str(data.employee_id),
                        texto=(
                            f"Sua batida de *{str(data.punch_type).replace('_', ' ')}* foi "
                            f"registrada, fique tranquilo — ela não se perde.\n\n"
                            f"Só que ela saiu {_t['atraso_min']} minuto(s) depois do previsto "
                            f"({_t['hora_prevista']}). *Me responde aqui o motivo* que eu "
                            f"registro a justificativa no seu nome e mando para a supervisão "
                            f"aprovar — assim ninguém precisa justificar por você."
                        ),
                        motivo=f"cobrar motivo de batida fora do horário ({punch_id})",
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("ponto: não consegui pedir o motivo a %s no WhatsApp — %s",
                                   data.employee_id, exc)

        logger.info(
            "Batida registrada no banco: %s employee=%s type=%s",
            punch_id,
            data.employee_id,
            data.punch_type,
        )
        return punch.to_dict()

    async def sync_offline_punches(self, punches: list[PunchCreate]) -> dict[str, Any]:
        """Sincroniza batidas feitas em modo offline.

        Verifica duplicatas por employee_id + timestamp + tipo antes de inserir.

        Args:
            punches: Lista de batidas offline para sincronizar.

        Returns:
            Resumo da sincronizacao (synced, duplicates, errors).
        """
        synced = 0
        duplicates = 0
        errors: list[dict[str, Any]] = []

        for p in punches:
            try:
                async with self.db.begin_nested():  # savepoint: erro de uma batida não aborta as demais
                    # Duplicata: timestamp normalizado para Manaus NAIVE (coluna é sem fuso; o app
                    # manda ISO com offset e a comparação estourava por batida — revisão 08/09/2026)
                    ts = p.timestamp or datetime.now().isoformat()
                    ts_dt = datetime.fromisoformat(str(ts))
                    if ts_dt.tzinfo is not None:
                        from zoneinfo import ZoneInfo

                        ts_dt = ts_dt.astimezone(ZoneInfo("America/Manaus")).replace(tzinfo=None)
                    existing = await self.db.execute(
                        select(ClockPunchModel.id)
                        .where(
                            ClockPunchModel.employee_id == p.employee_id,
                            ClockPunchModel.punch_type == p.punch_type,
                            ClockPunchModel.punch_timestamp == ts_dt,
                        )
                        .limit(1)
                    )
                    if existing.scalar_one_or_none():
                        duplicates += 1
                        continue
                    await self.registrar_batida(p)
                    synced += 1
            except Exception as e:
                logger.warning("Erro ao sincronizar batida: %s", e)
                errors.append({"employee_id": p.employee_id, "error": str(e)[:200]})

        return {
            "total_received": len(punches),
            "total_synced": synced,
            "total_duplicates": duplicates,
            "total_errors": len(errors),
            "errors": errors,
        }

    async def get_batidas_dia(self, employee_id: str, dia: str) -> list[dict[str, Any]]:
        """Retorna batidas de um funcionario em um dia especifico.

        Args:
            employee_id: ID do funcionario.
            dia: Data no formato YYYY-MM-DD.

        Returns:
            Lista de batidas do dia.
        """
        result = await self.db.execute(
            select(ClockPunchModel)
            .where(
                ClockPunchModel.employee_id == employee_id,
                func.date(_ts_local(ClockPunchModel.punch_timestamp)) == func.date(dia),
            )
            .order_by(ClockPunchModel.punch_timestamp)
        )
        return [p.to_dict() for p in result.scalars().all()]

    async def criar_justificativa(self, data: JustificationCreate) -> dict[str, Any]:
        """Cria uma justificativa de atraso ou falta no banco.

        Args:
            data: Dados da justificativa.

        Returns:
            Dicionario com a justificativa criada.
        """
        justification = JustificationModel(
            justification_id=str(uuid4()),
            employee_id=data.employee_id,
            punch_id=data.punch_id,
            justification_type=data.justification_type,
            reason=data.reason,
            category=data.category,
            status="pendente",
            attachments=data.attachments or [],
        )
        self.db.add(justification)
        await self.db.flush()

        # Push best-effort p/ Sólides em SAVEPOINT: se a query/conector falhar, faz rollback SÓ do
        # savepoint — a justificativa acima é preservada. Antes, a falha (coluna inexistente em
        # solides_employees) abortava a transação toda e o commit do get_db virava rollback
        # silencioso → justificativa perdida com 201 falso (data loss).
        try:
            async with self.db.begin_nested():
                await self._push_justification_to_solides(
                    data.employee_id, data.justification_type, data.reason, data.category
                )
        except Exception as e:  # noqa: BLE001
            logger.warning("Push Sólides falhou (justificativa preservada): %s", e)

        logger.info("Justificativa criada: %s", justification.justification_id)
        return justification.to_dict()

    async def revisar_justificativa(
        self,
        justification_id: str,
        action: str,
        reviewer_id: str,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Aprova ou rejeita uma justificativa.

        Args:
            justification_id: ID da justificativa.
            action: 'aprovar' ou 'rejeitar'.
            reviewer_id: ID do revisor.
            notes: Observacoes do revisor.

        Returns:
            Dicionario com a justificativa atualizada.

        Raises:
            ValueError: Se justificativa nao encontrada.
        """
        result = await self.db.execute(
            select(JustificationModel).where(JustificationModel.justification_id == justification_id)
        )
        justification = result.scalar_one_or_none()
        if not justification:
            raise ValueError(f"Justificativa {justification_id} nao encontrada")

        justification.status = "aprovada" if action == "aprovar" else "rejeitada"
        justification.reviewed_by = reviewer_id
        justification.reviewed_at = datetime.now()
        justification.review_notes = notes

        await self.db.flush()

        # Push bidirecional: envia status de revisão para Sólides
        await self._push_justification_review_to_solides(
            justification_id=justification_id,
            source_id=justification.source_id if hasattr(justification, "source_id") else None,
            approved=(action == "aprovar"),
            reviewer_notes=notes,
        )

        return justification.to_dict()

    async def get_justificativas_pendentes(self, employee_id: str | None = None) -> list[dict[str, Any]]:
        """Retorna justificativas pendentes de aprovacao.

        Args:
            employee_id: Filtro opcional por funcionario.

        Returns:
            Lista de justificativas pendentes.
        """
        query = select(JustificationModel).where(JustificationModel.status == "pendente")
        if employee_id:
            query = query.where(JustificationModel.employee_id == employee_id)

        query = query.order_by(JustificationModel.created_at.desc())
        result = await self.db.execute(query)
        rows = result.scalars().all()

        # Enriquecer com nome do colaborador (JOIN employees) e data de referencia.
        # gp_justifications so guarda employee_id; a UI mostra Colaborador e Data.
        emp_ids = {j.employee_id for j in rows if j.employee_id}
        nomes: dict[str, str] = {}
        if emp_ids:
            try:
                name_rows = (
                    await self.db.execute(
                        text("SELECT CAST(id AS TEXT) AS id, nome FROM employees WHERE CAST(id AS TEXT) = ANY(:ids)"),
                        {"ids": list(emp_ids)},
                    )
                ).fetchall()
                nomes = {r[0]: r[1] for r in name_rows}
            except Exception:
                nomes = {}

        out = []
        for j in rows:
            d = j.to_dict()
            nome = nomes.get(str(j.employee_id))
            d["employee_name"] = nome
            d["colaborador"] = nome
            # Data de referencia: created_at (data em que a justificativa foi lancada)
            data_ref = j.created_at.date().isoformat() if j.created_at else None
            d["data"] = data_ref
            d["date"] = data_ref
            out.append(d)
        return out

    async def fechar_mes(
        self,
        employee_id: str,  # [Ponto loop] era int — employee_id e UUID
        month: int,
        year: int,
        fechado_por: str,
    ) -> dict[str, Any]:
        """Fecha o ponto mensal de um funcionario.

        Calcula totais de horas, extras, faltas e atrasos a partir
        das batidas do mes e persiste em gp_monthly_closings.

        Args:
            employee_id: ID do funcionario.
            month: Mes (1-12).
            year: Ano.
            fechado_por: ID de quem esta fechando.

        Returns:
            Dicionario com o fechamento.
        """
        # [Ponto loop] Horas REAIS das batidas (nao estimativa por escala).
        # Mesma logica do caminho sync da folha: horas_service.parear_batidas. Aqui so muda
        # o transporte (sessao async). Tinhamos uma COPIA deste loop, e ela carregava o mesmo
        # defeito de parear por punch_type -- o fechamento do mes fechava com hora a menos.
        from .horas_service import (
            SQL_BATIDAS,
            SQL_TURNOS_JANELA,
            janelas_de_turno,
            params_batidas,
            params_turnos,
            parear_batidas,
        )

        p = params_batidas(employee_id, month, year)
        rows = (await self.db.execute(SQL_BATIDAS, {k: v for k, v in p.items() if not k.startswith("_")})).fetchall()
        # [DGX W1] as janelas de turno fecham a régua "um plantão é UM dia": sem elas o
        # segmento pós-meia-noite do 12x36 noturno virava um segundo dia no fechamento.
        turnos = (await self.db.execute(SQL_TURNOS_JANELA, params_turnos(p))).fetchall()
        _h = parear_batidas(rows, p["_ini_mes"], p["_fim_mes"], janelas_de_turno(turnos))

        total_batidas = _h["total_batidas"]
        horas_trabalhadas = _h["horas_trabalhadas"]
        horas_noturnas = _h["horas_noturnas"]
        dias_trabalhados = _h["dias_trabalhados"]

        # [Ponto loop] IDEMPOTÊNCIA: re-fechar o mesmo mês NÃO pode duplicar linha.
        # Sem UNIQUE(employee_id,month,year) no schema, aplicamos upsert manual:
        # comparamos por CAST TEXT (robusto a variações de tipo do employee_id — linhas
        # legadas podem ter sido criadas quando a coluna era Integer/uuid) e se já
        # houver MAIS DE UMA linha para (employee_id,month,year), consolidamos: UPDATE
        # na mais antiga e DELETE das órfãs (dedup na escrita, sem apagar dado real).
        existentes = list(
            (
                await self.db.execute(
                    select(MonthlyClosingModel)
                    .where(
                        cast(MonthlyClosingModel.employee_id, String) == str(employee_id),
                        MonthlyClosingModel.month == month,
                        MonthlyClosingModel.year == year,
                    )
                    .order_by(MonthlyClosingModel.id.asc())
                )
            )
            .scalars()
            .all()
        )
        existing = existentes[0] if existentes else None
        # Remove linhas duplicadas remanescentes (mantém apenas a mais antiga).
        for orfa in existentes[1:]:
            logger.warning(
                "Fechamento duplicado removido (dedup): id=%s employee=%s %02d/%d",
                orfa.id,
                employee_id,
                month,
                year,
            )
            await self.db.delete(orfa)

        agora = datetime.now()
        if existing is not None:
            existing.total_horas_trabalhadas = horas_trabalhadas  # REAL: soma dos pares entrada/saida
            # Extras 50/100 e faltas: sem base confiavel de escala/jornada esperada
            # ainda; deixados em 0.0 ate haver calculo honesto (nao inventar).
            existing.total_horas_extras_50 = 0.0
            existing.total_horas_extras_100 = 0.0
            existing.total_horas_noturnas = horas_noturnas  # REAL: janela noturna 22:00-05:00
            existing.total_faltas = 0
            existing.total_atrasos_minutos = 0.0
            existing.total_dias_trabalhados = dias_trabalhados
            existing.fechado = True
            existing.fechado_por = fechado_por
            existing.fechado_em = agora
            existing.updated_at = agora
            closing = existing
            acao = "reaberto/atualizado"
        else:
            closing = MonthlyClosingModel(
                employee_id=employee_id,
                month=month,
                year=year,
                total_horas_trabalhadas=horas_trabalhadas,  # REAL: soma dos pares entrada/saida
                total_horas_extras_50=0.0,
                total_horas_extras_100=0.0,
                total_horas_noturnas=horas_noturnas,  # REAL: janela noturna 22:00-05:00
                total_faltas=0,
                total_atrasos_minutos=0.0,
                total_dias_trabalhados=dias_trabalhados,
                fechado=True,
                fechado_por=fechado_por,
                fechado_em=agora,
            )
            self.db.add(closing)
            acao = "criado"

        await self.db.flush()

        logger.info(
            "Ponto fechado (%s): employee=%s %02d/%d (%d batidas, %d dias, %.2fh reais, %.2fh not.)",
            acao,
            employee_id,
            month,
            year,
            total_batidas,
            dias_trabalhados,
            horas_trabalhadas,
            horas_noturnas,
        )
        return closing.to_dict()

    # =========================================================================
    # PUSH SÓLIDES (Conecta PRO → Sólides)
    # =========================================================================

    async def _push_punch_to_solides(
        self,
        employee_id: str | int,
        punch_type: str,
        punch_timestamp: str,
        status: str,
        device_type: str,
    ) -> None:
        """Push batida para Sólides via connector — nunca bloqueia em caso de erro."""
        import os

        api_token = os.getenv("SOLIDES_API_TOKEN")
        if not api_token:
            return  # Integração não configurada

        try:
            # Use savepoint to isolate Sólides query — prevents aborting the main transaction on failure
            async with self.db.begin_nested():
                result = await self.db.execute(
                    text("SELECT solides_id FROM solides_employees WHERE employee_id::text = :eid LIMIT 1"),
                    {"eid": str(employee_id)},
                )
                row = result.first()
                if not row or not row[0]:
                    logger.debug("Push Sólides: employee %s sem solides_id mapeado", employee_id)
                    return

                solides_employee_id = str(row[0])

            from modules.integrations.connectors.solides.connector import SolidesConnector

            connector = SolidesConnector(credentials={"api_token": api_token})
            await connector.push_punch_as_occurrence(
                employee_solides_id=solides_employee_id,
                punch_type=punch_type,
                punch_timestamp=punch_timestamp,
                status=status,
                device_type=device_type,
            )
        except Exception as e:
            logger.warning("Push Sólides (batida) falhou — não crítico: %s", e)

    async def _push_justification_to_solides(
        self,
        employee_id: int,
        justification_type: str,
        reason: str,
        category: str,
    ) -> None:
        """Push justificativa para Sólides como absenteísmo — nunca bloqueia em caso de erro."""
        import os

        api_token = os.getenv("SOLIDES_API_TOKEN")
        if not api_token:
            return

        try:
            result = await self.db.execute(
                text("SELECT solides_id FROM solides_employees WHERE employee_id::text = :eid LIMIT 1"),
                {"eid": str(employee_id)},
            )
            row = result.first()
            if not row or not row[0]:
                return

            solides_employee_id = str(row[0])
            start_date = datetime.now().date().isoformat()

            from modules.integrations.connectors.solides.connector import SolidesConnector

            connector = SolidesConnector(credentials={"api_token": api_token})
            await connector.push_justification_as_absence(
                employee_solides_id=solides_employee_id,
                justification_type=justification_type,
                reason=reason,
                category=category,
                start_date=start_date,
            )
        except Exception:
            # propaga p/ o SAVEPOINT do chamador (criar_justificativa) fazer rollback isolado;
            # a justificativa já persistida é preservada. NÃO engolir aqui (engolir deixava a
            # transação async abortada e o commit virava rollback silencioso).
            raise

    async def _push_justification_review_to_solides(
        self,
        justification_id: str,
        source_id: str | None,
        approved: bool,
        reviewer_notes: str | None,
    ) -> None:
        """Push de aprovação/rejeição de justificativa para Sólides — nunca bloqueia."""
        import os

        api_token = os.getenv("SOLIDES_API_TOKEN")
        if not api_token:
            return

        # Extrair o ID do Sólides do source_id (formato: "solides_abs_123" ou "solides_occ_123")
        if not source_id:
            # Tentar buscar do DB
            try:
                result = await self.db.execute(
                    text("SELECT source_id FROM gp_justifications WHERE justification_id = :jid LIMIT 1"),
                    {"jid": justification_id},
                )
                row = result.fetchone()
                if row:
                    source_id = row[0]
            except Exception:
                return

        if not source_id or not source_id.startswith("solides_"):
            return  # Justificativa local, não do Sólides

        # Extrair ID Sólides do source_id
        # Formatos: "solides_abs_123" → "123" | "solides_occ_123" → "123"
        parts = source_id.split("_")
        if len(parts) < 3:
            return
        solides_absence_id = parts[-1]

        try:
            from modules.integrations.connectors.solides.connector import SolidesConnector

            connector = SolidesConnector(credentials={"api_token": api_token})
            await connector.update_absence_status(
                absence_solides_id=solides_absence_id,
                approved=approved,
                reviewer_notes=reviewer_notes,
            )
        except Exception as e:
            logger.warning("Push review Sólides falhou — não crítico: %s", e)

    # =========================================================================
    # GEOFENCE
    # =========================================================================

    async def _validar_geofence(
        self,
        employee_id: int | str,
        lat: float,
        lon: float,
        posto_id: int | str | None = None,
    ) -> dict[str, Any]:
        """Valida se o funcionario esta dentro do raio do posto.

        Busca o posto via:
        1. posto_id informado na batida
        2. Alocacao ativa do funcionario (allocations)
        3. Geofence zone vinculada ao posto

        Args:
            employee_id: ID do funcionario.
            lat: Latitude da batida.
            lon: Longitude da batida.
            posto_id: ID do posto (opcional).

        Returns:
            Dict com 'dentro' (bool), 'distancia_metros' (float),
            'posto_id', 'posto_nome', 'raio_metros'.
        """
        posto_lat = None
        posto_lon = None
        posto_nome = None
        raio = GEOFENCE_RADIUS_METERS

        try:
            # 1. Buscar posto por ID ou alocacao ativa
            if posto_id:
                row = await self.db.execute(
                    text("SELECT id, name, latitude, longitude FROM posts WHERE id::text = :pid"),
                    {"pid": str(posto_id)},
                )
            else:
                # Buscar posto via alocacao ativa do funcionario
                row = await self.db.execute(
                    text(
                        "SELECT p.id, p.name, p.latitude, p.longitude "
                        "FROM allocations a "
                        "JOIN posts p ON a.post_id = p.id "
                        "WHERE a.employee_id::text = :eid AND a.status = 'active' "
                        "ORDER BY a.created_at DESC LIMIT 1"
                    ),
                    {"eid": str(employee_id)},
                )
            posto = row.first()

            if posto:
                posto_id = str(posto[0])
                posto_nome = str(posto[1]) if posto[1] else None
                posto_lat = posto[2]
                posto_lon = posto[3]

            # 2. Se posto sem coords, tentar geofence_zones
            if not posto_lat or not posto_lon:
                gz_row = await self.db.execute(
                    text(
                        "SELECT center_latitude, center_longitude, radius_meters, name "
                        "FROM geofence_zones "
                        "WHERE post_id::text = :pid AND status = 'active' "
                        "LIMIT 1"
                    ),
                    {"pid": str(posto_id) if posto_id else ""},
                )
                gz = gz_row.first()
                if gz:
                    posto_lat = gz[0]
                    posto_lon = gz[1]
                    raio = gz[2] or GEOFENCE_RADIUS_METERS

        except Exception as exc:
            logger.warning("Erro ao buscar geofence: %s", exc)

        # 3. Calcular distancia
        if posto_lat and posto_lon:
            distancia = _haversine(lat, lon, posto_lat, posto_lon)
            dentro = distancia <= raio

            logger.info(
                "Geofence: employee=%s posto=%s dist=%.0fm raio=%.0fm %s",
                employee_id,
                posto_nome,
                distancia,
                raio,
                "DENTRO" if dentro else "FORA",
            )

            return {
                "dentro": dentro,
                "distancia_metros": round(distancia, 1),
                "posto_id": posto_id,
                "posto_nome": posto_nome,
                "raio_metros": raio,
            }

        # Sem coordenadas do posto — nao valida
        logger.info("Geofence: sem coordenadas do posto para employee=%s", employee_id)
        return {
            "dentro": None,
            "distancia_metros": None,
            "posto_id": posto_id,
            "posto_nome": posto_nome,
            "raio_metros": raio,
        }

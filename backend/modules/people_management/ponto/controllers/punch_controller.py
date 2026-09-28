"""Controller de Ponto Eletronico — rotas FastAPI com persistencia no banco."""

import asyncio
import logging
from datetime import date
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from core.auth.dependencies import CurrentActiveUser, get_current_user
from core.database.session import get_db, get_sync_db_dependency

from ..publishers import publish_batida_registrada, publish_espelho_fechado, publish_falta_confirmada
from ..schemas.dashboard_schemas import (
    AjusteRequest,
    BancoHorasResponse,
    ColaboradorSemEscalaResponse,
    DashboardPontoResponse,
    InconsistenciaResumoResponse,
    SyncSolidesRequest,
    SyncSolidesResponse,
)
from ..schemas.punch_schemas import (
    GeoLocationSchema,
    JustificationCreate,
    JustificationResponse,
    JustificationReview,
    MonthlyClosingResponse,
    PunchCreate,
    PunchResponse,
)
from ..services import dashboard_service
from ..services.folha_pdf_service import PontoFolhaPDFService
from ..services.punch_service import PunchService

router = APIRouter(prefix="/ponto", tags=["Ponto Eletronico"])


# ==================== BATIDA E ESPELHO (async, banco real) ====================


def _origem(req: Request) -> tuple[str | None, str | None]:
    """IP real e aparelho de quem bateu.

    Atrás do nginx, `request.client.host` é sempre 127.0.0.1 — o IP de verdade vem no
    `X-Forwarded-For`, primeiro da lista.
    """
    xff = req.headers.get("x-forwarded-for", "")
    ip = xff.split(",")[0].strip() if xff else (req.client.host if req.client else None)
    return ip or None, req.headers.get("user-agent")


#: Papéis que podem bater ponto PARA OUTRA PESSOA (correção de DP, posto sem aparelho).
#: Todo mundo fora desta lista bate só o próprio, venha o que vier no corpo.
_PODE_BATER_POR_OUTRO = ("admin", "super_admin", "operator", "gerente_operacional", "supervisor")


@router.post("/batida", response_model=PunchResponse, status_code=201)
async def registrar_batida(
    data: PunchCreate,
    current_user: CurrentActiveUser,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> PunchResponse:
    """Registra uma batida de ponto (entrada, saida, almoco).

    🔴 O `employee_id` do CORPO não manda mais. Até 17/09/2026 esta rota gravava a batida
    para QUALQUER employee_id que o cliente enviasse, sem conferir de quem era o token —
    qualquer pessoa logada batia ponto por qualquer colega. O Jordan: «cada deve ter acesso
    apenas ao que é seu».

    Agora o dono da batida sai do TOKEN. Gestor (ver `_PODE_BATER_POR_OUTRO`) segue podendo
    bater por outro, porque correção de ponto é trabalho real do DP — mas fica registrado em
    `created_by` quem fez.
    """
    dono = await _resolve_employee_id(db, current_user)
    pedido = str(data.employee_id) if data.employee_id else ""
    papel = (getattr(current_user, "role", "") or "").lower()

    if pedido and pedido != str(dono) and papel not in _PODE_BATER_POR_OUTRO:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você só pode bater o seu próprio ponto.",
        )
    # Sem gestor no meio, o dono é sempre o do token — o corpo é ignorado, não obedecido.
    if papel not in _PODE_BATER_POR_OUTRO or not pedido:
        data.employee_id = str(dono)

    service = PunchService(db)
    _ip, _ua = _origem(request)
    result = await service.registrar_batida(
        data, autor_user_id=str(getattr(current_user, "id", "") or "") or None, ip=_ip, user_agent=_ua
    )
    asyncio.create_task(
        publish_batida_registrada(
            punch_id=str(result["punch_id"]),
            employee_id=str(result["employee_id"]),
            funcionario_nome="",
            punch_type=result.get("punch_type") or "entrada",
            punch_timestamp=str(result.get("punch_timestamp") or ""),
            latitude=getattr(data, "latitude", None),
            longitude=getattr(data, "longitude", None),
        )
    )
    return PunchResponse(
        punch_id=result["punch_id"],
        employee_id=result["employee_id"],
        punch_type=result.get("punch_type"),
        punch_timestamp=result.get("punch_timestamp"),
        status=result.get("status"),
        facial_match=result.get("facial_match"),
        facial_confidence=result.get("facial_confidence"),
        dentro_geofence=result.get("dentro_geofence"),
        distancia_posto_metros=result.get("distancia_posto_metros"),
        is_offline=result.get("is_offline", False),
        message="Ponto registrado com sucesso",
    )


async def _resolve_employee_id(db: AsyncSession, current_user: Any) -> str:
    """Resolve o employee_id (UUID) do usuário autenticado pelo e-mail."""
    user_email = getattr(current_user, "email", None)
    if not user_email:
        raise HTTPException(status_code=400, detail="Usuário sem e-mail vinculado")
    row = (
        await db.execute(
            text("SELECT id FROM employees WHERE email = :email LIMIT 1"),
            {"email": user_email},
        )
    ).fetchone()
    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"Funcionário não encontrado para o e-mail {user_email}. Verifique se o cadastro do funcionário usa o mesmo e-mail do login.",
        )
    return str(row[0])


_PUNCH_SEQUENCE = ["entrada", "saida_almoco", "retorno_almoco", "saida"]


async def _next_punch_type(db: AsyncSession, employee_id: str) -> str:
    """Detecta o próximo tipo de batida pela JORNADA em curso, não pelo dia civil.

    Turno noturno (12x36 das 19h às 7h): à 1h da manhã o dia civil tem 0 batidas e o
    antigo cálculo devolvia "entrada" para quem estava SAINDO — 33 entradas falsas na
    auditoria de 23/08/2026. Jornada = batidas das últimas 18 h, reiniciando após uma "saida"."""
    rows = (
        await db.execute(
            text(
                "SELECT punch_type FROM gp_clock_punches "
                "WHERE employee_id = :eid AND punch_timestamp >= NOW() - INTERVAL '18 hours' "
                "ORDER BY punch_timestamp ASC"
            ),
            {"eid": employee_id},
        )
    ).fetchall()
    tipos = [r[0] for r in rows]
    if "saida" in tipos:
        tipos = tipos[len(tipos) - tipos[::-1].index("saida") :]  # só a jornada depois da última saída
    count = len(tipos)
    if count >= len(_PUNCH_SEQUENCE):
        return "saida"
    return _PUNCH_SEQUENCE[count]


@router.post("/batida/me", response_model=PunchResponse, status_code=201)
async def registrar_batida_me(
    current_user: CurrentActiveUser,
    request: Request,
    db: AsyncSession = Depends(get_db),
    latitude: float | None = Query(None),
    longitude: float | None = Query(None),
    punch_type: str | None = Query(None, description="entrada|saida_almoco|retorno_almoco|saida"),
) -> PunchResponse:
    """Registra batida do funcionário autenticado — resolve employee e tipo automaticamente."""
    employee_id = await _resolve_employee_id(db, current_user)
    tipo = punch_type or await _next_punch_type(db, employee_id)

    location = None
    if latitude is not None and longitude is not None:
        location = GeoLocationSchema(latitude=latitude, longitude=longitude)

    data = PunchCreate(
        employee_id=str(employee_id),
        punch_type=tipo,
        location=location,
        device_type="web",
    )
    service = PunchService(db)
    result = await service.registrar_batida(
        data,
        autor_user_id=str(getattr(current_user, "id", "") or "") or None,
        ip=_origem(request)[0],
        user_agent=_origem(request)[1],
    )
    await db.commit()
    return PunchResponse(
        punch_id=result["punch_id"],
        employee_id=result["employee_id"],
        punch_type=result.get("punch_type"),
        punch_timestamp=result.get("punch_timestamp"),
        status=result.get("status"),
        facial_match=result.get("facial_match"),
        facial_confidence=result.get("facial_confidence"),
        dentro_geofence=result.get("dentro_geofence"),
        distancia_posto_metros=result.get("distancia_posto_metros"),
        is_offline=False,
        message=f"Ponto registrado: {tipo}",
    )


@router.get("/batida/{punch_id}/foto", summary="Selfie da batida (arquivo)")
async def get_foto_batida(
    punch_id: str,
    current_user: CurrentActiveUser,
    req: Request,
    db: AsyncSession = Depends(get_db),
):
    """A selfie tirada no registro do ponto, para a conferência do DP ver na tela.

    🔴 POR QUE EXISTE (28/09/2026). A Pyetra pediu, sobre a rotina dela: *"ver as fotos que foram
    tiradas para registro de ponto"*. Fui medir esperando ter de construir tudo, e o que achei foi
    o padrão mais caro desta casa: **a tela já existia, o componente já existia, a URL já estava
    cabeada — e o endpoint nunca foi escrito.**

    O caminho inteiro já estava montado e apontando para o vazio:
      · `redesign_builders/gestao_de_pessoas.py:577` monta a célula com
        `/api/v1/people-management/ponto/batida/{punch_id}/foto`
      · `frontend/src/components/redesign/FotoBatida.tsx` busca essa URL com `Bearer` e amplia no
        clique
      · 985 arquivos (39 MB) em `/app/uploads/ponto`, volume `./uploads` que sobrevive a deploy
      · 909 batidas com `foto_capturada_url` preenchida desde 14/09
      · e a URL devolvia **404**. Medido por comportamento, no backend e no público.

    ⭐ Quatro das cinco peças prontas e a quinta faltando. É a forma mais cara do defeito desta
    casa, porque tudo *parece* existir: quem olha a tela vê a coluna da foto, quem olha o banco vê
    a URL, quem olha o disco vê o arquivo — e a pessoa do outro lado vê um espaço vazio.

    ⚠️ E NÃO é `StaticFiles` em `/uploads`. São **rostos de colaborador**: mount estático abre o
    diretório inteiro a quem enumerar, sem sessão e sem rastro. Aqui passa pela parede de DP
    (`requer_modulo('dp')`, injetada em `people_management/__init__.py:_gatear_rotas_por_modulo`
    — medido: funcionário comum recebe 403) e cada leitura vira LINHA em `gp_audit_logs`.

    ⚠️ Havia uma SEGUNDA função com este mesmo path (`foto_da_batida`), registrada depois e
    portanto MORTA — o FastAPI serve a primeira. Removida em 28/09/2026, provada morta por
    comportamento: com token de DP, batida sem foto devolve «Esta batida não tem foto
    registrada.» (texto DESTA função) e nunca o texto da outra.
    """
    from fastapi.responses import FileResponse

    from modules.people_management.hr.services.cracha_pdf import foto_path

    r = (
        await db.execute(
            text(
                "SELECT p.foto_capturada_url, e.nome, p.punch_type, p.punch_timestamp, "
                "       CAST(p.employee_id AS TEXT) "
                "  FROM gp_clock_punches p LEFT JOIN employees e ON e.id = p.employee_id "
                # `OR p.id` herdado da rota morta que removi abaixo: algumas telas carregam a
                # batida pela PK numérica, e perder essa tolerância seria regressão silenciosa.
                " WHERE p.punch_id = :p OR CAST(p.id AS TEXT) = :p LIMIT 1"
            ),
            {"p": str(punch_id).strip()},
        )
    ).first()
    if not r:
        raise HTTPException(status_code=404, detail="Batida não encontrada.")

    caminho = foto_path(r[0])
    if not caminho:
        # ⚠️ Motivo DIFERENTE do 404 de cima, de propósito: "esta batida não tem foto" não é
        # "esta batida não existe". 64,5% das batidas da casa não têm foto — este é o caso
        # COMUM, e confundi-lo com erro faria a tela acusar defeito onde só falta selfie.
        raise HTTPException(status_code=404, detail="Esta batida não tem foto registrada.")

    # 🔴 28/09/2026 — A AFIRMAÇÃO VIROU COMPORTAMENTO (LGPD).
    # O docstring daqui prometia que «cada leitura vai para o log com quem pediu», e o que havia
    # era UM `logger.info` com `getattr(current_user, 'username', '?')` — campo que o model `User`
    # NÃO TEM (ele tem `email` e `name`). Medido no log do contêiner: a única linha gravada até
    # agora diz literalmente **«foto de ponto: ? abriu a batida …»** — 1 de 1 sem saber quem olhou.
    # E `stdout` de contêiner não é trilha auditável: rotaciona e ninguém consulta.
    #
    # Agora vai para `gp_audit_logs`, a mesma tabela onde as tentativas de batida
    # (`tentativa_log`) e as correções de tipo (`_auditar_correcao_tipo`) já moram — sem migration.
    #
    # NÃO engole exceção, pelo mesmo critério de `_auditar_correcao_tipo`: ver rosto de
    # colaborador sem deixar marca é pior que não ver. Se o rastro não entra, a foto não sai.
    import json as _json  # noqa: PLC0415
    import uuid as _uuid  # noqa: PLC0415

    _ip, _ua = _origem(req)
    _quem = getattr(current_user, "email", None) or getattr(current_user, "name", None) or "desconhecido"
    await db.execute(
        text(
            "INSERT INTO gp_audit_logs (id, timestamp, action, entity, entity_id, description, "
            "  source_module, actor_user_id, actor_user_name, actor_user_role, actor_user_module, "
            "  context_ip, context_user_agent, related_funcionario_id, extra_data) "
            "VALUES (:id, (now() AT TIME ZONE 'America/Manaus'), 'ponto.foto_vista', "
            "  'gp_clock_punches', :pid, :desc, 'people_management.ponto', :uid, :unome, :urole, "
            "  'ponto', :ip, :ua, :eid, CAST(:ex AS jsonb))"
        ),
        {
            "id": str(_uuid.uuid4()),
            "pid": str(punch_id).strip(),
            "desc": f"{_quem} abriu a selfie da batida {r[2]} de {r[1]} em {r[3]}"[:600],
            "uid": str(getattr(current_user, "id", "") or "") or "desconhecido",
            "unome": str(_quem)[:120],
            "urole": (getattr(current_user, "role", "") or "desconhecido")[:40],
            "ip": (_ip or "")[:60] or None,
            "ua": _ua,
            "eid": str(r[4]) if r[4] else None,
            "ex": _json.dumps(
                {"foto_url": r[0], "punch_type": r[2], "dono": r[1], "quando": str(r[3])},
                ensure_ascii=False,
            ),
        },
    )
    await db.commit()  # sem commit a linha some no fim da sessão e o rastro volta a ser promessa
    # `private`: rosto de colaborador não pode ficar em cache compartilhado (proxy/CDN).
    return FileResponse(
        caminho, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"}
    )


@router.get("/batidas/me")
async def get_batidas_me(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retorna as batidas de hoje do funcionário autenticado."""
    try:
        employee_id = await _resolve_employee_id(db, current_user)
        today = date.today().isoformat()
        service = PunchService(db)
        batidas = await service.get_batidas_dia(employee_id, today)
        return {"employee_id": employee_id, "date": today, "batidas": batidas}
    except HTTPException:
        return {"employee_id": None, "date": date.today().isoformat(), "batidas": []}


@router.get("/batidas/{employee_id}")
async def get_batidas_dia(
    employee_id: str,
    current_user: CurrentActiveUser,
    data: str = Query(..., description="Data no formato YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retorna batidas de um funcionario em um dia.

    🔴 Exige ser o DONO do ponto ou gestor. Até 17/09/2026 bastava estar logado e saber o
    UUID do colega para ler a jornada dele inteira. Quem quer o próprio ponto tem
    `GET /batidas/me`, que nem precisa saber o próprio id.
    """
    papel = (getattr(current_user, "role", "") or "").lower()
    if papel not in _PODE_BATER_POR_OUTRO:
        dono = await _resolve_employee_id(db, current_user)
        if str(dono) != str(employee_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Você só pode ver o seu próprio ponto.",
            )
    service = PunchService(db)
    batidas = await service.get_batidas_dia(employee_id, data)
    return {"employee_id": employee_id, "date": data, "punches": batidas}


#: Abreviação do dia da semana, como o espelho legal imprime.
_DIA_SEMANA = ("Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom")


def _hm_de_min(minutos: Any) -> str:
    """1101 -> '18:21'. Aceita negativo; devolve '—' quando não há número."""
    if minutos is None:
        return "—"
    try:
        v = int(minutos)
    except (TypeError, ValueError):
        return "—"
    sinal = "-" if v < 0 else ""
    v = abs(v)
    return f"{sinal}{v // 60:02d}:{v % 60:02d}"


def _tem_intervalo(valor: Any) -> bool:
    """«01:00» -> True; «», «—», «00:00» -> False. Basta um dígito diferente de zero em HH:MM."""
    return any(c in "123456789" for c in str(valor or ""))


def _dia_da_tela(d: dict[str, Any]) -> dict[str, Any]:
    """Um dia do `daily_summary` na forma que a tela de espelho consome.

    O motor único já entrega a JORNADA consolidada: entrada, intervalo e saída numa linha só,
    mesmo quando o turno atravessa a meia-noite.

    28/09/2026 — `entrada2`/`saida2` PARAM de sair vazios. Vinham `""` por decisão de setembro
    ("o segundo par virou o campo intervalo"), e o efeito medido é que a tela escondia a segunda
    linha que o Sólides mostra: em 09/2026, de **675 dias-plantão, 362 têm 2+ segmentos** (361 com
    2, 13 com 3, 1 com 4) — mais da metade dos dias da casa saía como uma tarja só, e um plantão
    19:00→02:00 + 03:00→07:17 aparecia como "19:00 → 07:17".

    Quando há `segmentos`, `entrada1/saida1` passam a ser o PRIMEIRO par e não mais o par
    sintético (1ª entrada … ÚLTIMA saída) — sem isso a linha diria "19:00 → 07:17" na coluna 1 e
    "03:00 → 07:17" na coluna 2, repetindo a mesma saída em duas colunas. Com 0 ou 1 segmento
    nada muda: um segmento só É a jornada consolidada.

    Com 3+ segmentos as quatro colunas de hora não cabem — a marca vai em `obs` (nunca se
    esconde em silêncio) e `segmentos` continua com TODOS eles para quem quiser o detalhe.
    """
    from datetime import date as _date  # noqa: PLC0415

    iso = str(d.get("date") or "")
    dia_br, semana = "—", ""
    try:
        dt = _date.fromisoformat(iso)
        dia_br = f"{dt.day:02d}/{dt.month:02d}"
        semana = _DIA_SEMANA[dt.weekday()]
    except ValueError:
        pass

    obs: list[str] = []
    if d.get("is_absent"):
        obs.append("Falta")
    if d.get("is_holiday"):
        obs.append("Feriado")
    if d.get("late"):
        obs.append(f"Atraso {_hm_de_min(d.get('late'))}")
    if d.get("notes"):
        obs.append(str(d["notes"]))
    if d.get("aviso_segmentos"):
        obs.append(str(d["aviso_segmentos"]))
    # `notes` já costuma trazer a mesma palavra da flag ("Feriado" com is_holiday=True), e a
    # linha saía "Feriado · Feriado". Mantém a ordem e tira o eco.
    # `or []` porque o SEGUNDO escritor de `daily_summary`
    # (time_sheet_service._process_day) não grava a chave.
    segs = [s for s in (d.get("segmentos") or []) if isinstance(s, dict)]
    # Batida DUPLICADA não é segmento novo: NAILSON bateu «entrada» três vezes no mesmo segundo
    # (08:01:36,6 / ,75 / ,80) em 08/09/2026 e o motor devolve 2 órfãos + o par 08:01→12:00.
    # Mostrando os segmentos em ordem crua, as duas colunas ficavam «08:01 → —» duas vezes e o
    # ÚNICO par de verdade caía fora da tela. Órfão cuja hora já aparece num par fechado é
    # ruído do aparelho — sai das colunas, é contado no aviso e continua em `segmentos`.
    horas_de_par = {
        h for s in segs if not s.get("incompleto") for h in (s.get("entrada"), s.get("saida")) if h
    }
    vis = [
        s
        for s in segs
        if not (s.get("incompleto") and (s.get("entrada") or s.get("saida")) in horas_de_par)
    ]
    dup = len(segs) - len(vis)
    e1, s1 = d.get("entrada") or "", d.get("saida") or ""
    e2, s2 = "", ""
    if vis:
        e1, s1 = vis[0].get("entrada") or "", vis[0].get("saida") or ""
        if len(vis) > 1:
            e2, s2 = vis[1].get("entrada") or "", vis[1].get("saida") or ""
        if len(vis) > 2:
            obs.append(f"+{len(vis) - 2} segmento(s) além das colunas — ver segmentos")
        if any(s.get("incompleto") for s in vis):
            obs.append("intervalo quebrado: falta marcação")
    if dup:
        obs.append(f"{dup} marcação(ões) repetida(s)")
    # 28/09/2026 — POR QUE ESTA GUARDA: medido na aba VIVA (token da Pyetra, 1299 linhas de
    # 08+09/2026), **21 linhas** mostravam UM par com `intervalo 01:00` e a coluna Obs VAZIA.
    # Ex.: ANDREA 12/08 «19:01 → 07:00», intervalo 01:00, worked 10:59 — o espelho SUBTRAIU
    # 60 min, logo o dia tem dois segmentos; as batidas cruas confirmam (entrada 19:01 mobile ·
    # saida 00:00 tangerino · entrada 01:00 tangerino · saida 07:00 mobile). A derivação só
    # recompôs 1 par e a tela calava: uma linha única sobre um dia COM intervalo é exatamente a
    # mentira que esta aba existe para matar, e calar é pior que a tarja antiga, porque agora a
    # tela afirma «não houve segundo par».
    # CAUSA HERDADA (não consertada aqui — encosta em horas trabalhadas): `_uma_fonte_por_dia`
    # descarta, por dia CIVIL, batida de fonte não-medida (grade Tangerino) quando há batida
    # medida no mesmo dia; no plantão noturno o 2º par cai no dia seguinte junto de uma medida.
    # O intervalo do espelho é fato JÁ APURADO na linha gravada — declaro a ausência, não invento
    # a hora que falta.
    ja_avisado = any(k in t for t in obs for k in ("recalcule", "intervalo quebrado", "além das colunas"))
    if len(vis) < 2 and _tem_intervalo(d.get("intervalo")) and not ja_avisado:
        obs.append(
            f"intervalo de {d.get('intervalo')} no espelho sem 2º par visível — recalcule o espelho"
        )
    obs = list(dict.fromkeys(obs))

    # Saldo do DIA = trabalhadas − previsto, a mesma subtração que o mês faz no total. Não é
    # matemática nova de folha: `worked` e `expected` são os números que o motor já gravou.
    worked, esperado = d.get("worked"), d.get("expected")
    saldo = None
    if isinstance(worked, (int, float)) and isinstance(esperado, (int, float)):
        saldo = int(round(worked - esperado))

    return {
        "dia": dia_br,
        "data": iso,
        "dia_semana": semana,
        "entrada1": e1,
        "saida1": s1,
        "entrada2": e2,
        "saida2": s2,
        "intervalo": d.get("intervalo") or "",
        "total": _hm_de_min(d.get("worked")),
        "previsto": _hm_de_min(esperado),
        "saldo_dia": _hm_de_min(saldo),
        "saldo_min": saldo,
        "obs": " · ".join(obs),
        # ACRÉSCIMO (28/09/2026): o detalhe par-a-par do motor. Sem esta linha os `segmentos`
        # que o espelho passou a gravar morriam aqui — este dict é montado campo a campo, não
        # repassa chave nova sozinho.
        "segmentos": segs,
    }


def dias_com_segmentos(db: Session, esp: dict[str, Any], mes: int, ano: int) -> list[dict[str, Any]]:
    """Os `dias` do espelho GRAVADO, completados com os segmentos derivados na hora.

    POR QUE: `segmentos` só passou a ser gravado em 28/09/2026 e o banco tem **0 de 295**
    time_sheets com a chave; mês fechado/homologado nunca será recalculado (`calcular_espelho`
    protege o registro legal). Sem isto a coluna Ent.2/Saí.2 nasceria vazia em 100% dos espelhos
    que já existem.

    Não sobrescreve o documento: se a derivação de HOJE não recompõe as pontas que o espelho
    gravou (batidas ajustadas depois do cálculo), o dia fica SEM segmento e ganha uma nota —
    mostrar par que contradiz o PDF assinado seria pior que mostrar uma linha só.

    ⚠️ 28/09/2026, SEGUNDA CAMADA — «tem segmentos» não é o mesmo que «tem segmentos ÚTEIS».
    A guarda original era `if d.get("segmentos"): continue`, e isso observava a coisa errada:
    `entrada_punch_id`/`saida_punch_id` foram ACRESCENTADOS aos segmentos algumas horas depois
    de `segmentos` começar a ser gravado, então existe uma safra de espelhos com a chave
    `segmentos` presente e SEM id nenhum dentro. Medido no banco: o espelho 09/2026 de ADAILSON
    tem 13 dias com `segmentos` e **0 com `entrada_punch_id`** — e como a guarda via a chave
    externa, ela pulava a derivação e a tela ficava com **0 células de foto** e status «sem
    batida» em cima de linhas que mostravam 19:00→02:00. Um espelho recalculado hoje perdia a
    foto que um espelho de julho mostrava.

    Agora o que decide é a chave que a tela CONSOME. O par de ids é completado pela derivação
    sob a MESMA guarda de sempre (as pontas têm de bater com o que está gravado), então nenhuma
    hora muda de valor: o que entra é o id da batida que originou cada ponta.
    """
    from modules.people_management.hr.services.espelho_service import (  # noqa: PLC0415
        segmentos_do_mes,
    )

    def _util(d: dict[str, Any]) -> bool:
        """Segmentos gravados que já trazem o id da batida — os únicos que dispensam derivar."""
        segs = d.get("segmentos") or []
        return bool(segs) and any(
            s.get("entrada_punch_id") or s.get("saida_punch_id") for s in segs if isinstance(s, dict)
        )

    dias = [d for d in (esp.get("dias") or []) if isinstance(d, dict)]
    if not dias or all(_util(d) for d in dias):
        return dias
    derivados = segmentos_do_mes(db, str(esp["employee_id"]), int(mes), int(ano))
    for d in dias:
        if _util(d):
            continue
        segs = derivados.get(str(d.get("date") or ""))
        if not segs:
            continue
        if (segs[0].get("entrada") or "") != (d.get("entrada") or "") or (
            segs[-1].get("saida") or ""
        ) != (d.get("saida") or ""):
            # chave PRÓPRIA e não `notes`: `notes` entra em `obs` junto das flags, e concatenar
            # aqui ressuscitava o eco "Feriado · Feriado; ..." que a dedupe de `obs` já resolvia.
            d["aviso_segmentos"] = "batidas alteradas depois do cálculo — recalcule o espelho"
            continue
        d["segmentos"] = segs
    return dias


def _periodo(de: str | None, ate: str | None) -> tuple[date, date]:
    """`de`/`ate` em ISO → (início, fim) inclusivos. Falta uma ponta = o mês da outra."""
    import calendar  # noqa: PLC0415

    def _p(s: str) -> date:
        try:
            return date.fromisoformat(str(s)[:10])
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Data inválida «{s}» — use AAAA-MM-DD.") from e

    d1 = _p(de) if de else None
    d2 = _p(ate) if ate else None
    if d1 is None:
        d1 = d2.replace(day=1)  # type: ignore[union-attr]
    if d2 is None:
        d2 = d1.replace(day=calendar.monthrange(d1.year, d1.month)[1])
    if d1 > d2:
        raise HTTPException(status_code=400, detail="Período invertido: «de» é depois de «até».")
    if (d2.year - d1.year) * 12 + (d2.month - d1.month) > 11:
        raise HTTPException(status_code=400, detail="Período de no máximo 12 competências por consulta.")
    return d1, d2


def _espelho_periodo(db: Session, employee_id: str, d1: date, d2: date) -> dict[str, Any]:
    """Espelho de um PERÍODO livre — os dias dos espelhos gravados que caem entre d1 e d2.

    Cada competência mantém o seu total legal em `competencias` (é ele que vai assinado). Os
    totais do período são a SOMA dos dias do motor — não uma conta paralela: o mesmo `worked` e
    `expected` que o `time_sheets` já guardou, somados. READ-ONLY: não calcula, não grava.
    """
    from modules.people_management.hr.services.espelho_ponto_service import (  # noqa: PLC0415
        ler_espelho,
    )

    meses: list[tuple[int, int]] = []
    y, m = d1.year, d1.month
    while (y, m) <= (d2.year, d2.month):
        meses.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)

    dias: list[dict[str, Any]] = []
    comps: list[dict[str, Any]] = []
    sem: list[str] = []
    cab: dict[str, Any] = {}
    trab = prev = 0
    for ano, mes in meses:
        esp = ler_espelho(db, employee_id, mes, ano)
        if esp is None:
            sem.append(f"{mes:02d}/{ano}")
            continue
        cab = cab or esp
        for d in dias_com_segmentos(db, esp, mes, ano):
            try:
                dt = date.fromisoformat(str(d.get("date") or "")[:10])
            except ValueError:
                continue
            if not (d1 <= dt <= d2):
                continue
            trab += int(d.get("worked") or 0)
            prev += int(d.get("expected") or 0)
            dias.append(_dia_da_tela(d))
        comps.append(
            {
                "competencia": f"{mes:02d}/{ano}",
                "total_trabalhado": esp.get("horas_trabalhadas"),
                "horas_esperadas": esp.get("horas_previstas"),
                "saldo": esp.get("saldo_banco"),
                "status": esp.get("status"),
                "fechado": esp.get("fechado"),
                "homologado": esp.get("approved_by_employee"),
            }
        )
    if not comps:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Sem espelho calculado em {', '.join(sem)} para este colaborador — calcule na aba "
                "«Espelho: calcular/fechar». Nada é estimado aqui."
            ),
        )
    dias.sort(key=lambda r: str(r.get("data") or ""))
    return {
        "employee_id": str(cab.get("employee_id") or employee_id),
        "employee_name": cab.get("employee_name"),
        "competencia": f"{d1:%d/%m/%Y} a {d2:%d/%m/%Y}",
        "de": d1.isoformat(),
        "ate": d2.isoformat(),
        "jornada": cab.get("work_schedule_name") or "—",
        "escala": cab.get("work_schedule_name") or "—",
        "posto": cab.get("condominium_name"),
        "total_dias": len(dias),
        # do PERÍODO (soma dos dias), não do mês: quem quer o número legal do mês lê `competencias`
        "total_trabalhado_min": trab,
        "horas_esperadas_min": prev,
        "saldo_min": trab - prev,
        "total_trabalhado": _hm_de_min(trab),
        "horas_esperadas": _hm_de_min(prev),
        "saldo": _hm_de_min(trab - prev),
        "competencias": comps,
        "sem_espelho": sem,
        "dias": dias,
    }


@router.get("/espelho/{employee_id}")
def get_espelho_mensal(
    employee_id: str,
    month: int | None = Query(None, ge=1, le=12),
    year: int | None = Query(None, ge=2020),
    de: str | None = Query(None, description="Início do período (AAAA-MM-DD) — alternativa a month/year"),
    ate: str | None = Query(None, description="Fim do período (AAAA-MM-DD)"),
    db: Session = Depends(get_sync_db_dependency),
) -> dict[str, Any]:
    """Espelho mensal — a MESMA conta do PDF que vai a assinatura.

    Origem: 15/09/2026. Esta rota tinha motor próprio (`PunchService.get_espelho_mensal`) e
    discordava do PDF em TODOS os 12 colaboradores conferidos. O PDF junta o turno noturno
    (19:01 → 07:02, intervalo 00:59, 11:01); o motor daqui partia na meia-noite e contava dois
    «dias» de ~6h. Em setembro eram 115 pares de batidas cruzando a meia-noite, em 21 pessoas.

    Num caso a tela dizia que o colaborador devia 18h enquanto o PDF dizia que ele tinha 5h a
    receber. Quem confere na tela e manda assinar estava aprovando outro documento — e o que
    vale juridicamente é o PDF.

    Agora não há o que reconciliar: a tela LÊ `time_sheets`, a mesma fonte do PDF. Se o mês
    ainda não foi calculado, calcula com o motor legal (`calcular_espelho`) em vez de inventar
    um segundo número. Síncrona de propósito — o motor legal é sync, e o FastAPI já roda
    função `def` no threadpool.

    28/09/2026 — aceita `de`/`ate` (AAAA-MM-DD) além de `month`/`year`, porque a apropriação de
    horas do DP não tem borda de mês: a Pyetra escolhe o período. O período NÃO auto-calcula
    espelho (o mês avulso continua calculando, comportamento intacto): varrer 12 meses gravando
    time_sheets numa rota de leitura é escrita escondida — os meses sem espelho vêm listados em
    `sem_espelho`, e o total do período é a soma dos dias do próprio motor, nunca um número novo.
    """
    from modules.people_management.hr.services.espelho_ponto_service import (  # noqa: PLC0415
        ler_espelho,
    )

    # Chamada DIRETA (não-HTTP) desta função deixa `de`/`ate` como o objeto `Query`, que é
    # verdadeiro — sem isto, `get_espelho_mensal(eid, month=9, year=2026, db=s)` cai no caminho de
    # período e estoura em «Data inválida «annotation=…»». Acontece: é como a aba nova reusaria.
    de = de if isinstance(de, str) and de.strip() else None
    ate = ate if isinstance(ate, str) and ate.strip() else None
    if de or ate:
        return _espelho_periodo(db, employee_id, *_periodo(de, ate))
    if not month or not year:
        raise HTTPException(status_code=400, detail="Informe month/year ou de/ate.")

    esp = ler_espelho(db, employee_id, month, year)
    if esp is None:
        from modules.people_management.hr.services.espelho_service import (  # noqa: PLC0415
            calcular_espelho,
        )

        try:
            calcular_espelho(db, employee_id, month, year)
        except ValueError as e:
            # Funcionário inexistente => 404, igual ao banco-horas (antes desta rota devolver
            # 200 com espelho fantasma de -180h, [Ponto Ciclo3 - Achado 3]).
            raise HTTPException(status_code=404, detail=str(e)) from e
        esp = ler_espelho(db, employee_id, month, year)
        if esp is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Sem espelho de {int(month):02d}/{year} para este colaborador — nem "
                    "calculado, nem calculável (verifique se há batidas no período)."
                ),
            )

    dias = [_dia_da_tela(d) for d in dias_com_segmentos(db, esp, month, year)]
    return {
        "employee_id": esp["employee_id"],
        "employee_name": esp.get("employee_name"),
        "competencia": f"{int(month):02d}/{year}",
        "month": int(month),
        "year": int(year),
        "jornada": esp.get("work_schedule_name") or "—",
        "escala": esp.get("work_schedule_name") or "—",
        "posto": esp.get("condominium_name"),
        "total_dias": len(dias),
        "total_trabalhado": esp.get("horas_trabalhadas"),
        "horas_esperadas": esp.get("horas_previstas"),
        "saldo": esp.get("saldo_banco"),
        "extras_50": esp.get("extras_50"),
        "adicional_noturno": esp.get("adicional_noturno"),
        "atrasos": esp.get("atrasos"),
        "faltas_dias": esp.get("faltas_dias"),
        "anomalias": esp.get("anomaly_count"),
        # Quem confere precisa saber se o número ainda pode mudar antes de mandar assinar.
        "status": esp.get("status"),
        "fechado": esp.get("fechado"),
        "homologado": esp.get("approved_by_employee"),
        "dias": dias,
    }


# 🔴 REMOVIDA EM 28/09/2026 — rota MORTA: `foto_da_batida` declarava o MESMO path
# `/batida/{punch_id}/foto` de `get_foto_batida` (acima, linha ~217) e era registrada DEPOIS.
# O FastAPI casa a primeira rota compatível, então este corpo nunca executou. Provado por
# comportamento com token de DP: batida sem foto devolve «Esta batida não tem foto registrada.»
# (texto do de cima) e JAMAIS «Batidas anteriores a 14/09/2026 não guardaram a selfie», que era
# a mensagem daqui. O docstring dela afirmava «o acesso fica registrado» e a função não
# escrevia auditoria nenhuma — a promessa foi para o de cima, que agora grava em gp_audit_logs.
# As duas coisas boas que ela tinha foram salvas no de cima: aceitar `gp_clock_punches.id`
# numérico além do `punch_id`, e o header `Cache-Control: private`.


@router.post("/justificativa", response_model=JustificationResponse, status_code=201)
async def criar_justificativa(
    data: JustificationCreate,
    db: AsyncSession = Depends(get_db),
) -> JustificationResponse:
    """Cria justificativa de atraso ou falta."""
    service = PunchService(db)
    result = await service.criar_justificativa(data)
    return JustificationResponse(
        justification_id=result["justification_id"],
        employee_id=result["employee_id"],
        type=result["type"],
        reason=result["reason"],
        category=result["category"],
        status=result["status"],
        created_at=result["created_at"],
    )


@router.put("/justificativa/{justification_id}/revisar")
async def revisar_justificativa(
    justification_id: str,
    data: JustificationReview,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Aprova ou rejeita uma justificativa."""
    service = PunchService(db)
    try:
        result = await service.revisar_justificativa(
            justification_id,
            data.action,
            data.reviewer_id,
            data.notes,
        )
        # P5: hook falta confirmada quando justificativa de falta é aprovada
        if data.action in ("aprovar", "approve") and result.get("type") in ("falta", "FALTA"):
            asyncio.create_task(
                publish_falta_confirmada(
                    employee_id=str(result.get("employee_id", "")),
                    funcionario_nome=result.get("funcionario_nome", ""),
                    data=str(result.get("data", "")),
                    justificada=True,
                    cliente_id=result.get("cliente_id"),
                )
            )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/justificativas/pendentes")
async def get_justificativas_pendentes(
    employee_id: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Lista justificativas pendentes de aprovacao."""
    service = PunchService(db)
    return await service.get_justificativas_pendentes(employee_id)


@router.post("/fechamento", response_model=MonthlyClosingResponse, status_code=201)
async def fechar_mes(
    employee_id: str,  # [Ponto loop] era int — employees têm UUID; gp_monthly_closings.employee_id migrado p/ String
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2020),
    fechado_por: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> MonthlyClosingResponse:
    """Fecha o ponto mensal de um funcionario."""
    service = PunchService(db)
    result = await service.fechar_mes(employee_id, month, year, fechado_por)
    asyncio.create_task(
        publish_espelho_fechado(
            employee_id=str(employee_id),
            funcionario_nome="",
            competencia=f"{year}-{month:02d}",
            total_horas=result.get("total_horas", 0),
            horas_extras=result.get("horas_extras", 0),
            faltas=result.get("faltas", 0),
        )
    )
    return MonthlyClosingResponse(**result)


@router.post("/fechamento-mes", status_code=201)
async def fechar_mes_todos(
    payload: dict,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Fecha o ponto mensal de TODOS os funcionários ativos (tela Fechamento Mensal).
    Recebe {mes, ano, fechado_por?}. Fecha cada um; retorna resumo (fechados/erros)."""
    from fastapi import HTTPException
    from sqlalchemy import text as _text

    _mes = payload.get("mes") or payload.get("month")
    _ano = payload.get("ano") or payload.get("year")
    if _mes is None or _ano is None:
        raise HTTPException(status_code=422, detail="Campos 'mes' e 'ano' são obrigatórios.")
    mes, ano = int(_mes), int(_ano)
    fechado_por = payload.get("fechado_por") or "sistema"
    rows = (await db.execute(_text("SELECT CAST(id AS text) FROM employees WHERE status='ativo'"))).fetchall()
    service = PunchService(db)
    fechados, erros = 0, []
    for (eid,) in rows:
        try:
            async with db.begin_nested():  # savepoint: a falha de um não aborta a transação dos demais
                await service.fechar_mes(eid, mes, ano, fechado_por)
            fechados += 1
        except Exception as e:  # noqa: BLE001
            erros.append({"employee_id": eid, "erro": str(e)[:120]})
    return {
        "ok": True,
        "competencia": f"{ano}-{mes:02d}",
        "total": len(rows),
        "fechados": fechados,
        "erros": len(erros),
        "detalhe_erros": erros[:5],
    }


@router.get("/fechamento/status", summary="Status de fechamento por competência (estado REAL)")
async def fechamento_status(
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2020),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Estado REAL de fechamento de uma competência a partir de gp_monthly_closings.

    Retorna quantos colaboradores estão com o ponto fechado no mês/ano e deriva
    o status da competência: 'fechado' se todos ativos fecharam, 'em_revisao' se
    parte fechou, 'aberto' se nenhum. NUNCA hardcoded.
    """
    total_ativos = (await db.execute(text("SELECT COUNT(*) FROM employees WHERE status='ativo'"))).scalar() or 0
    # COUNT(DISTINCT employee_id): linhas duplicadas legadas (mesmo funcionário fechado
    # 2x) não podem estourar o total (>100%). fechados <= colaboradores sempre.
    row = (
        await db.execute(
            text(
                "SELECT COUNT(DISTINCT employee_id) FILTER (WHERE fechado IS TRUE) AS fechados, "
                "COUNT(*) AS registros "
                "FROM gp_monthly_closings WHERE month = :m AND year = :y"
            ),
            {"m": month, "y": year},
        )
    ).first()
    fechados = int(row[0]) if row else 0
    if total_ativos > 0 and fechados >= total_ativos:
        status = "fechado"
    elif fechados > 0:
        status = "em_revisao"
    else:
        status = "aberto"
    return {
        "month": month,
        "year": year,
        "status": status,
        "colaboradores": int(total_ativos),
        "fechados": fechados,
        "pendencias": max(0, int(total_ativos) - fechados),
    }


# ==================== DASHBOARD E RELATORIOS (sync, dados reais) ====================


@router.get(
    "/dashboard",
    response_model=DashboardPontoResponse,
    summary="Dashboard gerencial do ponto",
)
async def ponto_dashboard(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_sync_db_dependency),
) -> DashboardPontoResponse:
    """Visao gerencial com dados reais: presenca, inconsistencias, banco de horas."""
    data = dashboard_service.get_dashboard(db)
    return DashboardPontoResponse(**data)


@router.get(
    "/relatorio/inconsistencias",
    response_model=InconsistenciaResumoResponse,
    summary="Relatorio de inconsistencias CCT",
)
async def relatorio_inconsistencias(
    current_user=Depends(get_current_user),
    periodo_inicio: str | None = Query(None, description="YYYY-MM-DD"),
    periodo_fim: str | None = Query(None, description="YYYY-MM-DD"),
    db: Session = Depends(get_sync_db_dependency),
) -> InconsistenciaResumoResponse:
    """Analisa inconsistencias usando regras CCT 2026 SINDECOMPRESTS."""
    data = dashboard_service.get_inconsistencias(db, periodo_inicio, periodo_fim)
    return InconsistenciaResumoResponse(**data)


@router.get(
    "/banco-horas/{employee_id}",
    response_model=BancoHorasResponse,
    summary="Saldo banco de horas",
)
async def banco_horas(
    employee_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_sync_db_dependency),
) -> BancoHorasResponse:
    """Retorna saldo de banco de horas com prazo CCT (6 meses)."""
    data = dashboard_service.get_banco_horas(db, employee_id)
    if "error" in data:
        raise HTTPException(status_code=404, detail=data["error"])
    return BancoHorasResponse(**data)


@router.post(
    "/sincronizar-solides",
    response_model=SyncSolidesResponse,
    summary="Sincronizar ponto com Solides Tangerino",
    status_code=201,
)
async def sincronizar_solides(
    current_user=Depends(get_current_user),
    request: SyncSolidesRequest = Body(default=SyncSolidesRequest()),
    db: Session = Depends(get_sync_db_dependency),
) -> SyncSolidesResponse:
    """Importa registros de ponto do Solides Tangerino."""
    data = dashboard_service.sync_solides_ponto(db, request.periodo_inicio, request.periodo_fim)
    return SyncSolidesResponse(**data)


@router.post("/sync-escalas", summary="Sincronizar escalas de trabalho do Sólides", status_code=201)
async def sync_escalas(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_sync_db_dependency),
) -> dict[str, Any]:
    """Sincroniza escalas de trabalho do Sólides para employees.escala_padrao."""
    return dashboard_service.sync_escalas_from_solides(db)


@router.post("/ajuste", summary="Ajuste manual de ponto pelo DP", status_code=201)
async def ajuste_ponto(
    request: AjusteRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_sync_db_dependency),
) -> dict[str, Any]:
    """Registra ajuste manual de ponto (somente DP)."""
    try:
        return dashboard_service.registrar_ajuste(db, request.model_dump())
    except ValueError as exc:  # dgx t2: competência fechada → 409, não 500
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get(
    "/colaboradores-sem-escala",
    response_model=list[ColaboradorSemEscalaResponse],
    summary="Colaboradores sem escala definida",
)
async def colaboradores_sem_escala(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_sync_db_dependency),
) -> list[ColaboradorSemEscalaResponse]:
    """Lista colaboradores ativos sem escala — necessitam correcao."""
    items = dashboard_service.get_colaboradores_sem_escala(db)
    return [ColaboradorSemEscalaResponse(**i) for i in items]


# ==================== FOLHA DE PONTO PDF ====================


async def gerar_folha_pdf(
    employee_id: str,
    mes_ref: str = Query(..., description="Mês de referência no formato MM.YYYY"),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_sync_db_dependency),
) -> dict[str, Any]:
    """Gera HTML de folha de ponto a partir das batidas em gp_clock_punches."""
    svc = PontoFolhaPDFService(db)
    try:
        return svc.gerar_folha_pdf(employee_id, mes_ref)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


async def download_folha_pdf(
    employee_id: str,
    mes_ref: str = Query(..., description="Mês de referência no formato MM.YYYY"),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_sync_db_dependency),
) -> Any:
    """Serve o arquivo HTML da folha de ponto como download."""
    import re
    from pathlib import Path

    from fastapi.responses import FileResponse

    if not re.match(r"^(0[1-9]|1[0-2])\.\d{4}$", mes_ref):
        raise HTTPException(status_code=422, detail="mes_ref inválido. Formato: MM.YYYY")

    storage = Path("/app/uploads/ponto") / str(employee_id) / mes_ref
    arquivos = list(storage.glob("FolhaPonto_*.html")) if storage.exists() else []

    if not arquivos:
        # Gerar on-demand se ainda não existe
        svc = PontoFolhaPDFService(db)
        try:
            result = svc.gerar_folha_pdf(employee_id, mes_ref)
            filepath = Path(result["arquivo_path"])
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
    else:
        filepath = arquivos[0]

    return FileResponse(
        path=str(filepath),
        media_type="text/html",
        filename=filepath.name,
        headers={"Content-Disposition": f'attachment; filename="{filepath.name}"'},
    )


# ── Painel de completude do onboarding (DP) — rollout do ponto próprio 01/08 ──
_ONBOARDING_CAMPOS = {
    "telefone": "Telefone",
    "cep": "CEP",
    "logradouro": "Endereço",
    "bairro": "Bairro",
    "cidade": "Cidade",
    "nome_mae": "Nome da mãe",
    "naturalidade": "Naturalidade",
    "nacionalidade": "Nacionalidade",
    "rg": "RG",
    "estado_civil": "Estado civil",
    "pis": "PIS",
}


# frente 01 — REP-P: AFD/AEJ (hr/rep_integration) como sub-rota de /ponto/afd. Import guardado:
# se rep_integration quebrar no boot, o ponto continua de pé e o oráculo test_oraculo_rep_p acusa.
try:
    from modules.hr.rep_integration.controllers.afd_controller import router as afd_router

    router.include_router(afd_router)
except Exception as _exc:  # noqa: BLE001
    import logging

    logging.getLogger(__name__).error("frente 01: AFD não montado em /ponto: %s", _exc)


# frente 02 — batida OFFLINE: a fila do aparelho sobe por /ponto/offline/sync, que RECONFERE o
# rosto no servidor antes de aceitar. Import guardado pelo mesmo motivo da frente 01: se este
# sub-router quebrar no boot, o ponto continua de pé e o oráculo test_oraculo_batida_offline
# acusa em (a) que a rota não está montada.
try:
    from .offline_controller import router as offline_router

    router.include_router(offline_router)
except Exception as _exc_off:  # noqa: BLE001
    import logging

    logging.getLogger(__name__).error("frente 02: offline não montado em /ponto: %s", _exc_off)

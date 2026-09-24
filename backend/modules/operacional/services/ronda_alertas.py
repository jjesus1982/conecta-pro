"""DGX U4 — modelos de ronda com pontos, alertas, pânico e setores de chamado (24/09/2026).

O que o DGX tem (APP Vigilância / Q-Watcher): modelo de ronda reutilizável (locais, intervalo,
telefone de pânico), alerta quando a ronda não roda, botão de pânico com aceite, e chamado que
aponta o setor do contrato e avisa o responsável por e-mail.

O que existia aqui: `inspection_rounds` (frente 06 — foto na hora, offline) com `posts_to_visit`
por id de posto, SEM pontos ordenados, SEM template, SEM "atrasada", SEM pânico; `op_chamados`
(F8) com SLA, SEM setor e SEM notificação. Decisão: NÃO há modelo/rota com pontos na frente 06
para estender — `ronda_modelos` nasce nova e a ronda ganha `inspection_rounds.modelo_id`.

Convenção de tempo (medida no staging): `scheduled_date` é Manaus naive; `started_at`,
`completed_at` e `inspection_checkpoints.created_at` são UTC naive. O motor trabalha em UTC naive
e soma `_MANAUS_UTC` ao agendado.

Notificação: e-mail por `core.mailer.send_email` (que já recusa destinatário externo fora de
produção) e WhatsApp por `send_text_message` — em sandbox NUNCA envia, registra `simulado`.
Cada envio fica em `notificado jsonb` como [{canal, para, status: enviado|simulado|falhou}].
"""

from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import text

logger = logging.getLogger(__name__)
TZ = ZoneInfo("America/Manaus")
_MANAUS_UTC = timedelta(hours=4)  # Manaus = UTC−4, sem horário de verão
RAIO_PADRAO_M = 50  # ponytail: raio único quando o ponto não declara; GPS urbano erra 10–30 m
TIPOS_ALERTA = {
    "ronda_atrasada": "Ronda atrasada",
    "ponto_pulado": "Ponto pulado",
    "fora_de_sequencia": "Fora de sequência",
    "panico": "Pânico",
    "sem_movimento": "Sem movimento",
}
STATUS_DISPARO = {"aberto": "Aberto", "reconhecido": "Reconhecido", "encerrado": "Encerrado"}

_DDL = [
    """CREATE TABLE IF NOT EXISTS ronda_modelos (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        nome varchar(200) NOT NULL,
        post_id uuid,
        client_id uuid,
        pontos jsonb NOT NULL DEFAULT '[]',
        intervalo_min integer NOT NULL DEFAULT 60,
        tolerancia_min integer NOT NULL DEFAULT 15,
        ativo boolean NOT NULL DEFAULT true,
        created_by uuid,
        created_at timestamp NOT NULL DEFAULT now()
    )""",
    """CREATE TABLE IF NOT EXISTS ronda_alertas (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        modelo_id uuid NOT NULL REFERENCES ronda_modelos(id) ON DELETE CASCADE,
        tipo varchar(30) NOT NULL,
        minutos integer,
        destinatarios jsonb NOT NULL DEFAULT '{}',
        ativo boolean NOT NULL DEFAULT true,
        created_at timestamp NOT NULL DEFAULT now()
    )""",
    """CREATE TABLE IF NOT EXISTS ronda_alertas_disparados (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        alerta_id uuid REFERENCES ronda_alertas(id) ON DELETE CASCADE,
        tipo varchar(30) NOT NULL,
        ronda_id uuid,
        modelo_id uuid,
        post_id uuid,
        employee_id uuid,
        employee_nome varchar(255),
        latitude double precision,
        longitude double precision,
        foto_url text,
        mensagem text,
        detalhe jsonb,
        occurrence_id uuid,
        disparado_em timestamp NOT NULL DEFAULT now(),
        notificado jsonb NOT NULL DEFAULT '[]',
        status varchar(20) NOT NULL DEFAULT 'aberto',
        reconhecido_em timestamp,
        reconhecido_por uuid,
        encerrado_em timestamp,
        encerrado_por uuid
    )""",
    # idempotência do motor: um disparo por (alerta, ronda) — a segunda avaliação não duplica
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_ronda_disp_alerta_ronda ON ronda_alertas_disparados (alerta_id, ronda_id) "
    "WHERE alerta_id IS NOT NULL AND ronda_id IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS ix_ronda_disp_tipo_status ON ronda_alertas_disparados (tipo, status, disparado_em)",
    "ALTER TABLE inspection_rounds ADD COLUMN IF NOT EXISTS modelo_id uuid",
    """CREATE TABLE IF NOT EXISTS op_setores (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        client_id uuid,
        contract_id uuid,
        nome varchar(120) NOT NULL,
        responsavel varchar(120),
        email varchar(200),
        whatsapp varchar(30),
        ativo boolean NOT NULL DEFAULT true,
        created_at timestamp NOT NULL DEFAULT now()
    )""",
]


class RondaErro(ValueError):  # noqa: N818 — nome em PT-BR, padrão da casa
    def __init__(self, status: int, msg: str) -> None:
        super().__init__(msg)
        self.status = status


async def _ensure(db) -> None:
    for sql in _DDL:
        await db.execute(text(sql))
    await db.commit()


def agora_utc() -> datetime:
    return datetime.utcnow()


def _em_sandbox() -> bool:
    url = os.environ.get("DATABASE_URL", "").lower()
    return "staging" in url or "sandbox" in url


# ───────────────────────── notificação ─────────────────────────
async def notificar(destinos: list[dict], assunto: str, texto: str) -> list[dict]:
    """destinos = [{canal: email|whatsapp, para, nome?}]. Nunca levanta: cada item vira
    {canal, para, status} com status enviado | simulado | falhou. Em sandbox nada sai de verdade."""
    from core.config import settings
    from core.mailer import destinatario_permitido, send_email

    saida = []
    for d in destinos:
        canal, para = d.get("canal"), (d.get("para") or "").strip()
        if not para:
            continue
        item = {
            "canal": canal,
            "para": para,
            "nome": d.get("nome"),
            "em": datetime.now(TZ).isoformat(timespec="seconds"),
        }
        try:
            if canal == "email":
                if not settings.SMTP_HOST or not destinatario_permitido(para):
                    item["status"] = "simulado"
                else:
                    item["status"] = "enviado" if await send_email(para, assunto, f"<p>{texto}</p>") else "falhou"
            elif canal == "whatsapp":
                if _em_sandbox():
                    item["status"] = "simulado"
                else:
                    from modules.integrations.connectors.whatsapp.service import send_text_message

                    r = await send_text_message(para, f"{assunto}\n{texto}")
                    item["status"] = "enviado" if r and not r.get("error") else "falhou"
            else:
                item["status"] = "falhou"
                item["erro"] = f"canal desconhecido: {canal}"
        except Exception as exc:  # noqa: BLE001 — notificação nunca derruba o registro
            item["status"] = "falhou"
            item["erro"] = str(exc)[:200]
        saida.append(item)
    return saida


async def _destinos(db, destinatarios: dict | None) -> list[dict]:
    """{emails: [...], whatsapp_employee_ids: [...]} → lista de destinos com telefone resolvido."""
    d = destinatarios or {}
    out = [{"canal": "email", "para": e} for e in d.get("emails") or [] if e]
    ids = [i for i in d.get("whatsapp_employee_ids") or [] if i]
    if ids:
        rows = (
            await db.execute(
                text(
                    "SELECT id::text, nome, coalesce(nullif(celular,''), nullif(telefone,'')) FROM employees "
                    "WHERE id::text = ANY(:ids)"
                ),
                {"ids": ids},
            )
        ).fetchall()
        out += [{"canal": "whatsapp", "para": r[2] or "", "nome": r[1]} for r in rows]
    return out


async def _gravar_notificado(db, disparo_id: str, notificado: list[dict]) -> None:
    await db.execute(
        text("UPDATE ronda_alertas_disparados SET notificado = CAST(:n AS jsonb) WHERE id = CAST(:i AS uuid)"),
        {"n": json.dumps(notificado, ensure_ascii=False), "i": disparo_id},
    )


# ───────────────────────── pontos × checkpoints ─────────────────────────
def _dist_m(lat1, lng1, lat2, lng2) -> float:
    p = math.pi / 180
    a = (
        0.5
        - math.cos((lat2 - lat1) * p) / 2
        + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lng2 - lng1) * p)) / 2
    )
    return 12742000 * math.asin(math.sqrt(a))


def ponto_do_checkpoint(pontos: list[dict], cp: dict) -> int | None:
    """Índice do ponto que o checkpoint bateu: por nome (`extra_data.ponto`), por posto, ou por
    GPS dentro do raio. Régua única — o oráculo confere esta função."""
    nome = (cp.get("ponto") or "").strip().lower()
    for i, p in enumerate(pontos):
        if nome and nome == str(p.get("nome", "")).strip().lower():
            return i
    for i, p in enumerate(pontos):
        if p.get("post_id") and cp.get("post_id") and str(p["post_id"]) == str(cp["post_id"]):
            return i
    if cp.get("lat") is not None and cp.get("lng") is not None:
        for i, p in enumerate(pontos):
            if p.get("lat") is None or p.get("lng") is None:
                continue
            if _dist_m(float(p["lat"]), float(p["lng"]), float(cp["lat"]), float(cp["lng"])) <= float(
                p.get("raio_m") or RAIO_PADRAO_M
            ):
                return i
    return None


def avaliar_ronda(
    tipo: str,
    ronda: dict,
    pontos: list[dict],
    cps: list[dict],
    agora: datetime,
    minutos: int | None,
    intervalo_min: int,
    tolerancia_min: int,
) -> dict | None:
    """Regra pura de UM alerta sobre UMA ronda. Devolve o detalhe do disparo ou None.
    ronda: {status, scheduled_date (Manaus naive), started_at, completed_at (UTC naive)}."""
    st = ronda["status"]
    seq = [ponto_do_checkpoint(pontos, c) for c in cps]
    batidos = [i for i in seq if i is not None]
    if tipo == "ronda_atrasada":
        tol = minutos if minutos is not None else tolerancia_min
        if st == "agendada" and ronda.get("scheduled_date"):
            prev = ronda["scheduled_date"] + _MANAUS_UTC
            if agora > prev + timedelta(minutes=tol):
                return {
                    "motivo": "não iniciada",
                    "previsto_utc": prev.isoformat(),
                    "atraso_min": int((agora - prev).total_seconds() // 60),
                }
        if st == "em_andamento" and ronda.get("started_at"):
            limite = ronda["started_at"] + timedelta(minutes=intervalo_min + tol)
            if agora > limite:
                return {
                    "motivo": "não concluída no intervalo",
                    "limite_utc": limite.isoformat(),
                    "atraso_min": int((agora - limite).total_seconds() // 60),
                }
        return None
    if tipo == "ponto_pulado":
        if st != "concluida":
            return None
        faltam = [p.get("nome") for i, p in enumerate(pontos) if i not in batidos]
        return {"pulados": faltam, "batidos": len(set(batidos)), "previstos": len(pontos)} if faltam else None
    if tipo == "fora_de_sequencia":
        if len(batidos) < 2 or all(b >= a for a, b in zip(batidos, batidos[1:], strict=False)):
            return None
        return {"ordem_batida": [pontos[i].get("nome") for i in batidos]}
    if tipo == "sem_movimento":
        if st != "em_andamento" or not ronda.get("started_at"):
            return None
        ultimo = max([c["created_at"] for c in cps if c.get("created_at")] + [ronda["started_at"]])
        lim = minutos if minutos is not None else intervalo_min
        if agora - ultimo > timedelta(minutes=lim):
            return {"parado_desde_utc": ultimo.isoformat(), "minutos": int((agora - ultimo).total_seconds() // 60)}
        return None
    return None


SQL_ALERTAS = """
SELECT a.id::text, a.modelo_id::text, a.tipo, a.minutos, a.destinatarios, m.nome, m.pontos, m.intervalo_min, m.tolerancia_min
FROM ronda_alertas a JOIN ronda_modelos m ON m.id = a.modelo_id
WHERE a.ativo AND m.ativo AND a.tipo <> 'panico'
"""
SQL_RONDAS_DO_MODELO = """
SELECT r.id::text, r.code, r.status, r.scheduled_date, r.started_at, r.completed_at, r.inspector_name
FROM inspection_rounds r
WHERE r.modelo_id = CAST(:m AS uuid) AND r.is_active AND r.status IN ('agendada','em_andamento','concluida')
  AND coalesce(r.completed_at, r.started_at, r.scheduled_date + interval '4 hours', r.created_at) >= :desde
"""
SQL_CPS = """
SELECT post_id::text, latitude, longitude, extra_data->>'ponto', created_at
FROM inspection_checkpoints WHERE inspection_round_id = CAST(:r AS uuid) AND is_active ORDER BY created_at, sequence
"""


async def _checkpoints(db, ronda_id: str) -> list[dict]:
    rows = (await db.execute(text(SQL_CPS), {"r": ronda_id})).fetchall()
    return [{"post_id": r[0], "lat": r[1], "lng": r[2], "ponto": r[3], "created_at": r[4]} for r in rows]


async def avaliar_rondas(db, agora: datetime | None = None, janela_h: int = 48) -> list[dict]:
    """Motor idempotente: avalia cada alerta ativo contra as rondas do modelo na janela e grava
    UM disparo por (alerta, ronda) — `ON CONFLICT DO NOTHING`; só o que nasceu agora notifica."""
    await _ensure(db)
    agora = agora or agora_utc()
    novos = []
    for aid, mid, tipo, minutos, dest, mnome, pontos, intervalo, tol in (
        await db.execute(text(SQL_ALERTAS))
    ).fetchall():
        pontos = pontos if isinstance(pontos, list) else json.loads(pontos or "[]")
        rondas = (
            await db.execute(text(SQL_RONDAS_DO_MODELO), {"m": mid, "desde": agora - timedelta(hours=janela_h)})
        ).fetchall()
        for rid, code, st, sched, started, completed, insp in rondas:
            ronda = {"status": st, "scheduled_date": sched, "started_at": started, "completed_at": completed}
            det = avaliar_ronda(tipo, ronda, pontos, await _checkpoints(db, rid), agora, minutos, intervalo, tol)
            if not det:
                continue
            did = (
                await db.execute(
                    text(
                        "INSERT INTO ronda_alertas_disparados (alerta_id, tipo, ronda_id, modelo_id, detalhe, disparado_em) "
                        "VALUES (CAST(:a AS uuid), :t, CAST(:r AS uuid), CAST(:m AS uuid), CAST(:d AS jsonb), :ag) "
                        "ON CONFLICT (alerta_id, ronda_id) WHERE alerta_id IS NOT NULL AND ronda_id IS NOT NULL DO NOTHING RETURNING id::text"
                    ),
                    {
                        "a": aid,
                        "t": tipo,
                        "r": rid,
                        "m": mid,
                        "d": json.dumps(det, ensure_ascii=False, default=str),
                        "ag": agora,
                    },
                )
            ).scalar()
            if not did:
                continue
            texto = f"Ronda {code} ({mnome}, {insp or '—'}): {TIPOS_ALERTA[tipo]} — {json.dumps(det, ensure_ascii=False, default=str)}"
            notif = await notificar(await _destinos(db, dest), f"[Conecta PRO] {TIPOS_ALERTA[tipo]} — {code}", texto)
            await _gravar_notificado(db, did, notif)
            novos.append({"id": did, "tipo": tipo, "ronda": code, "modelo": mnome, "detalhe": det, "notificado": notif})
    await db.commit()
    return novos


# ───────────────────────── pânico ─────────────────────────
async def disparar_panico(
    db,
    *,
    user_id: str | None,
    employee_id: str | None,
    employee_nome: str,
    lat: float | None,
    lng: float | None,
    post_id: str | None = None,
    ronda_id: str | None = None,
    mensagem: str | None = None,
    foto_url: str | None = None,
) -> dict:
    """Disparo `panico` + ocorrência GRAVE pelo mesmo caminho da F8 + notificação imediata aos
    destinatários dos alertas `panico` do posto/cliente. Disparo e ocorrência saem no mesmo commit."""
    from modules.operacional.services import supervisao_service as ss

    await _ensure(db)
    if not post_id and ronda_id:
        post_id = (
            await db.execute(
                text("SELECT posts_to_visit->>0 FROM inspection_rounds WHERE id = CAST(:r AS uuid)"), {"r": ronda_id}
            )
        ).scalar()
    if not post_id and employee_id:
        post_id = (
            await db.execute(
                text("SELECT posto_atual_id::text FROM employees WHERE id = CAST(:e AS uuid)"), {"e": employee_id}
            )
        ).scalar()
    if not post_id:
        raise RondaErro(422, "Pânico sem posto: informe post_id ou ronda_id (o colaborador não tem posto atual).")
    posto = (
        await db.execute(text("SELECT name, client_id::text FROM posts WHERE id = CAST(:p AS uuid)"), {"p": post_id})
    ).fetchone()
    if not posto:
        raise RondaErro(404, "Posto não encontrado.")
    agora = agora_utc()
    did = (
        await db.execute(
            text(
                "INSERT INTO ronda_alertas_disparados (tipo, ronda_id, post_id, employee_id, employee_nome, latitude, longitude, "
                "foto_url, mensagem, disparado_em) VALUES ('panico', CAST(:r AS uuid), CAST(:p AS uuid), CAST(:e AS uuid), :n, "
                ":la, :lo, :f, :m, :ag) RETURNING id::text"
            ),
            {
                "r": ronda_id or None,
                "p": post_id,
                "e": employee_id or None,
                "n": employee_nome[:255],
                "la": lat,
                "lo": lng,
                "f": foto_url,
                "m": (mensagem or "").strip() or None,
                "ag": agora,
            },
        )
    ).scalar()
    where = f" em {posto[0]}" + (f" (lat {lat:.5f}, lng {lng:.5f})" if lat is not None and lng is not None else "")
    desc = f"BOTÃO DE PÂNICO acionado por {employee_nome}{where} às {(agora - _MANAUS_UTC).strftime('%d/%m/%Y %H:%M')}."
    if mensagem:
        desc += f" Mensagem: {mensagem.strip()}"
    occ = await ss.criar_ocorrencia(  # commita: disparo + ocorrência na mesma transação
        db,
        user_id=user_id or employee_id or "",
        post_id=post_id,
        titulo=f"PÂNICO — {employee_nome}",
        descricao=desc,
        tipo="incidente",
        gravidade="grave",
        categoria="operacional",
        employee_id=employee_id,
        quando=agora - _MANAUS_UTC,
        foto_url=foto_url,
    )
    await db.execute(
        text("UPDATE ronda_alertas_disparados SET occurrence_id = CAST(:o AS uuid) WHERE id = CAST(:i AS uuid)"),
        {"o": str(occ.id), "i": did},
    )
    dest_rows = (
        await db.execute(
            text(
                "SELECT a.destinatarios FROM ronda_alertas a JOIN ronda_modelos m ON m.id = a.modelo_id "
                "WHERE a.ativo AND m.ativo AND a.tipo = 'panico' AND (m.post_id = CAST(:p AS uuid) OR "
                "(m.client_id IS NOT NULL AND m.client_id = CAST(:c AS uuid)))"
            ),
            {"p": post_id, "c": posto[1]},
        )
    ).fetchall()
    destinos: list[dict] = []
    vistos: set[str] = set()
    for (d,) in dest_rows:
        for x in await _destinos(db, d if isinstance(d, dict) else json.loads(d or "{}")):
            if x["para"] and x["para"] not in vistos:
                vistos.add(x["para"])
                destinos.append(x)
    notif = await notificar(destinos, f"[Conecta PRO] PÂNICO — {posto[0]}", desc + f" Ocorrência {occ.code}.")
    await _gravar_notificado(db, did, notif)
    await db.commit()
    return {
        "id": did,
        "occurrence_id": str(occ.id),
        "occurrence_code": occ.code,
        "post_id": post_id,
        "notificado": notif,
    }


async def mudar_status_disparo(db, *, disparo_id: str, novo: str, user_id: str | None) -> dict:
    await _ensure(db)
    st = (
        await db.execute(
            text("SELECT status FROM ronda_alertas_disparados WHERE id = CAST(:i AS uuid)"), {"i": disparo_id}
        )
    ).scalar()
    if not st:
        raise RondaErro(404, "Disparo não encontrado.")
    if novo == "reconhecido" and st != "aberto":
        raise RondaErro(409, f"Disparo está '{STATUS_DISPARO.get(st, st)}' — só se reconhece disparo aberto.")
    if novo == "encerrado" and st == "encerrado":
        raise RondaErro(409, "Disparo já encerrado.")
    col = "reconhecido" if novo == "reconhecido" else "encerrado"
    await db.execute(
        text(
            f"UPDATE ronda_alertas_disparados SET status = :s, {col}_em = :a, {col}_por = CAST(:u AS uuid) WHERE id = CAST(:i AS uuid)"
        ),  # noqa: S608  # nosec B608 — col em {reconhecido, encerrado}
        {"s": novo, "a": agora_utc(), "u": user_id or None, "i": disparo_id},
    )
    await db.commit()
    return {"id": disparo_id, "status": novo}


# ───────────────────────── cadastros ─────────────────────────
def parse_pontos(texto: str) -> list[dict]:
    """Uma linha por ponto: `nome; lat; lng; raio_m; foto` (lat/lng/raio/foto opcionais).
    `foto` = s/sim/1 exige foto no ponto. Ordem das linhas = sequência da ronda."""
    pontos = []
    for ln in (texto or "").splitlines():
        partes = [x.strip() for x in ln.split(";")]
        if not partes or not partes[0]:
            continue
        p: dict = {"nome": partes[0][:120]}
        try:
            if len(partes) > 2 and partes[1] and partes[2]:
                p["lat"], p["lng"] = float(partes[1].replace(",", ".")), float(partes[2].replace(",", "."))
            if len(partes) > 3 and partes[3]:
                p["raio_m"] = int(float(partes[3]))
        except ValueError as exc:
            raise RondaErro(400, f"Ponto '{partes[0]}': lat/lng/raio inválidos ({exc}).") from exc
        p["foto_obrigatoria"] = len(partes) > 4 and partes[4].lower() in ("s", "sim", "1", "true")
        pontos.append(p)
    if not pontos:
        raise RondaErro(400, "Informe ao menos um ponto (uma linha por ponto).")
    return pontos


async def criar_modelo(
    db,
    *,
    nome: str,
    post_id: str | None,
    client_id: str | None,
    pontos: list[dict],
    intervalo_min: int,
    tolerancia_min: int,
    user_id: str | None,
) -> dict:
    await _ensure(db)
    if len((nome or "").strip()) < 3:
        raise RondaErro(400, "Nome do modelo com ao menos 3 caracteres.")
    if not post_id and not client_id:
        raise RondaErro(400, "Escolha o posto ou o cliente do modelo.")
    if post_id and not client_id:
        client_id = (
            await db.execute(text("SELECT client_id::text FROM posts WHERE id = CAST(:p AS uuid)"), {"p": post_id})
        ).scalar()
    mid = (
        await db.execute(
            text(
                "INSERT INTO ronda_modelos (nome, post_id, client_id, pontos, intervalo_min, tolerancia_min, created_by) VALUES "
                "(:n, CAST(:p AS uuid), CAST(:c AS uuid), CAST(:pt AS jsonb), :i, :t, CAST(:u AS uuid)) RETURNING id::text"
            ),
            {
                "n": nome.strip(),
                "p": post_id or None,
                "c": client_id or None,
                "pt": json.dumps(pontos, ensure_ascii=False),
                "i": max(1, int(intervalo_min or 60)),
                "t": max(0, int(tolerancia_min or 15)),
                "u": user_id or None,
            },
        )
    ).scalar()
    await db.commit()
    return {"id": mid, "pontos": len(pontos)}


async def criar_alerta(
    db, *, modelo_id: str, tipo: str, minutos: int | None, emails: list[str], whatsapp_employee_ids: list[str]
) -> dict:
    await _ensure(db)
    if tipo not in TIPOS_ALERTA:
        raise RondaErro(400, f"Tipo inválido: {tipo!r}.")
    emails = [e.strip().lower() for e in emails if e and "@" in e]
    ids = [i for i in whatsapp_employee_ids if i]
    if not emails and not ids:
        raise RondaErro(400, "Informe ao menos um e-mail ou um colaborador para WhatsApp.")
    aid = (
        await db.execute(
            text(
                "INSERT INTO ronda_alertas (modelo_id, tipo, minutos, destinatarios) VALUES (CAST(:m AS uuid), :t, :mi, CAST(:d AS jsonb)) RETURNING id::text"
            ),
            {
                "m": modelo_id,
                "t": tipo,
                "mi": minutos,
                "d": json.dumps({"emails": emails, "whatsapp_employee_ids": ids}),
            },
        )
    ).scalar()
    await db.commit()
    return {"id": aid}


async def agendar_ronda_do_modelo(
    db, *, modelo_id: str, user_id: str, user_nome: str, quando_manaus: datetime | None
) -> dict:
    """Ronda `agendada` nascida do modelo — o motor passa a vigiá-la (atrasada / pontos)."""
    await _ensure(db)
    m = (
        await db.execute(
            text("SELECT nome, post_id::text FROM ronda_modelos WHERE id = CAST(:m AS uuid) AND ativo"),
            {"m": modelo_id},
        )
    ).fetchone()
    if not m:
        raise RondaErro(404, "Modelo não encontrado ou inativo.")
    ano = datetime.now(TZ).year
    seq = (
        await db.execute(
            text("SELECT coalesce(max(substring(code from 10)::int), 0) + 1 FROM inspection_rounds WHERE code LIKE :p"),
            {"p": f"RON-{ano}-%"},
        )
    ).scalar()
    code = f"RON-{ano}-{int(seq):05d}"
    rid = (
        await db.execute(
            text(
                "INSERT INTO inspection_rounds (code, tenant_id, inspector_id, inspector_name, inspector_role, status, scheduled_date, "
                "posts_to_visit, posts_visited, modelo_id, observations, created_by) VALUES (:c, '00000000-0000-0000-0000-000000000000', "
                "CAST(:u AS uuid), :n, 'supervisor_operacional', 'agendada', :q, CAST(:pv AS jsonb), '[]', CAST(:m AS uuid), :o, CAST(:u AS uuid)) "
                "RETURNING id::text"
            ),
            {
                "c": code,
                "u": user_id,
                "n": user_nome[:255],
                "q": quando_manaus or datetime.now(TZ).replace(tzinfo=None),
                "pv": json.dumps([m[1]] if m[1] else []),
                "m": modelo_id,
                "o": f"Ronda do modelo «{m[0]}»",
            },
        )
    ).scalar()
    await db.commit()
    return {"id": rid, "code": code}


async def criar_setor(
    db,
    *,
    nome: str,
    client_id: str | None,
    contract_id: str | None,
    responsavel: str | None,
    email: str | None,
    whatsapp: str | None,
) -> dict:
    await _ensure(db)
    if len((nome or "").strip()) < 2:
        raise RondaErro(400, "Nome do setor com ao menos 2 caracteres.")
    if not (email or whatsapp):
        raise RondaErro(400, "Setor precisa de e-mail ou WhatsApp do responsável — sem isso não há quem avisar.")
    if email and "@" not in email:
        raise RondaErro(400, "E-mail inválido.")
    sid = (
        await db.execute(
            text(
                "INSERT INTO op_setores (nome, client_id, contract_id, responsavel, email, whatsapp) VALUES "
                "(:n, CAST(:c AS uuid), CAST(:k AS uuid), :r, :e, :w) RETURNING id::text"
            ),
            {
                "n": nome.strip(),
                "c": client_id or None,
                "k": contract_id or None,
                "r": (responsavel or "").strip() or None,
                "e": (email or "").strip().lower() or None,
                "w": (whatsapp or "").strip() or None,
            },
        )
    ).scalar()
    await db.commit()
    return {"id": sid}


async def desativar(db, tabela: str, id_: str) -> None:
    if tabela not in ("ronda_modelos", "ronda_alertas", "op_setores"):
        raise RondaErro(400, "Tabela inválida.")
    await _ensure(db)
    n = (
        await db.execute(text(f"UPDATE {tabela} SET ativo = false WHERE id = CAST(:i AS uuid) AND ativo"), {"i": id_})
    ).rowcount  # noqa: S608  # nosec B608 — tabela validada acima
    if not n:
        raise RondaErro(404, "Registro não encontrado ou já inativo.")
    await db.commit()

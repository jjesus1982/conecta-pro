"""DGX F12 — SESMT (tipos de exame, médicos) + Demandas (assuntos, atendimentos, feedbacks,
diretórios do cliente) + Comercial (fontes pagadoras, regiões, postos por cliente) — 24/09/2026.

O que foi cavado antes de construir (sandbox = cópia de produção de 23/09):
  · ASO tem DUAS tabelas: `gp_asos` (97, VIVA — model `people_management/sst/models/aso.py`,
    escrita por `sst_controller` POST /aso, /aso/retroativo, esteira/alertas, tools do Hermes) e
    `health_asos` (97, MORTA — model `health_occupational/models/pcmso.py`, escrita só por
    `pcmso_service.emitir_aso` (Session síncrona, sem rota montada); `sst_alerts_tasks` já a
    abandonou em 07/09). Espelho de 03/2026, `updated_at` idêntico. Tudo aqui lê e grava `gp_asos`.
  · Médico do ASO é texto: 'Dr. Carlos Mendes / CRM-AM 4521' em 96/97 linhas; o PCMSO (`sst_pcmso`,
    OCR de 07/2026) tem o coordenador DR. POJUCAN (CRM/AM 467) e `exames_por_funcao` com 3 grupos
    (PORTARIA/MANUTENCAO/CONSERVACAO_E_LIMPEZA → AGP, LIDER, ARTIFICE, ASG, JARDINEIRO) e códigos
    da Tabela 27. `gp_asos.exames` só cita 'Avaliação clínica ocupacional' (0295). É daí que os
    cadastros nascem — nada inventado.
  · Demandas: `ouvidoria_manifestacoes` (4, canal do meu-espaço) fica onde está e é LIDA como
    atendimento de origem 'ouvidoria'; `client_portal_tickets` (5) idem, origem 'portal';
    `feedback_insights` (0) e NPS (`crm_followups.template='nps'`, 0 respostas) entram na tela de
    feedbacks com a satisfação dos atendimentos. `cwi_message_log` (4.448) é a conversa, não o
    atendimento — o atendimento nasce aqui e aponta para ela pelo cliente.
  · Diretório do cliente = `crm_contacts` (20: Síndico 6, Contato principal 11…) + os contatos
    financeiro/técnico de `clients` + supervisor/emergência de `posts`. Form reusa POST
    /crm/contacts/ com papel tipado.
  · Comercial: `posts.required_headcount` é o contratado; «alocado hoje» é `allocations`
    status='active' — a MESMA fonte de `grade_do_posto`. `employee_alocacoes` (F5) tem
    `posto_id` NULL em 51/51 (aponta condomínio), por isso não serve para posto.
  · `fin_condicoes_pagamento` (F11) é a condição da fonte pagadora; `receivable_accounts` ganha
    `fonte_pagadora_id` e o form «Registrar conta a receber» ganha o select — o envio passa por
    F11 (`_conta_com_condicao`) e só grava a coluna depois. Nada do que emite NFS-e muda.

Prefixo `_` = o discovery pula. `crm.py` inclui `router` e chama `telas_crm`; `saude_ocupacional.py`
chama `telas_sst`; `departamento_pessoal.py` chama `ligar_aso_form`; `financeiro.py` chama
`telas_fin`. DDL idempotente em `_ensure`.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db

#: ANTES do import do data_controller (o ciclo de import fecha com o router pronto).
router = APIRouter()

from modules.operacional.controllers.redesign_data_controller import (  # noqa: E402
    _helpers,
    b,
    t,
)

_ND = "#0F1B3A"
_ACT = "/api/v1/redesign/action/"
_TZ = "America/Manaus"

IDS_SST = ("tipos-exame", "tipo-exame-novo", "medicos", "medico-novo", "exames-por-funcao", "aso-agendar")
IDS_CRM = (
    "demandas-assuntos",
    "demanda-assunto-novo",
    "atendimentos",
    "atendimento-novo",
    "feedbacks",
    "diretorios-cliente",
    "diretorio-contato-novo",
    "fontes-pagadoras",
    "fonte-pagadora-nova",
    "regioes",
    "regiao-nova",
    "postos-por-cliente",
)

AREAS = ("operacional", "dp", "financeiro", "comercial", "ouvidoria")
ORIGENS = ("whatsapp", "telefone", "email", "portal", "presencial", "ouvidoria")
PAPEIS = (
    ("sindico", "Síndico"),
    ("zelador", "Zelador"),
    ("administradora", "Administradora"),
    ("financeiro", "Financeiro"),
    ("emergencia", "Emergência"),
    ("contato", "Contato"),
)

#: códigos de função do PCMSO (OCR) → cargo como está em `employees.cargo` (normalizado por `norm`).
_FUNC_PCMSO = {
    "AGP": "AGENTE DE PORTARIA",
    "LIDER": "LIDER DE PORTARIA",
    "ASG": "AGENTE DE SERVICOS GERAIS",
    "JARDINEIRO": "JARDINEIRO",
    "ARTIFICE": "ARTIFICE",
}

# ── DDL ─────────────────────────────────────────────────────────────────────────────────────
_DDL = [
    """CREATE TABLE IF NOT EXISTS sst_tipos_exame (
        id serial PRIMARY KEY, nome text NOT NULL UNIQUE, codigo_esocial text, periodicidade_meses int NOT NULL DEFAULT 12,
        obrigatorio_admissional boolean NOT NULL DEFAULT true, obrigatorio_periodico boolean NOT NULL DEFAULT true,
        obrigatorio_demissional boolean NOT NULL DEFAULT false, obrigatorio_retorno boolean NOT NULL DEFAULT false,
        obrigatorio_mudanca_funcao boolean NOT NULL DEFAULT false, por_funcao jsonb NOT NULL DEFAULT '[]',
        custo_ref numeric(10,2), ativo boolean NOT NULL DEFAULT true, created_at timestamptz DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS sst_medicos (
        id serial PRIMARY KEY, nome text NOT NULL, crm text NOT NULL, uf char(2) NOT NULL DEFAULT 'AM', especialidade text,
        clinica text, telefone text, responsavel_pcmso boolean NOT NULL DEFAULT false, ativo boolean NOT NULL DEFAULT true,
        created_at timestamptz DEFAULT now(), UNIQUE (crm, uf))""",
    "ALTER TABLE gp_asos ADD COLUMN IF NOT EXISTS medico_id int",
    "ALTER TABLE gp_asos ADD COLUMN IF NOT EXISTS tipos_exame_ids jsonb",
    """CREATE TABLE IF NOT EXISTS dem_assuntos (
        id serial PRIMARY KEY, nome text NOT NULL UNIQUE, area text NOT NULL, sla_horas int NOT NULL DEFAULT 24,
        responsavel_padrao text, ativo boolean NOT NULL DEFAULT true, created_at timestamptz DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS dem_atendimentos (
        id serial PRIMARY KEY, numero text, assunto_id int REFERENCES dem_assuntos(id), origem text NOT NULL,
        cliente_id uuid, employee_id uuid, externo_nome text, externo_telefone text, descricao text NOT NULL,
        status text NOT NULL DEFAULT 'aberto', atribuido_a text, aberto_em timestamptz NOT NULL DEFAULT now(),
        resolvido_em timestamptz, resolucao text, satisfacao smallint, ref_tipo text, ref_id text,
        aberto_por text, created_at timestamptz DEFAULT now(),
        CONSTRAINT dem_atend_status CHECK (status IN ('aberto','em_andamento','resolvido','cancelado')),
        CONSTRAINT dem_atend_resolvido CHECK (resolvido_em IS NULL OR resolvido_em >= aberto_em),
        CONSTRAINT dem_atend_satisfacao CHECK (satisfacao IS NULL OR satisfacao BETWEEN 1 AND 5))""",
    "CREATE INDEX IF NOT EXISTS ix_dem_atend_status ON dem_atendimentos (status, aberto_em)",
    """CREATE TABLE IF NOT EXISTS crm_fontes_pagadoras (
        id serial PRIMARY KEY, cliente_id uuid NOT NULL, razao_social text NOT NULL, cnpj char(14) NOT NULL,
        endereco_cobranca text, email_nf text, condicao_id int, dia_vencimento smallint, ativo boolean NOT NULL DEFAULT true,
        created_at timestamptz DEFAULT now(), UNIQUE (cliente_id, cnpj))""",
    """CREATE TABLE IF NOT EXISTS crm_regioes (
        id serial PRIMARY KEY, nome text NOT NULL UNIQUE, uf char(2) NOT NULL DEFAULT 'AM', municipios jsonb NOT NULL DEFAULT '[]',
        supervisor_employee_id uuid, cor text, ativo boolean NOT NULL DEFAULT true, created_at timestamptz DEFAULT now())""",
    "ALTER TABLE clients ADD COLUMN IF NOT EXISTS regiao_id int",
    "ALTER TABLE posts ADD COLUMN IF NOT EXISTS regiao_id int",
    "ALTER TABLE receivable_accounts ADD COLUMN IF NOT EXISTS fonte_pagadora_id int",
]

#: (nome, área, SLA em horas) — o que chega hoje pelo WhatsApp/portal/ouvidoria, tipado.
_SEED_ASSUNTOS = [
    ("Falta / cobertura no posto", "operacional", 4),
    ("Ocorrência no posto", "operacional", 8),
    ("Holerite / pagamento do colaborador", "dp", 48),
    ("Boleto / nota fiscal", "financeiro", 48),
    ("Proposta / renovação de contrato", "comercial", 72),
    ("Solicitação pelo portal do cliente", "comercial", 24),
    ("Ouvidoria", "ouvidoria", 120),
]


def norm(s: str | None) -> str:
    """Cargo/função sem acento, maiúsculo, espaços únicos — 'LÍDER DE PORTARIA' == 'LIDER DE PORTARIA'."""
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().upper()


def sla_vencido(aberto_em: datetime, sla_horas: int, ref: datetime | None = None) -> bool:
    """SLA vencido quando (ref ou agora) − aberto_em > SLA. Regra pura; o oráculo a confere."""
    ref = ref or datetime.now(UTC)
    if aberto_em.tzinfo is None:
        aberto_em = aberto_em.replace(tzinfo=UTC)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=UTC)
    return ref - aberto_em > timedelta(hours=int(sla_horas or 0))


def _crm_split(crm_txt: str | None) -> tuple[str, str]:
    """'CRM-AM 4521' → ('4521', 'AM'); '467' → ('467', 'AM')."""
    s = str(crm_txt or "")
    uf = re.search(r"\b([A-Z]{2})\b", s.upper().replace("CRM", ""))
    num = re.search(r"\d+", s)
    return (num.group(0) if num else ""), (uf.group(1) if uf else "AM")


#: 🔴 27/09/2026 — DDL A CADA REQUEST CAUSAVA DEADLOCK, E O DANO CAÍA EM OUTRA TELA.
#:
#: `_ensure` rodava a lista `_DDL` inteira em TODA chamada — 15 pontos deste arquivo a chamam.
#: `CREATE TABLE IF NOT EXISTS` não é barato: ele pega **AccessExclusiveLock** na relação mesmo
#: quando a tabela já existe, e sob concorrência trava com quem está apenas LENDO.
#:
#: Medido: **13 deadlocks em 6 horas**. E o prejuízo aparecia longe da causa — o Hermes tentou
#: `dashboard_operacional` (rota de OUTRO módulo, que responde 200 sozinha) e levou HTTP 500,
#: porque o deadlock derrubou a transação de quem estava no meio do caminho.
#:
#: ⭐ O defeito não é o DDL: é o DDL ser reexecutado. Uma vez por processo basta, e a checagem
#: de existência é uma leitura barata que não pega lock exclusivo nenhum.
_PRONTO = False


async def _ensure(db: AsyncSession) -> None:
    global _PRONTO  # noqa: PLW0603
    if _PRONTO:
        return
    # ⚠️ Confere por LEITURA antes de tentar criar. `to_regclass` não pega lock de escrita;
    # `CREATE TABLE IF NOT EXISTS` pega, e era essa a diferença entre 13 deadlocks e zero.
    ja_existe = (await db.execute(
        text("SELECT to_regclass('dem_assuntos') IS NOT NULL"))).scalar()
    if ja_existe:
        _PRONTO = True
        return
    for sql in _DDL:
        await db.execute(text(sql))
    for nome, area, sla in _SEED_ASSUNTOS:
        await db.execute(
            text("INSERT INTO dem_assuntos (nome, area, sla_horas) VALUES (:n, :a, :s) ON CONFLICT (nome) DO NOTHING"),
            {"n": nome, "a": area, "s": sla},
        )
    await db.execute(
        text(
            "INSERT INTO crm_regioes (nome, uf, municipios) VALUES ('Manaus', 'AM', '[\"Manaus\"]') ON CONFLICT (nome) DO NOTHING"
        )
    )
    # médico coordenador do PCMSO + médicos citados nos ASOs (texto → cadastro)
    pcmso = (
        await db.execute(
            text(
                "SELECT medico_coordenador, crm, uf, exames_por_funcao FROM sst_pcmso ORDER BY vigencia_inicio DESC NULLS LAST LIMIT 1"
            )
        )
    ).first()
    if pcmso and pcmso[0]:
        num, uf = _crm_split(pcmso[1])
        await db.execute(
            text(
                "INSERT INTO sst_medicos (nome, crm, uf, especialidade, responsavel_pcmso) VALUES (:n, :c, :u, 'Medicina do Trabalho', true) "
                "ON CONFLICT (crm, uf) DO UPDATE SET responsavel_pcmso=true"
            ),
            {"n": pcmso[0].strip().title(), "c": num or "?", "u": (pcmso[2] or uf or "AM")[:2].upper()},
        )
    for med, crm_txt, clinica in (
        await db.execute(
            text(
                "SELECT medico, crm, max(clinica) FROM gp_asos WHERE medico IS NOT NULL AND medico<>'' GROUP BY medico, crm"
            )
        )
    ).all():
        num, uf = _crm_split(crm_txt)
        if not num:
            continue
        await db.execute(
            text(
                "INSERT INTO sst_medicos (nome, crm, uf, clinica) VALUES (:n, :c, :u, :cl) ON CONFLICT (crm, uf) DO NOTHING"
            ),
            {"n": med.strip(), "c": num, "u": uf, "cl": clinica},
        )
    # tipos de exame: do PCMSO (por grupo de função) e dos ASOs (código 0295)
    grupos = (pcmso[3] if pcmso and isinstance(pcmso[3], dict) else {}) or {}
    por_exame: dict[str, dict] = {}
    for g in grupos.values():
        cargos = [_FUNC_PCMSO.get(str(f).upper(), norm(f)) for f in (g.get("funcoes") or [])]
        for ex in g.get("exames") or []:
            nome = str(ex.get("nome") or "").strip()
            if not nome:
                continue
            d = por_exame.setdefault(nome, {"cod": ex.get("cod_tabela27"), "cargos": []})
            d["cargos"] += [c for c in cargos if c not in d["cargos"]]
    for nome, d in por_exame.items():
        so_adm = "admissional" in nome.lower()
        await db.execute(
            text(
                "INSERT INTO sst_tipos_exame (nome, codigo_esocial, por_funcao, obrigatorio_periodico, obrigatorio_demissional, "
                " obrigatorio_retorno, obrigatorio_mudanca_funcao) VALUES (:n, :c, CAST(:f AS jsonb), :p, :d, :r, :m) "
                "ON CONFLICT (nome) DO NOTHING"
            ),
            {
                "n": nome,
                "c": d["cod"],
                "f": json.dumps(d["cargos"]),
                "p": not so_adm,
                "d": nome.lower().startswith("exame clinico"),
                "r": nome.lower().startswith("exame clinico"),
                "m": nome.lower().startswith("exame clinico"),
            },
        )
    for nome, cod in (
        await db.execute(
            text(
                "SELECT DISTINCT x->>'nome', x->>'cod_procedimento' FROM gp_asos a, jsonb_array_elements(coalesce(a.exames,'[]')) x "
                "WHERE x->>'nome' IS NOT NULL"
            )
        )
    ).all():
        await db.execute(
            text(
                "INSERT INTO sst_tipos_exame (nome, codigo_esocial, por_funcao, obrigatorio_demissional, obrigatorio_retorno, obrigatorio_mudanca_funcao) "
                "SELECT :n, :c, '[]', true, true, true WHERE NOT EXISTS (SELECT 1 FROM sst_tipos_exame WHERE nome=:n OR (codigo_esocial IS NOT NULL AND codigo_esocial=:c))"
            ),
            {"n": nome, "c": cod},
        )
    await db.commit()


# ── serviços (o oráculo importa estes) ──────────────────────────────────────────────────────

    # ⚠️ Só no FIM: marcar pronto antes dos seeds faria uma falha no meio virar "já fiz",
    # e o processo seguiria com tabela criada e semente faltando.
    _PRONTO = True

async def vencidos_por_funcao(db: AsyncSession) -> dict[str, dict]:
    """Por função (cargo normalizado): ativos, ids com último ASO vencido ou sem ASO realizado.
    Mesma régua da aba Exames / `asos_vencendo`: ÚLTIMO ASO da pessoa ativa, não todo ASO da história."""
    rows = (
        await db.execute(
            text(
                "SELECT e.id::text, e.nome, e.cargo, "
                " (SELECT max(a.data_validade) FROM gp_asos a WHERE a.employee_id=e.id AND a.data_validade IS NOT NULL) AS validade, "
                " EXISTS (SELECT 1 FROM gp_asos a WHERE a.employee_id=e.id AND a.status='realizado') AS tem_aso, "
                " (now() AT TIME ZONE :tz)::date AS hoje "
                "FROM employees e WHERE e.status='ativo' ORDER BY e.nome"
            ),
            {"tz": _TZ},
        )
    ).all()
    out: dict[str, dict] = {}
    for eid, nome, cargo, validade, tem_aso, hoje in rows:
        d = out.setdefault(norm(cargo), {"cargo": cargo or "—", "ativos": 0, "vencidos": [], "nomes": []})
        d["ativos"] += 1
        if not tem_aso or (validade is not None and validade < hoje):
            d["vencidos"].append(eid)
            d["nomes"].append(nome)
    return out


async def listar_atendimentos(db: AsyncSession) -> list[dict]:
    """dem_atendimentos + ouvidoria_manifestacoes (lida, não migrada) + client_portal_tickets (idem)."""
    rows = (
        await db.execute(
            text(
                "SELECT * FROM ("
                "SELECT a.id, a.numero, coalesce(s.nome,'—'), coalesce(s.sla_horas,24), a.origem, "
                "  coalesce(c.name, e.nome, a.externo_nome, '—'), a.descricao, a.status, coalesce(a.atribuido_a,''), "
                "  a.aberto_em, a.resolvido_em, a.satisfacao, a.cliente_id::text, a.resolucao "
                "FROM dem_atendimentos a LEFT JOIN dem_assuntos s ON s.id=a.assunto_id "
                "LEFT JOIN clients c ON c.id=a.cliente_id LEFT JOIN employees e ON e.id=a.employee_id "
                "UNION ALL "
                "SELECT NULL, o.protocolo, 'Ouvidoria · '||coalesce(o.categoria,'—'), 120, 'ouvidoria', "
                "  CASE WHEN o.anonimo THEN 'Anônimo' ELSE coalesce(e.nome,'—') END, o.mensagem, "
                "  CASE WHEN o.status IN ('respondida','fechada','resolvida') THEN 'resolvido' ELSE 'aberto' END, "
                "  '', o.created_at, o.respondido_em, NULL, NULL, o.resposta "
                "FROM ouvidoria_manifestacoes o LEFT JOIN employees e ON e.id=o.employee_id "
                "UNION ALL "
                "SELECT NULL, 'PORTAL-'||left(t.id::text,8), 'Portal · '||coalesce(t.subject,'—'), 24, 'portal', coalesce(c.name,'—'), "
                "  coalesce(t.description,''), CASE WHEN upper(t.status) IN ('FECHADO','RESOLVIDO','RESPONDIDO') THEN 'resolvido' ELSE 'aberto' END, "
                "  '', t.created_at, coalesce(t.closed_at, CASE WHEN upper(t.status) IN ('FECHADO','RESOLVIDO','RESPONDIDO') THEN t.updated_at END), "
                "  NULL, t.client_id::text, NULL "
                "FROM client_portal_tickets t LEFT JOIN clients c ON c.id=t.client_id "
                ") u (id, numero, assunto, sla_horas, origem, solicitante, descricao, status, atribuido_a, aberto_em, resolvido_em, "
                "satisfacao, cliente_id, resolucao) ORDER BY status = 'resolvido', aberto_em DESC"
            )
        )
    ).all()
    return [
        {
            "id": r[0],
            "numero": r[1] or "—",
            "assunto": r[2],
            "sla_horas": int(r[3] or 0),
            "origem": r[4],
            "solicitante": r[5],
            "descricao": r[6] or "",
            "status": r[7],
            "atribuido_a": r[8],
            "aberto_em": r[9],
            "resolvido_em": r[10],
            "satisfacao": r[11],
            "cliente_id": r[12],
            "resolucao": r[13],
        }
        for r in rows
    ]


async def resolver_atendimento(db: AsyncSession, atid: int, resolucao: str, satisfacao: int | None, por: str) -> None:
    await db.execute(
        text(
            "UPDATE dem_atendimentos SET status='resolvido', resolvido_em=greatest(now(), aberto_em), resolucao=:r, "
            "satisfacao=:s, atribuido_a=coalesce(nullif(atribuido_a,''), :p) WHERE id=:i AND status<>'resolvido'"
        ),
        {"r": resolucao, "s": satisfacao, "p": por, "i": int(atid)},
    )
    await db.commit()


async def salvar_fonte_pagadora(db: AsyncSession, p: dict) -> int:
    from modules.government_integrations.utils import validar_cnpj

    cnpj = re.sub(r"\D", "", str(p.get("cnpj") or ""))
    if not validar_cnpj(cnpj):
        raise HTTPException(status_code=400, detail="CNPJ inválido.")
    rz = str(p.get("razao_social") or "").strip()
    if len(rz) < 3 or not p.get("cliente_id"):
        raise HTTPException(status_code=400, detail="Cliente e razão social são obrigatórios.")
    dia = int(p["dia_vencimento"]) if str(p.get("dia_vencimento") or "").strip() else None
    if dia is not None and not 1 <= dia <= 31:
        raise HTTPException(status_code=400, detail="Dia de vencimento: 1 a 31.")
    cond = int(p["condicao_id"]) if str(p.get("condicao_id") or "").strip() else None
    args = {
        "c": str(p["cliente_id"]),
        "rz": rz,
        "cnpj": cnpj,
        "end": (p.get("endereco_cobranca") or None),
        "em": (p.get("email_nf") or None),
        "cond": cond,
        "dia": dia,
    }
    fid = str(p.get("id") or "").strip()
    if fid:
        await db.execute(
            text(
                "UPDATE crm_fontes_pagadoras SET cliente_id=CAST(:c AS uuid), razao_social=:rz, cnpj=:cnpj, endereco_cobranca=:end, "
                "email_nf=:em, condicao_id=:cond, dia_vencimento=:dia WHERE id=:i"
            ),
            {**args, "i": int(fid)},
        )
        await db.commit()
        return int(fid)
    rid = (
        await db.execute(
            text(
                "INSERT INTO crm_fontes_pagadoras (cliente_id, razao_social, cnpj, endereco_cobranca, email_nf, condicao_id, dia_vencimento) "
                "VALUES (CAST(:c AS uuid), :rz, :cnpj, :end, :em, :cond, :dia) "
                "ON CONFLICT (cliente_id, cnpj) DO UPDATE SET razao_social=EXCLUDED.razao_social, endereco_cobranca=EXCLUDED.endereco_cobranca, "
                " email_nf=EXCLUDED.email_nf, condicao_id=EXCLUDED.condicao_id, dia_vencimento=EXCLUDED.dia_vencimento, ativo=true RETURNING id"
            ),
            args,
        )
    ).scalar()
    await db.commit()
    return int(rid)


async def regioes_sem_supervisor(db: AsyncSession) -> list[dict]:
    rows = (
        await db.execute(
            text(
                "SELECT id, nome FROM crm_regioes WHERE ativo AND (supervisor_employee_id IS NULL "
                " OR NOT EXISTS (SELECT 1 FROM employees e WHERE e.id=crm_regioes.supervisor_employee_id AND e.status='ativo'))"
            )
        )
    ).all()
    return [{"id": r[0], "nome": r[1]} for r in rows]


async def postos_por_cliente(db: AsyncSession) -> list[dict]:
    """Cliente → posto → função/escala/contratado × alocado hoje (`allocations` ativas = fonte da grade)."""
    rows = (
        await db.execute(
            text(
                "SELECT p.id::text, coalesce(c.name, '(sem cliente)'), p.name, coalesce(p.post_type,'—'), coalesce(p.shift_type,'—'), "
                " coalesce(p.required_headcount,0), "
                " (SELECT count(*) FROM allocations a WHERE a.post_id=p.id AND a.status='active' AND a.is_active), "
                " coalesce(r.nome,'—'), c.id::text "
                "FROM posts p LEFT JOIN clients c ON c.id=p.client_id LEFT JOIN crm_regioes r ON r.id=p.regiao_id "
                "WHERE coalesce(p.is_active,true) ORDER BY 2, 3"
            )
        )
    ).all()
    return [
        {
            "post_id": r[0],
            "cliente": r[1],
            "posto": r[2],
            "funcao": r[3],
            "escala": r[4],
            "contratado": int(r[5]),
            "alocado": int(r[6]),
            "regiao": r[7],
            "cliente_id": r[8],
        }
        for r in rows
    ]


# ── telas ──────────────────────────────────────────────────────────────────────────────────
def _fd(v, fmt="%d/%m/%Y %H:%M") -> str:
    try:
        return v.strftime(fmt) if v else "—"
    except Exception:  # noqa: BLE001
        return str(v or "—")


def _sn(v: bool) -> dict:
    return b("Sim", "ok") if v else b("Não", "mut")


_SN_OPT = [{"value": "1", "label": "Sim"}, {"value": "0", "label": "Não"}]


async def _opts(db, sql: str) -> list[dict]:
    try:
        return [{"value": str(r[0]), "label": str(r[1])} for r in (await db.execute(text(sql))).all()]
    except Exception:  # noqa: BLE001
        await db.rollback()
        return []


async def medicos_opts(db) -> list[dict]:
    return await _opts(
        db,
        "SELECT id, nome||' · CRM/'||uf||' '||crm FROM sst_medicos WHERE ativo ORDER BY responsavel_pcmso DESC, nome",
    )


async def tipos_opts(db) -> list[dict]:
    return await _opts(
        db, "SELECT id, nome||coalesce(' ('||codigo_esocial||')','') FROM sst_tipos_exame WHERE ativo ORDER BY nome"
    )


async def _form_aso(db, emps: list[dict]) -> dict:
    """Form de ASO com médico e exames vindos dos cadastros (substitui o texto livre)."""
    return {
        "title": "Agendar/renovar ASO",
        "sub": "Sem ASO válido o colaborador não trabalha (NR-7). Médico e exames vêm dos cadastros de SESMT "
        "(Tipos de exame / Médicos); o agendamento entra em gp_asos como hoje.",
        "cta": "Agendar",
        "type": "form",
        "submit": {"endpoint": f"{_ACT}aso-agendar", "okMsg": "ASO agendado. Recarregue."},
        "fields": [
            {
                "key": "employee_id",
                "label": "Colaborador*",
                "type": "select",
                "span": "span 2",
                "ph": "Selecione",
                "options": emps,
            },
            {
                "key": "tipo",
                "label": "Tipo*",
                "type": "select",
                "span": "span 1",
                "ph": "Selecione",
                "options": [
                    {"value": v, "label": l}
                    for v, l in (
                        ("periodico", "Periódico"),
                        ("admissional", "Admissional"),
                        ("demissional", "Demissional"),
                        ("retorno", "Retorno ao trabalho"),
                        ("mudanca_funcao", "Mudança de função"),
                    )
                ],
            },
            {"key": "data_agendamento", "label": "Data do exame*", "type": "date", "span": "span 1"},
            {
                "key": "medico_id",
                "label": "Médico",
                "type": "select",
                "span": "span 1",
                "ph": "Do cadastro",
                "options": await medicos_opts(db),
            },
            {
                "key": "tipos_exame_ids",
                "label": "Exames (ids separados por vírgula)",
                "type": "text",
                "span": "span 1",
                "ph": "ex.: 1,3 — veja a lista em Tipos de exame",
            },
            {"key": "clinica", "label": "Clínica", "type": "text", "span": "span 2"},
        ],
    }


async def ligar_aso_form(db, out: dict) -> None:
    """DP: o `renovar-aso` existente ganha selects de médico e exames (endpoint passa por aqui)."""
    try:
        await _ensure(db)
        scr = out.get("renovar-aso")
        if isinstance(scr, dict) and scr.get("type") == "form":
            emps = next((f["options"] for f in scr["fields"] if f.get("key") == "employee_id"), [])
            out["renovar-aso"] = await _form_aso(db, emps)
    except Exception:  # noqa: BLE001
        await db.rollback()


async def telas_sst(db, out: dict) -> dict:
    await _ensure(db)
    mine, safe, tbl = _helpers(db)
    hoje_txt = datetime.now().strftime("%d/%m/%Y")

    # 1) Tipos de exame ──────────────────────────────────────────────────────────────
    _campos_tipo = lambda r=None: [  # noqa: E731
        {"key": "nome", "label": "Nome*", "type": "text", "span": "span 2", **({"value": r[1]} if r else {})},
        {
            "key": "codigo_esocial",
            "label": "Código eSocial (Tabela 27)",
            "type": "text",
            "span": "span 1",
            "ph": "0295",
            **({"value": r[2] or ""} if r else {}),
        },
        {
            "key": "periodicidade_meses",
            "label": "Periodicidade (meses)*",
            "type": "number",
            "span": "span 1",
            **({"value": str(r[3])} if r else {"value": "12"}),
        },
        {
            "key": "obrigatorio_admissional",
            "label": "Admissional",
            "type": "select",
            "span": "span 1",
            "options": _SN_OPT,
            **({"value": "1" if r[4] else "0"} if r else {}),
        },
        {
            "key": "obrigatorio_periodico",
            "label": "Periódico",
            "type": "select",
            "span": "span 1",
            "options": _SN_OPT,
            **({"value": "1" if r[5] else "0"} if r else {}),
        },
        {
            "key": "obrigatorio_demissional",
            "label": "Demissional",
            "type": "select",
            "span": "span 1",
            "options": _SN_OPT,
            **({"value": "1" if r[6] else "0"} if r else {}),
        },
        {
            "key": "obrigatorio_retorno",
            "label": "Retorno ao trabalho",
            "type": "select",
            "span": "span 1",
            "options": _SN_OPT,
            **({"value": "1" if r[7] else "0"} if r else {}),
        },
        {
            "key": "obrigatorio_mudanca_funcao",
            "label": "Mudança de função",
            "type": "select",
            "span": "span 1",
            "options": _SN_OPT,
            **({"value": "1" if r[8] else "0"} if r else {}),
        },
        {
            "key": "por_funcao",
            "label": "Funções (cargos, separados por vírgula; vazio = todas)",
            "type": "text",
            "span": "span 2",
            "ph": "AGENTE DE PORTARIA, LIDER DE PORTARIA",
            **({"value": ", ".join(r[9] or [])} if r else {}),
        },
        {
            "key": "custo_ref",
            "label": "Custo de referência (R$)",
            "type": "number",
            "span": "span 1",
            **({"value": str(r[10] or "")} if r else {}),
        },
    ]
    tipos = (
        await db.execute(
            text(
                "SELECT id, nome, codigo_esocial, periodicidade_meses, obrigatorio_admissional, obrigatorio_periodico, obrigatorio_demissional, "
                "obrigatorio_retorno, obrigatorio_mudanca_funcao, por_funcao, custo_ref, ativo FROM sst_tipos_exame ORDER BY ativo DESC, nome"
            )
        )
    ).all()
    mine["tipos-exame"] = {
        "title": "Tipos de exame (PCMSO)",
        "sub": "Cadastro dos exames com código da Tabela 27 do eSocial, periodicidade e em quais funções são obrigatórios. "
        "Semente: PCMSO 05/2026 (OCR) e os exames citados nos ASOs. Códigos em branco = não verificados no PCMSO.",
        "cta": "Novo tipo de exame",
        "ctaTo": "tipo-exame-novo",
        "type": "table",
        "searchHint": "Buscar exame…",
        "grid": "2.2fr 0.7fr 0.7fr 0.6fr 0.6fr 0.6fr 1.6fr 0.6fr",
        "cols": ["Exame", "Tab. 27", "Meses", "Adm.", "Per.", "Dem.", "Funções", "Ativo"],
        "rows": [
            {
                "cells": [
                    t(r[1], 600, _ND),
                    t(r[2] or "—"),
                    t(str(r[3])),
                    _sn(r[4]),
                    _sn(r[5]),
                    _sn(r[6]),
                    t(", ".join(r[9] or []) or "todas"),
                    b("Ativo", "ok") if r[11] else b("Inativo", "mut"),
                ],
                "edit": {
                    "endpoint": f"{_ACT}tipo-exame-salvar",
                    "method": "POST",
                    "btnLabel": "Editar",
                    "submitLabel": "Salvar",
                    "okMsg": "Tipo de exame salvo. Recarregue.",
                    "fields": [
                        {"key": "id", "label": "id", "type": "text", "value": str(r[0]), "span": "span 1"},
                        *_campos_tipo(r),
                    ],
                },
                "actions": [
                    {
                        "title": f"{'Inativar' if r[11] else 'Reativar'} «{r[1]}»",
                        "endpoint": f"{_ACT}tipo-exame-salvar",
                        "method": "POST",
                        "btnLabel": "Inativar" if r[11] else "Reativar",
                        "btnStyle": "outline",
                        "submitLabel": "Confirmar",
                        "okMsg": "Feito. Recarregue.",
                        "fields": [
                            {"key": "id", "label": "id", "type": "text", "value": str(r[0]), "span": "span 1"},
                            {
                                "key": "ativo",
                                "label": "ativo",
                                "type": "text",
                                "value": "0" if r[11] else "1",
                                "span": "span 1",
                            },
                        ],
                    }
                ],
            }
            for r in tipos
        ],
    }
    mine["tipo-exame-novo"] = {
        "title": "Novo tipo de exame",
        "sub": "Código da Tabela 27 do eSocial é o que vai no S-2220.",
        "cta": "Salvar",
        "type": "form",
        "submit": {"endpoint": f"{_ACT}tipo-exame-salvar", "okMsg": "Tipo criado."},
        "fields": _campos_tipo(),
    }

    # 2) Médicos ──────────────────────────────────────────────────────────────────────
    _campos_med = lambda r=None: [  # noqa: E731
        {"key": "nome", "label": "Nome*", "type": "text", "span": "span 2", **({"value": r[1]} if r else {})},
        {"key": "crm", "label": "CRM*", "type": "text", "span": "span 1", **({"value": r[2]} if r else {})},
        {
            "key": "uf",
            "label": "UF*",
            "type": "text",
            "span": "span 1",
            "ph": "AM",
            **({"value": r[3]} if r else {"value": "AM"}),
        },
        {
            "key": "especialidade",
            "label": "Especialidade",
            "type": "text",
            "span": "span 1",
            **({"value": r[4] or ""} if r else {}),
        },
        {
            "key": "clinica",
            "label": "Clínica",
            "type": "text",
            "span": "span 1",
            **({"value": r[5] or ""} if r else {}),
        },
        {
            "key": "telefone",
            "label": "Telefone",
            "type": "text",
            "span": "span 1",
            **({"value": r[6] or ""} if r else {}),
        },
        {
            "key": "responsavel_pcmso",
            "label": "Responsável pelo PCMSO",
            "type": "select",
            "span": "span 1",
            "options": _SN_OPT,
            **({"value": "1" if r[7] else "0"} if r else {}),
        },
    ]
    meds = (
        await db.execute(
            text(
                "SELECT m.id, m.nome, m.crm, m.uf, m.especialidade, m.clinica, m.telefone, m.responsavel_pcmso, m.ativo, "
                " (SELECT count(*) FROM gp_asos a WHERE a.medico_id=m.id OR (a.crm IS NOT NULL AND a.crm ~ m.crm)) "
                "FROM sst_medicos m ORDER BY m.ativo DESC, m.responsavel_pcmso DESC, m.nome"
            )
        )
    ).all()
    mine["medicos"] = {
        "title": "Médicos",
        "sub": "Quem assina o ASO e quem coordena o PCMSO. Semente: coordenador do PCMSO e os médicos citados nos ASOs.",
        "cta": "Novo médico",
        "ctaTo": "medico-novo",
        "type": "table",
        "searchHint": "Buscar médico…",
        "grid": "1.8fr 0.9fr 1.2fr 1.2fr 0.9fr 0.7fr 0.6fr",
        "cols": ["Médico", "CRM", "Especialidade", "Clínica", "PCMSO", "ASOs", "Ativo"],
        "rows": [
            {
                "cells": [
                    t(r[1], 600, _ND),
                    t(f"CRM/{r[3]} {r[2]}"),
                    t(r[4] or "—"),
                    t(r[5] or "—"),
                    b("Coordenador", "info") if r[7] else t("—"),
                    t(str(r[9])),
                    b("Ativo", "ok") if r[8] else b("Inativo", "mut"),
                ],
                "edit": {
                    "endpoint": f"{_ACT}medico-salvar",
                    "method": "POST",
                    "btnLabel": "Editar",
                    "submitLabel": "Salvar",
                    "okMsg": "Médico salvo. Recarregue.",
                    "fields": [
                        {"key": "id", "label": "id", "type": "text", "value": str(r[0]), "span": "span 1"},
                        *_campos_med(r),
                    ],
                },
                "actions": [
                    {
                        "title": f"{'Inativar' if r[8] else 'Reativar'} «{r[1]}»",
                        "endpoint": f"{_ACT}medico-salvar",
                        "method": "POST",
                        "btnLabel": "Inativar" if r[8] else "Reativar",
                        "btnStyle": "outline",
                        "submitLabel": "Confirmar",
                        "okMsg": "Feito. Recarregue.",
                        "fields": [
                            {"key": "id", "label": "id", "type": "text", "value": str(r[0]), "span": "span 1"},
                            {
                                "key": "ativo",
                                "label": "ativo",
                                "type": "text",
                                "value": "0" if r[8] else "1",
                                "span": "span 1",
                            },
                        ],
                    }
                ],
            }
            for r in meds
        ],
    }
    mine["medico-novo"] = {
        "title": "Novo médico",
        "sub": "CRM + UF identificam o médico (não duplica).",
        "cta": "Salvar",
        "type": "form",
        "submit": {"endpoint": f"{_ACT}medico-salvar", "okMsg": "Médico cadastrado."},
        "fields": _campos_med(),
    }

    # 3) Exames por função ─────────────────────────────────────────────────────────────
    venc = await vencidos_por_funcao(db)
    linhas = []
    for r in tipos:
        if not r[11]:
            continue
        funcs = [norm(x) for x in (r[9] or [])] or sorted(venc)
        for fn in funcs:
            d = venc.get(fn)
            if not d:
                continue
            n = len(d["vencidos"])
            linhas.append(
                {
                    "cells": [
                        t(d["cargo"], 600, _ND),
                        t(r[1]),
                        t(r[2] or "—"),
                        _sn(r[4]),
                        _sn(r[5]),
                        t(str(d["ativos"])),
                        b(f"{n} vencido(s)", "bad") if n else b("em dia", "ok"),
                        t(", ".join(d["nomes"][:6]) + (" …" if n > 6 else "") if n else "—"),
                    ],
                    "filtro": d["cargo"],
                }
            )
    mine["exames-por-funcao"] = {
        "title": "Exames por função",
        "sub": f"Matriz função × exame obrigatório (PCMSO / cadastro) × quem está sem ASO válido em {hoje_txt}. "
        "Vencido = último ASO da pessoa ativa venceu ou não há ASO realizado — mesma régua da aba Exames e de «ASOs vencendo».",
        "cta": "—",
        "type": "table",
        "searchHint": "Buscar função ou exame…",
        "filterLabel": "Função",
        "grid": "1.6fr 2fr 0.6fr 0.5fr 0.5fr 0.6fr 1fr 2fr",
        "cols": ["Função", "Exame", "Tab. 27", "Adm.", "Per.", "Ativos", "Situação", "Quem"],
        "rows": linhas,
    }
    emps = await _opts(db, "SELECT id, nome FROM employees WHERE status='ativo' ORDER BY nome LIMIT 400")
    mine["aso-agendar"] = await _form_aso(db, emps)
    out.update(mine)
    return out


async def telas_crm(db, out: dict) -> dict:
    await _ensure(db)
    mine, safe, tbl = _helpers(db)
    clis = await _opts(db, "SELECT id, name FROM clients WHERE status::text='active' ORDER BY name")
    emps = await _opts(
        db, "SELECT id, nome||' · '||coalesce(cargo,'') FROM employees WHERE status='ativo' ORDER BY nome LIMIT 400"
    )
    _AREA = [{"value": a, "label": a.capitalize()} for a in AREAS]

    # 1) Assuntos ─────────────────────────────────────────────────────────────────────
    _campos_ass = lambda r=None: [  # noqa: E731
        {"key": "nome", "label": "Assunto*", "type": "text", "span": "span 2", **({"value": r[1]} if r else {})},
        {
            "key": "area",
            "label": "Área*",
            "type": "select",
            "span": "span 1",
            "options": _AREA,
            **({"value": r[2]} if r else {}),
        },
        {
            "key": "sla_horas",
            "label": "SLA (horas)*",
            "type": "number",
            "span": "span 1",
            **({"value": str(r[3])} if r else {"value": "24"}),
        },
        {
            "key": "responsavel_padrao",
            "label": "Responsável padrão",
            "type": "text",
            "span": "span 2",
            **({"value": r[4] or ""} if r else {}),
        },
    ]
    ass = (
        await db.execute(
            text(
                "SELECT s.id, s.nome, s.area, s.sla_horas, s.responsavel_padrao, s.ativo, "
                " (SELECT count(*) FROM dem_atendimentos a WHERE a.assunto_id=s.id AND a.status IN ('aberto','em_andamento')) "
                "FROM dem_assuntos s ORDER BY s.ativo DESC, s.area, s.nome"
            )
        )
    ).all()
    mine["demandas-assuntos"] = {
        "title": "Assuntos de demanda",
        "sub": "Tipo da demanda com área responsável e SLA. É o que classifica cada atendimento.",
        "cta": "Novo assunto",
        "ctaTo": "demanda-assunto-novo",
        "type": "table",
        "searchHint": "Buscar assunto…",
        "grid": "2fr 0.9fr 0.6fr 1.2fr 0.7fr 0.6fr",
        "cols": ["Assunto", "Área", "SLA", "Responsável", "Abertos", "Ativo"],
        "rows": [
            {
                "cells": [
                    t(r[1], 600, _ND),
                    t(r[2].capitalize()),
                    t(f"{r[3]}h"),
                    t(r[4] or "—"),
                    b(str(r[6]), "warn" if r[6] else "mut"),
                    b("Ativo", "ok") if r[5] else b("Inativo", "mut"),
                ],
                "edit": {
                    "endpoint": f"{_ACT}assunto-salvar",
                    "method": "POST",
                    "btnLabel": "Editar",
                    "submitLabel": "Salvar",
                    "okMsg": "Assunto salvo. Recarregue.",
                    "fields": [
                        {"key": "id", "label": "id", "type": "text", "value": str(r[0]), "span": "span 1"},
                        *_campos_ass(r),
                    ],
                },
                "actions": [
                    {
                        "title": f"{'Inativar' if r[5] else 'Reativar'} «{r[1]}»",
                        "endpoint": f"{_ACT}assunto-salvar",
                        "method": "POST",
                        "btnLabel": "Inativar" if r[5] else "Reativar",
                        "btnStyle": "outline",
                        "submitLabel": "Confirmar",
                        "okMsg": "Feito. Recarregue.",
                        "fields": [
                            {"key": "id", "label": "id", "type": "text", "value": str(r[0]), "span": "span 1"},
                            {
                                "key": "ativo",
                                "label": "ativo",
                                "type": "text",
                                "value": "0" if r[5] else "1",
                                "span": "span 1",
                            },
                        ],
                    }
                ],
            }
            for r in ass
        ],
    }
    mine["demanda-assunto-novo"] = {
        "title": "Novo assunto",
        "sub": "SLA em horas corridas a partir da abertura.",
        "cta": "Salvar",
        "type": "form",
        "submit": {"endpoint": f"{_ACT}assunto-salvar", "okMsg": "Assunto criado."},
        "fields": _campos_ass(),
    }

    # 2) Atendimentos ─────────────────────────────────────────────────────────────────
    lista = await listar_atendimentos(db)
    agora = datetime.now(UTC)
    rows = []
    for a in lista:
        aberto = a["status"] in ("aberto", "em_andamento")
        venc = aberto and sla_vencido(a["aberto_em"], a["sla_horas"], agora)
        st = (
            b("SLA vencido", "bad")
            if venc
            else b(
                {
                    "aberto": "Aberto",
                    "em_andamento": "Em andamento",
                    "resolvido": "Resolvido",
                    "cancelado": "Cancelado",
                }.get(a["status"], a["status"]),
                "warn" if aberto else "ok" if a["status"] == "resolvido" else "mut",
            )
        )
        acts = []
        if a["id"] and aberto:
            acts.append(
                {
                    "title": f"Assumir {a['numero']}",
                    "endpoint": f"{_ACT}atendimento-assumir",
                    "method": "POST",
                    "btnLabel": "Assumir",
                    "btnStyle": "outline",
                    "submitLabel": "Assumir",
                    "okMsg": "Assumido. Recarregue.",
                    "fields": [{"key": "id", "label": "id", "type": "text", "value": str(a["id"]), "span": "span 1"}],
                }
            )
            acts.append(
                {
                    "title": f"Resolver {a['numero']}",
                    "endpoint": f"{_ACT}atendimento-resolver",
                    "method": "POST",
                    "btnLabel": "Resolver",
                    "submitLabel": "Resolver",
                    "okMsg": "Resolvido. Recarregue.",
                    "fields": [
                        {"key": "id", "label": "id", "type": "text", "value": str(a["id"]), "span": "span 1"},
                        {"key": "resolucao", "label": "Resolução*", "type": "textarea", "span": "span 2"},
                        {
                            "key": "satisfacao",
                            "label": "Satisfação do solicitante (1–5)",
                            "type": "select",
                            "span": "span 1",
                            "options": [{"value": str(i), "label": str(i)} for i in range(1, 6)],
                        },
                    ],
                }
            )
        rows.append(
            {
                "cells": [
                    t(a["numero"], 600, _ND),
                    t(a["assunto"]),
                    t(a["origem"].capitalize()),
                    t(a["solicitante"][:40]),
                    t(a["descricao"][:80]),
                    t(a["atribuido_a"] or "—"),
                    t(_fd(a["aberto_em"])),
                    st,
                ],
                "filtro": "Abertos" if aberto else "Encerrados",
                "actions": acts,
            }
        )
    n_ab = sum(1 for a in lista if a["status"] in ("aberto", "em_andamento"))
    n_sla = sum(
        1
        for a in lista
        if a["status"] in ("aberto", "em_andamento") and sla_vencido(a["aberto_em"], a["sla_horas"], agora)
    )
    mine["atendimentos"] = {
        "title": "Atendimentos",
        "sub": f"{n_ab} aberto(s), {n_sla} com SLA vencido. Inclui ouvidoria (meu-espaço) e chamados do portal do cliente, "
        "lidos de onde nascem — resposta da ouvidoria continua na tela dela.",
        "cta": "Novo atendimento",
        "ctaTo": "atendimento-novo",
        "type": "table",
        "searchHint": "Buscar por número, cliente, texto…",
        "filterLabel": "Situação",
        "grid": "0.9fr 1.4fr 0.7fr 1.3fr 2fr 0.9fr 0.9fr 0.9fr",
        "cols": ["Nº", "Assunto", "Origem", "Solicitante", "Descrição", "Com", "Aberto em", "Situação"],
        "rows": rows,
    }
    mine["atendimento-novo"] = {
        "title": "Novo atendimento",
        "sub": "Quem pediu pode ser cliente, colaborador ou alguém de fora (nome/telefone). O número sai automático.",
        "cta": "Abrir",
        "type": "form",
        "submit": {"endpoint": f"{_ACT}atendimento-salvar", "okMsg": "Atendimento aberto.", "showResult": True},
        "fields": [
            {
                "key": "assunto_id",
                "label": "Assunto*",
                "type": "select",
                "span": "span 1",
                "ph": "Selecione",
                "options": [{"value": str(r[0]), "label": f"{r[1]} ({r[3]}h)"} for r in ass if r[5]],
            },
            {
                "key": "origem",
                "label": "Origem*",
                "type": "select",
                "span": "span 1",
                "options": [{"value": o, "label": o.capitalize()} for o in ORIGENS],
            },
            {"key": "cliente_id", "label": "Cliente", "type": "select", "span": "span 1", "ph": "—", "options": clis},
            {
                "key": "employee_id",
                "label": "Colaborador",
                "type": "select",
                "span": "span 1",
                "ph": "—",
                "options": emps,
            },
            {"key": "externo_nome", "label": "Externo — nome", "type": "text", "span": "span 1"},
            {"key": "externo_telefone", "label": "Externo — telefone", "type": "text", "span": "span 1"},
            {"key": "descricao", "label": "Descrição*", "type": "textarea", "span": "span 2"},
            {
                "key": "atribuido_a",
                "label": "Atribuir a",
                "type": "text",
                "span": "span 2",
                "ph": "vazio = responsável padrão do assunto",
            },
        ],
    }

    # 3) Feedbacks: NPS + satisfação dos atendimentos + insights, por cliente e mês ─────────
    agg: dict[tuple, dict] = {}

    def _k(cid, nome, dt):
        k = (cid or "—", dt.strftime("%m/%Y") if dt else "—")
        return agg.setdefault(k, {"cliente": nome or "—", "mes": k[1], "nps": [], "sat": [], "insights": 0})

    try:
        for cid, nome, dt, cl in (
            await db.execute(
                text(
                    "SELECT f.cliente_id::text, c.name, coalesce(f.resposta_em, f.created_at), f.classificacao FROM crm_followups f "
                    "LEFT JOIN clients c ON c.id=f.cliente_id WHERE f.template='nps' AND f.classificacao LIKE 'nps:%' AND f.classificacao<>'nps:?'"
                )
            )
        ).all():
            try:
                _k(cid, nome, dt)["nps"].append(int(str(cl).split(":")[1]))
            except (ValueError, IndexError):
                pass
        for a in lista:
            if a["satisfacao"] and a["resolvido_em"]:
                _k(a["cliente_id"], a["solicitante"], a["resolvido_em"])["sat"].append(int(a["satisfacao"]))
        for cid, nome, dt in (
            await db.execute(
                text(
                    "SELECT i.entity_id::text, coalesce(i.entity_name, c.name), i.created_at FROM feedback_insights i LEFT JOIN clients c ON c.id=i.entity_id"
                )
            )
        ).all():
            _k(cid, nome, dt)["insights"] += 1
    except Exception:  # noqa: BLE001
        await db.rollback()

    def _nps(ns):
        if not ns:
            return None
        return round((sum(1 for n in ns if n >= 9) - sum(1 for n in ns if n <= 6)) / len(ns) * 100)

    fb_rows = []
    for (_cid, mes), d in sorted(
        agg.items(), key=lambda kv: (kv[1]["mes"][3:] + kv[1]["mes"][:2], kv[1]["cliente"]), reverse=True
    ):
        nps = _nps(d["nps"])
        sat = round(sum(d["sat"]) / len(d["sat"]), 1) if d["sat"] else None
        fb_rows.append(
            {
                "cells": [
                    t(d["cliente"], 600, _ND),
                    t(mes),
                    t(str(len(d["nps"]))),
                    b(str(nps), "ok" if nps >= 50 else "warn" if nps >= 0 else "bad") if nps is not None else t("—"),
                    t(str(len(d["sat"]))),
                    b(f"{sat}", "ok" if sat >= 4 else "warn" if sat >= 3 else "bad") if sat else t("—"),
                    t(str(d["insights"])),
                ],
                "filtros": {"Mês": mes, "Cliente": d["cliente"]},
            }
        )
    mine["feedbacks"] = {
        "title": "Feedbacks",
        "sub": "Por cliente e mês: respostas de NPS (crm_followups), satisfação informada ao resolver atendimentos (1–5) e insights "
        "gerados (feedback_insights). Sem linha = ninguém respondeu — nunca inventado.",
        "cta": "Enviar NPS",
        "ctaTo": "nps-enviar",
        "type": "table",
        "searchHint": "Buscar cliente…",
        "grid": "2fr 0.7fr 0.7fr 0.7fr 0.8fr 0.8fr 0.7fr",
        "cols": ["Cliente", "Mês", "NPS resp.", "NPS", "Atend. avaliados", "Satisfação", "Insights"],
        "rows": fb_rows
        or [
            {
                "cells": [
                    t("Nenhum feedback registrado ainda", 500, "#64748B"),
                    t("—"),
                    t("0"),
                    t("—"),
                    t("0"),
                    t("—"),
                    t("0"),
                ]
            }
        ],
    }

    # 4) Diretórios do cliente ───────────────────────────────────────────────────────────
    def _papel(role: str | None) -> str:
        r = norm(role)
        for chave, rot in (
            ("SINDIC", "Síndico"),
            ("ZELADOR", "Zelador"),
            ("ADMINISTRADORA", "Administradora"),
            ("FINANC", "Financeiro"),
            ("EMERG", "Emergência"),
        ):
            if chave in r:
                return rot
        return role or "Contato"

    dir_rows = []
    try:
        for _cid, cli, nome, role, tel, wa, em, prim in (
            await db.execute(
                text(
                    "SELECT c.id::text, c.name, k.name, k.role, k.phone, k.whatsapp, k.email, k.is_primary FROM crm_contacts k JOIN clients c ON c.id=k.client_id "
                    "UNION ALL SELECT c.id::text, c.name, c.financial_contact_name, 'Financeiro', c.financial_contact_phone, NULL, c.financial_contact_email, false "
                    "FROM clients c WHERE c.financial_contact_name IS NOT NULL "
                    "UNION ALL SELECT c.id::text, c.name, c.technical_contact_name, 'Técnico', c.technical_contact_phone, NULL, c.technical_contact_email, false "
                    "FROM clients c WHERE c.technical_contact_name IS NOT NULL "
                    "UNION ALL SELECT c.id::text, c.name, p.emergency_contact, 'Emergência · '||p.name, p.emergency_phone, NULL, NULL, false "
                    "FROM posts p JOIN clients c ON c.id=p.client_id WHERE p.emergency_contact IS NOT NULL "
                    "ORDER BY 2, 4, 3"
                )
            )
        ).all():
            dir_rows.append(
                {
                    "cells": [
                        t(cli, 600, _ND),
                        b(_papel(role), "info" if prim else "mut"),
                        t(nome or "—"),
                        t(wa or tel or "—"),
                        t(em or "—"),
                    ],
                    "filtro": cli,
                }
            )
    except Exception:  # noqa: BLE001
        await db.rollback()
    mine["diretorios-cliente"] = {
        "title": "Diretórios do cliente",
        "sub": "Quem é quem em cada cliente: síndico, zelador, administradora, financeiro, emergência. "
        "Fonte: contatos do CRM + contatos financeiro/técnico do cadastro + emergência dos postos.",
        "cta": "Incluir contato",
        "ctaTo": "diretorio-contato-novo",
        "type": "table",
        "searchHint": "Buscar cliente, nome, telefone…",
        "filterLabel": "Cliente",
        "grid": "2fr 1fr 1.6fr 1.1fr 1.4fr",
        "cols": ["Cliente", "Papel", "Nome", "Telefone/WhatsApp", "E-mail"],
        "rows": dir_rows,
    }
    mine["diretorio-contato-novo"] = {
        "title": "Incluir contato no diretório",
        "sub": "Entra em crm_contacts (mesma porta de «Novo contato»), com o papel tipado.",
        "cta": "Salvar",
        "type": "form",
        "submit": {"endpoint": "/api/v1/crm/contacts/", "okMsg": "Contato incluído."},
        "fields": [
            {
                "key": "client_id",
                "label": "Cliente*",
                "type": "select",
                "span": "span 2",
                "ph": "Selecione",
                "options": clis,
            },
            {
                "key": "role",
                "label": "Papel*",
                "type": "select",
                "span": "span 1",
                "options": [{"value": l, "label": l} for _, l in PAPEIS],
            },
            {"key": "name", "label": "Nome*", "type": "text", "span": "span 1"},
            {"key": "phone", "label": "Telefone", "type": "text", "span": "span 1"},
            {"key": "whatsapp", "label": "WhatsApp", "type": "text", "span": "span 1"},
            {"key": "email", "label": "E-mail", "type": "text", "span": "span 2"},
        ],
    }

    # 5) Fontes pagadoras ─────────────────────────────────────────────────────────────────
    conds = await _opts(db, "SELECT id, nome FROM fin_condicoes_pagamento WHERE ativo ORDER BY id")
    _campos_fp = lambda r=None: [  # noqa: E731
        {
            "key": "cliente_id",
            "label": "Cliente (quem contrata)*",
            "type": "select",
            "span": "span 2",
            "ph": "Selecione",
            "options": clis,
            **({"value": r[1]} if r else {}),
        },
        {
            "key": "razao_social",
            "label": "Razão social de quem paga*",
            "type": "text",
            "span": "span 2",
            **({"value": r[3]} if r else {}),
        },
        {"key": "cnpj", "label": "CNPJ*", "type": "text", "span": "span 1", **({"value": r[4]} if r else {})},
        {
            "key": "email_nf",
            "label": "E-mail para NF",
            "type": "text",
            "span": "span 1",
            **({"value": r[6] or ""} if r else {}),
        },
        {
            "key": "endereco_cobranca",
            "label": "Endereço de cobrança",
            "type": "text",
            "span": "span 2",
            **({"value": r[5] or ""} if r else {}),
        },
        {
            "key": "condicao_id",
            "label": "Condição de pagamento",
            "type": "select",
            "span": "span 1",
            "ph": "—",
            "options": conds,
            **({"value": str(r[7] or "")} if r else {}),
        },
        {
            "key": "dia_vencimento",
            "label": "Dia de vencimento",
            "type": "number",
            "span": "span 1",
            **({"value": str(r[8] or "")} if r else {}),
        },
    ]
    fps = (
        await db.execute(
            text(
                "SELECT f.id, f.cliente_id::text, coalesce(c.name,'—'), f.razao_social, f.cnpj, f.endereco_cobranca, f.email_nf, f.condicao_id, f.dia_vencimento, "
                " f.ativo, (SELECT nome FROM fin_condicoes_pagamento p WHERE p.id=f.condicao_id), "
                " (SELECT count(*) FROM receivable_accounts r WHERE r.fonte_pagadora_id=f.id) "
                "FROM crm_fontes_pagadoras f LEFT JOIN clients c ON c.id=f.cliente_id ORDER BY f.ativo DESC, c.name, f.razao_social"
            )
        )
    ).all()
    mine["fontes-pagadoras"] = {
        "title": "Fontes pagadoras",
        "sub": "Quem PAGA pode ser diferente de quem CONTRATA (administradora paga pelo condomínio). "
        "Aparece como opção em «Registrar conta a receber»; a emissão de NFS-e não muda.",
        "cta": "Nova fonte pagadora",
        "ctaTo": "fonte-pagadora-nova",
        "type": "table",
        "searchHint": "Buscar cliente, razão social, CNPJ…",
        "grid": "1.8fr 1.8fr 1fr 1.2fr 0.9fr 0.5fr 0.6fr 0.6fr",
        "cols": ["Cliente", "Quem paga", "CNPJ", "E-mail NF", "Condição", "Dia", "Títulos", "Ativa"],
        "rows": [
            {
                "cells": [
                    t(r[2], 600, _ND),
                    t(r[3]),
                    t(f"{r[4][:2]}.{r[4][2:5]}.{r[4][5:8]}/{r[4][8:12]}-{r[4][12:]}"),
                    t(r[6] or "—"),
                    t(r[10] or "—"),
                    t(str(r[8] or "—")),
                    t(str(r[11])),
                    b("Ativa", "ok") if r[9] else b("Inativa", "mut"),
                ],
                "edit": {
                    "endpoint": f"{_ACT}fonte-pagadora-salvar",
                    "method": "POST",
                    "btnLabel": "Editar",
                    "submitLabel": "Salvar",
                    "okMsg": "Fonte salva. Recarregue.",
                    "fields": [
                        {"key": "id", "label": "id", "type": "text", "value": str(r[0]), "span": "span 1"},
                        *_campos_fp(r),
                    ],
                },
                "actions": [
                    {
                        "title": f"{'Inativar' if r[9] else 'Reativar'} «{r[3]}»",
                        "endpoint": f"{_ACT}fonte-pagadora-salvar",
                        "method": "POST",
                        "btnLabel": "Inativar" if r[9] else "Reativar",
                        "btnStyle": "outline",
                        "submitLabel": "Confirmar",
                        "okMsg": "Feito. Recarregue.",
                        "fields": [
                            {"key": "id", "label": "id", "type": "text", "value": str(r[0]), "span": "span 1"},
                            {
                                "key": "ativo",
                                "label": "ativo",
                                "type": "text",
                                "value": "0" if r[9] else "1",
                                "span": "span 1",
                            },
                        ],
                    }
                ],
            }
            for r in fps
        ],
    }
    mine["fonte-pagadora-nova"] = {
        "title": "Nova fonte pagadora",
        "sub": "CNPJ é validado (dígitos verificadores). Condição de pagamento vem do Financeiro.",
        "cta": "Salvar",
        "type": "form",
        "submit": {"endpoint": f"{_ACT}fonte-pagadora-salvar", "okMsg": "Fonte pagadora criada."},
        "fields": _campos_fp(),
    }

    # 6) Regiões ─────────────────────────────────────────────────────────────────────────
    _campos_reg = lambda r=None: [  # noqa: E731
        {"key": "nome", "label": "Nome*", "type": "text", "span": "span 1", **({"value": r[1]} if r else {})},
        {"key": "uf", "label": "UF*", "type": "text", "span": "span 1", **({"value": r[2]} if r else {"value": "AM"})},
        {
            "key": "municipios",
            "label": "Municípios (separados por vírgula)",
            "type": "text",
            "span": "span 2",
            **({"value": ", ".join(r[3] or [])} if r else {}),
        },
        {
            "key": "supervisor_employee_id",
            "label": "Supervisor",
            "type": "select",
            "span": "span 1",
            "ph": "—",
            "options": emps,
            **({"value": r[4] or ""} if r else {}),
        },
        {
            "key": "cor",
            "label": "Cor (hex)",
            "type": "text",
            "span": "span 1",
            "ph": "#2563EB",
            **({"value": r[6] or ""} if r else {}),
        },
    ]
    regs = (
        await db.execute(
            text(
                "SELECT r.id, r.nome, r.uf, r.municipios, r.supervisor_employee_id::text, e.nome, r.cor, r.ativo, "
                " (SELECT count(*) FROM clients c WHERE c.regiao_id=r.id), (SELECT count(*) FROM posts p WHERE p.regiao_id=r.id), "
                " (SELECT string_agg(c.name, ', ' ORDER BY c.name) FROM clients c WHERE c.regiao_id=r.id), "
                " (SELECT string_agg(p.name, ', ' ORDER BY p.name) FROM posts p WHERE p.regiao_id=r.id), e.status "
                "FROM crm_regioes r LEFT JOIN employees e ON e.id=r.supervisor_employee_id ORDER BY r.ativo DESC, r.nome"
            )
        )
    ).all()
    postos_opts = await _opts(db, "SELECT id, name FROM posts WHERE coalesce(is_active,true) ORDER BY name")
    mine["regioes"] = {
        "title": "Regiões",
        "sub": "Região com supervisor, municípios, clientes e postos vinculados. Sem supervisor ativo = acusado em vermelho.",
        "cta": "Nova região",
        "ctaTo": "regiao-nova",
        "type": "table",
        "searchHint": "Buscar região, cliente, posto…",
        "grid": "1.2fr 0.4fr 1.2fr 1.4fr 0.6fr 0.6fr 2fr",
        "cols": ["Região", "UF", "Municípios", "Supervisor", "Clientes", "Postos", "Vinculados"],
        "rows": [
            {
                "cells": [
                    t(r[1], 600, _ND),
                    t(r[2]),
                    t(", ".join(r[3] or []) or "—"),
                    t(r[5]) if r[5] and r[12] == "ativo" else b("Sem supervisor", "bad"),
                    t(str(r[8])),
                    t(str(r[9])),
                    t(("Clientes: " + r[10] if r[10] else "") + (" · Postos: " + r[11] if r[11] else "") or "—"),
                ],
                "edit": {
                    "endpoint": f"{_ACT}regiao-salvar",
                    "method": "POST",
                    "btnLabel": "Editar",
                    "submitLabel": "Salvar",
                    "okMsg": "Região salva. Recarregue.",
                    "fields": [
                        {"key": "id", "label": "id", "type": "text", "value": str(r[0]), "span": "span 1"},
                        *_campos_reg(r),
                    ],
                },
                "actions": [
                    {
                        "title": f"Vincular cliente/posto à região «{r[1]}»",
                        "endpoint": f"{_ACT}regiao-vincular",
                        "method": "POST",
                        "btnLabel": "Vincular",
                        "btnStyle": "outline",
                        "submitLabel": "Vincular",
                        "okMsg": "Vinculado. Recarregue.",
                        "fields": [
                            {
                                "key": "regiao_id",
                                "label": "regiao_id",
                                "type": "text",
                                "value": str(r[0]),
                                "span": "span 1",
                            },
                            {
                                "key": "cliente_id",
                                "label": "Cliente",
                                "type": "select",
                                "span": "span 1",
                                "ph": "—",
                                "options": clis,
                            },
                            {
                                "key": "posto_id",
                                "label": "Posto",
                                "type": "select",
                                "span": "span 1",
                                "ph": "—",
                                "options": postos_opts,
                            },
                        ],
                    }
                ],
            }
            for r in regs
        ],
    }
    mine["regiao-nova"] = {
        "title": "Nova região",
        "sub": "Depois vincule clientes e postos pela ação «Vincular» da lista.",
        "cta": "Salvar",
        "type": "form",
        "submit": {"endpoint": f"{_ACT}regiao-salvar", "okMsg": "Região criada."},
        "fields": _campos_reg(),
    }

    # 7) Postos por cliente ──────────────────────────────────────────────────────────────
    pcs = await postos_por_cliente(db)
    mine["postos-por-cliente"] = {
        "title": "Postos por cliente",
        "sub": "Cliente → postos → função/escala/efetivo contratado × alocado hoje (alocações ativas — a mesma fonte da grade do posto). "
        "Diferença em vermelho = posto descoberto; em azul = gente a mais.",
        "cta": "—",
        "type": "table",
        "searchHint": "Buscar cliente ou posto…",
        "filterLabel": "Cliente",
        "grid": "1.8fr 1.8fr 0.8fr 0.7fr 0.8fr 0.7fr 0.7fr 0.9fr",
        "cols": ["Cliente", "Posto", "Função", "Escala", "Região", "Contratado", "Alocado", "Diferença"],
        "rows": [
            {
                "cells": [
                    t(p["cliente"], 600, _ND),
                    t(p["posto"]),
                    t(p["funcao"]),
                    t(p["escala"]),
                    t(p["regiao"]),
                    t(str(p["contratado"])),
                    t(str(p["alocado"])),
                    b(f"{p['alocado'] - p['contratado']:+d}", "bad" if p["alocado"] < p["contratado"] else "info")
                    if p["alocado"] != p["contratado"]
                    else b("OK", "ok"),
                ],
                "filtro": p["cliente"],
            }
            for p in pcs
        ],
    }
    out.update(mine)
    return out


async def telas_fin(db, out: dict) -> None:
    """Financeiro: «Registrar conta a receber» ganha o select de fonte pagadora; o envio passa por aqui e grava a coluna."""
    try:
        await _ensure(db)
        scr = out.get("registrar-conta-receber")
        if not (isinstance(scr, dict) and scr.get("type") == "form") or any(
            f.get("key") == "fonte_pagadora_id" for f in scr.get("fields", [])
        ):
            return
        fps = await _opts(
            db,
            "SELECT f.id, f.razao_social||' (paga por '||coalesce(c.name,'?')||')' FROM crm_fontes_pagadoras f "
            "LEFT JOIN clients c ON c.id=f.cliente_id WHERE f.ativo ORDER BY c.name, f.razao_social",
        )
        scr["submit"]["endpoint"] = f"{_ACT}receivable-fonte"
        scr["fields"].append(
            {
                "key": "fonte_pagadora_id",
                "label": "Fonte pagadora (quem paga, se não for o cliente)",
                "type": "select",
                "span": "span 1",
                "ph": "— o próprio cliente —",
                "options": fps,
            }
        )
    except Exception:  # noqa: BLE001
        await db.rollback()


# ── ações ──────────────────────────────────────────────────────────────────────────────────
def _bool(v) -> bool:
    return str(v).strip().lower() in ("1", "true", "sim", "on")


def _lista(v) -> list[str]:
    return [x.strip() for x in re.split(r"[,;\n]+", str(v or "")) if x.strip()]


async def _toggle(db, tabela: str, payload: dict) -> dict | None:
    cid = str(payload.get("id") or "").strip()
    if cid and "ativo" in payload and "nome" not in payload and "razao_social" not in payload:
        await db.execute(
            text(f"UPDATE {tabela} SET ativo=:a WHERE id=:i"), {"a": _bool(payload["ativo"]), "i": int(cid)}
        )  # noqa: S608 — tabela fixa
        await db.commit()
        return {"ok": True, "message": "Atualizado."}
    return None


@router.post("/action/tipo-exame-salvar")
async def rd_tipo_exame_salvar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    await _ensure(db)
    if r := await _toggle(db, "sst_tipos_exame", payload):
        return r
    nome = str(payload.get("nome") or "").strip()
    if len(nome) < 3:
        raise HTTPException(status_code=400, detail="Nome do exame (mínimo 3 caracteres).")
    try:
        meses = int(payload.get("periodicidade_meses") or 12)
    except ValueError:
        raise HTTPException(status_code=400, detail="Periodicidade em meses (número).")
    if not 1 <= meses <= 60:
        raise HTTPException(status_code=400, detail="Periodicidade: 1 a 60 meses.")
    cod = re.sub(r"\D", "", str(payload.get("codigo_esocial") or "")) or None
    custo = str(payload.get("custo_ref") or "").replace(",", ".").strip()
    p = {
        "n": nome,
        "c": cod,
        "m": meses,
        "adm": _bool(payload.get("obrigatorio_admissional", "1")),
        "per": _bool(payload.get("obrigatorio_periodico", "1")),
        "dem": _bool(payload.get("obrigatorio_demissional")),
        "ret": _bool(payload.get("obrigatorio_retorno")),
        "mud": _bool(payload.get("obrigatorio_mudanca_funcao")),
        "f": json.dumps([norm(x) for x in _lista(payload.get("por_funcao"))]),
        "cu": float(custo) if custo else None,
    }
    cid = str(payload.get("id") or "").strip()
    if cid:
        await db.execute(
            text(
                "UPDATE sst_tipos_exame SET nome=:n, codigo_esocial=:c, periodicidade_meses=:m, obrigatorio_admissional=:adm, obrigatorio_periodico=:per, "
                "obrigatorio_demissional=:dem, obrigatorio_retorno=:ret, obrigatorio_mudanca_funcao=:mud, por_funcao=CAST(:f AS jsonb), custo_ref=:cu WHERE id=:i"
            ),
            {**p, "i": int(cid)},
        )
    else:
        await db.execute(
            text(
                "INSERT INTO sst_tipos_exame (nome, codigo_esocial, periodicidade_meses, obrigatorio_admissional, obrigatorio_periodico, obrigatorio_demissional, "
                "obrigatorio_retorno, obrigatorio_mudanca_funcao, por_funcao, custo_ref) VALUES (:n, :c, :m, :adm, :per, :dem, :ret, :mud, CAST(:f AS jsonb), :cu) "
                "ON CONFLICT (nome) DO UPDATE SET codigo_esocial=EXCLUDED.codigo_esocial, periodicidade_meses=EXCLUDED.periodicidade_meses, "
                "por_funcao=EXCLUDED.por_funcao, custo_ref=EXCLUDED.custo_ref, ativo=true"
            ),
            p,
        )
    await db.commit()
    return {"ok": True, "message": f"Exame «{nome}» salvo."}


@router.post("/action/medico-salvar")
async def rd_medico_salvar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    await _ensure(db)
    if r := await _toggle(db, "sst_medicos", payload):
        return r
    nome = str(payload.get("nome") or "").strip()
    crm = re.sub(r"\D", "", str(payload.get("crm") or ""))
    uf = str(payload.get("uf") or "AM").strip().upper()[:2]
    if len(nome) < 3 or not crm or len(uf) != 2:
        raise HTTPException(status_code=400, detail="Nome, CRM (números) e UF são obrigatórios.")
    p = {
        "n": nome,
        "c": crm,
        "u": uf,
        "e": payload.get("especialidade") or None,
        "cl": payload.get("clinica") or None,
        "t": payload.get("telefone") or None,
        "r": _bool(payload.get("responsavel_pcmso")),
    }
    if p["r"]:  # só um coordenador do PCMSO por vez
        await db.execute(text("UPDATE sst_medicos SET responsavel_pcmso=false WHERE responsavel_pcmso"))
    cid = str(payload.get("id") or "").strip()
    if cid:
        await db.execute(
            text(
                "UPDATE sst_medicos SET nome=:n, crm=:c, uf=:u, especialidade=:e, clinica=:cl, telefone=:t, responsavel_pcmso=:r WHERE id=:i"
            ),
            {**p, "i": int(cid)},
        )
    else:
        await db.execute(
            text(
                "INSERT INTO sst_medicos (nome, crm, uf, especialidade, clinica, telefone, responsavel_pcmso) VALUES (:n, :c, :u, :e, :cl, :t, :r) "
                "ON CONFLICT (crm, uf) DO UPDATE SET nome=EXCLUDED.nome, especialidade=EXCLUDED.especialidade, clinica=EXCLUDED.clinica, "
                "telefone=EXCLUDED.telefone, responsavel_pcmso=EXCLUDED.responsavel_pcmso, ativo=true"
            ),
            p,
        )
    await db.commit()
    return {"ok": True, "message": f"Médico «{nome}» (CRM/{uf} {crm}) salvo."}


@router.post("/action/aso-agendar")
async def rd_aso_agendar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    """Mesmo caminho do POST /sst/aso (gp_asos, status agendado) + médico/exames dos cadastros."""
    from modules.people_management.sst.controllers.sst_controller import agendar_aso
    from modules.people_management.sst.schemas.sst_schemas import ASOCreate

    await _ensure(db)
    try:
        data = ASOCreate(
            employee_id=str(payload.get("employee_id") or ""),
            tipo=str(payload.get("tipo") or ""),
            data_agendamento=payload.get("data_agendamento"),
            clinica=payload.get("clinica") or None,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"Dados do ASO: {e}")
    res = await agendar_aso(data, current_user, db)
    mid = str(payload.get("medico_id") or "").strip()
    tids = [int(x) for x in _lista(payload.get("tipos_exame_ids")) if x.isdigit()]
    med = (
        (await db.execute(text("SELECT nome, crm, uf, clinica FROM sst_medicos WHERE id=:i"), {"i": int(mid)})).first()
        if mid
        else None
    )
    exames = (
        (
            await db.execute(
                text("SELECT nome, codigo_esocial FROM sst_tipos_exame WHERE id = ANY(:ids)"), {"ids": tids}
            )
        ).all()
        if tids
        else []
    )
    await db.execute(
        text(
            "UPDATE gp_asos SET medico_id=:mid, medico=coalesce(:mn, medico), crm=coalesce(:mc, crm), clinica=coalesce(clinica, :cl), "
            "tipos_exame_ids=CAST(:t AS jsonb), exames=CASE WHEN :ex <> '[]' THEN CAST(:ex AS jsonb) ELSE exames END WHERE aso_id=:a"
        ),
        {
            "mid": int(mid) if mid else None,
            "mn": med[0] if med else None,
            "mc": f"CRM-{med[2]} {med[1]}" if med else None,
            "cl": med[3] if med else None,
            "t": json.dumps(tids),
            "a": res["aso_id"],
            "ex": json.dumps(
                [{"nome": n, "cod_procedimento": c, "fonte": "cadastro sst_tipos_exame"} for n, c in exames]
            ),
        },
    )
    await db.commit()
    return {
        "ok": True,
        "aso_id": res["aso_id"],
        "message": f"ASO agendado ({res['tipo']}) com {len(exames)} exame(s)" + (f" · {med[0]}" if med else "") + ".",
    }


@router.post("/action/assunto-salvar")
async def rd_assunto_salvar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    await _ensure(db)
    if r := await _toggle(db, "dem_assuntos", payload):
        return r
    nome = str(payload.get("nome") or "").strip()
    area = str(payload.get("area") or "").strip()
    if len(nome) < 3 or area not in AREAS:
        raise HTTPException(status_code=400, detail=f"Nome e área ({', '.join(AREAS)}) obrigatórios.")
    try:
        sla = int(payload.get("sla_horas") or 24)
    except ValueError:
        raise HTTPException(status_code=400, detail="SLA em horas (número).")
    p = {"n": nome, "a": area, "s": max(1, sla), "r": payload.get("responsavel_padrao") or None}
    cid = str(payload.get("id") or "").strip()
    if cid:
        await db.execute(
            text("UPDATE dem_assuntos SET nome=:n, area=:a, sla_horas=:s, responsavel_padrao=:r WHERE id=:i"),
            {**p, "i": int(cid)},
        )
    else:
        await db.execute(
            text(
                "INSERT INTO dem_assuntos (nome, area, sla_horas, responsavel_padrao) VALUES (:n, :a, :s, :r) "
                "ON CONFLICT (nome) DO UPDATE SET area=EXCLUDED.area, sla_horas=EXCLUDED.sla_horas, responsavel_padrao=EXCLUDED.responsavel_padrao, ativo=true"
            ),
            p,
        )
    await db.commit()
    return {"ok": True, "message": f"Assunto «{nome}» salvo (SLA {p['s']}h)."}


@router.post("/action/atendimento-salvar")
async def rd_atendimento_salvar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    await _ensure(db)
    desc = str(payload.get("descricao") or "").strip()
    origem = str(payload.get("origem") or "").strip()
    aid = str(payload.get("assunto_id") or "").strip()
    if len(desc) < 5 or origem not in ORIGENS or not aid.isdigit():
        raise HTTPException(status_code=400, detail="Assunto, origem e descrição (mín. 5 caracteres) são obrigatórios.")
    resp = (
        await db.execute(text("SELECT responsavel_padrao FROM dem_assuntos WHERE id=:i AND ativo"), {"i": int(aid)})
    ).scalar()
    rid = (
        await db.execute(
            text(
                "INSERT INTO dem_atendimentos (assunto_id, origem, cliente_id, employee_id, externo_nome, externo_telefone, descricao, atribuido_a, aberto_por) "
                "VALUES (:a, :o, CAST(:c AS uuid), CAST(:e AS uuid), :xn, :xt, :d, :at, :por) RETURNING id"
            ),
            {
                "a": int(aid),
                "o": origem,
                "c": payload.get("cliente_id") or None,
                "e": payload.get("employee_id") or None,
                "xn": payload.get("externo_nome") or None,
                "xt": payload.get("externo_telefone") or None,
                "d": desc,
                "at": (payload.get("atribuido_a") or resp or None),
                "por": getattr(current_user, "email", None),
            },
        )
    ).scalar()
    numero = f"DEM-{datetime.now().year}-{int(rid):04d}"
    await db.execute(text("UPDATE dem_atendimentos SET numero=:n WHERE id=:i"), {"n": numero, "i": rid})
    await db.commit()
    return {"ok": True, "id": rid, "numero": numero, "message": f"Atendimento {numero} aberto."}


@router.post("/action/atendimento-assumir")
async def rd_atendimento_assumir(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    await _ensure(db)
    quem = getattr(current_user, "email", None) or getattr(current_user, "nome", None) or "—"
    await db.execute(
        text(
            "UPDATE dem_atendimentos SET status='em_andamento', atribuido_a=:q WHERE id=:i AND status IN ('aberto','em_andamento')"
        ),
        {"q": quem, "i": int(payload.get("id") or 0)},
    )
    await db.commit()
    return {"ok": True, "message": f"Assumido por {quem}."}


@router.post("/action/atendimento-resolver")
async def rd_atendimento_resolver(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    await _ensure(db)
    res = str(payload.get("resolucao") or "").strip()
    if len(res) < 3:
        raise HTTPException(status_code=400, detail="Descreva a resolução.")
    sat = str(payload.get("satisfacao") or "").strip()
    await resolver_atendimento(
        db,
        int(payload.get("id") or 0),
        res,
        int(sat) if sat.isdigit() else None,
        getattr(current_user, "email", None) or "—",
    )
    return {"ok": True, "message": "Atendimento resolvido."}


@router.post("/action/fonte-pagadora-salvar")
async def rd_fonte_pagadora_salvar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    await _ensure(db)
    if r := await _toggle(db, "crm_fontes_pagadoras", payload):
        return r
    fid = await salvar_fonte_pagadora(db, payload)
    return {"ok": True, "id": fid, "message": f"Fonte pagadora «{payload.get('razao_social')}» salva."}


@router.post("/action/regiao-salvar")
async def rd_regiao_salvar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    await _ensure(db)
    if r := await _toggle(db, "crm_regioes", payload):
        return r
    nome = str(payload.get("nome") or "").strip()
    uf = str(payload.get("uf") or "AM").strip().upper()[:2]
    if len(nome) < 2 or len(uf) != 2:
        raise HTTPException(status_code=400, detail="Nome e UF obrigatórios.")
    p = {
        "n": nome,
        "u": uf,
        "m": json.dumps(_lista(payload.get("municipios"))),
        "s": payload.get("supervisor_employee_id") or None,
        "c": payload.get("cor") or None,
    }
    cid = str(payload.get("id") or "").strip()
    if cid:
        await db.execute(
            text(
                "UPDATE crm_regioes SET nome=:n, uf=:u, municipios=CAST(:m AS jsonb), supervisor_employee_id=CAST(:s AS uuid), cor=:c WHERE id=:i"
            ),
            {**p, "i": int(cid)},
        )
    else:
        await db.execute(
            text(
                "INSERT INTO crm_regioes (nome, uf, municipios, supervisor_employee_id, cor) VALUES (:n, :u, CAST(:m AS jsonb), CAST(:s AS uuid), :c) "
                "ON CONFLICT (nome) DO UPDATE SET uf=EXCLUDED.uf, municipios=EXCLUDED.municipios, supervisor_employee_id=EXCLUDED.supervisor_employee_id, "
                "cor=EXCLUDED.cor, ativo=true"
            ),
            p,
        )
    await db.commit()
    return {
        "ok": True,
        "message": f"Região «{nome}» salva" + ("" if p["s"] else " — SEM supervisor, fica acusada na lista") + ".",
    }


@router.post("/action/regiao-vincular")
async def rd_regiao_vincular(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    await _ensure(db)
    rid = int(payload.get("regiao_id") or 0)
    n = 0
    for tabela, chave in (("clients", "cliente_id"), ("posts", "posto_id")):
        v = str(payload.get(chave) or "").strip()
        if v:
            await db.execute(text(f"UPDATE {tabela} SET regiao_id=:r WHERE id=CAST(:i AS uuid)"), {"r": rid, "i": v})  # noqa: S608 — tabela fixa
            n += 1
    if not n:
        raise HTTPException(status_code=400, detail="Escolha um cliente e/ou um posto.")
    await db.commit()
    return {"ok": True, "message": f"{n} vínculo(s) gravado(s)."}


@router.post("/action/receivable-fonte")
async def rd_receivable_fonte(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    """Registrar conta a receber pelo caminho da F11 (condição → parcelas) e apontar a fonte pagadora."""
    from modules.operacional.controllers.redesign_builders._dgx_f11_financeiro import _conta_com_condicao

    await _ensure(db)
    res = await _conta_com_condicao(db, current_user, payload, "receber")
    fid = str(payload.get("fonte_pagadora_id") or "").strip()
    if fid and res.get("ids"):
        await db.execute(
            text("UPDATE receivable_accounts SET fonte_pagadora_id=:f WHERE id::text = ANY(:ids)"),
            {"f": int(fid), "ids": res["ids"]},
        )
        await db.commit()
        res["message"] += " Fonte pagadora apontada."
    return res

"""DGX F10 (24/09/2026) — Frotas: controle de saída/retorno, multas de trânsito com condutor,
trocas tipadas (óleo/pneu/correia/filtro/pastilha), locações e requisições de abastecimento/lavagem.

Estende a frente 10 (`_frente_10.py`: `frota_veiculos`, `frota_leituras`, `frota_vistorias`) — não a
substitui. As decisões da frente 10 continuam valendo, em código:
  · a frente 10 recusou apontar condutor de multa "sem posse datada". A posse datada agora existe:
    `frota_saidas` (quem saiu com o carro, quando, voltou quando). A multa SUGERE o condutor por
    essa posse (ou pela última vistoria dentro da janela) e um humano CONFIRMA — `indicado_em`;
  · o retorno grava uma leitura de KM pelo MESMO `frota_leitura` da frente 10 (hodômetro não recua);
    "Realizada" numa requisição de abastecimento grava a leitura de abastecimento pelo mesmo caminho;
  · troca é uma leitura tipada (`tipo = troca_*`, `proxima_km`, `proxima_data`) — tabela nova não;
    óleo/pneu/correia também atualizam `frota_veiculos.km_proxima_troca_*` para o painel da frente 10
    continuar dizendo a verdade;
  · `Restam` só com KM lido nos últimos `PERIODO_KM_DIAS`; fora disso "sem dado", nunca vencido
    (mesma régua do painel; a função de lá é fechada dentro de `_telas_frota`, por isso `restam()` aqui);
  · desconto em folha de multa = `employee_deductions` (tipo `outros`, valor fixo, 1 parcela) criado
    pelo MESMO `create_deduction` do DP — a multa guarda `deduction_id`;
  · locação pode gerar título em contas a pagar pelo MESMO `rd_action_payable` do redesign.

Plug: `equipamentos.py` importa `router` e `MENU` (topo) e chama `telas(db, out)` no fim do build().
DDL idempotente em `_ensure(db)`, chamada por `telas()` e por cada ação.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db

router = APIRouter()
logger = logging.getLogger(__name__)

# ANTES do import do data_controller (ciclo: data_controller → discovery → equipamentos → aqui)
MENU = [
    {"id": "frota-saidas", "label": "Frota · Saídas / retornos", "icon": "M22 2 11 13M22 2l-7 20-4-9-9-4z"},
    {"id": "frota-saida-nova", "label": "Frota · Nova saída", "icon": "M12 5v14M5 12h14"},
    {"id": "frota-multas", "label": "Frota · Multas", "icon": "M3 3v18h18"},
    {"id": "frota-multa-nova", "label": "Frota · Nova multa", "icon": "M12 5v14M5 12h14"},
    {"id": "frota-trocas", "label": "Frota · Trocas", "icon": "M3 3v18h18"},
    {"id": "frota-troca-nova", "label": "Frota · Nova troca", "icon": "M12 5v14M5 12h14"},
    {"id": "frota-locacoes", "label": "Frota · Locações", "icon": "M3 3v18h18"},
    {"id": "frota-locacao-nova", "label": "Frota · Nova locação", "icon": "M12 5v14M5 12h14"},
    {"id": "frota-requisicoes", "label": "Frota · Requisições", "icon": "M3 3v18h18"},
    {"id": "frota-requisicao-nova", "label": "Frota · Nova requisição", "icon": "M12 5v14M5 12h14"},
]

from modules.operacional.controllers.redesign_data_controller import _helpers, b, brl, doc, t  # noqa: E402

# módulo inteiro, não nomes: se `_frente_10` for importado primeiro (oráculo dele), ele ainda está
# pela metade quando o discovery chega aqui — nome resolvido na chamada nunca quebra o ciclo.
from . import _frente_10 as f10  # noqa: E402

_TZ = ZoneInfo("America/Manaus")
_ND = "#0F1B3A"
TROCAS = [
    ("troca_oleo", "Óleo", "km_proxima_troca_oleo"),
    ("troca_pneu", "Pneu", "km_proxima_troca_pneu"),
    ("troca_correia", "Correia", "km_proxima_troca_correia"),
    ("troca_filtro", "Filtro", None),
    ("troca_pastilha", "Pastilha", None),
]
_MOTIVOS = [
    ("supervisao", "Supervisão"),
    ("ronda", "Ronda"),
    ("manutencao", "Manutenção"),
    ("administrativo", "Administrativo"),
    ("outro", "Outro"),
]
_ST_MULTA = {
    "recebida": ("Recebida", "warn"),
    "indicada": ("Condutor indicado", "info"),
    "paga": ("Paga", "ok"),
    "recorrida": ("Em recurso", "info"),
    "desconto_em_folha": ("Desconto em folha", "ok"),
}
_ST_REQ = {
    "pendente": ("Pendente", "warn"),
    "aprovada": ("Aprovada", "info"),
    "realizada": ("Realizada", "ok"),
    "negada": ("Negada", "bad"),
}
# CNH primeiro (0 preenchidas em 24/09 — por isso a lista não se limita a quem tem CNH; ver relatório §7)
_SQL_MOTORISTAS = (
    "SELECT id, nome || CASE WHEN coalesce(cnh_numero,'') <> '' THEN ' · CNH ' || coalesce(cnh_categoria,'') ELSE '' END "
    "FROM employees WHERE status = 'ativo' AND coalesce(is_homologacao,false) = false "
    "ORDER BY coalesce(cnh_numero,'') = '', nome"
)


DDL = """
CREATE TABLE IF NOT EXISTS frota_saidas (
  id serial PRIMARY KEY, veiculo_id integer NOT NULL REFERENCES frota_veiculos(id),
  motorista_employee_id uuid NOT NULL, data_saida timestamptz NOT NULL DEFAULT now(),
  km_saida integer NOT NULL CHECK (km_saida >= 0), destino varchar(160),
  motivo varchar(20) NOT NULL DEFAULT 'supervisao' CHECK (motivo IN ('supervisao','ronda','manutencao','administrativo','outro')),
  data_retorno timestamptz, km_retorno integer CHECK (km_retorno IS NULL OR km_retorno >= km_saida),
  observacao text, vistoria_saida_id integer REFERENCES frota_vistorias(id), vistoria_retorno_id integer REFERENCES frota_vistorias(id),
  leitura_retorno_id integer REFERENCES frota_leituras(id), created_by varchar(120));
CREATE UNIQUE INDEX IF NOT EXISTS ux_frota_saidas_aberta ON frota_saidas (veiculo_id) WHERE data_retorno IS NULL;
CREATE INDEX IF NOT EXISTS ix_frota_saidas_veiculo ON frota_saidas (veiculo_id, data_saida);
CREATE TABLE IF NOT EXISTS frota_multas (
  id serial PRIMARY KEY, veiculo_id integer NOT NULL REFERENCES frota_veiculos(id),
  data_infracao date NOT NULL, hora time, local varchar(200), orgao varchar(80), auto_infracao varchar(40),
  codigo_infracao varchar(20), descricao text, pontos integer, valor numeric(10,2) NOT NULL CHECK (valor >= 0),
  valor_com_desconto numeric(10,2), vencimento date, condutor_sugerido_id uuid, condutor_employee_id uuid,
  indicado_em timestamptz, status varchar(20) NOT NULL DEFAULT 'recebida'
    CHECK (status IN ('recebida','indicada','paga','recorrida','desconto_em_folha')),
  desconto_folha boolean NOT NULL DEFAULT false, deduction_id uuid, paga_em timestamptz, observacao text,
  created_at timestamptz NOT NULL DEFAULT now(), created_by varchar(120));
CREATE TABLE IF NOT EXISTS frota_locacoes (
  id serial PRIMARY KEY, veiculo_id integer REFERENCES frota_veiculos(id), placa_terceiro varchar(10), modelo_terceiro varchar(80),
  locadora varchar(120) NOT NULL, contrato_num varchar(40), inicio date NOT NULL, fim date,
  valor_mensal numeric(12,2), km_franquia integer, km_excedente_valor numeric(10,2), responsavel_employee_id uuid,
  status varchar(15) NOT NULL DEFAULT 'ativa' CHECK (status IN ('ativa','encerrada')), payable_id uuid, observacao text,
  created_at timestamptz NOT NULL DEFAULT now(), created_by varchar(120));
CREATE TABLE IF NOT EXISTS frota_requisicoes (
  id serial PRIMARY KEY, veiculo_id integer NOT NULL REFERENCES frota_veiculos(id),
  tipo varchar(15) NOT NULL CHECK (tipo IN ('abastecimento','lavagem')), solicitante_employee_id uuid,
  data date NOT NULL DEFAULT current_date, km integer, litros numeric(8,2), valor numeric(10,2), posto_fornecedor varchar(120),
  status varchar(12) NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente','aprovada','realizada','negada')),
  aprovado_por varchar(120), aprovado_em timestamptz, comprovante_url varchar(500),
  leitura_id integer REFERENCES frota_leituras(id), observacao text,
  created_at timestamptz NOT NULL DEFAULT now(), created_by varchar(120));
-- dgx v3: multa vira conta a pagar e ganha ciclo de recurso
ALTER TABLE frota_multas ADD COLUMN IF NOT EXISTS payable_id uuid;
ALTER TABLE frota_multas ADD COLUMN IF NOT EXISTS cabe_recurso boolean NOT NULL DEFAULT false;
ALTER TABLE frota_multas ADD COLUMN IF NOT EXISTS recurso_lancado_em timestamptz;
ALTER TABLE frota_multas ADD COLUMN IF NOT EXISTS recurso_resultado varchar(12)
  CHECK (recurso_resultado IS NULL OR recurso_resultado IN ('pendente','deferido','parcial','indeferido'));
ALTER TABLE frota_multas ADD COLUMN IF NOT EXISTS recurso_observacao text;
ALTER TABLE frota_leituras ADD COLUMN IF NOT EXISTS proxima_km integer;
ALTER TABLE frota_leituras ADD COLUMN IF NOT EXISTS proxima_data date;
"""
_TIPOS_LEITURA = "'km','abastecimento'," + ",".join(f"'{k}'" for k, _, _ in TROCAS)


async def _ensure(db) -> None:
    for stmt in DDL.split(";"):
        if stmt.strip():
            await db.execute(text(stmt))
    # CHECK de tipo da frente 10 ganha as trocas — só quando ainda não tem (ADD CONSTRAINT revalida a tabela)
    atual = (
        await db.execute(
            text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'frota_leituras_tipo_check'")
        )
    ).scalar() or ""
    if "troca_oleo" not in atual:
        await db.execute(text("ALTER TABLE frota_leituras DROP CONSTRAINT IF EXISTS frota_leituras_tipo_check"))
        await db.execute(
            text(
                f"ALTER TABLE frota_leituras ADD CONSTRAINT frota_leituras_tipo_check CHECK (tipo IN ({_TIPOS_LEITURA}))"
            )
        )
    await db.commit()


# ----------------------------------------------------------------------------- régua
def restam(km_atual, proxima_km):
    """Mesma régua do painel da frente 10: sem KM recente → "sem dado"; vencido só com número."""
    if km_atual is None:
        return t("sem dado", "#64748B")
    if proxima_km is None:
        return t("—")
    rest = proxima_km - km_atual
    return b(f"{rest:,} km".replace(",", "."), "bad" if rest < 0 else ("warn" if rest < 500 else "ok"))


def _data(v, campo: str, obrigatorio=False):
    if v is None or str(v).strip() == "":
        if obrigatorio:
            raise HTTPException(status_code=400, detail=f"{campo}: informe a data.")
        return None
    try:
        return date.fromisoformat(str(v).strip()[:10])
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{campo}: data inválida (AAAA-MM-DD).") from None


def _hora(v):
    if not v or not str(v).strip():
        return None
    try:
        return time.fromisoformat(str(v).strip()[:5])
    except ValueError:
        raise HTTPException(status_code=400, detail="Hora inválida (HH:MM).") from None


def _uuid(v):
    return (str(v).strip() or None) if v not in (None, "") else None


def _km(v):
    return f"{v:,}".replace(",", ".") if v is not None else "—"


def _d(v):
    try:
        return v.strftime("%d/%m/%Y") if v else "—"
    except Exception:  # noqa: BLE001
        return "—"


async def _um(db, sql: str, **p):
    return (await db.execute(text(sql), p)).first()


async def _ultima_leitura_id(db, vid: int) -> int | None:
    # ponytail: `f10.frota_leitura` (frente 10) não devolve o id; a última do veículo nesta mesma sessão é a nossa
    return (await db.execute(text("SELECT max(id) FROM frota_leituras WHERE veiculo_id = :v"), {"v": vid})).scalar()


async def _sugerir_condutor(db, vid: int, quando: datetime):
    """Posse datada primeiro (`frota_saidas` cobrindo o instante); senão a última vistoria dentro da janela."""
    r = await _um(
        db,
        "SELECT motorista_employee_id FROM frota_saidas WHERE veiculo_id = :v AND data_saida <= :q "
        "AND coalesce(data_retorno, now()) >= :q ORDER BY data_saida DESC LIMIT 1",
        v=vid,
        q=quando,
    )
    if r:
        return r[0]
    r = await _um(
        db,
        "SELECT condutor_id FROM frota_vistorias WHERE veiculo_id = :v AND criado_em <= :q "
        f"AND criado_em >= :q - interval '{f10.JANELA_VISTORIA_HORAS} hours' ORDER BY criado_em DESC LIMIT 1",
        v=vid,
        q=quando,
    )
    return r[0] if r else None


def _acao(titulo, endpoint, btn, fields, ok="Feito. Recarregue.", style="outline"):
    return {
        "title": titulo,
        "endpoint": endpoint,
        "method": "POST",
        "btnLabel": btn,
        "submitLabel": btn,
        "btnStyle": style,
        "okMsg": ok,
        "fields": fields,
    }


# ----------------------------------------------------------------------------- telas
async def telas(db, out: dict | None = None) -> dict:
    from . import _dgx_v3_frota_app as v3  # noqa: PLC0415 — dgx v3: ações de conta/recurso na linha da multa

    await _ensure(db)
    _out, safe, tbl = _helpers(db)
    if out is None:
        out = {}
    veic = await f10._opts(db, f10._SQL_VEICULOS)
    motoristas = await f10._opts(db, _SQL_MOTORISTAS)
    A = "/api/v1/redesign/action/"

    # 1) saídas / retornos
    await safe(
        "frota-saidas",
        tbl(
            "Frota — saídas e retornos",
            "Abertas em destaque. Um veículo não sai de novo sem voltar. O retorno grava a leitura de KM.",
            "—",
            [
                "#",
                "Placa",
                "Motorista",
                "Saída",
                "KM saída",
                "Destino",
                "Motivo",
                "Retorno",
                "KM retorno",
                "Rodado",
                "Situação",
            ],
            "0.4fr 0.8fr 1.5fr 1fr 0.7fr 1.2fr 0.9fr 1fr 0.7fr 0.7fr 0.9fr",
            "SELECT s.id, v.placa, coalesce(e.nome,'—'), s.data_saida, s.km_saida, coalesce(s.destino,'—'), s.motivo, "
            "s.data_retorno, s.km_retorno, s.veiculo_id FROM frota_saidas s JOIN frota_veiculos v ON v.id = s.veiculo_id "
            "LEFT JOIN employees e ON e.id = s.motorista_employee_id ORDER BY (s.data_retorno IS NULL) DESC, s.data_saida DESC LIMIT 300",
            lambda r: [
                t(str(r[0]), 600, _ND),
                t(r[1], 600),
                t(r[2]),
                t(f10._dt(r[3])),
                t(_km(r[4])),
                t(r[5]),
                t(dict(_MOTIVOS).get(r[6], r[6])),
                t(f10._dt(r[7])),
                t(_km(r[8])),
                t(_km(r[8] - r[4]) if r[8] is not None else "—"),
                b("Em uso", "warn") if r[7] is None else b("Retornou", "ok"),
            ],
            actionsfn=lambda r: [
                _acao(
                    f"Registrar retorno de {r[1]} (saiu com {_km(r[4])} km)",
                    A + "frota-retorno",
                    "Registrar retorno",
                    [
                        {"key": "saida_id", "type": "hidden", "value": str(r[0])},
                        {
                            "key": "km_retorno",
                            "label": "KM do hodômetro no retorno*",
                            "type": "text",
                            "span": "span 1",
                            "value": "",
                        },
                        {"key": "observacao", "label": "Observação", "type": "text", "span": "span 2", "value": ""},
                    ],
                    "Retorno registrado. Recarregue.",
                    "primary",
                )
            ]
            if r[7] is None
            else [],
        ),
    )
    await safe(
        "frota-saida-nova",
        f10._form(
            db,
            "frota-saida-nova",
            "Nova saída de veículo",
            "Quem saiu, com que carro, KM e para quê. Veículo com saída aberta é recusado.",
            "Registrar saída",
            A + "frota-saida",
            [
                {"key": "veiculo_id", "label": "Veículo*", "type": "select", "options": veic},
                {"key": "motorista_employee_id", "label": "Motorista*", "type": "select", "options": motoristas},
                {"key": "km_saida", "label": "KM do hodômetro*", "type": "text"},
                {
                    "key": "motivo",
                    "label": "Motivo*",
                    "type": "select",
                    "options": [{"value": k, "label": v} for k, v in _MOTIVOS],
                },
                {"key": "destino", "label": "Destino", "type": "text", "span": "span 2"},
                {"key": "observacao", "label": "Observação", "type": "textarea", "span": "span 2"},
            ],
            okMsg="Saída registrada.",
        ),
    )

    # 2) multas
    def _acoes_multa(r):
        mid, status, sug_id, sug_nome, cond_id, valor = r[0], r[12], r[13], r[14], r[15], r[9]
        acts = []
        if status in ("recebida", "indicada", "recorrida"):
            acts.append(
                _acao(
                    f"Indicar condutor da multa #{mid}"
                    + (f" — sugerido: {sug_nome}" if sug_nome else " — sem posse datada"),
                    A + "frota-multa-indicar",
                    "Indicar condutor",
                    [
                        {"key": "multa_id", "type": "hidden", "value": str(mid)},
                        {
                            "key": "condutor_employee_id",
                            "label": "Condutor*",
                            "type": "select",
                            "span": "span 2",
                            "value": str(cond_id or sug_id or ""),
                            "options": motoristas,
                        },
                    ],
                    "Condutor indicado. Recarregue.",
                )
            )
        if status in ("recebida", "indicada", "recorrida"):
            acts.append(
                _acao(
                    f"Marcar multa #{mid} como paga",
                    A + "frota-multa-paga",
                    "Marcar paga",
                    [
                        {"key": "multa_id", "type": "hidden", "value": str(mid)},
                        {
                            "key": "observacao",
                            "label": "Como foi paga (opcional)",
                            "type": "text",
                            "span": "span 2",
                            "value": "",
                        },
                    ],
                    "Multa paga. Recarregue.",
                )
            )
        if status != "desconto_em_folha" and cond_id:
            acts.append(
                _acao(
                    f"Isto CRIA um desconto de {brl(float(valor or 0))} na folha do condutor indicado (multa #{mid}). Confirma?",
                    A + "frota-multa-desconto",
                    "Descontar em folha",
                    [
                        {"key": "multa_id", "type": "hidden", "value": str(mid)},
                        {
                            "key": "confirmo",
                            "label": "Confirmo o desconto*",
                            "type": "select",
                            "span": "span 2",
                            "value": "",
                            "options": [{"value": "", "label": "—"}, {"value": "sim", "label": "Sim, descontar"}],
                        },
                    ],
                    "Desconto criado na folha. Recarregue.",
                    "primary",
                )
            )
        return acts

    await safe(
        "frota-multas",
        tbl(
            "Frota — multas de trânsito",
            "Condutor sugerido por quem tinha o carro na data/hora (saída aberta ou última vistoria); um humano confirma.",
            "—",
            [
                "#",
                "Placa",
                "Infração",
                "Órgão / auto",
                "Descrição",
                "Pontos",
                "Valor",
                "Vencimento",
                "Condutor",
                "Sugerido",
                "Situação",
            ],
            "0.4fr 0.8fr 1fr 1.1fr 1.6fr 0.5fr 0.9fr 0.9fr 1.3fr 1.3fr 1fr",
            "SELECT m.id, v.placa, m.data_infracao, m.hora, coalesce(m.orgao,'—'), coalesce(m.auto_infracao,'—'), coalesce(m.descricao,'—'), "
            "m.pontos, m.vencimento, m.valor, m.valor_com_desconto, coalesce(c.nome,'—'), m.status, m.condutor_sugerido_id, s.nome, "
            "m.condutor_employee_id, m.desconto_folha, m.payable_id::text, m.cabe_recurso, m.recurso_resultado, "  # dgx v3
            "m.recurso_lancado_em FROM frota_multas m JOIN frota_veiculos v ON v.id = m.veiculo_id "
            "LEFT JOIN employees c ON c.id = m.condutor_employee_id LEFT JOIN employees s ON s.id = m.condutor_sugerido_id "
            "ORDER BY (m.status IN ('paga','desconto_em_folha')), m.vencimento NULLS LAST, m.id DESC LIMIT 300",
            lambda r: [
                t(str(r[0]), 600, _ND),
                t(r[1], 600),
                t(_d(r[2]) + (f" {r[3].strftime('%H:%M')}" if r[3] else "")),
                t(f"{r[4]} · {r[5]}"),
                t((r[6] or "—")[:60]),
                t(str(r[7]) if r[7] is not None else "—"),
                t(brl(float(r[9])) + (f" ({brl(float(r[10]))})" if r[10] else "")),
                t(_d(r[8])),
                t(r[11]),
                t(r[14] or "—"),
                b(*_ST_MULTA.get(r[12], (r[12], "mut"))),
            ],
            actionsfn=lambda r: [*_acoes_multa(r), *v3.acoes_multa(r)],  # dgx v3
            docsfn=lambda r: [doc(f"Multa #{r[0]} (PDF)", f"/api/v1/redesign/frota/multas/{r[0]}/pdf")],  # dgx v3
        ),
    )
    await safe(
        "frota-multa-nova",
        f10._form(
            db,
            "frota-multa-nova",
            "Nova multa de trânsito",
            "Campos livres (órgão, auto, código). O condutor é sugerido pela posse do veículo na data/hora.",
            "Registrar multa",
            A + "frota-multa",
            [
                {"key": "veiculo_id", "label": "Veículo*", "type": "select", "options": veic},
                {"key": "data_infracao", "label": "Data da infração*", "type": "date"},
                {"key": "hora", "label": "Hora (HH:MM)", "type": "text", "ph": "14:30"},
                {"key": "local", "label": "Local", "type": "text"},
                {"key": "orgao", "label": "Órgão autuador", "type": "text", "ph": "DETRAN-AM, MANAUSTRANS…"},
                {"key": "auto_infracao", "label": "Nº do auto", "type": "text"},
                {"key": "codigo_infracao", "label": "Código da infração", "type": "text"},
                {"key": "pontos", "label": "Pontos", "type": "text"},
                {"key": "valor", "label": "Valor (R$)*", "type": "text"},
                {"key": "valor_com_desconto", "label": "Valor com desconto (R$)", "type": "text"},
                {"key": "vencimento", "label": "Vencimento", "type": "date"},
                {"key": "descricao", "label": "Descrição", "type": "text", "span": "span 2"},
                {"key": "observacao", "label": "Observação", "type": "textarea", "span": "span 2"},
            ],
            okMsg="Multa registrada.",
            showResult=True,
        ),
    )

    # 3) trocas tipadas
    await safe(
        "frota-trocas",
        tbl(
            "Frota — trocas (óleo, pneu, correia, filtro, pastilha)",
            f"Última troca de cada tipo, KM atual (leitura nos últimos {f10.PERIODO_KM_DIAS} dias) e `Restam`; vermelho = vencido",
            "—",
            ["Placa", "Tipo", "Última troca", "KM na troca", "Próxima KM", "Restam", "Próxima data", "KM atual"],
            "0.8fr 0.8fr 1fr 0.8fr 0.8fr 0.9fr 0.9fr 0.8fr",
            "SELECT v.placa, l.tipo, l.lida_em, l.km, l.proxima_km, l.proxima_data, "
            f"(SELECT max(km) FROM frota_leituras k WHERE k.veiculo_id = v.id AND k.lida_em > now() - interval '{f10.PERIODO_KM_DIAS} days') "
            "FROM frota_veiculos v JOIN LATERAL (SELECT DISTINCT ON (tipo) tipo, lida_em, km, proxima_km, proxima_data FROM frota_leituras "
            "WHERE veiculo_id = v.id AND tipo LIKE 'troca_%' ORDER BY tipo, lida_em DESC, id DESC) l ON true "
            "WHERE v.ativo ORDER BY v.placa, l.tipo",
            lambda r: [
                t(r[0], 600, _ND),
                t({k: lab for k, lab, _ in TROCAS}.get(r[1], r[1])),
                t(f10._dt(r[2])),
                t(_km(r[3])),
                t(_km(r[4])),
                restam(r[6], r[4]),
                b(_d(r[5]), "bad") if r[5] and r[5] < date.today() else t(_d(r[5])),
                t(_km(r[6]) if r[6] is not None else "sem dado"),
            ],
        ),
    )
    await safe(
        "frota-troca-nova",
        f10._form(
            db,
            "frota-troca-nova",
            "Nova troca",
            "KM do hodômetro na troca e a próxima (KM absoluto e/ou data). Óleo/pneu/correia atualizam o painel.",
            "Registrar troca",
            A + "frota-troca",
            [
                {"key": "veiculo_id", "label": "Veículo*", "type": "select", "options": veic},
                {
                    "key": "tipo",
                    "label": "Tipo*",
                    "type": "select",
                    "options": [{"value": k, "label": lab} for k, lab, _ in TROCAS],
                },
                {"key": "km", "label": "KM do hodômetro*", "type": "text"},
                {"key": "proxima_km", "label": "Próxima troca (KM)", "type": "text"},
                {"key": "proxima_data", "label": "Próxima troca (data)", "type": "date"},
                {"key": "valor", "label": "Valor (R$)", "type": "text"},
                {"key": "condutor_id", "label": "Quem levou", "type": "select", "options": motoristas},
            ],
            okMsg="Troca registrada.",
        ),
    )

    # 4) locações
    await safe(
        "frota-locacoes",
        tbl(
            "Frota — locações",
            "Veículo da frota ou de terceiro (placa/modelo). Título mensal em contas a pagar é opcional, na criação.",
            "—",
            [
                "#",
                "Veículo",
                "Locadora",
                "Contrato",
                "Início",
                "Fim",
                "Mensal",
                "Franquia KM",
                "KM exced.",
                "Responsável",
                "Título",
                "Situação",
            ],
            "0.4fr 1.1fr 1.2fr 0.8fr 0.8fr 0.8fr 0.9fr 0.7fr 0.7fr 1.2fr 0.6fr 0.8fr",
            "SELECT l.id, coalesce(v.placa || ' · ' || coalesce(v.modelo,''), l.placa_terceiro || ' · ' || coalesce(l.modelo_terceiro,''), '—'), "
            "l.locadora, coalesce(l.contrato_num,'—'), l.inicio, l.fim, l.valor_mensal, l.km_franquia, l.km_excedente_valor, coalesce(e.nome,'—'), "
            "l.payable_id, l.status FROM frota_locacoes l LEFT JOIN frota_veiculos v ON v.id = l.veiculo_id "
            "LEFT JOIN employees e ON e.id = l.responsavel_employee_id ORDER BY (l.status = 'ativa') DESC, l.inicio DESC LIMIT 300",
            lambda r: [
                t(str(r[0]), 600, _ND),
                t(r[1], 600),
                t(r[2]),
                t(r[3]),
                t(_d(r[4])),
                t(_d(r[5])),
                t(brl(float(r[6])) if r[6] is not None else "—"),
                t(_km(r[7])),
                t(brl(float(r[8])) if r[8] is not None else "—"),
                t(r[9]),
                b("Sim", "ok") if r[10] else t("—"),
                b("Ativa", "ok") if r[11] == "ativa" else b("Encerrada", "mut"),
            ],
            actionsfn=lambda r: [
                _acao(
                    f"Encerrar locação #{r[0]} ({r[2]})",
                    A + "frota-locacao-encerrar",
                    "Encerrar",
                    [
                        {"key": "locacao_id", "type": "hidden", "value": str(r[0])},
                        {
                            "key": "fim",
                            "label": "Data de devolução*",
                            "type": "date",
                            "span": "span 1",
                            "value": date.today().isoformat(),
                        },
                    ],
                    "Locação encerrada. Recarregue.",
                )
            ]
            if r[11] == "ativa"
            else [],
        ),
    )
    await safe(
        "frota-locacao-nova",
        f10._form(
            db,
            "frota-locacao-nova",
            "Nova locação",
            "Escolha um veículo da frota OU informe placa/modelo do terceiro. «Gerar título» cria UMA conta a pagar (1ª mensalidade).",
            "Registrar locação",
            A + "frota-locacao",
            [
                {
                    "key": "veiculo_id",
                    "label": "Veículo da frota",
                    "type": "select",
                    "options": [{"value": "", "label": "— terceiro (placa abaixo) —"}] + veic,
                },
                {"key": "placa_terceiro", "label": "Placa (terceiro)", "type": "text", "ph": "ABC1D23"},
                {"key": "modelo_terceiro", "label": "Modelo (terceiro)", "type": "text"},
                {"key": "locadora", "label": "Locadora*", "type": "text"},
                {"key": "contrato_num", "label": "Nº do contrato", "type": "text"},
                {"key": "inicio", "label": "Início*", "type": "date"},
                {"key": "fim", "label": "Fim previsto", "type": "date"},
                {"key": "valor_mensal", "label": "Valor mensal (R$)", "type": "text"},
                {"key": "km_franquia", "label": "Franquia (KM/mês)", "type": "text"},
                {"key": "km_excedente_valor", "label": "KM excedente (R$/km)", "type": "text"},
                {"key": "responsavel_employee_id", "label": "Responsável", "type": "select", "options": motoristas},
                {
                    "key": "gerar_titulo",
                    "label": "Gerar título em contas a pagar?",
                    "type": "select",
                    "options": [{"value": "nao", "label": "Não"}, {"value": "sim", "label": "Sim — 1ª mensalidade"}],
                },
                {"key": "vencimento_titulo", "label": "Vencimento do título", "type": "date"},
                {"key": "observacao", "label": "Observação", "type": "textarea", "span": "span 2"},
            ],
            okMsg="Locação registrada.",
            confirm="Se marcou «Gerar título», isto CRIA uma conta a pagar (não paga). Confirma?",
            showResult=True,
        ),
    )

    # 5) requisições
    def _acoes_req(r):
        rid, tipo, status = r[0], r[2], r[10]
        acts = []
        if status == "pendente":
            acts.append(
                _acao(
                    f"Aprovar requisição #{rid}",
                    A + "frota-requisicao-status",
                    "Aprovar",
                    [
                        {"key": "requisicao_id", "type": "hidden", "value": str(rid)},
                        {"key": "status", "type": "hidden", "value": "aprovada"},
                    ],
                    "Aprovada. Recarregue.",
                )
            )
            acts.append(
                _acao(
                    f"Negar requisição #{rid}",
                    A + "frota-requisicao-status",
                    "Negar",
                    [
                        {"key": "requisicao_id", "type": "hidden", "value": str(rid)},
                        {"key": "status", "type": "hidden", "value": "negada"},
                        {"key": "observacao", "label": "Motivo", "type": "text", "span": "span 2", "value": ""},
                    ],
                    "Negada. Recarregue.",
                )
            )
        if status in ("pendente", "aprovada"):
            campos = [
                {"key": "requisicao_id", "type": "hidden", "value": str(rid)},
                {"key": "status", "type": "hidden", "value": "realizada"},
            ]
            if tipo == "abastecimento":
                campos += [
                    {
                        "key": "km",
                        "label": "KM do hodômetro*",
                        "type": "text",
                        "span": "span 1",
                        "value": str(r[5] or ""),
                    },
                    {"key": "litros", "label": "Litros*", "type": "text", "span": "span 1", "value": str(r[6] or "")},
                    {
                        "key": "valor",
                        "label": "Valor total (R$)*",
                        "type": "text",
                        "span": "span 1",
                        "value": str(r[7] or ""),
                    },
                ]
            else:
                campos += [
                    {"key": "valor", "label": "Valor (R$)", "type": "text", "span": "span 1", "value": str(r[7] or "")}
                ]
            campos.append(
                {"key": "comprovante_url", "label": "Comprovante (link)", "type": "text", "span": "span 2", "value": ""}
            )
            acts.append(
                _acao(
                    f"Marcar #{rid} como realizada" + (" — grava o abastecimento" if tipo == "abastecimento" else ""),
                    A + "frota-requisicao-status",
                    "Realizada",
                    campos,
                    "Realizada. Recarregue.",
                    "primary",
                )
            )
        return acts

    await safe(
        "frota-requisicoes",
        tbl(
            "Frota — requisições de abastecimento e lavagem",
            "Pendente → aprovada/negada → realizada. Abastecimento realizado vira leitura (R$/L e km/l no painel da frente 10).",
            "—",
            [
                "#",
                "Placa",
                "Tipo",
                "Solicitante",
                "Data",
                "KM",
                "Litros",
                "Valor",
                "Posto / fornecedor",
                "Aprovação",
                "Situação",
            ],
            "0.4fr 0.8fr 0.9fr 1.4fr 0.8fr 0.7fr 0.6fr 0.8fr 1.2fr 1.2fr 0.9fr",
            "SELECT r.id, v.placa, r.tipo, coalesce(e.nome,'—'), r.data, r.km, r.litros, r.valor, coalesce(r.posto_fornecedor,'—'), "
            "coalesce(r.aprovado_por,''), r.status, r.aprovado_em FROM frota_requisicoes r JOIN frota_veiculos v ON v.id = r.veiculo_id "
            "LEFT JOIN employees e ON e.id = r.solicitante_employee_id ORDER BY (r.status = 'pendente') DESC, r.data DESC, r.id DESC LIMIT 300",
            lambda r: [
                t(str(r[0]), 600, _ND),
                t(r[1], 600),
                t("Abastecimento" if r[2] == "abastecimento" else "Lavagem"),
                t(r[3]),
                t(_d(r[4])),
                t(_km(r[5])),
                t(f"{float(r[6]):.1f}" if r[6] is not None else "—"),
                t(brl(float(r[7])) if r[7] is not None else "—"),
                t(r[8]),
                t(f"{r[9]} · {f10._dt(r[11])}" if r[9] else "—"),
                b(*_ST_REQ.get(r[10], (r[10], "mut"))),
            ],
            actionsfn=_acoes_req,
        ),
    )
    await safe(
        "frota-requisicao-nova",
        f10._form(
            db,
            "frota-requisicao-nova",
            "Nova requisição",
            "Abastecimento ou lavagem. Litros e valor podem vir depois, ao marcar como realizada.",
            "Solicitar",
            A + "frota-requisicao",
            [
                {"key": "veiculo_id", "label": "Veículo*", "type": "select", "options": veic},
                {
                    "key": "tipo",
                    "label": "Tipo*",
                    "type": "select",
                    "options": [
                        {"value": "abastecimento", "label": "Abastecimento"},
                        {"value": "lavagem", "label": "Lavagem"},
                    ],
                },
                {"key": "solicitante_employee_id", "label": "Solicitante", "type": "select", "options": motoristas},
                {"key": "data", "label": "Data", "type": "date"},
                {"key": "km", "label": "KM do hodômetro", "type": "text"},
                {"key": "litros", "label": "Litros (previstos)", "type": "text"},
                {"key": "valor", "label": "Valor (R$, previsto)", "type": "text"},
                {"key": "posto_fornecedor", "label": "Posto / fornecedor", "type": "text"},
                {"key": "observacao", "label": "Observação", "type": "textarea", "span": "span 2"},
            ],
            okMsg="Requisição registrada.",
        ),
    )
    out.update(_out)
    return out


# ----------------------------------------------------------------------------- ações: saída / retorno
@router.post("/action/frota-saida")
async def frota_saida(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    await _ensure(db)
    vid, km = f10._int(payload.get("veiculo_id"), "Veículo"), f10._int(payload.get("km_saida"), "KM")
    mot = _uuid(payload.get("motorista_employee_id"))
    motivo = payload.get("motivo") or "supervisao"
    if not vid or km is None or not mot or motivo not in dict(_MOTIVOS):
        raise HTTPException(status_code=400, detail="Veículo, motorista, KM e motivo são obrigatórios.")
    if await _um(db, "SELECT 1 FROM frota_saidas WHERE veiculo_id = :v AND data_retorno IS NULL", v=vid):
        raise HTTPException(status_code=409, detail="Este veículo tem uma saída aberta. Registre o retorno antes.")
    from . import _dgx_v3_frota_app as v3  # noqa: PLC0415 — dgx v3

    item = await v3.bloqueio_locomocao(db, vid)
    if item:
        raise HTTPException(
            status_code=409,
            detail=f"Veículo BLOQUEADO: a última vistoria reprovou «{item}», item que impede locomoção. "
            "Registre uma vistoria nova com o item aprovado antes de liberar a saída.",
        )
    ultimo = (await db.execute(text("SELECT max(km) FROM frota_leituras WHERE veiculo_id = :v"), {"v": vid})).scalar()
    if ultimo is not None and km < ultimo:
        raise HTTPException(
            status_code=409, detail=f"KM {km} menor que a última leitura ({ultimo}). Hodômetro não anda para trás."
        )
    try:
        row = await _um(
            db,
            "INSERT INTO frota_saidas (veiculo_id, motorista_employee_id, km_saida, destino, motivo, observacao, created_by) "
            "VALUES (:v, CAST(:m AS uuid), :k, :d, :mo, :o, :u) RETURNING id",
            v=vid,
            m=mot,
            k=km,
            d=(payload.get("destino") or "").strip() or None,
            mo=motivo,
            o=(payload.get("observacao") or "").strip() or None,
            u=f10._quem(current_user),
        )
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Este veículo tem uma saída aberta (trava do banco).") from None
    await db.commit()
    return {"ok": True, "id": row[0], "message": f"Saída #{row[0]} registrada com {km} km."}


@router.post("/action/frota-retorno")
async def frota_retorno(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    await _ensure(db)
    sid, km = f10._int(payload.get("saida_id"), "Saída"), f10._int(payload.get("km_retorno"), "KM")
    if not sid or km is None:
        raise HTTPException(status_code=400, detail="Saída e KM de retorno são obrigatórios.")
    s = await _um(
        db,
        "SELECT veiculo_id, km_saida, motorista_employee_id::text, data_retorno FROM frota_saidas WHERE id = :s",
        s=sid,
    )
    if not s:
        raise HTTPException(status_code=404, detail="Saída não encontrada.")
    if s[3] is not None:
        raise HTTPException(status_code=409, detail="Esta saída já tem retorno.")
    if km < s[1]:
        raise HTTPException(status_code=409, detail=f"KM de retorno {km} menor que o de saída ({s[1]}).")
    # leitura de KM pelo MESMO caminho da frente 10 (valida hodômetro, commita)
    await f10.frota_leitura(current_user, {"veiculo_id": s[0], "tipo": "km", "km": km, "condutor_id": s[2]}, db)
    await db.execute(
        text(
            "UPDATE frota_saidas SET data_retorno = now(), km_retorno = :k, leitura_retorno_id = :l, "
            "observacao = coalesce(:o, observacao) WHERE id = :s"
        ),
        {
            "k": km,
            "l": await _ultima_leitura_id(db, s[0]),
            "o": (payload.get("observacao") or "").strip() or None,
            "s": sid,
        },
    )
    await db.commit()
    return {"ok": True, "message": f"Retorno registrado: {km - s[1]} km rodados."}


# ----------------------------------------------------------------------------- ações: multas
@router.post("/action/frota-multa")
async def frota_multa(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    await _ensure(db)
    vid, valor = f10._int(payload.get("veiculo_id"), "Veículo"), f10._dec(payload.get("valor"), "Valor")
    dia, hora = _data(payload.get("data_infracao"), "Data da infração", True), _hora(payload.get("hora"))
    if not vid or valor is None:
        raise HTTPException(status_code=400, detail="Veículo, data e valor são obrigatórios.")
    quando = datetime.combine(dia, hora or time(12, 0), tzinfo=_TZ)
    sug = await _sugerir_condutor(db, vid, quando)
    row = await _um(
        db,
        "INSERT INTO frota_multas (veiculo_id, data_infracao, hora, local, orgao, auto_infracao, codigo_infracao, descricao, pontos, "
        "valor, valor_com_desconto, vencimento, condutor_sugerido_id, observacao, created_by) VALUES (:v, :d, :h, :l, :org, :auto, :cod, "
        ":desc, :p, :val, :vd, :venc, CAST(:sug AS uuid), :o, :u) RETURNING id",
        v=vid,
        d=dia,
        h=hora,
        l=(payload.get("local") or "").strip() or None,
        org=(payload.get("orgao") or "").strip() or None,
        auto=(payload.get("auto_infracao") or "").strip() or None,
        cod=(payload.get("codigo_infracao") or "").strip() or None,
        desc=(payload.get("descricao") or "").strip() or None,
        p=f10._int(payload.get("pontos"), "Pontos"),
        val=valor,
        vd=f10._dec(payload.get("valor_com_desconto"), "Valor com desconto"),
        venc=_data(payload.get("vencimento"), "Vencimento"),
        sug=str(sug) if sug else None,
        o=(payload.get("observacao") or "").strip() or None,
        u=f10._quem(current_user),
    )
    await db.commit()
    nome = (await _um(db, "SELECT nome FROM employees WHERE id = CAST(:e AS uuid)", e=str(sug)))[0] if sug else None
    return {
        "ok": True,
        "id": row[0],
        "message": f"Multa #{row[0]} registrada. "
        + (
            f"Condutor sugerido: {nome} — confirme em «Indicar condutor»."
            if nome
            else "Sem posse datada do veículo nessa data/hora: indique o condutor manualmente."
        ),
    }


@router.post("/action/frota-multa-indicar")
async def frota_multa_indicar(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    await _ensure(db)
    mid, cond = f10._int(payload.get("multa_id"), "Multa"), _uuid(payload.get("condutor_employee_id"))
    if not mid or not cond:
        raise HTTPException(status_code=400, detail="Multa e condutor são obrigatórios.")
    if not await _um(db, "SELECT 1 FROM employees WHERE id = CAST(:e AS uuid)", e=cond):
        raise HTTPException(status_code=404, detail="Condutor não encontrado.")
    r = await db.execute(
        text(
            "UPDATE frota_multas SET condutor_employee_id = CAST(:c AS uuid), indicado_em = now(), "
            "status = CASE WHEN status = 'recebida' THEN 'indicada' ELSE status END WHERE id = :m AND status <> 'desconto_em_folha'"
        ),
        {"c": cond, "m": mid},
    )
    if not r.rowcount:
        raise HTTPException(status_code=409, detail="Multa não encontrada ou já descontada em folha.")
    await db.commit()
    return {"ok": True, "message": "Condutor indicado."}


@router.post("/action/frota-multa-paga")
async def frota_multa_paga(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    await _ensure(db)
    mid = f10._int(payload.get("multa_id"), "Multa")
    r = await db.execute(
        text(
            "UPDATE frota_multas SET status = 'paga', paga_em = now(), observacao = coalesce(:o, observacao) WHERE id = :m AND status NOT IN ('paga','desconto_em_folha')"
        ),
        {"m": mid, "o": (payload.get("observacao") or "").strip() or None},
    )
    if not r.rowcount:
        raise HTTPException(status_code=409, detail="Multa não encontrada ou já paga/descontada.")
    await db.commit()
    return {"ok": True, "message": "Multa marcada como paga."}


@router.post("/action/frota-multa-desconto")
async def frota_multa_desconto(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    """Cria o desconto na folha pelo MESMO `create_deduction` do DP (tipo `outros`, fixo, 1 parcela)."""
    from modules.people_management.hr.controllers.employee_controller import (  # noqa: PLC0415
        DeductionCreate,
        create_deduction,
    )

    await _ensure(db)
    mid = f10._int(payload.get("multa_id"), "Multa")
    if (payload.get("confirmo") or "").strip().lower() != "sim":
        raise HTTPException(status_code=400, detail="Confirme o desconto escolhendo «Sim, descontar».")
    m = await _um(
        db,
        "SELECT condutor_employee_id::text, valor, auto_infracao, data_infracao, deduction_id FROM frota_multas WHERE id = :m",
        m=mid,
    )
    if not m:
        raise HTTPException(status_code=404, detail="Multa não encontrada.")
    if m[4]:
        raise HTTPException(status_code=409, detail="Esta multa já foi descontada em folha.")
    if not m[0]:
        raise HTTPException(status_code=409, detail="Indique o condutor antes de descontar em folha.")
    dados = DeductionCreate(
        tipo="outros",
        descricao=f"Multa de trânsito #{mid}" + (f" — auto {m[2]}" if m[2] else "") + f" ({_d(m[3])})",
        valor=float(m[1]),
        base_calculo="fixo",
        total_parcelas=1,
        data_inicio=date.today().isoformat(),
    )
    ded = await create_deduction(m[0], dados, current_user, db)  # commita
    await db.execute(
        text(
            "UPDATE frota_multas SET desconto_folha = true, deduction_id = CAST(:d AS uuid), status = 'desconto_em_folha' WHERE id = :m"
        ),
        {"d": ded["id"], "m": mid},
    )
    await db.commit()
    return {
        "ok": True,
        "message": f"Desconto de {brl(float(m[1]))} criado na folha do condutor (employee_deductions {ded['id'][:8]}…).",
    }


# ----------------------------------------------------------------------------- ações: trocas
@router.post("/action/frota-troca")
async def frota_troca(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    await _ensure(db)
    vid, km, tipo = (
        f10._int(payload.get("veiculo_id"), "Veículo"),
        f10._int(payload.get("km"), "KM"),
        payload.get("tipo") or "",
    )
    col = {k: c for k, _, c in TROCAS}
    if not vid or km is None or tipo not in col:
        raise HTTPException(status_code=400, detail="Veículo, tipo de troca e KM são obrigatórios.")
    prox_km, prox_data = (
        f10._int(payload.get("proxima_km"), "Próxima KM"),
        _data(payload.get("proxima_data"), "Próxima data"),
    )
    if prox_km is not None and prox_km <= km:
        raise HTTPException(status_code=400, detail="A próxima troca (KM) tem de ser maior que o KM atual.")
    ultimo = (await db.execute(text("SELECT max(km) FROM frota_leituras WHERE veiculo_id = :v"), {"v": vid})).scalar()
    if ultimo is not None and km < ultimo:
        raise HTTPException(
            status_code=409, detail=f"KM {km} menor que a última leitura ({ultimo}). Hodômetro não anda para trás."
        )
    if not await _um(db, "SELECT 1 FROM frota_veiculos WHERE id = :v AND ativo", v=vid):
        raise HTTPException(status_code=404, detail="Veículo não encontrado.")
    await db.execute(
        text(
            "INSERT INTO frota_leituras (veiculo_id, tipo, km, valor, condutor_id, proxima_km, proxima_data, created_by) "
            "VALUES (:v, :t, :k, :va, CAST(:c AS uuid), :pk, :pd, :u)"
        ),
        {
            "v": vid,
            "t": tipo,
            "k": km,
            "va": f10._dec(payload.get("valor"), "Valor"),
            "c": _uuid(payload.get("condutor_id")),
            "pk": prox_km,
            "pd": prox_data,
            "u": f10._quem(current_user),
        },
    )
    if col[tipo]:  # painel da frente 10 lê a coluna do veículo
        await db.execute(text(f"UPDATE frota_veiculos SET {col[tipo]} = :pk WHERE id = :v"), {"pk": prox_km, "v": vid})  # noqa: S608 — coluna fixa
    await db.commit()
    return {"ok": True, "message": f"Troca de {({k: lab for k, lab, _ in TROCAS})[tipo].lower()} registrada a {km} km."}


# ----------------------------------------------------------------------------- ações: locações
@router.post("/action/frota-locacao")
async def frota_locacao(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    await _ensure(db)
    vid = f10._int(payload.get("veiculo_id"), "Veículo")
    placa = (payload.get("placa_terceiro") or "").strip().upper() or None
    locadora, inicio = (payload.get("locadora") or "").strip(), _data(payload.get("inicio"), "Início", True)
    if not locadora or not (vid or placa):
        raise HTTPException(
            status_code=400, detail="Locadora, início e um veículo (da frota ou placa do terceiro) são obrigatórios."
        )
    mensal = f10._dec(payload.get("valor_mensal"), "Valor mensal")
    gerar = (payload.get("gerar_titulo") or "nao") == "sim"
    payable_id = None
    if gerar:
        if not mensal:
            raise HTTPException(status_code=400, detail="Para gerar título informe o valor mensal.")
        from modules.operacional.controllers.redesign_data_controller import rd_action_payable  # noqa: PLC0415

        venc = _data(payload.get("vencimento_titulo"), "Vencimento do título") or inicio
        r = await rd_action_payable(
            current_user,
            {
                "description": f"Locação de veículo — {locadora} — {placa or f'frota #{vid}'} — {venc.strftime('%m/%Y')}",
                "valor": f"{mensal:.2f}",
                "due_date": venc.isoformat(),
                "supplier_name": locadora,
                "notes": f"Contrato {payload.get('contrato_num') or '—'}; 1ª mensalidade gerada pela tela Frota · Locações",
            },
            db,
        )
        payable_id = r.get("id")
    row = await _um(
        db,
        "INSERT INTO frota_locacoes (veiculo_id, placa_terceiro, modelo_terceiro, locadora, contrato_num, inicio, fim, valor_mensal, km_franquia, "
        "km_excedente_valor, responsavel_employee_id, payable_id, observacao, created_by) VALUES (:v, :p, :mo, :l, :c, :i, :f, :vm, :kf, :ke, "
        "CAST(:r AS uuid), CAST(:pay AS uuid), :o, :u) RETURNING id",
        v=vid,
        p=placa,
        mo=(payload.get("modelo_terceiro") or "").strip() or None,
        l=locadora,
        c=(payload.get("contrato_num") or "").strip() or None,
        i=inicio,
        f=_data(payload.get("fim"), "Fim"),
        vm=mensal,
        kf=f10._int(payload.get("km_franquia"), "Franquia"),
        ke=f10._dec(payload.get("km_excedente_valor"), "KM excedente"),
        r=_uuid(payload.get("responsavel_employee_id")),
        pay=payable_id,
        o=(payload.get("observacao") or "").strip() or None,
        u=f10._quem(current_user),
    )
    await db.commit()
    return {
        "ok": True,
        "id": row[0],
        "message": f"Locação #{row[0]} registrada."
        + (f" Título {payable_id[:8]}… criado em contas a pagar (não pago)." if payable_id else ""),
    }


@router.post("/action/frota-locacao-encerrar")
async def frota_locacao_encerrar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)
) -> dict:
    await _ensure(db)
    lid, fim = f10._int(payload.get("locacao_id"), "Locação"), _data(payload.get("fim"), "Devolução", True)
    r = await db.execute(
        text("UPDATE frota_locacoes SET status = 'encerrada', fim = :f WHERE id = :l AND status = 'ativa'"),
        {"f": fim, "l": lid},
    )
    if not r.rowcount:
        raise HTTPException(status_code=409, detail="Locação não encontrada ou já encerrada.")
    await db.commit()
    return {"ok": True, "message": "Locação encerrada."}


# ----------------------------------------------------------------------------- ações: requisições
@router.post("/action/frota-requisicao")
async def frota_requisicao(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    await _ensure(db)
    vid, tipo = f10._int(payload.get("veiculo_id"), "Veículo"), payload.get("tipo") or ""
    if not vid or tipo not in ("abastecimento", "lavagem"):
        raise HTTPException(status_code=400, detail="Veículo e tipo são obrigatórios.")
    row = await _um(
        db,
        "INSERT INTO frota_requisicoes (veiculo_id, tipo, solicitante_employee_id, data, km, litros, valor, posto_fornecedor, observacao, created_by) "
        "VALUES (:v, :t, CAST(:s AS uuid), coalesce(:d, current_date), :k, :l, :va, :p, :o, :u) RETURNING id",
        v=vid,
        t=tipo,
        s=_uuid(payload.get("solicitante_employee_id")),
        d=_data(payload.get("data"), "Data"),
        k=f10._int(payload.get("km"), "KM"),
        l=f10._dec(payload.get("litros"), "Litros"),
        va=f10._dec(payload.get("valor"), "Valor"),
        p=(payload.get("posto_fornecedor") or "").strip() or None,
        o=(payload.get("observacao") or "").strip() or None,
        u=f10._quem(current_user),
    )
    await db.commit()
    return {"ok": True, "id": row[0], "message": f"Requisição #{row[0]} registrada (pendente)."}


@router.post("/action/frota-requisicao-status")
async def frota_requisicao_status(
    current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)
) -> dict:
    await _ensure(db)
    rid, novo = f10._int(payload.get("requisicao_id"), "Requisição"), payload.get("status") or ""
    if not rid or novo not in ("aprovada", "negada", "realizada"):
        raise HTTPException(status_code=400, detail="Requisição e status (aprovada|negada|realizada) são obrigatórios.")
    r = await _um(
        db, "SELECT veiculo_id, tipo, status, solicitante_employee_id::text FROM frota_requisicoes WHERE id = :r", r=rid
    )
    if not r:
        raise HTTPException(status_code=404, detail="Requisição não encontrada.")
    permitido = {"aprovada": ("pendente",), "negada": ("pendente",), "realizada": ("pendente", "aprovada")}
    if r[2] not in permitido[novo]:
        raise HTTPException(status_code=409, detail=f"Requisição está '{r[2]}'; não pode ir para '{novo}'.")
    quem, obs = f10._quem(current_user), (payload.get("observacao") or "").strip() or None
    leitura_id = None
    km, litros, valor = (
        f10._int(payload.get("km"), "KM"),
        f10._dec(payload.get("litros"), "Litros"),
        f10._dec(payload.get("valor"), "Valor"),
    )
    if novo == "realizada" and r[1] == "abastecimento":
        if km is None or not litros or not valor:
            raise HTTPException(status_code=400, detail="Abastecimento realizado pede KM, litros e valor.")
        # MESMO insert da frente 10 (R$/L e km/l no painel saem daí); valida o hodômetro e commita
        await f10.frota_leitura(
            current_user,
            {
                "veiculo_id": r[0],
                "tipo": "abastecimento",
                "km": km,
                "litros": litros,
                "valor": valor,
                "condutor_id": r[3],
            },
            db,
        )
        leitura_id = await _ultima_leitura_id(db, r[0])
    await db.execute(
        text(
            "UPDATE frota_requisicoes SET status = :s, aprovado_por = :q, aprovado_em = now(), km = coalesce(:k, km), litros = coalesce(:l, litros), "
            "valor = coalesce(:va, valor), comprovante_url = coalesce(:c, comprovante_url), leitura_id = coalesce(:lid, leitura_id), "
            "observacao = coalesce(:o, observacao) WHERE id = :r"
        ),
        {
            "s": novo,
            "q": quem,
            "k": km,
            "l": litros,
            "va": valor,
            "c": (payload.get("comprovante_url") or "").strip() or None,
            "lid": leitura_id,
            "o": obs,
            "r": rid,
        },
    )
    await db.commit()
    return {
        "ok": True,
        "message": f"Requisição #{rid}: {novo}."
        + (f" Abastecimento gravado (leitura #{leitura_id})." if leitura_id else ""),
    }

"""DGX F9 (24/09/2026) — Suprimentos: solicitação → pedido de compra → NF de entrada; materiais com
mínimo/máximo e movimentação; fornecedores; comunicações móveis e rastreadores como equipamento
controlado; kit de uniforme por função.

O que existia e QUEM escreve (medido no sandbox, 24/09 — detalhe em auditoria/frentes/DGX_F9_suprimentos.md):
  · `nfe_compras_estoque` (147) — escrita pelo sync SEFAZ (`nfe_entrada_sync_service.processar_xml_nfe`:
    entrada com custo médio ponderado) e por `estoque_real_service.registrar_saida` (baixa + COGS no razão).
    É o estoque VIVO. Ganha mínimo/máximo/grupo/ativo/origem por ADD COLUMN — não nasce tabela paralela.
  · `nfe_estoque_movimentos` (1) — só saídas eram registradas. Entradas passam a ser registradas aqui,
    com `ref_chave` (chave da NF-e ou nº do pedido) e índice único → uma NF entra UMA vez.
  · `fin_stock_items` (2, 12/04) / `inventory_items` (2) — semente sem escritor. Não migradas (§7).
  · `purchase_requisitions/_items`, `purchase_orders/_items`, `goods_receipts` (0) — models e repositório
    sem controller nem rota. Reusadas como estão (ADD COLUMN só do que faltou: posto, item_code, condição).
  · `suppliers` (60) — criados a partir das notas reais (`fornecedor_categoria_service`, `payable_auto_service`).
    `financial_fornecedores` (12) é padrão de casamento do extrato (`inter_sync_service`), não cadastro.
  · `equipamentos_controlados` (frente 05) — CHECK de tipo ganha radio|celular|rastreador; posse continua
    sendo a alocação aberta (índice único parcial `ux_equip_aloc_aberta`); entregar/devolver são os da frente 05.
  · `sst_uniforme_grade` (frente 10) não tem noção de kit → `sst_uniforme_kits` (função × SKU × quantidade);
    a entrega do kit chama o MESMO `uniforme_entrega_lote` da frente 10, uma vez por item.

Plug: `suprimentos.py` (builder novo) importa `router`/`MENU` e chama `telas(db, out)` no fim do build().
DDL idempotente em `_ensure(db)`, chamada por `telas()` e por cada ação.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime
from types import SimpleNamespace
from xml.etree import ElementTree as ET  # noqa: S405
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db

router = APIRouter()
logger = logging.getLogger(__name__)

_ICO_T = "M3 3v18h18"
_ICO_N = "M12 5v14M5 12h14"
# ANTES do import do data_controller (ciclo: data_controller → discovery → suprimentos → aqui)
MENU = [
    {"id": "solicitacoes-compra", "label": "Solicitações de compra", "icon": _ICO_T, "grupo": "Compras"},
    {"id": "solicitacao-compra-nova", "label": "Nova solicitação", "icon": _ICO_N, "grupo": "Compras"},
    {"id": "pedidos-compra", "label": "Pedidos de compra", "icon": _ICO_T, "grupo": "Compras"},
    {"id": "pedido-compra-novo", "label": "Novo pedido", "icon": _ICO_N, "grupo": "Compras"},
    {"id": "nf-entrada", "label": "Notas fiscais de entrada", "icon": _ICO_T, "grupo": "Compras"},
    {"id": "materiais", "label": "Materiais", "icon": _ICO_T, "grupo": "Materiais & estoque"},
    {"id": "material-novo", "label": "Novo material", "icon": _ICO_N, "grupo": "Materiais & estoque"},
    {"id": "estoque", "label": "Estoque", "icon": _ICO_T, "grupo": "Materiais & estoque"},
    {"id": "estoque-movimentar", "label": "Movimentar estoque", "icon": _ICO_N, "grupo": "Materiais & estoque"},
    {"id": "fornecedores", "label": "Fornecedores", "icon": _ICO_T, "grupo": "Fornecedores"},
    {"id": "fornecedor-novo", "label": "Novo fornecedor", "icon": _ICO_N, "grupo": "Fornecedores"},
    {"id": "comunicacoes-moveis", "label": "Comunicações móveis", "icon": _ICO_T, "grupo": "Equipamentos controlados"},
    {"id": "rastreadores", "label": "Rastreadores", "icon": _ICO_T, "grupo": "Equipamentos controlados"},
    {
        "id": "equipamento-movel-novo",
        "label": "Novo rádio / celular / rastreador",
        "icon": _ICO_N,
        "grupo": "Equipamentos controlados",
    },
    {"id": "kit-uniforme", "label": "Kit de uniforme por função", "icon": _ICO_T, "grupo": "Kits"},
    {"id": "kit-uniforme-novo", "label": "Adicionar item ao kit", "icon": _ICO_N, "grupo": "Kits"},
    {"id": "kit-uniforme-entregar", "label": "Entregar kit da função", "icon": _ICO_N, "grupo": "Kits"},
]

from modules.operacional.controllers.redesign_data_controller import S, _helpers, b, brl, t  # noqa: E402
from modules.people_management.hr.services import conformidade_vigilante as cv  # noqa: E402

from . import _frente_10 as f10  # noqa: E402  # módulo inteiro: nome resolvido na chamada nunca quebra o ciclo

_TZ = ZoneInfo("America/Manaus")
_ND = "#0F1B3A"
A = "/api/v1/redesign/action/"
#: tenant dos `suppliers` e das `purchase_*` (mesmo dos serviços que já gravam suppliers)
COND_MATRIZ = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
EMPRESA_PRINCIPAL_ID = "619a3df1-8bce-49ce-b77a-04f80a0e8491"
GRUPOS = [
    ("uniforme", "Uniforme"),
    ("epi", "EPI"),
    ("material", "Material"),
    ("equipamento", "Equipamento"),
    ("limpeza", "Limpeza"),
    ("escritorio", "Escritório"),
]
UNIDADES = ["UN", "PC", "PR", "CX", "KG", "M", "M2", "M3", "ML", "RL", "CT", "T"]
TIPOS_MOVEIS = [("radio", "Rádio"), ("celular", "Celular"), ("rastreador", "Rastreador")]
#: "Próximo do mínimo" = saldo até 20 % acima do mínimo (o DGX não publica a régua; esta é a da casa)
MARGEM_PROXIMO = 0.2
_ST_SOL = {
    "pendente": ("Pendente", "warn"),
    "aprovada": ("Aprovada", "info"),
    "negada": ("Negada", "bad"),
    "atendida": ("Atendida", "ok"),
}
_ST_PED = {
    "rascunho": ("Rascunho", "mut"),
    "enviado": ("Enviado", "info"),
    "recebido": ("Recebido", "ok"),
    "cancelado": ("Cancelado", "bad"),
}

DDL = """
ALTER TABLE nfe_compras_estoque ADD COLUMN IF NOT EXISTS grupo varchar(20);
ALTER TABLE nfe_compras_estoque ADD COLUMN IF NOT EXISTS minimo numeric(15,4) CHECK (minimo IS NULL OR minimo >= 0);
ALTER TABLE nfe_compras_estoque ADD COLUMN IF NOT EXISTS maximo numeric(15,4) CHECK (maximo IS NULL OR maximo >= 0);
ALTER TABLE nfe_compras_estoque ADD COLUMN IF NOT EXISTS ativo boolean NOT NULL DEFAULT true;
ALTER TABLE nfe_compras_estoque ADD COLUMN IF NOT EXISTS origem varchar(10) NOT NULL DEFAULT 'nfe';
ALTER TABLE nfe_estoque_movimentos ADD COLUMN IF NOT EXISTS ref_chave varchar(60);
ALTER TABLE nfe_estoque_movimentos ADD COLUMN IF NOT EXISTS created_by varchar(120);
CREATE UNIQUE INDEX IF NOT EXISTS ux_nfe_estoque_mov_entrada ON nfe_estoque_movimentos (ref_chave, item_code) WHERE tipo = 'entrada' AND ref_chave IS NOT NULL;
ALTER TABLE purchase_requisitions ADD COLUMN IF NOT EXISTS post_id uuid;
ALTER TABLE purchase_requisition_items ADD COLUMN IF NOT EXISTS item_code varchar(60);
ALTER TABLE purchase_order_items ADD COLUMN IF NOT EXISTS item_code varchar(60);
ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS condicao_pagamento_id integer;
ALTER TABLE goods_receipts ADD COLUMN IF NOT EXISTS nfe_entrada_id integer;
CREATE UNIQUE INDEX IF NOT EXISTS ux_goods_receipts_invoice_key ON goods_receipts (invoice_key) WHERE invoice_key IS NOT NULL;
ALTER TABLE equipamentos_controlados ADD COLUMN IF NOT EXISTS imei varchar(40);
ALTER TABLE equipamentos_controlados ADD COLUMN IF NOT EXISTS numero_linha varchar(20);
ALTER TABLE equipamentos_controlados ADD COLUMN IF NOT EXISTS operadora varchar(40);
ALTER TABLE equipamentos_controlados ADD COLUMN IF NOT EXISTS plano_mensal numeric(10,2) CHECK (plano_mensal IS NULL OR plano_mensal >= 0);
ALTER TABLE equipamentos_controlados ADD COLUMN IF NOT EXISTS post_id uuid;
CREATE TABLE IF NOT EXISTS sst_uniforme_kits (
  id serial PRIMARY KEY, funcao varchar(80) NOT NULL, grade_id integer NOT NULL REFERENCES sst_uniforme_grade(id),
  quantidade integer NOT NULL CHECK (quantidade > 0), ativo boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(), created_by varchar(120), UNIQUE (funcao, grade_id));
-- dgx v3: grupo hierárquico (sup_grupos) também no kit de uniforme
ALTER TABLE sst_uniforme_kits ADD COLUMN IF NOT EXISTS grupo varchar(20);
"""
_TIPOS_EQUIP = "'armamento','colete','radio','celular','rastreador'"


async def _ensure(db) -> None:
    for stmt in DDL.split(";"):
        if stmt.strip():
            await db.execute(text(stmt))
    atual = (
        await db.execute(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'equipamentos_controlados_tipo_check'"
            )
        )
    ).scalar() or ""
    if "rastreador" not in atual:
        await db.execute(
            text("ALTER TABLE equipamentos_controlados DROP CONSTRAINT IF EXISTS equipamentos_controlados_tipo_check")
        )
        await db.execute(
            text(
                f"ALTER TABLE equipamentos_controlados ADD CONSTRAINT equipamentos_controlados_tipo_check CHECK (tipo IN ({_TIPOS_EQUIP}))"
            )
        )
    await db.commit()


# ----------------------------------------------------------------------------- régua
def status_estoque(qty, minimo, maximo) -> tuple[str, str]:
    """Os 6 status do DGX. Ordem: zerado → mínimo não informado → abaixo → acima do máximo → próximo → regular."""
    q = float(qty or 0)
    if q <= 0:
        return "Zerado", "bad"
    if minimo is None:
        return "Mínimo não informado", "mut"
    mi = float(minimo)
    if q < mi:
        return "Abaixo do mínimo", "bad"
    if maximo is not None and q > float(maximo):
        return "Acima do máximo", "warn"
    if q <= mi * (1 + MARGEM_PROXIMO):
        return "Próximo do mínimo", "warn"
    return "Regular", "ok"


def _d(v):
    try:
        return v.strftime("%d/%m/%Y") if v else "—"
    except Exception:  # noqa: BLE001
        return "—"


def _n(v, casas=2):
    if v is None:
        return "—"
    s = f"{float(v):,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s[:-3] if casas == 2 and s.endswith(",00") else s


def _cnpj(v: str | None) -> str:
    return "".join(c for c in (v or "") if c.isdigit())


def _data(v, campo, obrigatorio=False):
    if v is None or str(v).strip() == "":
        if obrigatorio:
            raise HTTPException(status_code=400, detail=f"{campo}: informe a data.")
        return None
    try:
        return date.fromisoformat(str(v).strip()[:10])
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{campo}: data inválida.") from None


def _uuid(v):
    return (str(v).strip() or None) if v not in (None, "") else None


async def _um(db, sql: str, **p):
    return (await db.execute(text(sql), p)).first()


def _itens_texto(txt: str, com_preco: bool) -> list[dict]:
    """Uma linha por item: `código ou descrição | quantidade | justificativa` (ou `| preço` no pedido)."""
    out = []
    for ln in (txt or "").splitlines():
        if not ln.strip():
            continue
        p = [x.strip() for x in ln.split("|")]
        if len(p) < 2:
            raise HTTPException(
                status_code=400,
                detail=f"Item '{ln[:40]}': use `descrição | quantidade | {'preço' if com_preco else 'justificativa'}`.",
            )
        qtd = f10._dec(p[1], "Quantidade")
        if not qtd:
            raise HTTPException(status_code=400, detail=f"Item '{p[0][:40]}': quantidade deve ser maior que zero.")
        it = {"ref": p[0], "qtd": qtd, "extra": p[2] if len(p) > 2 else ""}
        if com_preco:
            it["preco"] = f10._dec(it["extra"], "Preço") if it["extra"] else None
        out.append(it)
    if not out:
        raise HTTPException(status_code=400, detail="Informe ao menos um item.")
    return out


async def _material(db, ref: str):
    """Código exato ou descrição única; senão fica texto livre (item_code NULL)."""
    r = await _um(db, "SELECT item_code, descricao FROM nfe_compras_estoque WHERE ativo AND item_code = :r", r=ref)
    if r:
        return r[0], r[1]
    rs = (
        await db.execute(
            text("SELECT item_code, descricao FROM nfe_compras_estoque WHERE ativo AND descricao ILIKE :r LIMIT 2"),
            {"r": f"%{ref}%"},
        )
    ).fetchall()
    if len(rs) == 1:
        return rs[0][0], rs[0][1]
    return None, ref


async def _numero(db, tabela: str, prefixo: str) -> str:
    n = (await db.execute(text(f"SELECT count(*) + 1 FROM {tabela}"))).scalar()  # noqa: S608 — tabela é literal interno
    return f"{prefixo}-{datetime.now(_TZ):%Y%m}-{n:04d}"


async def _mov(
    db,
    item_code: str,
    tipo: str,
    qtd: float,
    custo: float | None,
    motivo: str,
    quem: str,
    ref_chave: str | None = None,
    ajusta_saldo: bool = True,
):
    """Movimento de estoque sobre `nfe_compras_estoque` (a tabela viva). `entrada` soma com custo médio
    ponderado (mesma conta do sync SEFAZ); `ajuste` recebe a CONTAGEM e grava o delta. Com `ref_chave`,
    o índice único garante que a mesma NF/pedido entre uma vez — repetição devolve None sem mexer no saldo.
    `ajusta_saldo=False` só registra (NF-e que o sync já somou ao saldo)."""
    r = await _um(
        db,
        "SELECT descricao, qty_on_hand, avg_cost FROM nfe_compras_estoque WHERE item_code = :c FOR UPDATE",
        c=item_code,
    )
    if not r:
        raise HTTPException(status_code=404, detail=f"Material {item_code} não encontrado.")
    desc, atual, avg = r[0], float(r[1] or 0), float(r[2] or 0)
    if tipo == "entrada":
        delta, novo = qtd, atual + qtd
        custo = avg if custo is None else custo
        novo_avg = ((avg * atual + custo * qtd) / novo) if novo > 0 else custo
    elif tipo == "ajuste":
        delta, novo, custo, novo_avg = qtd - atual, qtd, avg, avg
    else:
        raise HTTPException(status_code=400, detail="Tipo de movimento inválido.")
    row = await _um(
        db,
        "INSERT INTO nfe_estoque_movimentos (item_code, descricao, tipo, quantidade, custo_unitario, valor_total, motivo, empresa_id, ref_chave, created_by) "
        "VALUES (:c, :d, :t, :q, :cu, :v, :m, CAST(:e AS uuid), :r, :u) ON CONFLICT (ref_chave, item_code) WHERE tipo = 'entrada' AND ref_chave IS NOT NULL DO NOTHING RETURNING id",
        c=item_code,
        d=desc,
        t=tipo,
        q=delta,
        cu=custo,
        v=round(delta * custo, 2),
        m=motivo,
        e=EMPRESA_PRINCIPAL_ID,
        r=ref_chave,
        u=quem,
    )
    if not row:
        return None
    if ajusta_saldo:
        await db.execute(
            text(
                "UPDATE nfe_compras_estoque SET qty_on_hand = :n, avg_cost = :a, updated_at = now() WHERE item_code = :c"
            ),
            {"n": novo, "a": novo_avg, "c": item_code},
        )
    return row[0]


def _itens_xml(xml: str) -> list[tuple[str, str, float, float]]:
    """(cProd, xProd, qCom, vUnCom) dos `det` — o mesmo que o sync lê para dar entrada."""
    try:
        root = ET.fromstring(xml)  # noqa: S314  # nosec B314 — XML vindo da SEFAZ, já parseado pelo sync
    except ET.ParseError:
        return []
    for e in root.iter():
        if "}" in e.tag:
            e.tag = e.tag.split("}", 1)[1]
    out = []
    for det in root.iter("det"):
        p = det.find("prod")
        if p is None:
            continue
        try:
            q, v = float(p.findtext("qCom") or 0), float(p.findtext("vUnCom") or 0)
        except ValueError:
            continue
        cod = (p.findtext("cProd") or "").strip()
        if cod and q > 0:
            out.append((cod, (p.findtext("xProd") or "").strip(), q, v))
    return out


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


def _h(k, v):
    return {"key": k, "type": "hidden", "value": str(v)}


def _sel(key, label, options, span="span 1", value=""):
    return {"key": key, "label": label, "type": "select", "span": span, "options": options, "value": value}


_SQL_POSTOS = "SELECT id, coalesce(name, code) FROM posts WHERE coalesce(is_active,true) ORDER BY 2"
_SQL_FORN = "SELECT id, name || coalesce(' · ' || cpf_cnpj, '') FROM suppliers WHERE coalesce(status,'ativo') = 'ativo' AND coalesce(ativo,true) ORDER BY name"
_SQL_COND = "SELECT id, nome FROM fin_condicoes_pagamento WHERE ativo ORDER BY id"
_SQL_MAT = "SELECT item_code, item_code || ' · ' || left(coalesce(descricao,'—'), 50) FROM nfe_compras_estoque WHERE ativo ORDER BY descricao"
_SQL_FUNCOES = "SELECT DISTINCT upper(cargo), upper(cargo) FROM employees WHERE status = 'ativo' AND coalesce(cargo,'') <> '' ORDER BY 1"
_SQL_PESSOAS = (
    "SELECT id, nome FROM employees WHERE status = 'ativo' AND coalesce(is_homologacao,false) = false ORDER BY nome"
)


# ----------------------------------------------------------------------------- telas
async def telas(db, out: dict | None = None) -> dict:
    await _ensure(db)
    _out, safe, tbl = _helpers(db)
    if out is None:
        out = {}
    postos, forn, cond, mats = [await f10._opts(db, s) for s in (_SQL_POSTOS, _SQL_FORN, _SQL_COND, _SQL_MAT)]
    vazio = [{"value": "", "label": "—"}]

    # ── 1) compras ─────────────────────────────────────────────────────────────────────────
    def _acoes_sol(r):
        if r[8] != "pendente":
            return []
        return [
            _acao(
                f"Aprovar solicitação {r[1]}",
                A + "compra-solicitacao-status",
                "Aprovar",
                [
                    _h("id", r[0]),
                    _h("status", "aprovada"),
                    {"key": "observacao", "label": "Observação", "type": "text", "span": "span 2", "value": ""},
                ],
                "Aprovada. Recarregue.",
                "primary",
            ),
            _acao(
                f"Negar solicitação {r[1]}",
                A + "compra-solicitacao-status",
                "Negar",
                [
                    _h("id", r[0]),
                    _h("status", "negada"),
                    {"key": "observacao", "label": "Motivo*", "type": "text", "span": "span 2", "value": ""},
                ],
                "Negada. Recarregue.",
            ),
        ]

    await safe(
        "solicitacoes-compra",
        tbl(
            "Solicitações de compra",
            "Quem pediu, para qual posto, o quê e por quê. Aprovada vira pedido em «Novo pedido».",
            "—",
            ["#", "Número", "Título", "Solicitante", "Posto", "Itens", "Qtd", "Urgência", "Data", "Status"],
            "0.4fr 1.1fr 1.6fr 1.2fr 1.2fr 0.5fr 0.5fr 0.8fr 0.8fr 0.9fr",
            "SELECT r.id::text, r.number, r.title, coalesce(r.requester_name,'—'), coalesce(p.name, p.code, '—'), "
            "(SELECT count(*) FROM purchase_requisition_items i WHERE i.requisition_id = r.id), "
            "(SELECT coalesce(sum(i.quantity),0) FROM purchase_requisition_items i WHERE i.requisition_id = r.id), "
            "r.priority, r.requisition_date, r.status FROM purchase_requisitions r LEFT JOIN posts p ON p.id = r.post_id "
            "WHERE coalesce(r.ativo,true) ORDER BY (r.status = 'pendente') DESC, r.requisition_date DESC, r.created_at DESC LIMIT 300",
            lambda r: [
                t(r[0][:8]),
                t(r[1], 600, _ND),
                t(r[2]),
                t(r[3]),
                t(r[4]),
                t(str(r[5])),
                t(_n(r[6])),
                b("Urgente", "bad") if r[7] == "urgente" else b("Normal", "mut"),
                t(_d(r[8])),
                b(*_ST_SOL.get(r[9], (r[9], "info"))),
            ],
            actionsfn=_acoes_sol,
            filtrofn=lambda r: _ST_SOL.get(r[9], (r[9],))[0],
        ),
    )
    await safe(
        "solicitacao-compra-nova",
        f10._form(
            db,
            "solicitacao-compra-nova",
            "Nova solicitação de compra",
            "Um item por linha: `código do material ou descrição | quantidade | justificativa`. Código que existe em Materiais casa com o estoque.",
            "Solicitar",
            A + "compra-solicitacao",
            [
                {"key": "titulo", "label": "Título*", "type": "text", "span": "span 2"},
                _sel("post_id", "Centro / posto", vazio + postos),
                _sel(
                    "urgencia",
                    "Urgência*",
                    [{"value": "normal", "label": "Normal"}, {"value": "urgente", "label": "Urgente"}],
                    value="normal",
                ),
                {
                    "key": "itens",
                    "label": "Itens* (um por linha)",
                    "type": "textarea",
                    "span": "span 2",
                    "ph": "78225 | 2 | reposição do posto\nPilha AA | 10 | rádios",
                },
                {"key": "necessario_em", "label": "Necessário até", "type": "date"},
            ],
            okMsg="Solicitação criada (pendente de aprovação).",
            showResult=True,
        ),
    )

    def _acoes_ped(r):
        acts = []
        if r[10] == "rascunho":
            acts.append(
                _acao(
                    f"Enviar pedido {r[1]} ao fornecedor",
                    A + "compra-pedido-enviar",
                    "Enviar",
                    [_h("id", r[0])],
                    "Enviado. Recarregue.",
                    "primary",
                )
            )
        if r[10] in ("rascunho", "enviado"):
            acts.append(
                _acao(
                    f"Receber pedido {r[1]} SEM NF-e (recebimento manual — itens com código entram no estoque)",
                    A + "compra-pedido-receber",
                    "Receber",
                    [
                        _h("id", r[0]),
                        {"key": "invoice_number", "label": "Nº da nota (se houver)", "type": "text", "value": ""},
                        {"key": "observacao", "label": "Observação", "type": "text", "value": ""},
                    ],
                    "Recebido. Recarregue.",
                )
            )
            acts.append(
                _acao(
                    f"Cancelar pedido {r[1]}",
                    A + "compra-pedido-cancelar",
                    "Cancelar",
                    [
                        _h("id", r[0]),
                        {"key": "motivo", "label": "Motivo*", "type": "text", "span": "span 2", "value": ""},
                    ],
                    "Cancelado. Recarregue.",
                )
            )
        return acts

    await safe(
        "pedidos-compra",
        tbl(
            "Pedidos de compra",
            "Enviar → fornecedor entrega → «Conferir recebimento» na NF de entrada (ou Receber manual, sem NF).",
            "—",
            [
                "#",
                "Número",
                "Fornecedor",
                "Solicitação",
                "Itens",
                "Total",
                "Condição",
                "Previsão",
                "Emissão",
                "Recebido",
                "Status",
            ],
            "0.4fr 1.1fr 1.6fr 1fr 0.5fr 0.9fr 0.9fr 0.8fr 0.8fr 0.9fr 0.9fr",
            "SELECT o.id::text, o.number, coalesce(s.name,'—'), coalesce(r.number,'—'), "
            "(SELECT count(*) FROM purchase_order_items i WHERE i.order_id = o.id), o.total, coalesce(c.nome, o.payment_condition, '—'), "
            "o.expected_delivery_date, o.order_date, o.received_total, o.status FROM purchase_orders o "
            "LEFT JOIN suppliers s ON s.id = o.supplier_id LEFT JOIN purchase_requisitions r ON r.id = o.requisition_id "
            "LEFT JOIN fin_condicoes_pagamento c ON c.id = o.condicao_pagamento_id WHERE coalesce(o.ativo,true) "
            "ORDER BY (o.status IN ('rascunho','enviado')) DESC, o.order_date DESC, o.created_at DESC LIMIT 300",
            lambda r: [
                t(r[0][:8]),
                t(r[1], 600, _ND),
                t(r[2]),
                t(r[3]),
                t(str(r[4])),
                t(brl(float(r[5] or 0)), 600),
                t(r[6]),
                t(_d(r[7])),
                t(_d(r[8])),
                t(brl(float(r[9] or 0)) if r[9] else "—"),
                b(*_ST_PED.get(r[10], (r[10], "info"))),
            ],
            actionsfn=_acoes_ped,
            filtrofn=lambda r: _ST_PED.get(r[10], (r[10],))[0],
        ),
    )
    sols = await f10._opts(
        db,
        "SELECT id, number || ' · ' || title FROM purchase_requisitions WHERE status = 'aprovada' ORDER BY requisition_date DESC",
    )
    await safe(
        "pedido-compra-novo",
        f10._form(
            db,
            "pedido-compra-novo",
            "Novo pedido de compra",
            "A partir de uma solicitação aprovada (itens copiados; informe preços abaixo se quiser) ou avulso. Itens: `código ou descrição | quantidade | preço unitário`.",
            "Criar pedido",
            A + "compra-pedido",
            [
                _sel("requisition_id", "Solicitação aprovada", vazio + sols, "span 2"),
                _sel("supplier_id", "Fornecedor*", forn, "span 2"),
                _sel("condicao_pagamento_id", "Condição de pagamento", vazio + cond),
                {"key": "previsao", "label": "Previsão de entrega", "type": "date"},
                {
                    "key": "itens",
                    "label": "Itens (vazio = copiar da solicitação)",
                    "type": "textarea",
                    "span": "span 2",
                    "ph": "78225 | 2 | 125,14",
                },
                {"key": "observacao", "label": "Observação ao fornecedor", "type": "textarea", "span": "span 2"},
            ],
            okMsg="Pedido criado (rascunho).",
            showResult=True,
        ),
    )

    # NF de entrada: nfe_entradas (SEFAZ) + goods_receipts (conferência)
    ped_abertos = (
        await db.execute(
            text(
                "SELECT o.id::text, o.number, regexp_replace(coalesce(s.cpf_cnpj,''),'\\D','','g'), o.total FROM purchase_orders o "
                "JOIN suppliers s ON s.id = o.supplier_id WHERE o.status IN ('rascunho','enviado')"
            )
        )
    ).fetchall()

    def _acoes_nf(r):
        if r[9]:  # já conferida
            return []
        cnpj = r[2]
        opts = [{"value": p[0], "label": f"{p[1]} · {brl(float(p[3] or 0))}"} for p in ped_abertos if p[2] == cnpj]
        sug = next((p[0] for p in ped_abertos if p[2] == cnpj and abs(float(p[3] or 0) - float(r[5] or 0)) < 0.01), "")
        return [
            _acao(
                f"Conferir recebimento da NF-e {r[1] or ''} de {r[3]} ({brl(float(r[5] or 0))})"
                + (" — sem XML: só o pedido é baixado, estoque não muda" if not r[7] else ""),
                A + "compra-nf-conferir",
                "Conferir recebimento",
                [
                    _h("nfe_id", r[0]),
                    _sel(
                        "order_id",
                        "Pedido de compra*",
                        (opts or [{"value": "", "label": "nenhum pedido aberto deste fornecedor"}]),
                        "span 2",
                        sug,
                    ),
                ],
                "Recebimento conferido. Recarregue.",
                "primary",
            )
        ]

    await safe(
        "nf-entrada",
        tbl(
            "Notas fiscais de entrada",
            "NF-e contra o CNPJ (SEFAZ). «Conferir recebimento» casa a nota com o pedido do mesmo fornecedor (sugere o de mesmo valor) e registra a entrada no estoque uma única vez.",
            "—",
            ["#", "Nº", "Emitente", "Emissão", "Valor", "XML", "Estoque", "Pedido", "Conferida"],
            "0.4fr 0.7fr 2fr 0.8fr 0.9fr 0.7fr 0.8fr 1fr 0.9fr",
            "SELECT n.id, n.numero, regexp_replace(coalesce(n.emitente_cnpj,''),'\\D','','g'), coalesce(n.emitente_nome,'—'), n.data_emissao, n.valor_total, n.chave_acesso, "
            "(n.xml_raw IS NOT NULL), coalesce(n.processada,false), g.id::text, o.number, g.receipt_date "
            "FROM nfe_entradas n LEFT JOIN goods_receipts g ON g.invoice_key = n.chave_acesso LEFT JOIN purchase_orders o ON o.id = g.order_id "
            "ORDER BY n.data_emissao DESC NULLS LAST, n.id DESC LIMIT 300",
            lambda r: [
                t(str(r[0])),
                t(r[1] or "—", 600, _ND),
                t(r[3][:40]),
                t(_d(r[4])),
                t(brl(float(r[5] or 0)), 600),
                b("completo", "ok") if r[7] else b("resumo", "warn"),
                b("lançado", "ok") if r[8] else b("não", "mut"),
                t(r[10] or "—"),
                b(_d(r[11]), "ok") if r[9] else b("pendente", "warn"),
            ],
            actionsfn=_acoes_nf,
            filtrofn=lambda r: "Conferida" if r[9] else "Pendente",
        ),
    )

    # ── 2) materiais e estoque ─────────────────────────────────────────────────────────────
    # dgx v3: grupo deixa de ser a lista fixa de 6 e passa a ser a hierarquia de `sup_grupos`
    from ._dgx_v3_frota_app import grupos_opts as _gopts  # noqa: PLC0415
    from ._dgx_v3_frota_app import rotulo_grupo as _grot

    g_opts = await _gopts(db)
    g_rot = await _grot(db)

    def _edit_mat(r):
        return _acao(
            f"Editar {r[0]} — {(r[1] or '')[:40]}",
            A + "material-editar",
            "Salvar",
            [
                _h("item_code", r[0]),
                _sel("grupo", "Grupo", vazio + g_opts, value=r[2] or ""),  # dgx v3
                {"key": "minimo", "label": "Mínimo", "type": "text", "value": _n(r[4], 0) if r[4] is not None else ""},
                {"key": "maximo", "label": "Máximo", "type": "text", "value": _n(r[5], 0) if r[5] is not None else ""},
                {"key": "descricao", "label": "Descrição", "type": "text", "span": "span 2", "value": r[1] or ""},
            ],
            "Material atualizado. Recarregue.",
        )

    await safe(
        "materiais",
        tbl(
            "Materiais",
            "Cadastro = `nfe_compras_estoque` (o que entrou por NF-e + cadastro manual). Mínimo/máximo alimentam a tela Estoque.",
            "—",
            ["Código", "Descrição", "Grupo", "Un", "Mín", "Máx", "Custo médio", "Saldo", "Origem"],
            "0.8fr 2.4fr 0.9fr 0.5fr 0.5fr 0.5fr 0.9fr 0.6fr 0.7fr",
            "SELECT item_code, descricao, grupo, unidade, minimo, maximo, coalesce(avg_cost, unit_cost, 0), qty_on_hand, origem FROM nfe_compras_estoque WHERE ativo ORDER BY descricao LIMIT 500",
            lambda r: [
                t(r[0], 600, _ND),
                t((r[1] or "—")[:60]),
                t(g_rot.get(r[2], r[2] or "—")),  # dgx v3
                t(r[3] or "—"),
                t(_n(r[4], 0)),
                t(_n(r[5], 0)),
                t(brl(float(r[6] or 0))),
                t(_n(r[7], 0), 600),
                b("NF-e" if r[8] == "nfe" else "manual", "info" if r[8] == "nfe" else "mut"),
            ],
            actionsfn=lambda r: [
                _edit_mat(r),
                _acao(
                    f"Inativar {r[0]}",
                    A + "material-inativar",
                    "Inativar",
                    [_h("item_code", r[0])],
                    "Inativado. Recarregue.",
                ),
            ],
            filtrofn=lambda r: g_rot.get(r[2], "Sem grupo"),  # dgx v3
        ),
    )
    await safe(
        "material-novo",
        f10._form(
            db,
            "material-novo",
            "Novo material",
            "Material que não veio por NF-e (o código vira `MAT-…` se ficar vazio).",
            "Cadastrar",
            A + "material",
            [
                {"key": "item_code", "label": "Código", "type": "text"},
                _sel("grupo", "Grupo*", g_opts),  # dgx v3
                {"key": "descricao", "label": "Descrição*", "type": "text", "span": "span 2"},
                _sel("unidade", "Unidade*", [{"value": u, "label": u} for u in UNIDADES], value="UN"),
                {"key": "custo", "label": "Custo unitário (R$)", "type": "text"},
                {"key": "minimo", "label": "Estoque mínimo", "type": "text"},
                {"key": "maximo", "label": "Estoque máximo", "type": "text"},
                {"key": "saldo_inicial", "label": "Saldo inicial (contagem)", "type": "text"},
            ],
            okMsg="Material cadastrado.",
        ),
    )

    linhas_est = (
        await db.execute(
            text(
                "SELECT item_code, descricao, grupo, unidade, qty_on_hand, minimo, maximo, coalesce(avg_cost, unit_cost, 0), "
                "(SELECT max(data_mov) FROM nfe_estoque_movimentos m WHERE m.item_code = e.item_code) FROM nfe_compras_estoque e WHERE ativo ORDER BY descricao"
            )
        )
    ).fetchall()
    cont: dict[str, int] = {}
    for r in linhas_est:
        cont[status_estoque(r[4], r[5], r[6])[0]] = cont.get(status_estoque(r[4], r[5], r[6])[0], 0) + 1
    ordem = ["Zerado", "Abaixo do mínimo", "Próximo do mínimo", "Regular", "Acima do máximo", "Mínimo não informado"]
    tom = {
        "Zerado": "bad",
        "Abaixo do mínimo": "bad",
        "Próximo do mínimo": "warn",
        "Regular": "ok",
        "Acima do máximo": "warn",
        "Mínimo não informado": "mut",
    }
    valor_total = sum(float(r[4] or 0) * float(r[7] or 0) for r in linhas_est)
    out["estoque"] = {
        "title": "Estoque",
        "sub": f"{len(linhas_est)} materiais · {brl(valor_total)} em estoque · «Próximo do mínimo» = até {int(MARGEM_PROXIMO * 100)} % acima do mínimo",
        "cta": "—",
        "type": "table",
        "searchHint": "Buscar material ou status…",
        "grid": "0.8fr 2.2fr 0.9fr 0.5fr 0.7fr 0.5fr 0.5fr 0.9fr 0.8fr 1.3fr",
        "cols": ["Código", "Material", "Grupo", "Un", "Saldo", "Mín", "Máx", "Valor", "Últ. mov.", "Status"],
        "rows": [
            {
                "cells": [
                    t(r[0], 600, _ND),
                    t((r[1] or "—")[:55]),
                    t(g_rot.get(r[2], r[2] or "—")),  # dgx v3
                    t(r[3] or "—"),
                    t(_n(r[4], 0), 600),
                    t(_n(r[5], 0)),
                    t(_n(r[6], 0)),
                    t(brl(float(r[4] or 0) * float(r[7] or 0))),
                    t(_d(r[8])),
                    b(*status_estoque(r[4], r[5], r[6])),
                ],
                "filtro": status_estoque(r[4], r[5], r[6])[0],
            }
            for r in linhas_est
        ],
        "panelGrid": "1fr",
        "panels": [
            {
                "title": "Legenda — status do DGX (contagem)",
                "rows": [{"left": s, "right": str(cont.get(s, 0)), **S[tom[s]]} for s in ordem],
            }
        ],
    }
    await safe(
        "estoque-movimentar",
        f10._form(
            db,
            "estoque-movimentar",
            "Movimentar estoque",
            "Entrada soma com custo médio ponderado; saída baixa e lança o custo no razão (mesmo caminho das baixas por serviço); ajuste recebe a CONTAGEM física e grava o delta.",
            "Registrar",
            A + "estoque-movimento",
            [
                _sel("item_code", "Material*", mats, "span 2"),
                _sel(
                    "tipo",
                    "Tipo*",
                    [
                        {"value": "entrada", "label": "Entrada"},
                        {"value": "saida", "label": "Saída"},
                        {"value": "ajuste", "label": "Ajuste (contagem)"},
                    ],
                ),
                {"key": "quantidade", "label": "Quantidade* (no ajuste: contagem física)", "type": "text"},
                {"key": "custo", "label": "Custo unitário (entrada; vazio = custo médio)", "type": "text"},
                {"key": "motivo", "label": "Motivo*", "type": "text"},
                {"key": "destino", "label": "Destino / posto (saída)", "type": "text", "span": "span 2"},
            ],
            okMsg="Movimento registrado.",
            confirm="Confirma o movimento de estoque?",
            showResult=True,
        ),
    )

    # ── 3) fornecedores ────────────────────────────────────────────────────────────────────
    await safe(
        "fornecedores",
        tbl(
            "Fornecedores",
            "`suppliers` (cadastro, criado a partir das notas reais) + `financial_fornecedores` (padrões do extrato). Últimas compras = NF-e recebidas.",
            "—",
            ["Fornecedor", "CNPJ", "Contato", "Fornece", "NF-e", "Última compra", "Comprado", "Origem", "Status"],
            "2fr 1.1fr 1.3fr 0.9fr 0.5fr 0.8fr 0.9fr 1fr 0.8fr",
            "WITH sup AS (SELECT s.id::text AS id, s.name, regexp_replace(coalesce(s.cpf_cnpj,''),'\\D','','g') AS cnpj, "
            "coalesce(nullif(s.contact_name,''), nullif(s.email,''), nullif(s.phone,''), '—') AS contato, coalesce(nullif(s.category,''),'—') AS cat, coalesce(s.status,'ativo') AS st, "
            "(SELECT f.id FROM financial_fornecedores f WHERE (nullif(regexp_replace(coalesce(f.cnpj,''),'\\D','','g'),'') = regexp_replace(coalesce(s.cpf_cnpj,''),'\\D','','g')) "
            " OR upper(s.name) LIKE '%' || upper(f.padrao_match) || '%' LIMIT 1) AS fin_id FROM suppliers s WHERE coalesce(s.ativo,true)) "
            "SELECT sup.name, sup.cnpj, sup.contato, sup.cat, n.qtd, n.ultima, n.valor, CASE WHEN sup.fin_id IS NULL THEN 'cadastro' ELSE 'cadastro + extrato' END, sup.st "
            "FROM sup LEFT JOIN LATERAL (SELECT count(*) AS qtd, max(data_emissao) AS ultima, sum(valor_total) AS valor FROM nfe_entradas e WHERE e.emitente_cnpj = sup.cnpj AND sup.cnpj <> '') n ON true "
            "UNION ALL SELECT f.nome, coalesce(f.cnpj,'—'), '—', '—', NULL, NULL, NULL, 'extrato (sem cadastro)', CASE WHEN f.ativo THEN 'ativo' ELSE 'inativo' END "
            "FROM financial_fornecedores f WHERE NOT EXISTS (SELECT 1 FROM suppliers s WHERE (nullif(regexp_replace(coalesce(f.cnpj,''),'\\D','','g'),'') = regexp_replace(coalesce(s.cpf_cnpj,''),'\\D','','g')) "
            " OR upper(s.name) LIKE '%' || upper(f.padrao_match) || '%') ORDER BY 1 LIMIT 400",
            lambda r: [
                t(r[0], 600, _ND),
                t(r[1] or "—"),
                t(r[2]),
                t(r[3]),
                t(str(r[4]) if r[4] else "—"),
                t(_d(r[5])),
                t(brl(float(r[6])) if r[6] else "—"),
                b(r[7], "ok" if r[7].startswith("cadastro +") else ("info" if r[7] == "cadastro" else "warn")),
                b(r[8], "ok" if r[8] == "ativo" else "mut"),
            ],
            filtrofn=lambda r: r[7],
        ),
    )
    await safe(
        "fornecedor-novo",
        f10._form(
            db,
            "fornecedor-novo",
            "Novo fornecedor",
            "Grava em `suppliers` (a tabela que os pedidos usam). CNPJ único.",
            "Cadastrar",
            A + "fornecedor",
            [
                {"key": "name", "label": "Razão social*", "type": "text", "span": "span 2"},
                {"key": "cpf_cnpj", "label": "CNPJ*", "type": "text"},
                _sel(
                    "category",
                    "O que fornece*",
                    [{"value": k, "label": v} for k, v in GRUPOS]
                    + [{"value": "servico", "label": "Serviço"}, {"value": "outros", "label": "Outros"}],
                ),
                {"key": "contact_name", "label": "Contato", "type": "text"},
                {"key": "phone", "label": "Telefone", "type": "text"},
                {"key": "email", "label": "E-mail", "type": "text", "span": "span 2"},
            ],
            okMsg="Fornecedor cadastrado.",
        ),
    )

    # ── 4) comunicações móveis e rastreadores ──────────────────────────────────────────────
    pessoas = await f10._opts(db, _SQL_PESSOAS)

    def _acoes_eq(r):
        if r[10]:  # em posse
            return [
                _acao(
                    f"Devolver {r[1]} {r[2]} (com {r[10]})",
                    A + "equipamento-movel-devolver",
                    "Devolver",
                    [
                        _h("equipamento_id", r[0]),
                        {"key": "observacao", "label": "Observação", "type": "text", "span": "span 2", "value": ""},
                    ],
                    "Devolvido. Recarregue.",
                )
            ]
        if r[6] != "ativo":
            return []
        return [
            _acao(
                f"Entregar {r[1]} {r[2]}",
                A + "equipamento-movel-entregar",
                "Entregar",
                [
                    _h("equipamento_id", r[0]),
                    _sel("employee_id", "Responsável*", pessoas, "span 2"),
                    {"key": "observacao", "label": "Observação", "type": "text", "span": "span 2", "value": ""},
                ],
                "Entregue. Recarregue.",
                "primary",
            )
        ]

    _SQL_EQ = (
        "SELECT q.id::text, q.tipo, q.numero_serie, coalesce(q.modelo,'—'), coalesce(q.numero_linha,'—'), coalesce(q.operadora,'—'), q.status, q.plano_mensal, "
        "coalesce(p.name, p.code, '—'), coalesce(q.imei,'—'), e.nome, a.entregue_em FROM equipamentos_controlados q "
        "LEFT JOIN posts p ON p.id = q.post_id LEFT JOIN equipamentos_controlados_alocacoes a ON a.equipamento_id = q.id AND a.devolvido_em IS NULL "
        "LEFT JOIN employees e ON e.id = a.employee_id WHERE q.tipo IN ({tipos}) ORDER BY q.tipo, q.numero_serie"
    )
    _COLS_EQ = [
        "Tipo",
        "Série / nº",
        "IMEI",
        "Modelo",
        "Linha / chip",
        "Operadora",
        "Plano R$/mês",
        "Posto",
        "Responsável",
        "Entregue em",
        "Estado",
    ]
    _GRID_EQ = "0.7fr 1fr 1fr 1fr 1fr 0.8fr 0.8fr 1.1fr 1.4fr 1fr 0.8fr"

    def _linha_eq(r):
        return [
            b(dict(TIPOS_MOVEIS).get(r[1], r[1]), "info"),
            t(r[2], 600, _ND),
            t(r[9]),
            t(r[3]),
            t(r[4]),
            t(r[5]),
            t(brl(float(r[7])) if r[7] is not None else "—"),
            t(r[8]),
            t(r[10] or "disponível", 600 if r[10] else 500),
            t(f10._dt(r[11])),
            b(r[6], "ok" if r[6] == "ativo" else "warn"),
        ]

    custo = await _um(
        db,
        "SELECT coalesce(sum(plano_mensal),0), count(*) FILTER (WHERE plano_mensal > 0) FROM equipamentos_controlados WHERE tipo IN ('radio','celular') AND status = 'ativo'",
    )
    tela_com = await tbl(
        "Comunicações móveis — rádios e celulares",
        f"Série única, posse única (alocação aberta). Custo dos planos: {brl(float(custo[0]))}/mês em {custo[1]} linha(s) — só leitura, não gera título.",
        "—",
        _COLS_EQ,
        _GRID_EQ,
        _SQL_EQ.format(tipos="'radio','celular'"),
        _linha_eq,
        actionsfn=_acoes_eq,
        filtrofn=lambda r: dict(TIPOS_MOVEIS).get(r[1], r[1]),
    )
    tela_com["panelGrid"] = "1fr"
    tela_com["panels"] = [
        {
            "title": "Custo mensal dos planos (leitura — vai para Custos do Financeiro sem criar título)",
            "rows": [
                {
                    "left": f"{dict(TIPOS_MOVEIS).get(r[0], r[0])} · {r[1]} linha(s)",
                    "right": brl(float(r[2])),
                    **S["info"],
                }
                for r in (
                    await db.execute(
                        text(
                            "SELECT tipo, count(*), coalesce(sum(plano_mensal),0) FROM equipamentos_controlados WHERE tipo IN ('radio','celular') AND status='ativo' GROUP BY tipo ORDER BY tipo"
                        )
                    )
                ).fetchall()
            ]
            or [{"left": "Nenhum rádio/celular cadastrado", "right": "—", **S["mut"]}],
        }
    ]
    out["comunicacoes-moveis"] = tela_com
    await safe(
        "rastreadores",
        tbl(
            "Rastreadores",
            "Rastreador por série/IMEI, posto e responsável. Entrega/devolução datadas (mesmo controle da frente 05).",
            "—",
            _COLS_EQ,
            _GRID_EQ,
            _SQL_EQ.format(tipos="'rastreador'"),
            _linha_eq,
            actionsfn=_acoes_eq,
        ),
    )
    await safe(
        "equipamento-movel-novo",
        f10._form(
            db,
            "equipamento-movel-novo",
            "Novo rádio / celular / rastreador",
            "Sem número de série não é controle, é contador. Série é única entre TODOS os equipamentos controlados.",
            "Cadastrar",
            A + "equipamento-movel",
            [
                _sel("tipo", "Tipo*", [{"value": k, "label": v} for k, v in TIPOS_MOVEIS]),
                {"key": "numero_serie", "label": "Número de série / patrimônio*", "type": "text"},
                {"key": "imei", "label": "IMEI", "type": "text"},
                {"key": "modelo", "label": "Modelo", "type": "text"},
                {"key": "numero_linha", "label": "Número da linha / chip", "type": "text"},
                {"key": "operadora", "label": "Operadora", "type": "text"},
                {"key": "plano_mensal", "label": "Plano (R$/mês)", "type": "text"},
                _sel("post_id", "Posto", vazio + postos),
            ],
            okMsg="Equipamento cadastrado.",
        ),
    )

    # ── 5) kits por função ─────────────────────────────────────────────────────────────────
    funcoes = await f10._opts(db, _SQL_FUNCOES)
    skus = await f10._opts(
        db, "SELECT id, item || ' · ' || tamanho FROM sst_uniforme_grade WHERE ativo ORDER BY item, tamanho"
    )
    await safe(
        "kit-uniforme",
        tbl(
            "Kit de uniforme por função",
            "Composição: quais SKUs e quantas unidades cada função recebe. «Entregar kit da função» cria uma solicitação de entrega por item, para cada pessoa da função.",
            "—",
            ["Função", "Item", "Tamanho", "Grupo", "Qtd por pessoa", "Estoque do SKU", "Pessoas na função"],
            "1.6fr 1.6fr 0.7fr 1fr 0.9fr 0.9fr 1fr",
            "SELECT k.id, k.funcao, g.item, g.tamanho, k.quantidade, g.atual, (SELECT count(*) FROM employees e WHERE upper(e.cargo) = k.funcao AND e.status = 'ativo'), "
            "k.grupo "  # dgx v3
            "FROM sst_uniforme_kits k JOIN sst_uniforme_grade g ON g.id = k.grade_id WHERE k.ativo ORDER BY k.funcao, g.item, g.tamanho",
            lambda r: [
                t(r[1], 600, _ND),
                t(r[2]),
                t(r[3]),
                t(g_rot.get(r[7], r[7] or "—")),  # dgx v3
                t(str(r[4]), 600),
                t(str(r[5]) if r[5] is not None else "sem contagem"),
                t(str(r[6])),
            ],
            actionsfn=lambda r: [
                _acao(
                    f"Remover {r[2]} {r[3]} do kit de {r[1]}",
                    A + "kit-uniforme-remover",
                    "Remover",
                    [_h("id", r[0])],
                    "Removido. Recarregue.",
                )
            ],
            filtrofn=lambda r: r[1],
        ),
    )
    await safe(
        "kit-uniforme-novo",
        f10._form(
            db,
            "kit-uniforme-novo",
            "Adicionar item ao kit da função",
            "Funções = cargos dos ativos. SKUs = grade da frente 10 (Gestão de Pessoas → Uniforme/EPI).",
            "Adicionar",
            A + "kit-uniforme",
            [
                _sel("funcao", "Função*", funcoes, "span 2"),
                _sel("grade_id", "SKU*", skus, "span 2"),
                _sel(
                    "grupo", "Grupo", [{"value": "", "label": "—"}, *await _gopts(db, ("uniforme", "ambos"))]
                ),  # dgx v3
                {"key": "quantidade", "label": "Quantidade por pessoa*", "type": "text", "value": "1"},
            ],
            okMsg="Item adicionado ao kit.",
        ),
    )
    await safe(
        "kit-uniforme-entregar",
        f10._form(
            db,
            "kit-uniforme-entregar",
            "Entregar kit da função",
            "Cria a entrega em lote da frente 10 (status «solicitado») para CADA item do kit, para todos os ativos da função — ou só os alocados no posto.",
            "Solicitar entregas",
            A + "kit-uniforme-entregar",
            [
                _sel("funcao", "Função*", funcoes, "span 2"),
                _sel("post_id", "Só os alocados no posto", vazio + postos, "span 2"),
                _sel("motivo", "Motivo*", [{"value": k, "label": v} for k, v in f10._MOTIVOS], value="reposicao"),
                {"key": "prazo", "label": "Prazo de entrega", "type": "date"},
            ],
            okMsg="Entregas solicitadas.",
            showResult=True,
        ),
    )
    out.update(_out)  # o `safe` grava no dict do _helpers; `estoque` e `comunicacoes-moveis` já estão em `out`
    return out


# ----------------------------------------------------------------------------- ações: compras
@router.post("/action/compra-solicitacao")
async def compra_solicitacao(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    await _ensure(db)
    titulo = (payload.get("titulo") or "").strip()
    if not titulo:
        raise HTTPException(status_code=400, detail="Título é obrigatório.")
    itens = _itens_texto(payload.get("itens") or "", com_preco=False)
    urg = "urgente" if payload.get("urgencia") == "urgente" else "normal"
    num = await _numero(db, "purchase_requisitions", "SOL")
    quem = f10._quem(current_user)
    hoje = datetime.now(_TZ).date()
    row = await _um(
        db,
        "INSERT INTO purchase_requisitions (condominio_id, number, title, description, priority, status, requisition_date, request_date, required_date, needed_by_date, "
        "requester_id, requester_name, post_id, estimated_total, created_by, created_at, updated_at) VALUES (CAST(:c AS uuid), :n, :t, :t, :p, 'pendente', :h, :h, :r, :r, "
        "CAST(:u AS uuid), :qn, CAST(:post AS uuid), 0, CAST(:u AS uuid), now(), now()) RETURNING id::text",
        c=COND_MATRIZ,
        n=num,
        t=titulo,
        p=urg,
        h=hoje,
        r=_data(payload.get("necessario_em"), "Necessário até"),
        u=str(current_user.id),
        qn=quem,
        post=_uuid(payload.get("post_id")),
    )
    for i, it in enumerate(itens, 1):
        code, desc = await _material(db, it["ref"])
        await db.execute(
            text(
                "INSERT INTO purchase_requisition_items (requisition_id, item_number, item_code, description, quantity, quantity_requested, notes, is_urgent, status, created_at) "
                "VALUES (CAST(:r AS uuid), :i, :c, :d, :q, :q, :j, :u, 'pendente', now())"
            ),
            {
                "r": row[0],
                "i": i,
                "c": code,
                "d": desc[:200],
                "q": it["qtd"],
                "j": it["extra"] or None,
                "u": urg == "urgente",
            },
        )
    await db.commit()
    return {
        "ok": True,
        "id": row[0],
        "numero": num,
        "itens": len(itens),
        "message": f"Solicitação {num} criada com {len(itens)} item(ns) — pendente de aprovação.",
    }


@router.post("/action/compra-solicitacao-status")
async def compra_solicitacao_status(
    current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)
) -> dict:
    await _ensure(db)
    sid, novo, obs = _uuid(payload.get("id")), payload.get("status") or "", (payload.get("observacao") or "").strip()
    if not sid or novo not in ("aprovada", "negada"):
        raise HTTPException(status_code=400, detail="Solicitação e status (aprovada|negada) são obrigatórios.")
    if novo == "negada" and not obs:
        raise HTTPException(status_code=400, detail="Negar pede o motivo.")
    r = await _um(db, "SELECT status, number FROM purchase_requisitions WHERE id = CAST(:s AS uuid)", s=sid)
    if not r:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada.")
    if r[0] != "pendente":
        raise HTTPException(status_code=409, detail=f"Solicitação está '{r[0]}'.")
    col = (
        "approval_date = now(), approved_by = CAST(:u AS uuid), approval_notes = :o"
        if novo == "aprovada"
        else "rejection_date = now(), rejected_by = CAST(:u AS uuid), rejection_reason = :o"
    )
    await db.execute(
        text(f"UPDATE purchase_requisitions SET status = :s, {col}, updated_at = now() WHERE id = CAST(:id AS uuid)"),
        {"s": novo, "u": str(current_user.id), "o": obs or None, "id": sid},
    )
    await db.commit()
    return {"ok": True, "message": f"Solicitação {r[1]}: {novo}."}


@router.post("/action/compra-pedido")
async def compra_pedido(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    await _ensure(db)
    sup, req = _uuid(payload.get("supplier_id")), _uuid(payload.get("requisition_id"))
    if not sup:
        raise HTTPException(status_code=400, detail="Fornecedor é obrigatório.")
    if not await _um(db, "SELECT 1 FROM suppliers WHERE id = CAST(:s AS uuid)", s=sup):
        raise HTTPException(status_code=404, detail="Fornecedor não encontrado.")
    itens: list[dict] = []
    if (payload.get("itens") or "").strip():
        for it in _itens_texto(payload["itens"], com_preco=True):
            code, desc = await _material(db, it["ref"])
            itens.append({"code": code, "desc": desc, "qtd": it["qtd"], "preco": it["preco"] or 0.0, "req_item": None})
    if req:
        r = await _um(db, "SELECT status, number FROM purchase_requisitions WHERE id = CAST(:r AS uuid)", r=req)
        if not r:
            raise HTTPException(status_code=404, detail="Solicitação não encontrada.")
        if r[0] != "aprovada":
            raise HTTPException(status_code=409, detail=f"Solicitação {r[1]} está '{r[0]}' — só aprovada vira pedido.")
        req_itens = (
            await db.execute(
                text(
                    "SELECT id::text, item_code, description, quantity, coalesce(estimated_unit_price, estimated_price, 0) FROM purchase_requisition_items i WHERE i.requisition_id = CAST(:r AS uuid) ORDER BY item_number"
                ),
                {"r": req},
            )
        ).fetchall()
        for it in itens:  # itens digitados (com preço) casam com os da solicitação por código ou descrição
            ri = next(
                (
                    x
                    for x in req_itens
                    if (it["code"] and x[1] == it["code"])
                    or (x[2] or "").strip().lower() == (it["desc"] or "").strip().lower()
                ),
                None,
            )
            it["req_item"] = ri[0] if ri else None
        if not itens:  # copia os itens — a soma das quantidades é a mesma (oráculo confere)
            for ri in req_itens:
                itens.append(
                    {"code": ri[1], "desc": ri[2], "qtd": float(ri[3]), "preco": float(ri[4] or 0), "req_item": ri[0]}
                )
    if not itens:
        raise HTTPException(status_code=400, detail="Informe os itens ou escolha uma solicitação aprovada.")
    cond_id = f10._int(payload.get("condicao_pagamento_id"), "Condição")
    cond = (
        await _um(db, "SELECT nome, parcelas FROM fin_condicoes_pagamento WHERE id = :i AND ativo", i=cond_id)
        if cond_id
        else None
    )
    total = round(sum(i["qtd"] * i["preco"] for i in itens), 2)
    num = await _numero(db, "purchase_orders", "PED")
    row = await _um(
        db,
        "INSERT INTO purchase_orders (condominio_id, supplier_id, requisition_id, number, status, order_date, expected_delivery_date, payment_condition, payment_installments, condicao_pagamento_id, "
        "subtotal, total, notes, created_by, created_at, updated_at) VALUES (CAST(:c AS uuid), CAST(:s AS uuid), CAST(:r AS uuid), :n, 'rascunho', :h, :p, :pc, :pi, :ci, :t, :t, :o, CAST(:u AS uuid), now(), now()) RETURNING id::text",
        c=COND_MATRIZ,
        s=sup,
        r=req,
        n=num,
        h=datetime.now(_TZ).date(),
        p=_data(payload.get("previsao"), "Previsão"),
        pc=cond[0] if cond else None,
        pi=cond[1] if cond else None,
        ci=cond_id if cond else None,
        t=total,
        o=(payload.get("observacao") or "").strip() or None,
        u=str(current_user.id),
    )
    for i, it in enumerate(itens, 1):
        await db.execute(
            text(
                "INSERT INTO purchase_order_items (order_id, requisition_item_id, item_number, item_code, description, quantity_ordered, unit_price, total, created_at) "
                "VALUES (CAST(:o AS uuid), CAST(:ri AS uuid), :i, :c, :d, :q, :p, :t, now())"
            ),
            {
                "o": row[0],
                "ri": it["req_item"],
                "i": i,
                "c": it["code"],
                "d": (it["desc"] or "—")[:200],
                "q": it["qtd"],
                "p": it["preco"],
                "t": round(it["qtd"] * it["preco"], 2),
            },
        )
    if req:
        await db.execute(
            text(
                "UPDATE purchase_requisitions SET status = 'atendida', updated_at = now() WHERE id = CAST(:r AS uuid)"
            ),
            {"r": req},
        )
    await db.commit()
    return {
        "ok": True,
        "id": row[0],
        "numero": num,
        "itens": len(itens),
        "total": total,
        "message": f"Pedido {num} criado: {len(itens)} item(ns), {brl(total)}"
        + (f", {cond[0]}" if cond else "")
        + ". Envie ao fornecedor em Pedidos.",
    }


@router.post("/action/compra-pedido-enviar")
async def compra_pedido_enviar(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    await _ensure(db)
    oid = _uuid(payload.get("id"))
    r = await _um(db, "SELECT status, number FROM purchase_orders WHERE id = CAST(:o AS uuid)", o=oid) if oid else None
    if not r:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    if r[0] != "rascunho":
        raise HTTPException(status_code=409, detail=f"Pedido está '{r[0]}'.")
    await db.execute(
        text(
            "UPDATE purchase_orders SET status = 'enviado', sent_date = now(), updated_at = now() WHERE id = CAST(:o AS uuid)"
        ),
        {"o": oid},
    )
    await db.commit()
    return {"ok": True, "message": f"Pedido {r[1]} marcado como enviado."}


@router.post("/action/compra-pedido-cancelar")
async def compra_pedido_cancelar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)
) -> dict:
    await _ensure(db)
    oid, motivo = _uuid(payload.get("id")), (payload.get("motivo") or "").strip()
    if not oid or not motivo:
        raise HTTPException(status_code=400, detail="Pedido e motivo são obrigatórios.")
    r = await _um(db, "SELECT status, number FROM purchase_orders WHERE id = CAST(:o AS uuid)", o=oid)
    if not r or r[0] not in ("rascunho", "enviado"):
        raise HTTPException(status_code=409, detail="Só pedido em rascunho/enviado pode ser cancelado.")
    await db.execute(
        text(
            "UPDATE purchase_orders SET status = 'cancelado', cancelled_at = now(), cancelled_by = CAST(:u AS uuid), cancellation_reason = :m, updated_at = now() WHERE id = CAST(:o AS uuid)"
        ),
        {"u": str(current_user.id), "m": motivo, "o": oid},
    )
    await db.commit()
    return {"ok": True, "message": f"Pedido {r[1]} cancelado."}


async def _receber(
    db,
    oid: str,
    quem: str,
    *,
    receipt_type: str,
    invoice_number=None,
    invoice_key=None,
    invoice_date=None,
    invoice_total=None,
    nfe_id=None,
    obs=None,
) -> tuple[str, str]:
    """`goods_receipts` + pedido recebido. Chave da NF-e é única (índice) → conferir duas vezes é 409."""
    o = await _um(
        db, "SELECT status, number, supplier_id::text, total FROM purchase_orders WHERE id = CAST(:o AS uuid)", o=oid
    )
    if not o:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    if o[0] not in ("rascunho", "enviado"):
        raise HTTPException(status_code=409, detail=f"Pedido {o[1]} está '{o[0]}' — não recebe de novo.")
    num = await _numero(db, "goods_receipts", "REC")
    try:
        g = await _um(
            db,
            "INSERT INTO goods_receipts (condominio_id, order_id, supplier_id, number, receipt_type, status, receipt_date, invoice_number, invoice_key, invoice_date, invoice_total, "
            "total_expected, total_received, received_at, receiver_name, nfe_entrada_id, notes, created_at, updated_at) VALUES (CAST(:c AS uuid), CAST(:o AS uuid), CAST(:s AS uuid), :n, :rt, 'conferido', :h, :inum, :ik, :idt, :it, "
            ":te, :tr, now(), :q, :nid, :obs, now(), now()) RETURNING id::text",
            c=COND_MATRIZ,
            o=oid,
            s=o[2],
            n=num,
            rt=receipt_type,
            h=datetime.now(_TZ).date(),
            inum=invoice_number,
            ik=invoice_key,
            idt=invoice_date,
            it=invoice_total,
            te=o[3],
            tr=invoice_total if invoice_total is not None else o[3],
            q=quem,
            nid=nfe_id,
            obs=obs,
        )
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Esta NF-e já foi conferida (chave única).") from None
    await db.execute(
        text(
            "UPDATE purchase_orders SET status = 'recebido', actual_delivery_date = :h, received_total = coalesce(received_total,0) + :v, invoiced_total = coalesce(invoiced_total,0) + :v, updated_at = now() WHERE id = CAST(:o AS uuid)"
        ),
        {
            "h": datetime.now(_TZ).date(),
            "v": float(invoice_total if invoice_total is not None else o[3] or 0),
            "o": oid,
        },
    )
    return g[0], o[1]


@router.post("/action/compra-pedido-receber")
async def compra_pedido_receber(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    """Recebimento manual (sem NF-e): itens do pedido com código de material entram no estoque UMA vez (ref `PED-nº`)."""
    await _ensure(db)
    oid = _uuid(payload.get("id"))
    if not oid:
        raise HTTPException(status_code=400, detail="Pedido é obrigatório.")
    quem = f10._quem(current_user)
    gid, num = await _receber(
        db,
        oid,
        quem,
        receipt_type="manual",
        invoice_number=(payload.get("invoice_number") or "").strip() or None,
        obs=(payload.get("observacao") or "").strip() or None,
    )
    entraram, sem_codigo = 0, 0
    for it in (
        await db.execute(
            text(
                "SELECT item_code, quantity_ordered, unit_price FROM purchase_order_items WHERE order_id = CAST(:o AS uuid)"
            ),
            {"o": oid},
        )
    ).fetchall():
        if not it[0]:
            sem_codigo += 1
            continue
        if await _mov(
            db,
            it[0],
            "entrada",
            float(it[1]),
            float(it[2] or 0) or None,
            f"Recebimento manual do pedido {num}",
            quem,
            ref_chave=num,
        ):
            entraram += 1
    await db.execute(
        text(
            "UPDATE purchase_order_items SET quantity_received = quantity_ordered, actual_delivery_date = :h WHERE order_id = CAST(:o AS uuid)"
        ),
        {"h": datetime.now(_TZ).date(), "o": oid},
    )
    await db.commit()
    return {
        "ok": True,
        "recebimento_id": gid,
        "itens_no_estoque": entraram,
        "itens_sem_codigo": sem_codigo,
        "message": f"Pedido {num} recebido: {entraram} item(ns) entraram no estoque"
        + (f"; {sem_codigo} sem código de material (não estocados)" if sem_codigo else "")
        + ".",
    }


@router.post("/action/compra-nf-conferir")
async def compra_nf_conferir(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    """Casa a NF-e com o pedido (mesmo fornecedor; sugerido o de mesmo valor) e registra a entrada no estoque
    exatamente uma vez. O sync SEFAZ já somou o saldo das NF-e `processada` — aqui só o movimento é
    registrado (ref = chave), sem somar de novo. NF sem XML (resumo) baixa o pedido e não move estoque."""
    await _ensure(db)
    nid, oid = f10._int(payload.get("nfe_id"), "NF-e"), _uuid(payload.get("order_id"))
    if not nid:
        raise HTTPException(status_code=400, detail="NF-e é obrigatória.")
    n = await _um(
        db,
        "SELECT chave_acesso, numero, regexp_replace(coalesce(emitente_cnpj,''),'\\D','','g'), emitente_nome, data_emissao, valor_total, xml_raw, coalesce(processada,false) FROM nfe_entradas WHERE id = :i",
        i=nid,
    )
    if not n:
        raise HTTPException(status_code=404, detail="NF-e não encontrada.")
    if await _um(db, "SELECT 1 FROM goods_receipts WHERE invoice_key = :k", k=n[0]):
        raise HTTPException(status_code=409, detail="Esta NF-e já foi conferida.")
    if not oid:
        cands = (
            await db.execute(
                text(
                    "SELECT o.id::text FROM purchase_orders o JOIN suppliers s ON s.id = o.supplier_id WHERE o.status IN ('rascunho','enviado') "
                    "AND regexp_replace(coalesce(s.cpf_cnpj,''),'\\D','','g') = :c AND abs(coalesce(o.total,0) - :v) < 0.01"
                ),
                {"c": n[2], "v": float(n[5] or 0)},
            )
        ).fetchall()
        if len(cands) != 1:
            raise HTTPException(
                status_code=400,
                detail=f"{len(cands)} pedido(s) aberto(s) deste fornecedor com este valor — escolha o pedido.",
            )
        oid = cands[0][0]
    o = await _um(
        db,
        "SELECT regexp_replace(coalesce(s.cpf_cnpj,''),'\\D','','g') FROM purchase_orders o JOIN suppliers s ON s.id = o.supplier_id WHERE o.id = CAST(:o AS uuid)",
        o=oid,
    )
    if not o:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    if o[0] != n[2]:
        raise HTTPException(
            status_code=409, detail="O pedido é de outro fornecedor (CNPJ diferente do emitente da NF-e)."
        )
    quem = f10._quem(current_user)
    gid, num = await _receber(
        db,
        oid,
        quem,
        receipt_type="nfe",
        invoice_number=n[1],
        invoice_key=n[0],
        invoice_date=n[4],
        invoice_total=float(n[5] or 0),
        nfe_id=nid,
    )
    movs = 0
    if n[6] and n[7]:
        for cod, _desc, q, v in _itens_xml(n[6]):
            if not await _um(db, "SELECT 1 FROM nfe_compras_estoque WHERE item_code = :c", c=cod):
                continue  # o sync não conheceu este item (qtd 0 / sem código) — nada a registrar
            if await _mov(
                db,
                cod,
                "entrada",
                q,
                v,
                f"NF-e {n[1] or ''} de {(n[3] or '')[:40]} — pedido {num}",
                quem,
                ref_chave=n[0],
                ajusta_saldo=False,
            ):
                movs += 1
    await db.commit()
    aviso = (
        ""
        if n[6]
        else " NF sem XML completo (resumo da SEFAZ): estoque não movimentado — manifeste a NF-e para receber o XML."
    )
    return {
        "ok": True,
        "recebimento_id": gid,
        "movimentos": movs,
        "message": f"NF-e {n[1] or ''} conferida contra o pedido {num}: {movs} movimento(s) de entrada registrado(s) (saldo já lançado pelo sync SEFAZ).{aviso}",
    }


# ----------------------------------------------------------------------------- ações: materiais e estoque
@router.post("/action/material")
async def material(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    await _ensure(db)
    desc, grupo, un = (
        (payload.get("descricao") or "").strip(),
        payload.get("grupo") or "",
        (payload.get("unidade") or "UN").strip().upper()[:6],
    )
    if not desc:
        raise HTTPException(status_code=400, detail="Descrição e grupo são obrigatórios.")
    from ._dgx_v3_frota_app import garantir_grupo  # noqa: PLC0415 — dgx v3: grupo novo nasce, não é recusado

    grupo = await garantir_grupo(db, grupo)
    code = (payload.get("item_code") or "").strip().upper()[:60]
    if not code:
        code = f"MAT-{(await db.execute(text('SELECT count(*) + 1 FROM nfe_compras_estoque WHERE item_code LIKE :p'), {'p': 'MAT-%'})).scalar():04d}"
    mi, ma = f10._dec(payload.get("minimo"), "Mínimo"), f10._dec(payload.get("maximo"), "Máximo")
    if mi is not None and ma is not None and ma < mi:
        raise HTTPException(status_code=400, detail="Máximo não pode ser menor que o mínimo.")
    custo, saldo = (
        f10._dec(payload.get("custo"), "Custo") or 0.0,
        f10._dec(payload.get("saldo_inicial"), "Saldo inicial") or 0.0,
    )
    try:
        await db.execute(
            text(
                "INSERT INTO nfe_compras_estoque (item_code, descricao, unidade, qty_on_hand, unit_cost, avg_cost, grupo, minimo, maximo, origem, updated_at) VALUES (:c, :d, :u, 0, :cu, :cu, :g, :mi, :ma, 'manual', now())"
            ),
            {"c": code, "d": desc[:200], "u": un, "cu": custo, "g": grupo, "mi": mi, "ma": ma},
        )
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail=f"Código {code} já existe.") from None
    if saldo > 0:
        await _mov(db, code, "ajuste", saldo, None, "Saldo inicial (cadastro)", f10._quem(current_user))
    await db.commit()
    return {"ok": True, "item_code": code, "message": f"Material {code} cadastrado."}


@router.post("/action/material-editar")
async def material_editar(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    await _ensure(db)
    code = (payload.get("item_code") or "").strip()
    grupo = payload.get("grupo") or None
    if grupo:
        from ._dgx_v3_frota_app import garantir_grupo  # noqa: PLC0415 — dgx v3

        grupo = await garantir_grupo(db, grupo)
    mi, ma = f10._dec(payload.get("minimo"), "Mínimo"), f10._dec(payload.get("maximo"), "Máximo")
    if mi is not None and ma is not None and ma < mi:
        raise HTTPException(status_code=400, detail="Máximo não pode ser menor que o mínimo.")
    r = await db.execute(
        text(
            "UPDATE nfe_compras_estoque SET grupo = :g, minimo = :mi, maximo = :ma, descricao = coalesce(nullif(:d,''), descricao), updated_at = now() WHERE item_code = :c AND ativo"
        ),
        {"g": grupo, "mi": mi, "ma": ma, "d": (payload.get("descricao") or "").strip()[:200], "c": code},
    )
    if not r.rowcount:
        raise HTTPException(status_code=404, detail="Material não encontrado.")
    await db.commit()
    return {"ok": True, "message": f"Material {code} atualizado."}


@router.post("/action/material-inativar")
async def material_inativar(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    await _ensure(db)
    r = await db.execute(
        text("UPDATE nfe_compras_estoque SET ativo = false, updated_at = now() WHERE item_code = :c AND ativo"),
        {"c": (payload.get("item_code") or "").strip()},
    )
    if not r.rowcount:
        raise HTTPException(status_code=404, detail="Material não encontrado.")
    await db.commit()
    return {"ok": True, "message": "Material inativado (histórico preservado)."}


@router.post("/action/estoque-movimento")
async def estoque_movimento(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    await _ensure(db)
    code, tipo, motivo = (
        (payload.get("item_code") or "").strip(),
        payload.get("tipo") or "",
        (payload.get("motivo") or "").strip(),
    )
    qtd = f10._dec(payload.get("quantidade"), "Quantidade")
    if not code or tipo not in ("entrada", "saida", "ajuste") or qtd is None or not motivo:
        raise HTTPException(status_code=400, detail="Material, tipo, quantidade e motivo são obrigatórios.")
    quem = f10._quem(current_user)
    if tipo == "saida":
        if qtd <= 0:
            raise HTTPException(status_code=400, detail="Quantidade deve ser maior que zero.")
        # MESMO caminho das baixas por serviço: reduz saldo, registra e posta o COGS no razão (psycopg2 → thread)
        from modules.financial.services.estoque_real_service import EstoqueRealService

        try:
            r = await asyncio.to_thread(
                EstoqueRealService().registrar_saida,
                code,
                qtd,
                (payload.get("destino") or "").strip() or None,
                f"{motivo} · {quem}",
            )
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e)) from None
        return {
            "ok": True,
            **r,
            "message": f"Saída de {qtd:g} × {r['item']}: custo {brl(r['custo_total'])} lançado; restam {r['saldo_restante']:g}.",
        }
    if tipo == "entrada" and qtd <= 0:
        raise HTTPException(status_code=400, detail="Quantidade deve ser maior que zero.")
    mid = await _mov(
        db, code, tipo, qtd, f10._dec(payload.get("custo"), "Custo") if tipo == "entrada" else None, motivo, quem
    )
    await db.commit()
    return {
        "ok": True,
        "movimento_id": mid,
        "message": f"{'Entrada' if tipo == 'entrada' else 'Ajuste'} registrado (#{mid}).",
    }


# ----------------------------------------------------------------------------- ações: fornecedores
@router.post("/action/fornecedor")
async def fornecedor(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    await _ensure(db)
    nome, cnpj, cat = (payload.get("name") or "").strip(), _cnpj(payload.get("cpf_cnpj")), payload.get("category") or ""
    if not nome or len(cnpj) not in (11, 14) or not cat:
        raise HTTPException(status_code=400, detail="Razão social, CNPJ (14 dígitos) e categoria são obrigatórios.")
    try:
        row = await _um(
            db,
            "INSERT INTO suppliers (id, condominio_id, cpf_cnpj, name, supplier_type, category, status, contact_name, phone, email, created_by, created_at, updated_at) "
            "VALUES (gen_random_uuid(), CAST(:c AS uuid), :cnpj, :n, :tipo, :cat, 'ativo', :ct, :ph, :em, CAST(:u AS uuid), now(), now()) RETURNING id::text",
            c=COND_MATRIZ,
            cnpj=cnpj,
            n=nome[:180],
            tipo="pessoa_fisica" if len(cnpj) == 11 else "pessoa_juridica",
            cat=cat,
            ct=(payload.get("contact_name") or "").strip() or None,
            ph=(payload.get("phone") or "").strip() or None,
            em=(payload.get("email") or "").strip() or None,
            u=str(current_user.id),
        )
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Já existe fornecedor com este CNPJ.") from None
    await db.commit()
    return {"ok": True, "id": row[0], "message": f"Fornecedor {nome} cadastrado."}


# ----------------------------------------------------------------------------- ações: equipamentos móveis
@router.post("/action/equipamento-movel")
async def equipamento_movel(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    await _ensure(db)
    tipo, serie = payload.get("tipo") or "", (payload.get("numero_serie") or "").strip().upper()
    if tipo not in dict(TIPOS_MOVEIS) or not serie:
        raise HTTPException(status_code=400, detail="Tipo e número de série são obrigatórios.")
    try:
        row = await _um(
            db,
            "INSERT INTO equipamentos_controlados (tipo, numero_serie, modelo, imei, numero_linha, operadora, plano_mensal, post_id) "
            "VALUES (:t, :s, :m, :i, :l, :o, :p, CAST(:post AS uuid)) RETURNING id::text",
            t=tipo,
            s=serie[:60],
            m=(payload.get("modelo") or "").strip()[:80] or None,
            i=(payload.get("imei") or "").strip()[:40] or None,
            l=(payload.get("numero_linha") or "").strip()[:20] or None,
            o=(payload.get("operadora") or "").strip()[:40] or None,
            p=f10._dec(payload.get("plano_mensal"), "Plano"),
            post=_uuid(payload.get("post_id")),
        )
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail=f"Número de série {serie} já cadastrado.") from None
    await db.commit()
    return {"ok": True, "id": row[0], "message": f"{dict(TIPOS_MOVEIS)[tipo]} {serie} cadastrado."}


@router.post("/action/equipamento-movel-entregar")
async def equipamento_movel_entregar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)
) -> dict:
    await _ensure(db)
    eq, emp = _uuid(payload.get("equipamento_id")), _uuid(payload.get("employee_id"))
    if not eq or not emp:
        raise HTTPException(status_code=400, detail="Equipamento e responsável são obrigatórios.")
    try:  # MESMA entrega da frente 05 (posse única pelo índice parcial)
        r = await cv.entregar(
            db,
            equipamento_id=eq,
            employee_id=emp,
            user_id=str(current_user.id),
            observacao=(payload.get("observacao") or "").strip() or None,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    return {"ok": True, **r, "message": "Entrega registrada."}


@router.post("/action/equipamento-movel-devolver")
async def equipamento_movel_devolver(
    current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)
) -> dict:
    await _ensure(db)
    eq = _uuid(payload.get("equipamento_id"))
    if not eq:
        raise HTTPException(status_code=400, detail="Equipamento é obrigatório.")
    try:
        r = await cv.devolver(
            db,
            equipamento_id=eq,
            user_id=str(current_user.id),
            observacao=(payload.get("observacao") or "").strip() or None,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    return {"ok": True, **r, "message": "Devolução registrada."}


# ----------------------------------------------------------------------------- ações: kits
@router.post("/action/kit-uniforme")
async def kit_uniforme(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    await _ensure(db)
    funcao, gid, qtd = (
        (payload.get("funcao") or "").strip().upper(),
        f10._int(payload.get("grade_id"), "SKU"),
        f10._int(payload.get("quantidade"), "Quantidade", 1),
    )
    if not funcao or not gid or not qtd:
        raise HTTPException(status_code=400, detail="Função, SKU e quantidade são obrigatórios.")
    grupo = (payload.get("grupo") or "").strip() or None
    if grupo:  # dgx v3 — texto livre cria o grupo
        from ._dgx_v3_frota_app import garantir_grupo  # noqa: PLC0415

        grupo = await garantir_grupo(db, grupo, "uniforme")
    if not await _um(db, "SELECT 1 FROM sst_uniforme_grade WHERE id = :g AND ativo", g=gid):
        raise HTTPException(status_code=404, detail="SKU não encontrado.")
    await db.execute(
        text(
            "INSERT INTO sst_uniforme_kits (funcao, grade_id, quantidade, grupo, created_by) VALUES (:f, :g, :q, :gr, :u) "  # dgx v3
            "ON CONFLICT (funcao, grade_id) DO UPDATE SET quantidade = EXCLUDED.quantidade, grupo = EXCLUDED.grupo, ativo = true"
        ),
        {"f": funcao[:80], "g": gid, "q": qtd, "gr": grupo, "u": f10._quem(current_user)},
    )
    await db.commit()
    return {"ok": True, "message": f"Kit de {funcao}: item gravado ({qtd} por pessoa)."}


@router.post("/action/kit-uniforme-remover")
async def kit_uniforme_remover(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    await _ensure(db)
    r = await db.execute(
        text("UPDATE sst_uniforme_kits SET ativo = false WHERE id = :i AND ativo"),
        {"i": f10._int(payload.get("id"), "id")},
    )
    if not r.rowcount:
        raise HTTPException(status_code=404, detail="Item do kit não encontrado.")
    await db.commit()
    return {"ok": True, "message": "Item removido do kit."}


async def entregar_kit(db, current_user, funcao: str, post_id: str | None, motivo: str, prazo: str | None) -> dict:
    """Uma entrega em lote da frente 10 POR ITEM do kit, para as pessoas da função (opcionalmente só as do posto).
    Regra: N itens no kit → N solicitações por pessoa. Pessoa sem CPF no cadastro não é endereçável pelo lote."""
    kit = (
        await db.execute(
            text("SELECT grade_id, quantidade FROM sst_uniforme_kits WHERE funcao = :f AND ativo ORDER BY id"),
            {"f": funcao},
        )
    ).fetchall()
    if not kit:
        raise HTTPException(status_code=404, detail=f"A função {funcao} não tem kit. Monte em «Adicionar item ao kit».")
    sql = "SELECT e.id::text, e.cpf FROM employees e WHERE upper(e.cargo) = :f AND e.status = 'ativo' AND e.data_demissao IS NULL AND coalesce(e.is_homologacao,false) = false"
    if post_id:
        sql += " AND EXISTS (SELECT 1 FROM allocations a WHERE a.employee_id = e.id AND a.post_id::text = :p AND coalesce(a.is_active,true))"
    pessoas = (await db.execute(text(sql), {"f": funcao, "p": post_id})).fetchall()
    cpfs = [_cnpj(p[1]) for p in pessoas if _cnpj(p[1])]
    if not cpfs:
        raise HTTPException(
            status_code=400,
            detail=f"Nenhum ativo com CPF na função {funcao}" + (" neste posto" if post_id else "") + ".",
        )
    lotes = []
    for gid, qtd in kit:
        r = await f10.uniforme_entrega_lote(
            current_user,
            {"grade_id": gid, "quantidade": qtd, "motivo": motivo, "prazo": prazo or "", "cpfs": "\n".join(cpfs)},
            db,
        )
        lotes.append(r["lote"])
    return {
        "ok": True,
        "itens_do_kit": len(kit),
        "pessoas": len(cpfs),
        "sem_cpf": len(pessoas) - len(cpfs),
        "lotes": lotes,
        "message": f"Kit de {funcao}: {len(kit)} item(ns) × {len(cpfs)} pessoa(s) = {len(kit) * len(cpfs)} solicitação(ões) de entrega (lotes {', '.join(lotes)})."
        + (f" {len(pessoas) - len(cpfs)} pessoa(s) sem CPF ficaram de fora." if len(pessoas) > len(cpfs) else ""),
    }


@router.post("/action/kit-uniforme-entregar")
async def kit_uniforme_entregar(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    await _ensure(db)
    funcao, motivo = (payload.get("funcao") or "").strip().upper(), payload.get("motivo") or "reposicao"
    if not funcao:
        raise HTTPException(status_code=400, detail="Função é obrigatória.")
    if motivo not in dict(f10._MOTIVOS):
        raise HTTPException(status_code=400, detail="Motivo inválido.")
    return await entregar_kit(
        db, current_user, funcao, _uuid(payload.get("post_id")), motivo, (payload.get("prazo") or "").strip() or None
    )


def usuario_fixture(email: str = "FIXTURE DGX F9"):
    """Para o oráculo chamar as ações sem HTTP (as funções só leem `.email`/`.id`)."""
    return SimpleNamespace(email=email, id="00000000-0000-0000-0000-000000000001")

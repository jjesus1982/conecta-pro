"""DGX V3 (24/09/2026) — Frota como no APP Frotas do DGX: manutenção como ENTIDADE, multa que vira
conta a pagar e tem ciclo de recurso, itens de vistoria CONFIGURÁVEIS e grupos hierárquicos de
materiais/uniformes (lacunas #6, #7, #8 e #9 de docs/dgx/lacunas/suprimentos_frotas_sesmt_config.md).

Estende a frente 10 (`_frente_10`: veículos, leituras, vistorias) e a DGX F10 (`_dgx_f10_frotas`:
saídas, multas, trocas, locações, requisições) — não as substitui. As decisões delas continuam
valendo, em código:

  · CONCLUIR uma manutenção que trocou óleo/pneu/correia/filtro/pastilha NÃO escreve em
    `frota_leituras`: chama a MESMA `f10.frota_troca` da F10, que valida hodômetro, grava a leitura
    tipada com `proxima_km` e atualiza `frota_veiculos.km_proxima_troca_*` para o painel da frente 10
    continuar dizendo a verdade. Uma troca por TIPO por manutenção — o oráculo conta.
  · CONTA a pagar (manutenção e multa) nasce pelo MESMO `rd_action_payable` → `PayableService`, e
    NUNCA é paga aqui. Idempotente por `payable_id`: a 2ª chamada devolve o mesmo título.
  · RECURSO DEFERIDO cancela o título AINDA PENDENTE por `PayableService.reject_account` — nunca por
    UPDATE direto em `payable_accounts`. Título já pago/cancelado fica como está e a tela diz isso.
  · VISTORIA passa a montar o formulário por `frota_vistoria_itens`. A tabela nasce SEMEADA com as
    5 áreas fixas que a frente 10 usa hoje (`_AREAS`), com as MESMAS chaves (`aval_<cod>`/`foto_<cod>`)
    e os MESMOS rótulos — o formulário publicado é campo a campo o de ontem. Tabela vazia → a tela é
    literalmente a da frente 10 (mesmo endpoint), e o oráculo compara os dois dicionários.
  · Item de vistoria com `impede_locomocao` REPROVADO na última vistoria do veículo bloqueia
    «Registrar saída» com 409 nomeando o item (gancho `bloqueio_locomocao`, chamado pela F10).
  · GRUPOS: `sup_grupos` nasce semeada dos 6 grupos que a F9 já usava e dos valores distintos de
    `nfe_compras_estoque.grupo`. Texto livre continua aceito — `garantir_grupo` cria o grupo em vez
    de recusar o material.

Plug: `equipamentos.py` e `suprimentos.py` importam `router`/`MENU_*` e chamam `telas_*(db, out)`.
DDL idempotente em `_ensure(db)`, chamada por `telas_*()` e por cada ação.
"""

from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from sqlalchemy import text

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db

router = APIRouter()

_ICO_T = "M3 3v18h18"
_ICO_N = "M12 5v14M5 12h14"
MENU_EQUIP = [
    {"id": "frota-manutencoes", "label": "Frota · Manutenções", "icon": _ICO_T},
    {"id": "frota-manutencao-nova", "label": "Frota · Nova manutenção", "icon": _ICO_N},
    {"id": "frota-vistoria-itens", "label": "Frota · Itens de vistoria", "icon": _ICO_T},
    {"id": "frota-vistoria-item-novo", "label": "Frota · Novo item de vistoria", "icon": _ICO_N},
]
MENU_SUP = [
    {"id": "sup-grupos", "label": "Grupos de materiais", "icon": _ICO_T, "grupo": "Materiais & estoque"},
    {"id": "sup-grupo-novo", "label": "Novo grupo", "icon": _ICO_N, "grupo": "Materiais & estoque"},
]

from modules.operacional.controllers.redesign_data_controller import _helpers, b, brl, t  # noqa: E402

# módulos inteiros, nunca nomes: o discovery importa estes arquivos pela metade (ciclo
# data_controller → discovery → equipamentos → aqui) e nome resolvido na chamada não quebra o ciclo.
from . import _dgx_f10_frotas as f10  # noqa: E402
from . import _frente_10 as fr10  # noqa: E402

_ND = "#0F1B3A"
_A = "/api/v1/redesign/action/"

TIPOS_MANUT = [("preventiva", "Preventiva"), ("corretiva", "Corretiva"), ("revisao", "Revisão")]
_ST_MANUT = {
    "solicitada": ("Solicitada", "warn"),
    "aprovada": ("Aprovada", "info"),
    "em_execucao": ("Em execução", "info"),
    "concluida": ("Concluída", "ok"),
    "cancelada": ("Cancelada", "bad"),
}
TIPOS_ITEM_MANUT = [("peca", "Peça"), ("servico", "Serviço")]
#: Intervalo de KM da casa para a próxima troca quando a MANUTENÇÃO gera a troca sozinha (como o
#: «Gerar troca de óleo» do DGX). Não é lei nem manual do fabricante — é a régua declarada aqui,
#: única, para o Jordan corrigir num lugar só. Quem quiser outro número usa «Frota · Nova troca».
INTERVALO_KM = {
    "troca_oleo": 10000,
    "troca_filtro": 10000,
    "troca_pastilha": 30000,
    "troca_pneu": 40000,
    "troca_correia": 60000,
}
#: Ordem IMPORTA: "filtro de óleo" é filtro, não óleo; "pastilha" antes de qualquer outra.
_PALAVRA_TROCA = [
    ("pastilha", "troca_pastilha"),
    ("correia", "troca_correia"),
    ("filtro", "troca_filtro"),
    ("pneu", "troca_pneu"),
    ("óleo", "troca_oleo"),
    ("oleo", "troca_oleo"),
]
TIPOS_DADO = [("sim_nao", "Sim / Não"), ("nota", "Bom / Ruim"), ("texto", "Texto"), ("foto", "Só foto")]
RESULTADOS_RECURSO = [
    ("pendente", "Pendente"),
    ("deferido", "Deferido"),
    ("parcial", "Parcial"),
    ("indeferido", "Indeferido"),
]
TIPOS_GRUPO = [("material", "Material"), ("uniforme", "Uniforme"), ("ambos", "Ambos")]
#: Os 6 grupos que a F9 já usava em texto fixo viram as raízes de `sup_grupos` (tipo por natureza).
_SEED_GRUPOS = [
    ("uniforme", "Uniforme", "uniforme"),
    ("epi", "EPI", "ambos"),
    ("material", "Material", "material"),
    ("equipamento", "Equipamento", "material"),
    ("limpeza", "Limpeza", "material"),
    ("escritorio", "Escritório", "material"),
]

DDL = """
CREATE TABLE IF NOT EXISTS frota_manutencoes (
  id serial PRIMARY KEY, veiculo_id integer NOT NULL REFERENCES frota_veiculos(id),
  tipo varchar(12) NOT NULL DEFAULT 'corretiva' CHECK (tipo IN ('preventiva','corretiva','revisao')),
  fornecedor_id uuid, km integer CHECK (km IS NULL OR km >= 0),
  previsao_entrada date, previsao_saida date, liberacao date,
  itens jsonb NOT NULL DEFAULT '[]'::jsonb,
  valor_total numeric(12,2) NOT NULL DEFAULT 0 CHECK (valor_total >= 0),
  centro_custo varchar(60),
  status varchar(12) NOT NULL DEFAULT 'solicitada'
    CHECK (status IN ('solicitada','aprovada','em_execucao','concluida','cancelada')),
  aprovado_por varchar(120), aprovado_em timestamptz,
  payable_id uuid, solicitacao_material_id integer,
  km_conclusao integer, concluida_em timestamptz,
  observacao text, created_at timestamptz NOT NULL DEFAULT now(), created_by varchar(120));
CREATE INDEX IF NOT EXISTS ix_frota_manutencoes_veiculo ON frota_manutencoes (veiculo_id, created_at DESC);
CREATE TABLE IF NOT EXISTS frota_vistoria_itens (
  id serial PRIMARY KEY, codigo varchar(40) NOT NULL UNIQUE, grupo varchar(60) NOT NULL DEFAULT 'Geral',
  ordem integer NOT NULL DEFAULT 0, texto varchar(160) NOT NULL,
  tipo_dado varchar(10) NOT NULL DEFAULT 'nota' CHECK (tipo_dado IN ('sim_nao','nota','texto','foto')),
  foto_obrigatoria boolean NOT NULL DEFAULT false, texto_obrigatorio boolean NOT NULL DEFAULT false,
  impede_locomocao boolean NOT NULL DEFAULT false, nao_se_aplica boolean NOT NULL DEFAULT false,
  tipo_veiculo varchar(30), ativo boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(), created_by varchar(120));
CREATE TABLE IF NOT EXISTS frota_vistoria_respostas (
  id serial PRIMARY KEY, vistoria_id integer NOT NULL REFERENCES frota_vistorias(id) ON DELETE CASCADE,
  item_id integer NOT NULL REFERENCES frota_vistoria_itens(id),
  valor varchar(200), reprovado boolean NOT NULL DEFAULT false,
  UNIQUE (vistoria_id, item_id));
CREATE INDEX IF NOT EXISTS ix_frota_vist_resp_bloqueio ON frota_vistoria_respostas (vistoria_id) WHERE reprovado;
"""

DDL_GRUPOS = """
CREATE TABLE IF NOT EXISTS sup_grupos (
  id serial PRIMARY KEY, codigo varchar(20) NOT NULL UNIQUE, descricao varchar(80) NOT NULL,
  pai_id integer REFERENCES sup_grupos(id),
  tipo varchar(10) NOT NULL DEFAULT 'ambos' CHECK (tipo IN ('material','uniforme','ambos')),
  ativo boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now());
"""


async def _ensure_grupos(db) -> None:
    """Só `sup_grupos` e as sementes. Chamado por quem lê/escreve grupo — inclusive a F9, que roda
    antes do `_ensure` completo daqui."""
    await db.execute(text(DDL_GRUPOS.strip().rstrip(";")))
    for cod, desc, tipo in _SEED_GRUPOS:
        await db.execute(
            text(
                "INSERT INTO sup_grupos (codigo, descricao, tipo) VALUES (:c, :d, :t) ON CONFLICT (codigo) DO NOTHING"
            ),
            {"c": cod, "d": desc, "t": tipo},
        )
    # todo valor que já existe em `nfe_compras_estoque.grupo` vira grupo — nenhum material fica órfão
    await db.execute(
        text(
            "INSERT INTO sup_grupos (codigo, descricao, tipo) "
            "SELECT DISTINCT left(trim(grupo), 20), initcap(trim(grupo)), 'material' FROM nfe_compras_estoque "
            "WHERE coalesce(trim(grupo),'') <> '' ON CONFLICT (codigo) DO NOTHING"
        )
    )


async def _ensure(db) -> None:
    # as tabelas de base (frente 10 + F10) e as colunas de recurso da multa vivem no `_ensure` da F10
    await f10._ensure(db)
    for stmt in DDL.split(";"):
        if stmt.strip():
            await db.execute(text(stmt))
    # semente 1: os itens de vistoria nascem sendo as 5 áreas fixas da frente 10, com as MESMAS
    # chaves e os MESMOS rótulos — o formulário publicado não muda de forma no dia em que a tabela nasce.
    for i, (cod, lbl) in enumerate(fr10._AREAS, start=1):
        await db.execute(
            text(
                "INSERT INTO frota_vistoria_itens (codigo, grupo, ordem, texto, tipo_dado, created_by) "
                "VALUES (:c, 'Áreas', :o, :t, 'nota', 'seed frente 10') ON CONFLICT (codigo) DO NOTHING"
            ),
            {"c": cod, "o": i, "t": lbl},
        )
    # semente 2: grupos da F9 + todo valor que já existe em `nfe_compras_estoque.grupo`
    await _ensure_grupos(db)
    await db.commit()


# ----------------------------------------------------------------------------- réguas
def troca_do_item(descricao: str) -> str | None:
    """Qual troca tipada (se alguma) este item de manutenção representa. A primeira palavra que casa
    ganha, na ordem de `_PALAVRA_TROCA` — "filtro de óleo" é FILTRO, não óleo."""
    d = (descricao or "").lower()
    for palavra, tipo in _PALAVRA_TROCA:
        if palavra in d:
            return tipo
    return None


def trocas_da_manutencao(itens) -> list[str]:
    """Tipos de troca DISTINTOS de uma manutenção — uma leitura por tipo, nunca duas."""
    vistos: list[str] = []
    for it in itens or []:
        tp = troca_do_item((it or {}).get("descricao", ""))
        if tp and tp not in vistos:
            vistos.append(tp)
    return vistos


def reprovado(tipo_dado: str, valor: str) -> bool:
    """Reprovação depende do tipo do dado: 'ruim' numa nota, 'nao' num sim/não. 'na' nunca reprova."""
    v = (valor or "").strip().lower()
    if v in ("", "na"):
        return False
    return (tipo_dado == "nota" and v == "ruim") or (tipo_dado == "sim_nao" and v == "nao")


async def bloqueio_locomocao(db, veiculo_id) -> str | None:
    """Item que impede locomoção reprovado na ÚLTIMA vistoria do veículo → devolve o texto do item.
    Chamado pela F10 antes de aceitar «Registrar saída». Uma vistoria nova, aprovando, libera."""
    if not veiculo_id:
        return None
    if not (await db.execute(text("SELECT to_regclass('public.frota_vistoria_respostas')"))).scalar():
        return None
    r = (
        await db.execute(
            text(
                "SELECT i.texto FROM frota_vistoria_respostas r JOIN frota_vistoria_itens i ON i.id = r.item_id "
                "WHERE r.reprovado AND i.impede_locomocao AND r.vistoria_id = "
                "(SELECT max(id) FROM frota_vistorias WHERE veiculo_id = :v) ORDER BY i.ordem, i.id LIMIT 1"
            ),
            {"v": veiculo_id},
        )
    ).first()
    return r[0] if r else None


async def grupos_opts(db, tipos=("material", "uniforme", "ambos")) -> list[dict]:
    """Opções de grupo com o pai no rótulo ("Material › Limpeza")."""
    await _ensure_grupos(db)
    rows = (
        await db.execute(
            text(
                "SELECT g.codigo, coalesce(p.descricao || ' › ', '') || g.descricao FROM sup_grupos g "
                "LEFT JOIN sup_grupos p ON p.id = g.pai_id WHERE g.ativo AND g.tipo = ANY(:t) ORDER BY 2"
            ),
            {"t": list(tipos)},
        )
    ).fetchall()
    return [{"value": r[0], "label": r[1]} for r in rows]


async def rotulo_grupo(db) -> dict:
    await _ensure_grupos(db)
    rows = (await db.execute(text("SELECT codigo, descricao FROM sup_grupos"))).fetchall()
    return {r[0]: r[1] for r in rows}


async def garantir_grupo(db, codigo: str, tipo: str = "material") -> str:
    """Texto livre continua aceito: o grupo que ainda não existe NASCE em vez de o material ser
    recusado (era `grupo not in dict(GRUPOS)` → 400). Devolve o código normalizado."""
    cod = (codigo or "").strip()[:20]
    if not cod:
        raise HTTPException(status_code=400, detail="Grupo é obrigatório.")
    await _ensure_grupos(db)
    await db.execute(
        text("INSERT INTO sup_grupos (codigo, descricao, tipo) VALUES (:c, :d, :t) ON CONFLICT (codigo) DO NOTHING"),
        {"c": cod, "d": cod.replace("_", " ").capitalize()[:80], "t": tipo if tipo in dict(TIPOS_GRUPO) else "ambos"},
    )
    return cod


# ----------------------------------------------------------------------------- utilitários
async def _um(db, sql: str, **p):
    return (await db.execute(text(sql), p)).first()


def _jd(v):
    return v if isinstance(v, list) else (json.loads(v or "[]") if v else [])


def _itens(txt: str) -> tuple[list[dict], float]:
    """`tipo | descrição | valor` por linha → lista de itens + total."""
    itens, total = [], 0.0
    for ln in (txt or "").splitlines():
        if not ln.strip():
            continue
        p = [x.strip() for x in ln.split("|")]
        if len(p) < 2:
            raise HTTPException(status_code=400, detail=f"Item «{ln.strip()}»: informe tipo | descrição | valor.")
        tipo = p[0].lower()
        if tipo not in dict(TIPOS_ITEM_MANUT):
            raise HTTPException(status_code=400, detail=f"Item «{p[1]}»: o tipo é «peca» ou «servico».")
        valor = fr10._dec(p[2], "Valor do item") if len(p) > 2 else 0.0
        itens.append({"tipo": tipo, "descricao": p[1][:160], "valor": round(valor or 0.0, 2)})
        total += valor or 0.0
    if not itens:
        raise HTTPException(status_code=400, detail="Informe ao menos um item (peça ou serviço).")
    return itens, round(total, 2)


async def _payable(current_user, db, *, descricao, valor, vencimento, fornecedor, nota):
    from modules.operacional.controllers.redesign_data_controller import rd_action_payable  # noqa: PLC0415

    r = await rd_action_payable(
        current_user,
        {
            "description": descricao,
            "valor": f"{valor:.2f}",
            "due_date": vencimento.isoformat(),
            "supplier_name": fornecedor,
            "notes": nota,
        },
        db,
    )
    return r.get("id")


def _acao(titulo, endpoint, btn, fields, ok="Feito. Recarregue.", style="outline", gated=False):
    a = {
        "title": titulo,
        "endpoint": endpoint,
        "method": "POST",
        "btnLabel": btn,
        "submitLabel": btn,
        "btnStyle": style,
        "okMsg": ok,
        "fields": fields,
    }
    if gated:
        a["gated"] = True
    return a


def _h(k, v):
    return {"key": k, "type": "hidden", "value": str(v)}


def _sel(key, label, options, span="span 1", value=""):
    return {"key": key, "label": label, "type": "select", "span": span, "options": options, "value": value}


_SIM_NAO = [{"value": "sim", "label": "Sim"}, {"value": "nao", "label": "Não"}]


# ----------------------------------------------------------------------------- multa: ações na linha
def acoes_multa(r) -> list[dict]:
    """Ações do V3 que a F10 anexa às dela na tela `frota-multas`. `r` é a linha do SELECT de lá:
    0 id · 9 valor · 10 valor com desconto · 8 vencimento · 12 status · 17 payable_id · 18 cabe_recurso
    · 19 recurso_resultado · 20 recurso_lancado_em."""
    mid, venc, status, pay, lancado, resultado = r[0], r[8], r[12], r[17], r[20], r[19]
    valor = float(r[10] if (r[10] is not None and venc and date.today() <= venc) else r[9] or 0)
    acts: list[dict] = []
    if not pay and status not in ("desconto_em_folha",):
        acts.append(
            _acao(
                f"Gerar a CONTA A PAGAR da multa #{mid} ({brl(valor)}, venc. "
                + (venc.strftime("%d/%m/%Y") if venc else "sem vencimento")
                + ") — cria o título, NÃO paga",
                _A + "frota-multa-conta",
                "Gerar conta",
                [_h("multa_id", mid)],
                "Título criado no Financeiro. Nada foi pago.",
                "danger",
                gated=True,
            )
        )
    if not lancado and status not in ("paga", "desconto_em_folha"):
        acts.append(
            _acao(
                f"Lançar recurso da multa #{mid}",
                _A + "frota-multa-recurso",
                "Lançar recurso",
                [
                    _h("multa_id", mid),
                    {
                        "key": "recurso_observacao",
                        "label": "Razões / protocolo",
                        "type": "text",
                        "span": "span 2",
                        "value": "",
                    },
                ],
                "Recurso lançado. Recarregue.",
            )
        )
    if lancado and resultado in (None, "pendente"):
        acts.append(
            _acao(
                f"Resultado do recurso da multa #{mid} — DEFERIDO cancela o título ainda pendente no Financeiro",
                _A + "frota-multa-recurso-resultado",
                "Resultado",
                [
                    _h("multa_id", mid),
                    _sel(
                        "recurso_resultado",
                        "Resultado*",
                        [{"value": k, "label": v} for k, v in RESULTADOS_RECURSO],
                        "span 2",
                    ),
                    {"key": "recurso_observacao", "label": "Observação", "type": "text", "span": "span 2", "value": ""},
                ],
                "Resultado registrado. Recarregue.",
                "primary",
            )
        )
    return acts


# ----------------------------------------------------------------------------- vistoria configurável
async def itens_vistoria(db, tipo_veiculo: str | None = None) -> list[dict]:
    rows = (
        (
            await db.execute(
                text(
                    "SELECT id, codigo, grupo, ordem, texto, tipo_dado, foto_obrigatoria, texto_obrigatorio, "
                    "impede_locomocao, nao_se_aplica FROM frota_vistoria_itens WHERE ativo "
                    "AND (CAST(:tv AS varchar) IS NULL OR tipo_veiculo IS NULL OR tipo_veiculo = CAST(:tv AS varchar)) "
                    "ORDER BY grupo, ordem, id"
                ),
                {"tv": tipo_veiculo},
            )
        )
        .mappings()
        .all()
    )
    return [dict(r) for r in rows]


def campos_do_item(it: dict) -> list[dict]:
    """Um item da tabela → os campos do formulário. Para `tipo_dado='nota'` sem «não se aplica» sai
    EXATAMENTE o par que a frente 10 gera hoje (`aval_<cod>` Bom/Ruim + `foto_<cod>` image/*)."""
    cod, lbl, tp = it["codigo"], it["texto"], it["tipo_dado"]
    campos: list[dict] = []
    if tp in ("nota", "sim_nao"):
        ops = (
            [{"value": "bom", "label": "Bom"}, {"value": "ruim", "label": "Ruim"}]
            if tp == "nota"
            else [dict(o) for o in _SIM_NAO]
        )
        if it["nao_se_aplica"]:
            ops = [*ops, {"value": "na", "label": "Não se aplica"}]
        campos.append({"key": f"aval_{cod}", "label": f"{lbl} — avaliação", "type": "select", "options": ops})
        campos.append({"key": f"foto_{cod}", "label": f"{lbl} — foto", "type": "file", "accept": "image/*"})
    elif tp == "texto":
        campos.append({"key": f"aval_{cod}", "label": f"{lbl} — observação", "type": "text", "span": "span 2"})
    else:  # foto
        campos.append({"key": f"foto_{cod}", "label": f"{lbl} — foto", "type": "file", "accept": "image/*"})
    return campos


async def form_vistoria(db, itens: list[dict]) -> dict:
    """A tela `frota-vistoria-nova`. Com a tabela VAZIA devolve, campo a campo e endpoint incluído, o
    formulário da frente 10 — o oráculo compara os dois dicionários."""
    campos = [
        {
            "key": "veiculo_id",
            "label": "Veículo*",
            "type": "select",
            "options": await fr10._opts(db, fr10._SQL_VEICULOS),
        },
        {
            "key": "tipo",
            "label": "Tipo*",
            "type": "select",
            "options": [{"value": "chegada", "label": "Chegada"}, {"value": "saida", "label": "Saída"}],
        },
        {"key": "os_ref", "label": "OS / referência*", "type": "text", "ph": "Ex.: OS-2026-0912"},
        {
            "key": "condutor_id",
            "label": "Condutor*",
            "type": "select",
            "options": await fr10._opts(db, fr10._SQL_EMPREGADOS),
        },
        {"key": "km", "label": "KM do hodômetro", "type": "text"},
        {
            "key": "checklist",
            "label": "Checklist*",
            "type": "select",
            "options": [{"value": "ok", "label": "Ok"}, {"value": "avariado", "label": "Avariado"}],
        },
    ]
    if not itens:
        for a, lbl in fr10._AREAS:
            campos.append(
                {
                    "key": f"aval_{a}",
                    "label": f"{lbl} — avaliação",
                    "type": "select",
                    "options": [{"value": "bom", "label": "Bom"}, {"value": "ruim", "label": "Ruim"}],
                }
            )
            campos.append({"key": f"foto_{a}", "label": f"{lbl} — foto", "type": "file", "accept": "image/*"})
        return await fr10._form(
            db,
            "frota-vistoria-nova",
            "Nova vistoria",
            "Chegada primeiro; a saída da mesma OS/condutor compara com ela.",
            "Registrar vistoria",
            "/api/v1/redesign/action/frota-vistoria",
            campos,
            multipart=True,
            showResult=True,
        )
    bloqueia = [i["texto"] for i in itens if i["impede_locomocao"]]
    for it in itens:
        campos.extend(campos_do_item(it))
    return await fr10._form(
        db,
        "frota-vistoria-nova",
        "Nova vistoria",
        "Chegada primeiro; a saída da mesma OS/condutor compara com ela. Os itens vêm de «Frota · Itens de vistoria»"
        + (f" — reprovar {', '.join(bloqueia[:3]).lower()} bloqueia a saída do veículo." if bloqueia else "."),
        "Registrar vistoria",
        "/api/v1/redesign/action/frota-vistoria-v3",
        campos,
        multipart=True,
        showResult=True,
    )


# ----------------------------------------------------------------------------- telas: equipamentos
async def telas_equip(db, out: dict) -> dict:
    await _ensure(db)
    _out, safe, tbl = _helpers(db)
    veic = await fr10._opts(db, fr10._SQL_VEICULOS)
    forn = await fr10._opts(
        db,
        "SELECT id, name || coalesce(' · ' || cpf_cnpj, '') FROM suppliers "
        "WHERE coalesce(status,'ativo') = 'ativo' AND coalesce(ativo,true) ORDER BY name",
    )

    # 1) manutenções de veículo (entidade nova)
    def _acoes_manut(r):
        mid, status, pay, total, sol = r[0], r[8], r[10], float(r[7] or 0), r[11]
        acts = []
        if status == "solicitada":
            acts.append(
                _acao(
                    f"APROVAR a manutenção #{mid} de {r[1]} ({brl(total)}) — libera a execução",
                    _A + "frota-manutencao-aprovar",
                    "Aprovar",
                    [
                        _h("id", mid),
                        {"key": "observacao", "label": "Observação", "type": "text", "span": "span 2", "value": ""},
                    ],
                    "Manutenção aprovada. Recarregue.",
                    "primary",
                    gated=True,
                )
            )
        if status in ("aprovada", "em_execucao"):
            acts.append(
                _acao(
                    f"Concluir a manutenção #{mid} de {r[1]} — grava o KM e, se houve troca, a leitura tipada",
                    _A + "frota-manutencao-concluir",
                    "Concluir",
                    [
                        _h("id", mid),
                        {"key": "km", "label": "KM do hodômetro na liberação*", "type": "text", "value": ""},
                        {"key": "liberacao", "label": "Liberado em", "type": "date", "value": ""},
                    ],
                    "Manutenção concluída. Recarregue.",
                    "primary",
                )
            )
        if status in ("aprovada", "em_execucao", "concluida") and not pay and total > 0:
            acts.append(
                _acao(
                    f"Gerar a CONTA A PAGAR da manutenção #{mid} ({brl(total)}) — cria o título, NÃO paga",
                    _A + "frota-manutencao-conta",
                    "Gerar conta",
                    [_h("id", mid), {"key": "vencimento", "label": "Vencimento", "type": "date", "value": ""}],
                    "Título criado no Financeiro. Nada foi pago.",
                    "danger",
                    gated=True,
                )
            )
        if status in ("solicitada", "aprovada", "em_execucao") and not sol:
            acts.append(
                _acao(
                    f"Abrir solicitação de material com as PEÇAS da manutenção #{mid} "
                    "(a descrição tem de casar com um material do almoxarifado)",
                    _A + "frota-manutencao-materiais",
                    "Solicitar materiais",
                    [_h("id", mid)],
                    "Solicitação de material aberta. Recarregue.",
                )
            )
        if status in ("solicitada", "aprovada"):
            acts.append(
                _acao(
                    f"Cancelar a manutenção #{mid}",
                    _A + "frota-manutencao-cancelar",
                    "Cancelar",
                    [
                        _h("id", mid),
                        {"key": "motivo", "label": "Motivo", "type": "text", "span": "span 2", "value": ""},
                    ],
                    "Manutenção cancelada. Recarregue.",
                )
            )
        return acts

    await safe(
        "frota-manutencoes",
        tbl(
            "Frota — manutenções",
            "Manutenção é entidade: aprova, conclui (gravando o KM e a troca tipada), vira conta a pagar e pede as peças ao "
            "almoxarifado. Nada aqui paga — o título nasce PENDENTE no Financeiro.",
            "Nova manutenção",
            [
                "#",
                "Veículo",
                "Tipo",
                "Fornecedor",
                "KM",
                "Entrada",
                "Liberação",
                "Valor",
                "Situação",
                "Itens",
                "Conta",
                "SM",
            ],
            "0.4fr 1.2fr 0.8fr 1.4fr 0.6fr 0.9fr 0.9fr 0.9fr 1fr 2fr 0.7fr 0.6fr",
            "SELECT m.id, v.placa || ' · ' || coalesce(v.modelo,'—'), m.tipo, coalesce(s.name,'—'), m.km, m.previsao_entrada, "
            "coalesce(m.liberacao, m.previsao_saida), m.valor_total, m.status, m.itens, m.payable_id::text, m.solicitacao_material_id "
            "FROM frota_manutencoes m JOIN frota_veiculos v ON v.id = m.veiculo_id "
            "LEFT JOIN suppliers s ON s.id = m.fornecedor_id "
            "ORDER BY (m.status IN ('concluida','cancelada')), m.id DESC LIMIT 300",
            lambda r: [
                t(str(r[0]), 600, _ND),
                t(r[1], 600),
                t(dict(TIPOS_MANUT).get(r[2], r[2])),
                t(r[3]),
                t(f10._km(r[4])),
                t(f10._d(r[5])),
                t(f10._d(r[6])),
                t(brl(float(r[7] or 0))),
                b(*_ST_MANUT.get(r[8], (r[8], "mut"))),
                t(
                    " · ".join(f"{i.get('descricao', '—')} ({brl(float(i.get('valor') or 0))})" for i in _jd(r[9]))
                    or "—"
                ),
                b("Gerada", "ok") if r[10] else t("—"),
                t(f"#{r[11]}" if r[11] else "—"),
            ],
            actionsfn=_acoes_manut,
            filtrofn=lambda r: _ST_MANUT.get(r[8], (r[8], ""))[0],
        ),
    )
    await safe(
        "frota-manutencao-nova",
        fr10._form(
            db,
            "frota-manutencao-nova",
            "Nova manutenção de veículo",
            "Uma linha por item: «peca | descrição | valor» ou «servico | descrição | valor». O total é a soma — não se digita. "
            "Item cuja descrição diga óleo, pneu, correia, filtro ou pastilha vira a troca tipada quando a manutenção for CONCLUÍDA.",
            "Registrar manutenção",
            _A + "frota-manutencao",
            [
                _sel("veiculo_id", "Veículo*", veic),
                _sel("tipo", "Tipo*", [{"value": k, "label": v} for k, v in TIPOS_MANUT], value="corretiva"),
                _sel("fornecedor_id", "Fornecedor", [{"value": "", "label": "—"}, *forn], "span 2"),
                {"key": "km", "label": "KM na entrada", "type": "text"},
                {"key": "centro_custo", "label": "Centro de custo", "type": "text"},
                {"key": "previsao_entrada", "label": "Previsão de entrada", "type": "date"},
                {"key": "previsao_saida", "label": "Previsão de saída", "type": "date"},
                {
                    "key": "itens",
                    "label": "Itens (um por linha: tipo | descrição | valor)*",
                    "type": "textarea",
                    "span": "span 2",
                    "ph": "peca | Filtro de óleo | 65,00\nservico | Troca de óleo 5W30 | 180,00",
                },
                {"key": "observacao", "label": "Observação", "type": "textarea", "span": "span 2"},
            ],
            okMsg="Manutenção registrada.",
            showResult=True,
        ),
    )

    # 2) itens de vistoria configuráveis
    itens = await itens_vistoria(db)
    await safe(
        "frota-vistoria-itens",
        tbl(
            "Frota — itens de vistoria",
            "O formulário de vistoria é montado por esta tabela. Nasceu com as 5 áreas que a frente 10 já usava — mesmos campos, "
            "mesmos rótulos. Item marcado «impede locomoção» reprovado na última vistoria BLOQUEIA a saída do veículo.",
            "Novo item",
            [
                "#",
                "Grupo",
                "Ordem",
                "Item",
                "Tipo do dado",
                "Foto obrig.",
                "Texto obrig.",
                "Impede locomoção",
                "N/A",
                "Tipo de veículo",
                "Situação",
            ],
            "0.4fr 1fr 0.5fr 1.8fr 1fr 0.7fr 0.7fr 1fr 0.5fr 1fr 0.8fr",
            "SELECT id, grupo, ordem, texto, tipo_dado, foto_obrigatoria, texto_obrigatorio, impede_locomocao, "
            "nao_se_aplica, coalesce(tipo_veiculo,'todos'), ativo, codigo FROM frota_vistoria_itens ORDER BY grupo, ordem, id",
            lambda r: [
                t(str(r[0]), 600, _ND),
                t(r[1]),
                t(str(r[2])),
                t(r[3], 600),
                t(dict(TIPOS_DADO).get(r[4], r[4])),
                b("Sim", "warn") if r[5] else t("—"),
                b("Sim", "warn") if r[6] else t("—"),
                b("Bloqueia", "bad") if r[7] else t("—"),
                t("Sim" if r[8] else "—"),
                t(r[9]),
                b("Ativo", "ok") if r[10] else b("Inativo", "mut"),
            ],
            actionsfn=lambda r: [
                _acao(
                    f"Editar «{r[3]}»",
                    _A + "frota-vistoria-item",
                    "Editar",
                    [
                        _h("codigo", r[11]),
                        {"key": "texto", "label": "Item*", "type": "text", "span": "span 2", "value": r[3]},
                        {"key": "grupo", "label": "Grupo", "type": "text", "value": r[1]},
                        {"key": "ordem", "label": "Ordem", "type": "text", "value": str(r[2])},
                        _sel(
                            "tipo_dado",
                            "Tipo do dado*",
                            [{"value": k, "label": v} for k, v in TIPOS_DADO],
                            value=r[4],
                        ),
                        _sel("impede_locomocao", "Impede locomoção", _SIM_NAO, value="sim" if r[7] else "nao"),
                        _sel("foto_obrigatoria", "Foto obrigatória", _SIM_NAO, value="sim" if r[5] else "nao"),
                        _sel("texto_obrigatorio", "Texto obrigatório", _SIM_NAO, value="sim" if r[6] else "nao"),
                        _sel("nao_se_aplica", "Permite «não se aplica»", _SIM_NAO, value="sim" if r[8] else "nao"),
                        _sel("ativo", "Ativo", _SIM_NAO, value="sim" if r[10] else "nao"),
                    ],
                    "Item gravado. Recarregue.",
                )
            ],
            filtrofn=lambda r: r[1],
        ),
    )
    await safe(
        "frota-vistoria-item-novo",
        fr10._form(
            db,
            "frota-vistoria-item-novo",
            "Novo item de vistoria",
            "O código é a chave do campo no formulário (`aval_<código>` e `foto_<código>`) — minúsculas, sem espaço.",
            "Gravar item",
            _A + "frota-vistoria-item",
            [
                {"key": "codigo", "label": "Código*", "type": "text", "ph": "pneu_estepe"},
                {"key": "texto", "label": "Item*", "type": "text", "ph": "Estepe calibrado"},
                {"key": "grupo", "label": "Grupo", "type": "text", "ph": "Segurança"},
                {"key": "ordem", "label": "Ordem", "type": "text", "value": "10"},
                _sel("tipo_dado", "Tipo do dado*", [{"value": k, "label": v} for k, v in TIPOS_DADO], value="sim_nao"),
                {"key": "tipo_veiculo", "label": "Só para o tipo de veículo", "type": "text", "ph": "vazio = todos"},
                _sel("impede_locomocao", "Impede locomoção", _SIM_NAO, value="nao"),
                _sel("foto_obrigatoria", "Foto obrigatória", _SIM_NAO, value="nao"),
                _sel("texto_obrigatorio", "Texto obrigatório", _SIM_NAO, value="nao"),
                _sel("nao_se_aplica", "Permite «não se aplica»", _SIM_NAO, value="nao"),
            ],
            okMsg="Item gravado.",
        ),
    )

    # 3) a vistoria passa a ser montada pela tabela (vazia → a tela da frente 10, igual)
    await safe("frota-vistoria-nova", form_vistoria(db, itens))

    # 4) `manutencoes` deixa de ser só patrimônio: duas fontes com coluna «Origem»
    await safe(
        "manutencoes",
        tbl(
            "Manutenções",
            "Duas fontes na mesma fila: ordens de manutenção do PATRIMÔNIO (`equipment_maintenances`) e manutenções de VEÍCULO "
            "(`frota_manutencoes`). Nada foi migrado — cada uma continua com a sua tela e o seu ciclo.",
            "Nova manutenção",
            ["Origem", "Código", "Equipamento / veículo", "Tipo", "Técnico / fornecedor", "Data", "Valor", "Status"],
            "0.8fr 1fr 1.6fr 1fr 1.4fr 1fr 0.9fr 0.9fr",
            "SELECT 'Patrimônio' AS origem, coalesce(maintenance_code,'—'), coalesce(equipment_name,'—'), "
            "coalesce(maintenance_type::text,'—'), coalesce(technician_name,'—'), scheduled_date AS quando, "
            "NULL::numeric AS valor, coalesce(status::text,'—') FROM equipment_maintenances WHERE coalesce(is_active,true) "
            "UNION ALL SELECT 'Frota', 'FM-' || m.id::text, v.placa || ' · ' || coalesce(v.modelo,'—'), m.tipo, "
            "coalesce(s.name,'—'), coalesce(m.liberacao, m.previsao_entrada), m.valor_total, m.status "
            "FROM frota_manutencoes m JOIN frota_veiculos v ON v.id = m.veiculo_id LEFT JOIN suppliers s ON s.id = m.fornecedor_id "
            "ORDER BY quando DESC NULLS LAST LIMIT 300",
            lambda r: [
                b(r[0], "info" if r[0] == "Frota" else "mut"),
                t(r[1], 600, _ND),
                t(r[2]),
                t((r[3] or "—").replace("_", " ")),
                t(r[4]),
                t(f10._d(r[5])),
                t(brl(float(r[6])) if r[6] is not None else "—"),
                b(*_ST_MANUT.get(r[7], (r[7] or "—", "mut"))),
            ],
            filtrofn=lambda r: r[0],
        ),
    )
    out.update(_out)
    return out


# ----------------------------------------------------------------------------- telas: suprimentos
async def telas_sup(db, out: dict) -> dict:
    await _ensure(db)
    _out, safe, tbl = _helpers(db)
    pais = [{"value": "", "label": "— sem pai (raiz) —"}, *await grupos_opts(db)]
    await safe(
        "sup-grupos",
        tbl(
            "Grupos de materiais e uniformes",
            "Hierarquia compartilhada por materiais e uniformes (DGX `/GruposAlmoxarifado`). Grupo digitado à mão na tela de "
            "materiais continua aceito — ele nasce aqui automaticamente.",
            "Novo grupo",
            ["#", "Código", "Descrição", "Grupo pai", "Tipo", "Materiais", "Situação"],
            "0.4fr 1fr 1.8fr 1.4fr 0.9fr 0.8fr 0.8fr",
            "SELECT g.id, g.codigo, g.descricao, coalesce(p.descricao,'—'), g.tipo, "
            "(SELECT count(*) FROM nfe_compras_estoque e WHERE e.grupo = g.codigo AND coalesce(e.ativo,true)), g.ativo "
            "FROM sup_grupos g LEFT JOIN sup_grupos p ON p.id = g.pai_id ORDER BY coalesce(p.descricao,''), g.descricao",
            lambda r: [
                t(str(r[0]), 600, _ND),
                t(r[1], 600, _ND),
                t(r[2]),
                t(r[3]),
                t(dict(TIPOS_GRUPO).get(r[4], r[4])),
                t(str(r[5])),
                b("Ativo", "ok") if r[6] else b("Inativo", "mut"),
            ],
            actionsfn=lambda r: [
                _acao(
                    f"Editar o grupo «{r[2]}»",
                    _A + "sup-grupo",
                    "Editar",
                    [
                        _h("codigo", r[1]),
                        {"key": "descricao", "label": "Descrição*", "type": "text", "span": "span 2", "value": r[2]},
                        _sel("pai_codigo", "Grupo pai", pais, "span 2"),
                        _sel("tipo", "Tipo*", [{"value": k, "label": v} for k, v in TIPOS_GRUPO], value=r[4]),
                        _sel("ativo", "Ativo", _SIM_NAO, value="sim" if r[6] else "nao"),
                    ],
                    "Grupo gravado. Recarregue.",
                )
            ],
            filtrofn=lambda r: dict(TIPOS_GRUPO).get(r[4], r[4]),
        ),
    )
    await safe(
        "sup-grupo-novo",
        fr10._form(
            db,
            "sup-grupo-novo",
            "Novo grupo",
            "Código numérico ou texto curto (até 20). O pai é opcional — sem pai, o grupo é raiz.",
            "Gravar grupo",
            _A + "sup-grupo",
            [
                {"key": "codigo", "label": "Código*", "type": "text", "ph": "limpeza_pesada"},
                {"key": "descricao", "label": "Descrição*", "type": "text", "span": "span 2"},
                _sel("pai_codigo", "Grupo pai", pais, "span 2"),
                _sel("tipo", "Tipo*", [{"value": k, "label": v} for k, v in TIPOS_GRUPO], value="material"),
            ],
            okMsg="Grupo gravado.",
        ),
    )
    out.update(_out)
    return out


# ----------------------------------------------------------------------------- ações: manutenção
@router.post("/action/frota-manutencao")
async def frota_manutencao(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    await _ensure(db)
    vid = fr10._int(payload.get("veiculo_id"), "Veículo")
    tipo = payload.get("tipo") or "corretiva"
    if not vid or tipo not in dict(TIPOS_MANUT):
        raise HTTPException(status_code=400, detail="Veículo e tipo são obrigatórios.")
    if not await _um(db, "SELECT 1 FROM frota_veiculos WHERE id = :v AND ativo", v=vid):
        raise HTTPException(status_code=404, detail="Veículo não encontrado.")
    itens, total = _itens(payload.get("itens"))
    row = await _um(
        db,
        "INSERT INTO frota_manutencoes (veiculo_id, tipo, fornecedor_id, km, previsao_entrada, previsao_saida, itens, "
        "valor_total, centro_custo, observacao, created_by) VALUES (:v, :t, CAST(:f AS uuid), :km, :pe, :ps, "
        "CAST(:it AS jsonb), :vt, :cc, :o, :u) RETURNING id",
        v=vid,
        t=tipo,
        f=f10._uuid(payload.get("fornecedor_id")),
        km=fr10._int(payload.get("km"), "KM"),
        pe=f10._data(payload.get("previsao_entrada"), "Previsão de entrada"),
        ps=f10._data(payload.get("previsao_saida"), "Previsão de saída"),
        it=json.dumps(itens),
        vt=total,
        cc=(payload.get("centro_custo") or "").strip()[:60] or None,
        o=(payload.get("observacao") or "").strip() or None,
        u=fr10._quem(current_user),
    )
    await db.commit()
    trocas = trocas_da_manutencao(itens)
    return {
        "ok": True,
        "id": row[0],
        "message": f"Manutenção #{row[0]} registrada com {len(itens)} item(ns), total {brl(total)}."
        + (f" Ao concluir, gera a troca de {', '.join(x.replace('troca_', '') for x in trocas)}." if trocas else ""),
    }


@router.post("/action/frota-manutencao-aprovar")
async def frota_manutencao_aprovar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)
) -> dict:
    await _ensure(db)
    mid = fr10._int(payload.get("id"), "Manutenção")
    r = await db.execute(
        text(
            "UPDATE frota_manutencoes SET status = 'aprovada', aprovado_por = :u, aprovado_em = now(), "
            "observacao = coalesce(nullif(:o,''), observacao) WHERE id = :m AND status = 'solicitada'"
        ),
        {"m": mid, "u": fr10._quem(current_user), "o": (payload.get("observacao") or "").strip()},
    )
    if not r.rowcount:
        raise HTTPException(status_code=409, detail="Manutenção não encontrada ou já saiu de «solicitada».")
    await db.commit()
    return {"ok": True, "message": f"Manutenção #{mid} aprovada."}


@router.post("/action/frota-manutencao-cancelar")
async def frota_manutencao_cancelar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)
) -> dict:
    await _ensure(db)
    mid = fr10._int(payload.get("id"), "Manutenção")
    r = await db.execute(
        text(
            "UPDATE frota_manutencoes SET status = 'cancelada', observacao = coalesce(observacao || ' · ', '') || :o "
            "WHERE id = :m AND status IN ('solicitada','aprovada') AND payable_id IS NULL"
        ),
        {"m": mid, "o": "Cancelada: " + ((payload.get("motivo") or "").strip() or "sem motivo informado")},
    )
    if not r.rowcount:
        raise HTTPException(
            status_code=409, detail="Manutenção não encontrada, já em execução/concluída, ou já tem conta gerada."
        )
    await db.commit()
    return {"ok": True, "message": f"Manutenção #{mid} cancelada."}


@router.post("/action/frota-manutencao-concluir")
async def frota_manutencao_concluir(
    current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)
) -> dict:
    """Grava o KM da liberação e, havendo item de troca, cria a leitura tipada pela MESMA
    `f10.frota_troca` da F10 (que valida hodômetro e atualiza a próxima troca do veículo)."""
    await _ensure(db)
    mid, km = fr10._int(payload.get("id"), "Manutenção"), fr10._int(payload.get("km"), "KM")
    if km is None:
        raise HTTPException(status_code=400, detail="Informe o KM do hodômetro na liberação.")
    m = await _um(db, "SELECT veiculo_id, status, itens FROM frota_manutencoes WHERE id = :m", m=mid)
    if not m:
        raise HTTPException(status_code=404, detail="Manutenção não encontrada.")
    if m[1] not in ("aprovada", "em_execucao"):
        raise HTTPException(status_code=409, detail=f"Manutenção em «{m[1]}» — só se conclui o que foi aprovado.")
    trocas = trocas_da_manutencao(_jd(m[2]))
    feitas = []
    for tp in trocas:
        # commita; valida hodômetro e atualiza frota_veiculos.km_proxima_troca_*
        await f10.frota_troca(
            current_user,
            {"veiculo_id": m[0], "tipo": tp, "km": km, "proxima_km": km + INTERVALO_KM[tp]},
            db,
        )
        feitas.append(tp.replace("troca_", ""))
    if not trocas:  # sem troca, o KM da liberação ainda é uma leitura honesta do hodômetro
        await fr10.frota_leitura(current_user, {"veiculo_id": m[0], "tipo": "km", "km": km}, db)
    await db.execute(
        text(
            "UPDATE frota_manutencoes SET status = 'concluida', km_conclusao = :k, concluida_em = now(), "
            "liberacao = coalesce(:l, liberacao, current_date) WHERE id = :m"
        ),
        {"k": km, "l": f10._data(payload.get("liberacao"), "Liberação"), "m": mid},
    )
    await db.commit()
    return {
        "ok": True,
        "message": f"Manutenção #{mid} concluída a {km} km."
        + (f" Troca de {', '.join(feitas)} registrada, com a próxima KM já calculada." if feitas else ""),
    }


@router.post("/action/frota-manutencao-conta")
async def frota_manutencao_conta(
    current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)
) -> dict:
    await _ensure(db)
    mid = fr10._int(payload.get("id"), "Manutenção")
    m = await _um(
        db,
        "SELECT m.valor_total, m.payable_id::text, m.status, v.placa, coalesce(s.name,''), "
        "coalesce(m.liberacao, m.previsao_saida) FROM frota_manutencoes m JOIN frota_veiculos v ON v.id = m.veiculo_id "
        "LEFT JOIN suppliers s ON s.id = m.fornecedor_id WHERE m.id = :m",
        m=mid,
    )
    if not m:
        raise HTTPException(status_code=404, detail="Manutenção não encontrada.")
    if m[1]:  # idempotente: a 2ª chamada devolve o MESMO título, não um segundo
        return {
            "ok": True,
            "id": m[1],
            "message": f"Conta já gerada para a manutenção #{mid} ({m[1][:8]}…) — nada duplicado.",
        }
    if m[2] == "cancelada":
        raise HTTPException(status_code=409, detail="Manutenção cancelada não gera conta.")
    total = float(m[0] or 0)
    if total <= 0:
        raise HTTPException(status_code=409, detail="Manutenção sem valor — nada a pagar.")
    venc = f10._data(payload.get("vencimento"), "Vencimento") or m[5] or date.today()
    pid = await _payable(
        current_user,
        db,
        descricao=f"Manutenção de veículo #{mid} — {m[3]}",
        valor=total,
        vencimento=venc,
        fornecedor=m[4] or None,
        nota=f"Gerada pela tela Frota · Manutenções (manutenção #{mid}). Título PENDENTE — pagamento é fluxo próprio.",
    )
    await db.execute(
        text("UPDATE frota_manutencoes SET payable_id = CAST(:p AS uuid) WHERE id = :m"), {"p": pid, "m": mid}
    )
    await db.commit()
    return {
        "ok": True,
        "id": pid,
        "message": f"Conta a pagar de {brl(total)} criada (venc. {venc.strftime('%d/%m/%Y')}). Não foi paga.",
    }


@router.post("/action/frota-manutencao-materiais")
async def frota_manutencao_materiais(
    current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)
) -> dict:
    """Abre a solicitação de material da T5 com os itens tipo PEÇA — mesma tabela, mesmo número, mesma fila."""
    from . import _dgx_t5_suprimentos_frotas_sesmt_config as t5  # noqa: PLC0415

    await _ensure(db)
    mid = fr10._int(payload.get("id"), "Manutenção")
    m = await _um(db, "SELECT itens, solicitacao_material_id, status FROM frota_manutencoes WHERE id = :m", m=mid)
    if not m:
        raise HTTPException(status_code=404, detail="Manutenção não encontrada.")
    if m[1]:
        raise HTTPException(status_code=409, detail=f"Manutenção #{mid} já tem a solicitação de material #{m[1]}.")
    pecas = [i for i in _jd(m[0]) if (i or {}).get("tipo") == "peca"]
    if not pecas:
        raise HTTPException(status_code=409, detail="Esta manutenção não tem item do tipo «peça».")
    r = await t5.sup_solicitacao_material(
        current_user,
        {
            "tipo": "urgente",
            "observacao": f"Peças da manutenção de veículo #{mid}",
            "itens": "\n".join(f"{i.get('descricao', '')} | 1" for i in pecas),
        },
        db,
    )
    await db.execute(
        text("UPDATE frota_manutencoes SET solicitacao_material_id = :s WHERE id = :m"), {"s": r["id"], "m": mid}
    )
    await db.commit()
    return {"ok": True, "id": r["id"], "message": f"Solicitação {r['numero']} aberta com {len(pecas)} peça(s)."}


# ----------------------------------------------------------------------------- ações: multa → conta e recurso
@router.post("/action/frota-multa-conta")
async def frota_multa_conta(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    await _ensure(db)
    mid = fr10._int(payload.get("multa_id"), "Multa")
    m = await _um(
        db,
        "SELECT m.valor, m.valor_com_desconto, m.vencimento, m.payable_id::text, m.status, v.placa, coalesce(m.orgao,''), "
        "coalesce(m.auto_infracao,'') FROM frota_multas m JOIN frota_veiculos v ON v.id = m.veiculo_id WHERE m.id = :m",
        m=mid,
    )
    if not m:
        raise HTTPException(status_code=404, detail="Multa não encontrada.")
    if m[3]:
        return {
            "ok": True,
            "id": m[3],
            "message": f"Conta já gerada para a multa #{mid} ({m[3][:8]}…) — nada duplicado.",
        }
    if not m[2]:
        raise HTTPException(
            status_code=409, detail="Multa sem vencimento — informe o vencimento na multa antes de gerar a conta."
        )
    # o desconto do CTB (art. 284) só vale ANTES do vencimento; depois, valor cheio
    com_desconto = m[1] is not None and date.today() <= m[2]
    valor = float(m[1] if com_desconto else m[0])
    pid = await _payable(
        current_user,
        db,
        descricao=f"Multa de trânsito #{mid} — {m[5]}" + (f" — {m[6]} auto {m[7]}" if m[7] else ""),
        valor=valor,
        vencimento=m[2],
        fornecedor=m[6] or None,
        nota=("Valor COM desconto (pago até o vencimento)." if com_desconto else "Valor cheio (sem desconto).")
        + " Gerada pela tela Frota · Multas. Título PENDENTE — pagamento é fluxo próprio.",
    )
    await db.execute(text("UPDATE frota_multas SET payable_id = CAST(:p AS uuid) WHERE id = :m"), {"p": pid, "m": mid})
    await db.commit()
    return {
        "ok": True,
        "id": pid,
        "message": f"Conta a pagar de {brl(valor)} criada (venc. {m[2].strftime('%d/%m/%Y')}"
        + (", com desconto" if com_desconto else ", valor cheio")
        + "). Não foi paga.",
    }


@router.post("/action/frota-multa-recurso")
async def frota_multa_recurso(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    await _ensure(db)
    mid = fr10._int(payload.get("multa_id"), "Multa")
    r = await db.execute(
        text(
            "UPDATE frota_multas SET cabe_recurso = true, recurso_lancado_em = now(), recurso_resultado = 'pendente', "
            "recurso_observacao = nullif(:o,''), status = CASE WHEN status IN ('recebida','indicada') THEN 'recorrida' ELSE status END "
            "WHERE id = :m AND status NOT IN ('paga','desconto_em_folha') AND recurso_lancado_em IS NULL"
        ),
        {"m": mid, "o": (payload.get("recurso_observacao") or "").strip()},
    )
    if not r.rowcount:
        raise HTTPException(
            status_code=409, detail="Multa não encontrada, já paga/descontada, ou o recurso já foi lançado."
        )
    await db.commit()
    return {"ok": True, "message": f"Recurso da multa #{mid} lançado — aguardando resultado."}


@router.post("/action/frota-multa-recurso-resultado")
async def frota_multa_recurso_resultado(
    current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)
) -> dict:
    """Deferido CANCELA o título ainda pendente pelo `PayableService` — nunca por UPDATE direto."""
    import uuid as _uuid  # noqa: PLC0415

    from modules.financial.services.payable_service import PayableService  # noqa: PLC0415

    await _ensure(db)
    mid, res = fr10._int(payload.get("multa_id"), "Multa"), (payload.get("recurso_resultado") or "").strip()
    if res not in dict(RESULTADOS_RECURSO):
        raise HTTPException(status_code=400, detail="O resultado é deferido, parcial, indeferido ou pendente.")
    m = await _um(db, "SELECT payable_id::text, recurso_lancado_em FROM frota_multas WHERE id = :m", m=mid)
    if not m:
        raise HTTPException(status_code=404, detail="Multa não encontrada.")
    if not m[1]:
        raise HTTPException(status_code=409, detail="Lance o recurso antes de registrar o resultado.")
    extra = ""
    if res == "deferido" and m[0]:
        st = await _um(db, "SELECT status FROM payable_accounts WHERE id = CAST(:p AS uuid)", p=m[0])
        if st and st[0] == "pendente":
            try:
                await PayableService(db).reject_account(
                    _uuid.UUID(m[0]), current_user.id, f"Multa #{mid} — recurso DEFERIDO"
                )
                extra = f" Título {m[0][:8]}… cancelado no Financeiro."
            except ValueError as e:
                raise HTTPException(status_code=409, detail=f"Título não pôde ser cancelado: {e}") from None
        else:
            extra = f" Título {m[0][:8]}… está «{st[0] if st else 'ausente'}» — não foi tocado; acerte no Financeiro."
    await db.execute(
        text(
            "UPDATE frota_multas SET recurso_resultado = :r, "
            "recurso_observacao = coalesce(nullif(:o,''), recurso_observacao) WHERE id = :m"
        ),
        {"r": res, "o": (payload.get("recurso_observacao") or "").strip(), "m": mid},
    )
    await db.commit()
    return {"ok": True, "message": f"Recurso da multa #{mid}: {dict(RESULTADOS_RECURSO)[res].lower()}.{extra}"}


@router.get("/frota/multas/{multa_id}/pdf", summary="Detalhes da multa de trânsito (PDF padrão-ouro)")
async def frota_multa_pdf(multa_id: int, current_user: CurrentActiveUser, db=Depends(get_db)):
    from modules.operacional.services.frota_multa_pdf import montar_multa  # noqa: PLC0415

    m = (
        (
            await db.execute(
                text(
                    "SELECT m.*, v.placa, v.modelo, coalesce(c.nome,'') AS condutor_nome, "
                    "coalesce(c.cpf,'') AS condutor_cpf, coalesce(s.nome,'') AS sugerido_nome FROM frota_multas m "
                    "JOIN frota_veiculos v ON v.id = m.veiculo_id LEFT JOIN employees c ON c.id = m.condutor_employee_id "
                    "LEFT JOIN employees s ON s.id = m.condutor_sugerido_id WHERE m.id = :i"
                ),
                {"i": multa_id},
            )
        )
        .mappings()
        .first()
    )
    if not m:
        raise HTTPException(status_code=404, detail="Multa não encontrada.")
    return Response(
        content=montar_multa(dict(m)),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="multa-{multa_id}.pdf"'},
    )


# ----------------------------------------------------------------------------- ações: itens de vistoria
@router.post("/action/frota-vistoria-item")
async def frota_vistoria_item(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    await _ensure(db)
    bruto = (payload.get("codigo") or "").strip().lower().replace(" ", "_")
    cod = "".join(ch for ch in bruto if ch.isalnum() or ch == "_")[:40]
    texto = (payload.get("texto") or "").strip()[:160]
    tipo_dado = payload.get("tipo_dado") or "sim_nao"
    if not cod or len(texto) < 2 or tipo_dado not in dict(TIPOS_DADO):
        raise HTTPException(status_code=400, detail="Código, texto e tipo do dado são obrigatórios.")

    def _b(k):
        return (payload.get(k) or "nao").strip().lower() == "sim"

    await db.execute(
        text(
            "INSERT INTO frota_vistoria_itens (codigo, grupo, ordem, texto, tipo_dado, foto_obrigatoria, texto_obrigatorio, "
            "impede_locomocao, nao_se_aplica, tipo_veiculo, ativo, created_by) "
            "VALUES (:c, :g, :o, :t, :td, :fo, :tob, :il, :na, :tv, :at, :u) "
            "ON CONFLICT (codigo) DO UPDATE SET grupo = EXCLUDED.grupo, ordem = EXCLUDED.ordem, texto = EXCLUDED.texto, "
            "tipo_dado = EXCLUDED.tipo_dado, foto_obrigatoria = EXCLUDED.foto_obrigatoria, "
            "texto_obrigatorio = EXCLUDED.texto_obrigatorio, impede_locomocao = EXCLUDED.impede_locomocao, "
            "nao_se_aplica = EXCLUDED.nao_se_aplica, tipo_veiculo = EXCLUDED.tipo_veiculo, ativo = EXCLUDED.ativo"
        ),
        {
            "c": cod,
            "g": (payload.get("grupo") or "Geral").strip()[:60] or "Geral",
            "o": fr10._int(payload.get("ordem"), "Ordem") or 0,
            "t": texto,
            "td": tipo_dado,
            "fo": _b("foto_obrigatoria"),
            "tob": _b("texto_obrigatorio"),
            "il": _b("impede_locomocao"),
            "na": _b("nao_se_aplica"),
            "tv": (payload.get("tipo_veiculo") or "").strip()[:30] or None,
            "at": (payload.get("ativo") or "sim").strip().lower() == "sim",
            "u": fr10._quem(current_user),
        },
    )
    await db.commit()
    return {"ok": True, "message": f"Item «{texto}» gravado. O formulário de vistoria já reflete a mudança."}


@router.post("/action/frota-vistoria-v3")
async def frota_vistoria_v3(request: Request, current_user: CurrentActiveUser, db=Depends(get_db)) -> dict:
    """Vistoria com os itens configuráveis. Valida as obrigatoriedades ANTES e delega o registro da
    vistoria (par chegada×saída, fotos das áreas, veredito) à MESMA `fr10.frota_vistoria`."""
    await _ensure(db)
    form = await request.form()  # starlette guarda o form parseado: a frente 10 relê o mesmo objeto
    itens = await itens_vistoria(db)
    areas_frente10 = {a for a, _ in fr10._AREAS}
    respostas, fotos_extra = [], {}
    for it in itens:
        cod = it["codigo"]
        valor = (form.get(f"aval_{cod}") or "").strip()
        arq = form.get(f"foto_{cod}")
        tem_foto = arq is not None and hasattr(arq, "read")
        if it["foto_obrigatoria"] and not tem_foto:
            raise HTTPException(status_code=422, detail=f"«{it['texto']}»: a foto é obrigatória.")
        if it["texto_obrigatorio"] and not valor:
            raise HTTPException(status_code=422, detail=f"«{it['texto']}»: o preenchimento é obrigatório.")
        respostas.append((it["id"], valor[:200] or None, reprovado(it["tipo_dado"], valor)))
        if tem_foto and cod not in areas_frente10:
            ext = fr10._MIME_EXT.get((arq.content_type or "").lower())
            if not ext:
                raise HTTPException(status_code=422, detail=f"Foto «{it['texto']}»: envie JPEG, PNG ou WebP.")
            conteudo = await arq.read()
            if len(conteudo) > fr10._MAX_FOTO:
                raise HTTPException(status_code=422, detail=f"Foto «{it['texto']}» acima de 10MB.")
            if conteudo:
                fotos_extra[cod] = (ext, conteudo)
    r = await fr10.frota_vistoria(request, current_user, db)  # commita a vistoria
    vid = r["id"]
    for item_id, valor, rep in respostas:
        await db.execute(
            text(
                "INSERT INTO frota_vistoria_respostas (vistoria_id, item_id, valor, reprovado) VALUES (:v, :i, :val, :r) "
                "ON CONFLICT (vistoria_id, item_id) DO UPDATE SET valor = EXCLUDED.valor, reprovado = EXCLUDED.reprovado"
            ),
            {"v": vid, "i": item_id, "val": valor, "r": rep},
        )
    if fotos_extra:  # itens novos (fora das 5 áreas) gravam no MESMO lugar e no MESMO jsonb
        areas = (await db.execute(text("SELECT areas FROM frota_vistorias WHERE id = :i"), {"i": vid})).scalar()
        areas = areas if isinstance(areas, dict) else json.loads(areas or "{}")
        dest = fr10._FOTOS_DIR / str(vid)
        dest.mkdir(parents=True, exist_ok=True)
        for cod, (ext, conteudo) in fotos_extra.items():
            (dest / f"{cod}{ext}").write_bytes(conteudo)
            areas.setdefault(cod, {})["foto"] = f"{cod}{ext}"
        await db.execute(
            text("UPDATE frota_vistorias SET areas = CAST(:a AS jsonb) WHERE id = :i"),
            {"a": json.dumps(areas), "i": vid},
        )
    await db.commit()
    bloqueio = await bloqueio_locomocao(db, fr10._int(form.get("veiculo_id"), "Veículo"))
    return {
        **r,
        "itens_respondidos": len(respostas),
        "bloqueio": bloqueio,
        "message": r["message"]
        + (f" ATENÇÃO: «{bloqueio}» reprovado — o veículo está BLOQUEADO para saída." if bloqueio else ""),
    }


# ----------------------------------------------------------------------------- ações: grupos
@router.post("/action/sup-grupo")
async def sup_grupo(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    await _ensure(db)
    cod = (payload.get("codigo") or "").strip()[:20]
    desc = (payload.get("descricao") or "").strip()[:80]
    tipo = payload.get("tipo") or "material"
    if not cod or len(desc) < 2 or tipo not in dict(TIPOS_GRUPO):
        raise HTTPException(status_code=400, detail="Código, descrição e tipo são obrigatórios.")
    pai_cod = (payload.get("pai_codigo") or "").strip()
    pai = None
    if pai_cod:
        if pai_cod == cod:
            raise HTTPException(status_code=400, detail="Um grupo não pode ser pai de si mesmo.")
        p = await _um(db, "SELECT id FROM sup_grupos WHERE codigo = :c", c=pai_cod)
        if not p:
            raise HTTPException(status_code=404, detail=f"Grupo pai «{pai_cod}» não existe.")
        pai = p[0]
        eu = await _um(db, "SELECT id FROM sup_grupos WHERE codigo = :c", c=cod)
        if eu:  # o pai escolhido não pode DESCENDER deste grupo — isso fecharia um ciclo
            descendentes = (
                (
                    await db.execute(
                        text(
                            "WITH RECURSIVE d AS (SELECT id FROM sup_grupos WHERE id = :e UNION ALL "
                            "SELECT g.id FROM sup_grupos g JOIN d ON g.pai_id = d.id) SELECT id FROM d"
                        ),
                        {"e": eu[0]},
                    )
                )
                .scalars()
                .all()
            )
            if pai in descendentes:
                raise HTTPException(status_code=409, detail="Isso criaria um ciclo na hierarquia de grupos.")
    await db.execute(
        text(
            "INSERT INTO sup_grupos (codigo, descricao, pai_id, tipo, ativo) VALUES (:c, :d, :p, :t, :a) "
            "ON CONFLICT (codigo) DO UPDATE SET descricao = EXCLUDED.descricao, pai_id = EXCLUDED.pai_id, "
            "tipo = EXCLUDED.tipo, ativo = EXCLUDED.ativo"
        ),
        {"c": cod, "d": desc, "p": pai, "t": tipo, "a": (payload.get("ativo") or "sim").strip().lower() == "sim"},
    )
    await db.commit()
    return {"ok": True, "message": f"Grupo «{desc}» gravado."}

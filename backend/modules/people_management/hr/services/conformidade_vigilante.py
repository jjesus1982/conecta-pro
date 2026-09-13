"""Conformidade de vigilante — aptidão, vencimentos e posse de equipamento controlado (frente 05, 12/09/2026).

Régua única para o oráculo, o painel do redesign e as rotas do DP. A regra, em três linhas:

  1. AUSÊNCIA DE DADO É BLOQUEIO. Sem curso cadastrado = inapto. Sem validade de CNV = inapto.
     Nunca `coalesce` para "válido" — 12 pessoas sem telefone no cadastro provam que dado faltante
     é a regra, não a exceção.
  2. A validade da reciclagem conta da CONCLUSÃO do curso (Lei 7.102/83; PF exige 2 anos). Os
     meses vêm de `system_configs` (`vigilante.reciclagem_validade_meses`), não do código.
  3. Arma só existe com NÚMERO DE SÉRIE, responsável e entrega/devolução datadas. O flag
     `employees.porte_arma` continua existindo, mas não é controle — é o caçador que o acusa.

Quem está SUJEITO à régua: lido de `system_configs` (`vigilante.funcoes_exigem_credencial`, lista
JSON de trechos casados contra `employees.cargo` e `posts.post_type`). Sem essa chave, TODO MUNDO é
sujeito — conservador de propósito: a empresa hoje é de portaria (0 vigilantes por cargo, medido
em 12/09), e é o DP quem decide quais funções exigem CNV, não o código. Posto `requires_armed`,
CNV preenchida ou curso cadastrado põem a pessoa na régua mesmo com a chave preenchida.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from modules.people_management.ponto.coorte_ponto import SQL_NAO_AUSENTE_HOJE

logger = logging.getLogger(__name__)

TIPOS_CURSO = ("formacao", "reciclagem_patrimonial", "reciclagem_escolta_armada", "reciclagem_vspp", "outro")
TIPOS_EQUIPAMENTO = ("armamento", "colete")
CHAVE_VALIDADE_MESES = "vigilante.reciclagem_validade_meses"
CHAVE_FUNCOES = "vigilante.funcoes_exigem_credencial"
JANELAS_DIAS = (30, 60, 90)


def hoje_manaus() -> date:
    return datetime.now(ZoneInfo("America/Manaus")).date()


#: Quem está escalado HOJE — mesma régua do lembrete de ponto (`operacional/lembrete_ponto`):
#: turno de hoje (Manaus), ativo, não folga, status agendado; pessoa ativa, não homologação; e a
#: coorte da casa (férias aprovadas, afastamento em curso, reta final de desligamento) importada,
#: não copiada. `DISTINCT ON` porque 12x36 pode ter mais de um turno no dia.
SQL_ESCALADOS_HOJE = (
    """
SELECT DISTINCT ON (e.id) e.id, p.name AS posto, p.post_type, p.requires_armed
  FROM shifts sh
  JOIN employees e ON e.id = sh.employee_id
  JOIN posts p ON p.id = sh.post_id
 WHERE sh.shift_date = (now() AT TIME ZONE 'America/Manaus')::date
   AND sh.is_active = TRUE
   AND sh.is_off_day = FALSE
   AND lower(coalesce(sh.status,'')) IN ('scheduled','agendado','ativo')
   AND e.status = 'ativo'
   AND coalesce(e.is_homologacao, false) = false
"""
    + SQL_NAO_AUSENTE_HOJE
    + " ORDER BY e.id, sh.planned_start_time"
)

_SQL_APTIDAO = """
WITH esc AS ({escalados})
SELECT e.id::text AS id, e.nome, e.nome_de_guerra, e.cargo, e.cnv, e.cnv_validade,
       esc.posto, esc.post_type, coalesce(esc.requires_armed, false) AS requires_armed,
       c.tipo AS curso_tipo, c.data_conclusao, c.vence_em AS curso_vence_em,
       EXISTS (SELECT 1 FROM equipamentos_controlados_alocacoes a
                 JOIN equipamentos_controlados q ON q.id = a.equipamento_id
                WHERE a.employee_id = e.id AND a.devolvido_em IS NULL AND q.tipo = 'armamento') AS arma_em_posse
  FROM employees e
  {join} esc ON esc.id = e.id
  LEFT JOIN LATERAL (
        SELECT tipo, data_conclusao, vence_em FROM vigilante_cursos v
         WHERE v.employee_id = e.id ORDER BY vence_em DESC LIMIT 1) c ON TRUE
 WHERE e.status = 'ativo' AND coalesce(e.is_homologacao, false) = false
 ORDER BY e.nome
"""


async def _config(db: AsyncSession, chave: str) -> str | None:
    return (
        await db.execute(text("SELECT valor FROM system_configs WHERE chave = :c AND ativo"), {"c": chave})
    ).scalar()


async def validade_meses_padrao(db: AsyncSession) -> int | None:
    """Meses de validade da reciclagem. None = parâmetro não configurado (e aí ninguém cadastra curso sem informar)."""
    v = await _config(db, CHAVE_VALIDADE_MESES)
    try:
        return int(str(v).strip()) if v else None
    except ValueError:
        return None


async def funcoes_exigem_credencial(db: AsyncSession) -> list[str] | None:
    """Trechos (minúsculos) de cargo/tipo de posto que exigem credencial de vigilante. None = chave ausente = todos."""
    v = await _config(db, CHAVE_FUNCOES)
    if not v:
        return None
    try:
        lst = json.loads(v)
    except ValueError:
        return None
    return [str(x).strip().lower() for x in lst if str(x).strip()] or None


def avaliar(cnv_validade: date | None, curso_vence_em: date | None, hoje: date) -> list[str]:
    """Motivos de inaptidão. Lista vazia = apto. Regra pura, sem banco: o oráculo afirma esta função."""
    motivos: list[str] = []
    if cnv_validade is None:
        motivos.append("CNV sem validade cadastrada")
    elif cnv_validade < hoje:
        motivos.append(f"CNV vencida em {cnv_validade:%d/%m/%Y}")
    if curso_vence_em is None:
        motivos.append("sem curso/reciclagem cadastrado")
    elif curso_vence_em < hoje:
        motivos.append(f"reciclagem vencida em {curso_vence_em:%d/%m/%Y}")
    return motivos


def _sujeito(r, funcoes: list[str] | None) -> bool:
    if funcoes is None or r["requires_armed"] or r["cnv"] or r["curso_vence_em"] is not None:
        return True
    alvo = f"{r['cargo'] or ''} {r['post_type'] or ''}".lower()
    return any(f in alvo for f in funcoes)


async def aptidao(db: AsyncSession, *, so_escalados_hoje: bool = False) -> list[dict]:
    """Uma linha por pessoa ativa (ou só quem está escalado hoje), com `sujeito`, `apto` e `motivos`.

    `apto` é None para quem não está sujeito à régua (a função não exige credencial).
    """
    hoje = hoje_manaus()
    funcoes = await funcoes_exigem_credencial(db)
    sql = _SQL_APTIDAO.format(escalados=SQL_ESCALADOS_HOJE, join="JOIN" if so_escalados_hoje else "LEFT JOIN")
    rows = (await db.execute(text(sql))).mappings().all()
    out = []
    for r in rows:
        d = dict(r)
        d["sujeito"] = _sujeito(r, funcoes)
        d["motivos"] = avaliar(r["cnv_validade"], r["curso_vence_em"], hoje) if d["sujeito"] else []
        d["apto"] = (not d["motivos"]) if d["sujeito"] else None
        out.append(d)
    return out


def _dias(d: date | None, hoje: date) -> int | None:
    return (d - hoje).days if d else None


async def vencimentos(db: AsyncSession) -> dict:
    """Quem vence em 30/60/90 dias, quem já venceu e quem está SEM DADO — só entre os sujeitos à régua."""
    hoje = hoje_manaus()
    linhas = await aptidao(db)
    vencendo, vencidos, sem_dado = [], [], []
    for p in linhas:
        if not p["sujeito"]:
            continue
        for item, d in (("CNV", p["cnv_validade"]), (f"reciclagem ({p['curso_tipo'] or '—'})", p["curso_vence_em"])):
            if d is None:
                sem_dado.append({"nome": p["nome"], "id": p["id"], "item": item.split(" (")[0], "cargo": p["cargo"]})
                continue
            dias = _dias(d, hoje)
            reg = {"nome": p["nome"], "id": p["id"], "item": item, "vence_em": d, "dias": dias}
            if dias < 0:
                vencidos.append(reg)
            elif dias <= max(JANELAS_DIAS):
                reg["janela"] = next(j for j in JANELAS_DIAS if dias <= j)
                vencendo.append(reg)
    vencendo.sort(key=lambda x: x["vence_em"])
    vencidos.sort(key=lambda x: x["vence_em"])
    return {"hoje": hoje, "vencendo": vencendo, "vencidos": vencidos, "sem_dado": sem_dado}


async def posse_equipamentos(db: AsyncSession) -> list[dict]:
    """Todo equipamento controlado, com quem está (ou 'disponível') — a posse vem da alocação aberta."""
    rows = (
        (
            await db.execute(
                text(
                    """
SELECT q.id::text AS id, q.tipo, q.numero_serie, q.modelo, q.calibre, q.status,
       a.id::text AS alocacao_id, e.id::text AS employee_id, e.nome AS responsavel, e.nome_de_guerra,
       a.entregue_em
  FROM equipamentos_controlados q
  LEFT JOIN equipamentos_controlados_alocacoes a ON a.equipamento_id = q.id AND a.devolvido_em IS NULL
  LEFT JOIN employees e ON e.id = a.employee_id
 ORDER BY q.tipo, q.numero_serie
"""
                )
            )
        )
        .mappings()
        .all()
    )
    return [dict(r) for r in rows]


async def cursos(db: AsyncSession, employee_id: str | None = None) -> list[dict]:
    sql = """
SELECT v.id::text AS id, v.employee_id::text AS employee_id, e.nome, v.tipo, v.data_conclusao, v.validade_meses,
       v.vence_em, v.local, v.certificado_url, v.created_at
  FROM vigilante_cursos v JOIN employees e ON e.id = v.employee_id
 {where} ORDER BY v.vence_em DESC, e.nome
"""
    if employee_id:
        rows = await db.execute(
            text(sql.format(where="WHERE v.employee_id = CAST(:e AS uuid)")), {"e": str(employee_id)}
        )
    else:
        rows = await db.execute(text(sql.format(where="")))
    return [dict(r) for r in rows.mappings().all()]


# ────────────────────────────── escrita ──────────────────────────────


async def cadastrar_curso(
    db: AsyncSession,
    *,
    employee_id: str,
    tipo: str,
    data_conclusao: date,
    validade_meses: int | None = None,
    local: str | None = None,
    certificado_url: str | None = None,
    user_id: str | None = None,
) -> dict:
    """Grava curso/reciclagem. `vence_em` = conclusão + meses (o banco soma meses de calendário)."""
    if tipo not in TIPOS_CURSO:
        raise ValueError(f"tipo inválido: {tipo!r} (aceitos: {', '.join(TIPOS_CURSO)})")
    if data_conclusao > hoje_manaus():
        raise ValueError("data de conclusão no futuro — o curso ainda não foi concluído")
    meses = validade_meses if validade_meses else await validade_meses_padrao(db)
    if not meses or meses <= 0:
        raise ValueError(f"validade em meses não informada e o parâmetro {CHAVE_VALIDADE_MESES} não está configurado")
    row = (
        (
            await db.execute(
                text(
                    """
INSERT INTO vigilante_cursos (employee_id, tipo, data_conclusao, validade_meses, vence_em, local, certificado_url, created_by)
VALUES (CAST(:e AS uuid), :tipo, CAST(:d AS date), :m, (CAST(:d AS date) + make_interval(months => :m))::date,
        :local, :url, CAST(:u AS uuid))
RETURNING id::text AS id, vence_em
"""
                ),
                {
                    "e": str(employee_id),
                    "tipo": tipo,
                    "d": data_conclusao,
                    "m": int(meses),
                    "local": (local or "").strip()[:120] or None,
                    "url": (certificado_url or "").strip() or None,
                    "u": str(user_id) if user_id else None,
                },
            )
        )
        .mappings()
        .one()
    )
    await db.commit()
    return dict(row)


async def cadastrar_equipamento(
    db: AsyncSession, *, tipo: str, numero_serie: str, modelo: str | None = None, calibre: str | None = None
) -> dict:
    if tipo not in TIPOS_EQUIPAMENTO:
        raise ValueError(f"tipo inválido: {tipo!r} (aceitos: {', '.join(TIPOS_EQUIPAMENTO)})")
    serie = (numero_serie or "").strip().upper()
    if not serie:
        raise ValueError("número de série é obrigatório — sem série não é controle, é contador")
    try:
        row = (
            (
                await db.execute(
                    text(
                        "INSERT INTO equipamentos_controlados (tipo, numero_serie, modelo, calibre) "
                        "VALUES (:t, :s, :m, :c) RETURNING id::text AS id"
                    ),
                    {
                        "t": tipo,
                        "s": serie[:60],
                        "m": (modelo or "").strip()[:80] or None,
                        "c": (calibre or "").strip()[:20] or None,
                    },
                )
            )
            .mappings()
            .one()
        )
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(f"número de série {serie} já cadastrado") from e
    await db.commit()
    return dict(row)


async def entregar(
    db: AsyncSession,
    *,
    equipamento_id: str,
    employee_id: str,
    user_id: str | None = None,
    observacao: str | None = None,
) -> dict:
    """Entrega datada. ARMAMENTO só sai para quem está APTO — é para isso que a régua existe."""
    q = (
        (
            await db.execute(
                text("SELECT tipo, numero_serie, status FROM equipamentos_controlados WHERE id = CAST(:q AS uuid)"),
                {"q": str(equipamento_id)},
            )
        )
        .mappings()
        .first()
    )
    if not q:
        raise ValueError("equipamento não encontrado")
    if q["status"] != "ativo":
        raise ValueError(f"equipamento {q['numero_serie']} está '{q['status']}' — não pode ser entregue")
    if q["tipo"] == "armamento":
        pessoa = next((p for p in await aptidao(db) if p["id"] == str(employee_id)), None)
        if not pessoa:
            raise ValueError("funcionário não encontrado ou não está ativo")
        # régua INTEIRA, mesmo para quem o cargo não sujeita: arma na mão exige credencial, sempre
        motivos = avaliar(pessoa["cnv_validade"], pessoa["curso_vence_em"], hoje_manaus())
        if motivos:
            raise ValueError(f"{pessoa['nome']} está INAPTO para armamento: " + "; ".join(motivos))
    try:
        row = (
            (
                await db.execute(
                    text(
                        """
INSERT INTO equipamentos_controlados_alocacoes (equipamento_id, employee_id, entregue_por, observacao)
VALUES (CAST(:q AS uuid), CAST(:e AS uuid), CAST(:u AS uuid), :o)
RETURNING id::text AS id, entregue_em
"""
                    ),
                    {
                        "q": str(equipamento_id),
                        "e": str(employee_id),
                        "u": str(user_id) if user_id else None,
                        "o": (observacao or "").strip() or None,
                    },
                )
            )
            .mappings()
            .one()
        )
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(f"{q['numero_serie']} já está em posse de alguém — registre a devolução antes") from e
    await db.commit()
    return dict(row)


async def devolver(
    db: AsyncSession, *, equipamento_id: str, user_id: str | None = None, observacao: str | None = None
) -> dict:
    row = (
        (
            await db.execute(
                text(
                    """
UPDATE equipamentos_controlados_alocacoes
   SET devolvido_em = now(), devolvido_por = CAST(:u AS uuid),
       observacao = coalesce(nullif(:o, ''), observacao)
 WHERE equipamento_id = CAST(:q AS uuid) AND devolvido_em IS NULL
RETURNING id::text AS id, devolvido_em
"""
                ),
                {"q": str(equipamento_id), "u": str(user_id) if user_id else None, "o": (observacao or "").strip()},
            )
        )
        .mappings()
        .first()
    )
    if not row:
        raise ValueError("este equipamento não está em posse de ninguém")
    await db.commit()
    return dict(row)


async def definir_nome_de_guerra(db: AsyncSession, *, employee_id: str, nome_de_guerra: str | None) -> bool:
    """`nome_de_guerra` é identificação operacional. `nome_social` é tratamento — NÃO se reutiliza."""
    v = (nome_de_guerra or "").strip()[:60] or None
    r = await db.execute(
        text("UPDATE employees SET nome_de_guerra = :n WHERE id = CAST(:e AS uuid)"), {"n": v, "e": str(employee_id)}
    )
    await db.commit()
    return r.rowcount == 1


# ────────────────────────────── caçador ──────────────────────────────

#: Arma que existe só como FLAG (porte_arma / porte_arma_numero no cadastro) sem nenhuma entrega
#: registrada por série; e posto que exige armamento com gente escalada hoje sem arma em posse.
SQL_ARMA_SEM_CONTROLE = """
WITH esc AS ({escalados})
SELECT e.nome, 'flag porte_arma sem arma com série entregue' AS motivo
  FROM employees e
 WHERE e.status = 'ativo' AND (e.porte_arma = TRUE OR nullif(e.porte_arma_numero, '') IS NOT NULL)
   AND NOT EXISTS (SELECT 1 FROM equipamentos_controlados_alocacoes a
                     JOIN equipamentos_controlados q ON q.id = a.equipamento_id
                    WHERE a.employee_id = e.id AND a.devolvido_em IS NULL AND q.tipo = 'armamento')
UNION ALL
SELECT e.nome, 'escalado hoje em posto armado (' || esc.posto || ') sem arma em posse'
  FROM esc JOIN employees e ON e.id = esc.id
 WHERE esc.requires_armed
   AND NOT EXISTS (SELECT 1 FROM equipamentos_controlados_alocacoes a
                     JOIN equipamentos_controlados q ON q.id = a.equipamento_id
                    WHERE a.employee_id = e.id AND a.devolvido_em IS NULL AND q.tipo = 'armamento')
ORDER BY 1
"""


async def armas_sem_controle(db: AsyncSession) -> list[dict]:
    rows = (await db.execute(text(SQL_ARMA_SEM_CONTROLE.format(escalados=SQL_ESCALADOS_HOJE)))).mappings().all()
    return [dict(r) for r in rows]

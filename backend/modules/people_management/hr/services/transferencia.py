"""Transferência de colaborador entre as empresas do grupo (paridade DGX, frente W4).

O «Transferir (filial destino)» do `/Colaboradores/Index` do DGX. Aqui a casa tem DUAS empresas
(`empresas`): Conecta Mais Eletrônica (35.710.481/0001-03) e Conecta Mais Patrimonial
(66.014.833/0001-10), e até 24/09/2026 NÃO havia fluxo nenhum entre elas — a única forma de
"transferir" era demitir e readmitir, que zera admissão, período aquisitivo de férias e histórico.

Em 30/06/2026 o GEILSON RODRIGUES DE ANDRADE foi transferido para a Patrimonial e o sistema não
soube: apareceu só no espelho do eSocial (S-2299 com `mtvDeslig=11`), e o DP descobriu consultando
o governo. `regua()` existe por causa dele.

**Transferência NÃO é rescisão + admissão.** No eSocial é:
  • origem  — S-2299 com `mtvDeslig` 10 (mesmo grupo econômico / quem assumiu os encargos) ou
    11 (sucessão, incorporação, cisão ou fusão) — tabela 19. Os dois códigos são os mesmos que
    `people_management/services/conferencia_esocial._MOTIVOS_TRANSFERENCIA` já trata como
    "continua sendo nosso, noutro CNPJ"; importamos de lá para não haver duas listas.
  • destino — S-2200 com `tpAdmissao` 2 (↔ motivo 10) ou 3 (↔ motivo 11) e o bloco `sucessaoVinc`
    (CNPJ anterior, matrícula anterior, data da transferência). `dtAdm` continua sendo a data de
    admissão ORIGINAL: o vínculo é contínuo.
O que NÃO muda: data de admissão, período aquisitivo de férias (`hr_vacation_periods`), saldo de
banco de horas, dependentes (`employee_dp.dependentes`) e documentos. `efetivar` não toca em
nenhuma dessas tabelas — e o oráculo reconta as três por SQL próprio, antes e depois.

**Os dois eventos entram como RASCUNHO e nada é transmitido.** Vão para
`esocial_transmissao_propostas` com `status='proposto'` — a mesma fila que o orquestrador do
Hermes usa (`ai/.../acoes/onda_c.py`), justamente porque transmitir ao governo é ato legal
irreversível e 100% humano, pelo fluxo que já existe. Este módulo NUNCA chama
`transmitir_evento_sst` nem monta XML final: o rascunho carrega os FATOS que o humano confere.

Alocação: quem trabalha num posto continua no mesmo posto, mas sob outro CNPJ. `efetivar` encerra
a alocação de origem em D−1 e abre a nova em D pelo `operacional/services/movimentacao_service`
(F5) — sem buraco e sem sobreposição — com o motivo `transferencia_de_empresa`, acrescentado à
lista dos 7 motivos do DGX porque nenhum deles descrevia isto.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text

from modules.people_management.services.conferencia_esocial import _MOTIVOS_TRANSFERENCIA

#: Tabela 19 do eSocial, só os dois códigos que NÃO encerram o vínculo com o grupo.
MOTIVOS = {
    "10": "Transferência para empresa do mesmo grupo econômico (ou que assumiu os encargos), sem rescisão",
    "11": "Transferência por motivo de sucessão, incorporação, cisão ou fusão",
}
#: motivo (tabela 19, S-2299) → tpAdmissao (S-2200 do destino).
TP_ADMISSAO = {"10": "2", "11": "3"}
STATUS = ("rascunho", "efetivada", "cancelada")
MOTIVO_ALOCACAO = "transferencia_de_empresa"

_DDL = [
    "CREATE TABLE IF NOT EXISTS dp_transferencias ("
    " id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    " employee_id uuid NOT NULL,"
    " empresa_origem_cnpj varchar(18),"
    " empresa_destino_cnpj varchar(18) NOT NULL,"
    " data date NOT NULL,"
    " motivo varchar(2) NOT NULL DEFAULT '10',"
    " mantem_admissao boolean NOT NULL DEFAULT true,"
    " novo_cargo_id uuid,"
    " novo_salario numeric(12,2),"
    " observacao text,"
    " status varchar(12) NOT NULL DEFAULT 'rascunho',"
    " esocial_s2299_id uuid,"
    " esocial_s2200_id uuid,"
    " criado_por uuid,"
    " criado_em timestamp DEFAULT (now() AT TIME ZONE 'America/Manaus'),"
    " efetivada_por uuid, efetivada_em timestamp,"
    " cancelada_por uuid, cancelada_em timestamp)",
    "CREATE INDEX IF NOT EXISTS ix_dp_transferencias_emp ON dp_transferencias (employee_id, data DESC)",
    "CREATE INDEX IF NOT EXISTS ix_dp_transferencias_status ON dp_transferencias (status, data DESC)",
]


class TransferenciaErro(ValueError):  # noqa: N818 — nome em PT-BR, padrão da casa (MovimentacaoErro)
    def __init__(self, status: int, msg: str) -> None:
        super().__init__(msg)
        self.status = status


async def _ensure(db) -> None:
    for sql in _DDL:
        await db.execute(text(sql))
    await db.commit()


def hoje_manaus() -> date:
    return datetime.now(ZoneInfo("America/Manaus")).date()


def so_digitos(v: Any) -> str:
    return "".join(c for c in str(v or "") if c.isdigit())


def _data(v) -> date:
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        raise TransferenciaErro(400, f"Data inválida: {v!r} (use AAAA-MM-DD).") from None


def _valor(v) -> Decimal | None:
    if v in (None, ""):
        return None
    try:
        return Decimal(str(v).replace(".", "").replace(",", ".") if "," in str(v) else str(v))
    except InvalidOperation:
        raise TransferenciaErro(422, f"Salário inválido: {v!r}.") from None


async def _empresa(db, cnpj: str) -> dict:
    """Empresa do grupo pelo CNPJ (com ou sem máscara). 422 se não for uma das nossas."""
    row = (
        (
            await db.execute(
                text(
                    "SELECT id::text, slug, razao_social, cnpj FROM empresas "
                    "WHERE regexp_replace(coalesce(cnpj,''),'\\D','','g') = :c LIMIT 1"
                ),
                {"c": so_digitos(cnpj)},
            )
        )
        .mappings()
        .first()
    )
    if not row:
        raise TransferenciaErro(422, f"CNPJ {cnpj!r} não é de uma empresa do grupo (cadastro `empresas`).")
    return dict(row)


async def _colaborador(db, employee_id: str) -> dict:
    row = (
        (
            await db.execute(
                text(
                    "SELECT e.id::text, e.nome, e.matricula, e.cpf, e.status, e.data_admissao, e.cargo, e.salario_base, "
                    "       e.cct_cargo_id::text, em.id::text AS empresa_id, em.cnpj AS empresa_cnpj, "
                    "       em.razao_social AS empresa_nome "
                    "FROM employees e LEFT JOIN empresas em ON em.id = e.empresa_id WHERE e.id = CAST(:e AS uuid)"
                ),
                {"e": employee_id},
            )
        )
        .mappings()
        .first()
    )
    if not row:
        raise TransferenciaErro(404, "Colaborador não encontrado.")
    return dict(row)


# ───────────────────────────────── simular ─────────────────────────────────
async def simular(
    db,
    *,
    employee_id: str,
    empresa_destino_cnpj: str,
    data=None,
    novo_cargo_id: str | None = None,
    novo_salario=None,
) -> dict:
    """O antes/depois, sem escrever NADA. `muda` e `nao_muda` são o painel que o DP lê antes
    de efetivar — e o que `nao_muda` afirma é verificado pelo oráculo, não prometido aqui."""
    await _ensure(db)
    e = await _colaborador(db, employee_id)
    destino = await _empresa(db, empresa_destino_cnpj)
    dia = _data(data) if data else hoje_manaus()
    if e.get("empresa_id") == destino["id"]:
        raise TransferenciaErro(422, f"{e['nome']} já está em {destino['razao_social']}.")

    cargo_novo = None
    if novo_cargo_id:
        cargo_novo = (
            await db.execute(
                text("SELECT cargo_nome, piso_salarial FROM cct_cargos WHERE id = CAST(:c AS uuid)"),
                {"c": novo_cargo_id},
            )
        ).first()
        if not cargo_novo:
            raise TransferenciaErro(422, "Cargo (CCT) não encontrado.")
    salario = _valor(novo_salario)

    periodos = (
        await db.execute(
            text(
                "SELECT count(*), min(start_date)::text, coalesce(sum(days_remaining),0) "
                "FROM hr_vacation_periods WHERE employee_id = CAST(:e AS uuid)"
            ),
            {"e": employee_id},
        )
    ).first()
    deps = (
        await db.execute(
            text(
                "SELECT coalesce(jsonb_array_length(coalesce(dependentes,'[]'::jsonb)),0) "
                "FROM employee_dp WHERE employee_id = CAST(:e AS uuid)"
            ),
            {"e": employee_id},
        )
    ).scalar() or 0
    docs = (
        await db.execute(
            text("SELECT count(*) FROM hr_employee_documents WHERE employee_id = CAST(:e AS uuid)"),
            {"e": employee_id},
        )
    ).scalar() or 0
    banco = (
        await db.execute(
            text(
                "SELECT coalesce(sum(CASE WHEN entry_type = 'debit' THEN -hours ELSE hours END),0) FROM time_bank "
                "WHERE employee_id = CAST(:e AS uuid) AND coalesce(is_active,true)"
            ),
            {"e": employee_id},
        )
    ).scalar()
    aloc = (
        await db.execute(
            text(
                "SELECT c.nome, a.funcao, a.data_inicio FROM employee_alocacoes a "
                "LEFT JOIN condominios c ON c.id = a.condominio_id "
                "WHERE a.employee_id = CAST(:e AS uuid) AND a.ativo ORDER BY a.data_inicio DESC"
            ),
            {"e": employee_id},
        )
    ).fetchall()

    return {
        "colaborador": e["nome"],
        "matricula": e.get("matricula") or "—",
        "data": dia.isoformat(),
        "muda": {
            "empresa": f"{e.get('empresa_nome') or '(sem empresa)'} → {destino['razao_social']}",
            "cnpj": f"{e.get('empresa_cnpj') or '—'} → {destino['cnpj']}",
            "cargo": (
                f"{e.get('cargo') or '—'} → {cargo_novo[0]}" if cargo_novo else f"{e.get('cargo') or '—'} (sem mudança)"
            ),
            "salario": (
                f"{e.get('salario_base')} → {salario}"
                if salario is not None
                else f"{e.get('salario_base')} (sem mudança)"
            ),
            "alocacao": (
                f"{aloc[0][0] or '—'} · {aloc[0][1] or '—'}: encerra em {(dia - timedelta(days=1)):%d/%m/%Y} "
                f"e reabre em {dia:%d/%m/%Y} sob o novo CNPJ"
                if aloc
                else "sem alocação ativa — nada a reabrir"
            ),
            "esocial": "2 rascunhos: S-2299 na origem e S-2200 no destino (nada é transmitido)",
        },
        "nao_muda": {
            "data_de_admissao": f"{e['data_admissao']:%d/%m/%Y}" if e.get("data_admissao") else "—",
            "periodo_aquisitivo_de_ferias": (
                f"{int(periodos[0] or 0)} período(s), âncora {periodos[1] or '—'}, "
                f"{int(periodos[2] or 0)} dia(s) de saldo — NÃO reinicia"
            ),
            "banco_de_horas": (f"{banco} hora(s) de saldo" if banco is not None else "sem saldo registrado"),
            "dependentes": f"{int(deps)} dependente(s)",
            "documentos": f"{int(docs)} documento(s) no GED do colaborador",
            "vinculo": "contínuo: não há rescisão nem admissão nova — status e data de demissão intocados",
        },
    }


# ───────────────────────────────── criar ─────────────────────────────────
async def criar(
    db,
    *,
    employee_id: str,
    empresa_destino_cnpj: str,
    data=None,
    motivo: str = "10",
    novo_cargo_id: str | None = None,
    novo_salario=None,
    observacao: str | None = None,
    mantem_admissao: bool = True,
    user_id: str | None = None,
) -> dict:
    """Grava a transferência como RASCUNHO. Nada muda no colaborador até `efetivar`."""
    await _ensure(db)
    motivo = str(motivo or "10").strip()
    if motivo not in MOTIVOS:
        raise TransferenciaErro(400, f"Motivo inválido: {motivo!r}. Use 10 ou 11 (tabela 19 do eSocial).")
    # a simulação faz todas as checagens de entrada (colaborador, empresa, cargo, salário, mesma empresa)
    await simular(
        db,
        employee_id=employee_id,
        empresa_destino_cnpj=empresa_destino_cnpj,
        data=data,
        novo_cargo_id=novo_cargo_id,
        novo_salario=novo_salario,
    )
    e = await _colaborador(db, employee_id)
    destino = await _empresa(db, empresa_destino_cnpj)
    dia = _data(data) if data else hoje_manaus()
    dup = (
        await db.execute(
            text("SELECT 1 FROM dp_transferencias WHERE employee_id = CAST(:e AS uuid) AND status = 'rascunho'"),
            {"e": employee_id},
        )
    ).scalar()
    if dup:
        raise TransferenciaErro(409, f"{e['nome']} já tem uma transferência em rascunho — efetive ou cancele antes.")
    tid = (
        await db.execute(
            text(
                "INSERT INTO dp_transferencias (employee_id, empresa_origem_cnpj, empresa_destino_cnpj, data, motivo, "
                " mantem_admissao, novo_cargo_id, novo_salario, observacao, status, criado_por) "
                "VALUES (CAST(:e AS uuid), :co, :cd, :d, :m, :ma, CAST(:cg AS uuid), :sal, :obs, 'rascunho', CAST(:u AS uuid)) "
                "RETURNING id::text"
            ),
            {
                "e": employee_id,
                "co": e.get("empresa_cnpj"),
                "cd": destino["cnpj"],
                "d": dia,
                "m": motivo,
                "ma": bool(mantem_admissao),
                "cg": novo_cargo_id or None,
                "sal": _valor(novo_salario),
                "obs": (observacao or "").strip() or None,
                "u": user_id or None,
            },
        )
    ).scalar()
    await db.commit()
    return {"id": tid, "colaborador": e["nome"], "destino": destino["razao_social"], "data": dia.isoformat()}


# ─────────────────────────────── rascunho eSocial ───────────────────────────────
async def _rascunho_esocial(db, *, tipo: str, ref: str, empresa_id: str | None, employee_id: str, payload: dict) -> str:
    """Uma linha 'proposto' em `esocial_transmissao_propostas` — a MESMA fila humana do orquestrador.
    Nada é transmitido aqui: o rascunho carrega os fatos que o DP confere antes de mandar ao governo."""
    existente = (
        await db.execute(
            text(
                "SELECT id::text FROM esocial_transmissao_propostas "
                "WHERE tipo_evento = :t AND referencia = :r AND status = 'proposto' LIMIT 1"
            ),
            {"t": tipo, "r": ref},
        )
    ).scalar()
    if existente:
        return existente
    return (
        await db.execute(
            text(
                "INSERT INTO esocial_transmissao_propostas (tipo_evento, referencia, empresa_id, employee_id, status, "
                " payload, correlation_id) VALUES (:t, :r, CAST(:em AS uuid), CAST(:e AS uuid), 'proposto', "
                " CAST(:p AS jsonb), :c) RETURNING id::text"
            ),
            {"t": tipo, "r": ref, "em": empresa_id, "e": employee_id, "p": json.dumps(payload, default=str), "c": ref},
        )
    ).scalar()


# ───────────────────────────────── efetivar ─────────────────────────────────
async def efetivar(db, *, transferencia_id: str, user_id: str | None = None) -> dict:
    """Troca a empresa do colaborador, remaneja a alocação pela F5 e enfileira os 2 rascunhos.

    NÃO toca em: `data_admissao`, `status`, `data_demissao`, `hr_vacation_periods`, banco de horas,
    `employee_dp.dependentes`, documentos. Não cria rescisão nem admissão.
    """
    await _ensure(db)
    t = (
        (
            await db.execute(
                text("SELECT * FROM dp_transferencias WHERE id = CAST(:i AS uuid) FOR UPDATE"),
                {"i": transferencia_id},
            )
        )
        .mappings()
        .first()
    )
    if not t:
        raise TransferenciaErro(404, "Transferência não encontrada.")
    if t["status"] != "rascunho":
        raise TransferenciaErro(409, f"Esta transferência já está '{t['status']}'.")

    e = await _colaborador(db, str(t["employee_id"]))
    destino = await _empresa(db, t["empresa_destino_cnpj"])
    origem_id = e.get("empresa_id")
    dia = t["data"]

    ativas = (
        await db.execute(
            text(
                "SELECT id::text, condominio_id::text, posto_id::text, funcao, data_inicio FROM employee_alocacoes "
                "WHERE employee_id = CAST(:e AS uuid) AND ativo ORDER BY data_inicio DESC"
            ),
            {"e": e["id"]},
        )
    ).fetchall()
    if len(ativas) > 1:
        raise TransferenciaErro(
            409,
            f"{e['nome']} tem {len(ativas)} alocações ativas — a movimentação (F5) garante no máximo uma. "
            "Encerre as excedentes antes de transferir.",
        )
    if ativas and ativas[0][4] >= dia:
        raise TransferenciaErro(
            422,
            f"A alocação atual começa em {ativas[0][4]:%d/%m/%Y}; a transferência precisa ser depois disso.",
        )

    # 1) o vínculo muda de CNPJ. Admissão, status e demissão ficam onde estão, de propósito.
    await db.execute(
        text(
            "UPDATE employees SET empresa_id = CAST(:em AS uuid), "
            " cct_cargo_id = coalesce(CAST(:cg AS uuid), cct_cargo_id), "
            " cargo = coalesce((SELECT cargo_nome FROM cct_cargos WHERE id = CAST(:cg AS uuid)), cargo), "
            " salario_base = coalesce(CAST(:sal AS numeric), salario_base) "
            "WHERE id = CAST(:e AS uuid)"
        ),
        {"em": destino["id"], "cg": t["novo_cargo_id"], "sal": t["novo_salario"], "e": e["id"]},
    )
    await db.commit()

    # 2) alocação: encerra em D−1 e reabre em D, pela F5 (mesmo caminho do DP)
    from modules.operacional.services import movimentacao_service as ms

    nota = f"transferência para {destino['razao_social']} ({destino['cnpj']})"
    reaberta = None
    for a in ativas:
        await ms.remover(
            db,
            alocacao_id=a[0],
            data_fim=dia - timedelta(days=1),
            motivo=MOTIVO_ALOCACAO,
            observacao=nota,
            user_id=user_id,
        )
        nova = await ms.alocar(
            db,
            employee_id=e["id"],
            condominio_id=a[1],
            funcao=a[3],
            data_inicio=dia,
            motivo=MOTIVO_ALOCACAO,
            solicitado_por="dp",
            posto_id=a[2],
            observacao=nota,
            user_id=user_id,
        )
        reaberta = nova["id"]
        await db.execute(
            text("UPDATE employee_alocacoes SET alocacao_origem_id = CAST(:o AS uuid) WHERE id = CAST(:n AS uuid)"),
            {"o": a[0], "n": reaberta},
        )

    # 3) os DOIS rascunhos de eSocial — nunca transmitidos
    ref = f"transferencia:{transferencia_id}"
    comum = {
        "transferencia_id": transferencia_id,
        "colaborador": e["nome"],
        "cpf": so_digitos(e.get("cpf")),
        "matricula": e.get("matricula"),
        "data_transferencia": dia,
        "nota": "RASCUNHO — nada foi transmitido ao eSocial. A transmissão é ato humano, no fluxo do eSocial (SST).",
    }
    s2299 = await _rascunho_esocial(
        db,
        tipo="S-2299",
        ref=ref,
        empresa_id=origem_id,
        employee_id=e["id"],
        payload=comum
        | {
            "cnpj_origem": e.get("empresa_cnpj"),
            "dtDeslig": dia,
            "mtvDeslig": t["motivo"],
            "motivo_por_extenso": MOTIVOS[t["motivo"]],
            "atencao": "Desligamento SEM rescisão: não gera verbas rescisórias nem TRCT.",
        },
    )
    s2200 = await _rascunho_esocial(
        db,
        tipo="S-2200",
        ref=ref,
        empresa_id=destino["id"],
        employee_id=e["id"],
        payload=comum
        | {
            "cnpj_destino": destino["cnpj"],
            "tpAdmissao": TP_ADMISSAO[t["motivo"]],
            "indAdmissao": "1",
            "dtAdm": e.get("data_admissao"),
            "sucessaoVinc": {
                "tpInsc": "1",
                "nrInsc": so_digitos(e.get("empresa_cnpj")),
                "matricAnt": e.get("matricula"),
                "dtTransf": dia,
            },
            "cargo": e.get("cargo"),
            "atencao": "dtAdm é a admissão ORIGINAL — o vínculo é contínuo (sucessaoVinc).",
        },
    )

    await db.execute(
        text(
            "UPDATE dp_transferencias SET status = 'efetivada', esocial_s2299_id = CAST(:a AS uuid), "
            " esocial_s2200_id = CAST(:b AS uuid), efetivada_por = CAST(:u AS uuid), "
            " efetivada_em = (now() AT TIME ZONE 'America/Manaus') WHERE id = CAST(:i AS uuid)"
        ),
        {"a": s2299, "b": s2200, "u": user_id or None, "i": transferencia_id},
    )
    await db.commit()
    return {
        "id": transferencia_id,
        "colaborador": e["nome"],
        "destino": destino["razao_social"],
        "alocacao_reaberta": reaberta,
        "esocial_s2299_id": s2299,
        "esocial_s2200_id": s2200,
    }


async def cancelar(db, *, transferencia_id: str, user_id: str | None = None, motivo: str | None = None) -> dict:
    """Cancela um RASCUNHO. Uma transferência efetivada não se cancela aqui — se foi errada, a
    correção é uma nova transferência de volta (e, no governo, um S-3000 pelo fluxo humano)."""
    await _ensure(db)
    st = (
        await db.execute(
            text("SELECT status FROM dp_transferencias WHERE id = CAST(:i AS uuid)"), {"i": transferencia_id}
        )
    ).scalar()
    if st is None:
        raise TransferenciaErro(404, "Transferência não encontrada.")
    if st != "rascunho":
        raise TransferenciaErro(409, f"Só rascunho se cancela; esta está '{st}'.")
    await db.execute(
        text(
            "UPDATE dp_transferencias SET status = 'cancelada', cancelada_por = CAST(:u AS uuid), "
            " cancelada_em = (now() AT TIME ZONE 'America/Manaus'), "
            " observacao = concat_ws(' | ', observacao, CAST(:m AS text)) WHERE id = CAST(:i AS uuid)"
        ),
        {"u": user_id or None, "m": (motivo or "").strip() or None, "i": transferencia_id},
    )
    await db.commit()
    return {"id": transferencia_id, "status": "cancelada"}


# ───────────────────────────── régua de conferência ─────────────────────────────
SQL_ESPELHO_TRANSF = """
SELECT DISTINCT ON (esp.cpf_trabalhador)
       esp.cpf_trabalhador AS cpf, esp.dt_evento AS quando,
       (regexp_match(esp.xml_completo, '<[^>]*mtvDeslig>([^<]+)<'))[1] AS motivo
  FROM esocial_eventos_espelho esp
 WHERE esp.tipo = 'S-2299' AND coalesce(esp.download_status,'ok') = 'ok'
 ORDER BY esp.cpf_trabalhador, esp.dt_evento DESC NULLS LAST
"""
SQL_NOSSOS = """
SELECT e.id::text AS employee_id, e.nome, e.status,
       regexp_replace(coalesce(e.cpf,''),'\\D','','g') AS cpf,
       coalesce(em.razao_social,'(sem empresa)') AS empresa, em.cnpj AS empresa_cnpj
  FROM employees e LEFT JOIN empresas em ON em.id = e.empresa_id
 WHERE coalesce(e.is_homologacao,false) = false
"""
SQL_TRANSF_EFETIVADAS = """
SELECT t.id::text, t.employee_id::text AS employee_id, t.data, t.motivo, t.empresa_destino_cnpj
  FROM dp_transferencias t WHERE t.status = 'efetivada'
"""


async def regua(db, *, tolerancia_dias: int = 45) -> dict:
    """O que o eSocial diz × o que o sistema registra, sobre transferência.

    Nasceu do GEILSON: S-2299 com `mtvDeslig=11` em 30/06/2026 no espelho do governo, `ativo` no
    nosso cadastro e nenhuma transferência registrada — o DP só soube consultando o eSocial.

    Três listas: `so_no_governo` (transferido lá, sem registro aqui — o caso do GEILSON),
    `so_no_sistema` (efetivada aqui, sem S-2299 10/11 no espelho — pode ser só espelho velho, e a
    data da última leitura vai junto) e `casados` (os dois lados batem, dentro de ±`tolerancia_dias`).

    Ausência de evento no espelho NÃO é prova de nada: a consulta é por CPF e o governo bloqueia
    os dias 1 a 7 — os mesmos dois limites que `conferencia_esocial` documenta.
    """
    await _ensure(db)
    espelho = {
        r["cpf"]: dict(r)
        for r in (await db.execute(text(SQL_ESPELHO_TRANSF))).mappings().all()
        if r["cpf"] and (r["motivo"] or "") in _MOTIVOS_TRANSFERENCIA
    }
    nossos = [dict(r) for r in (await db.execute(text(SQL_NOSSOS))).mappings().all()]
    por_cpf = {p["cpf"]: p for p in nossos if p["cpf"]}
    transf: dict[str, list[dict]] = {}
    for r in (await db.execute(text(SQL_TRANSF_EFETIVADAS))).mappings().all():
        transf.setdefault(r["employee_id"], []).append(dict(r))
    ultima = (await db.execute(text("SELECT max(baixado_em)::date FROM esocial_eventos_espelho"))).scalar()

    def _casa(p: dict, quando) -> dict | None:
        for t in transf.get(p["employee_id"], []):
            if quando is None or abs((t["data"] - quando).days) <= tolerancia_dias:
                return t
        return None

    so_no_governo, casados = [], []
    for cpf, ev in espelho.items():
        p = por_cpf.get(cpf)
        if not p:
            continue  # CPF que o governo conhece e nós não — é assunto da admissão, não desta régua
        item = {
            "employee_id": p["employee_id"],
            "cpf": cpf,
            "nome": p["nome"],
            "status_aqui": p["status"],
            "empresa_aqui": p["empresa"],
            "quando_no_governo": str(ev["quando"] or "?"),
            "motivo": ev["motivo"],
            "motivo_por_extenso": MOTIVOS.get(ev["motivo"] or "", "?"),
        }
        casado = _casa(p, ev["quando"])
        if casado:
            casados.append(item | {"transferencia_id": casado["id"], "quando_aqui": str(casado["data"])})
        else:
            so_no_governo.append(item)

    casadas = {c["transferencia_id"] for c in casados}
    so_no_sistema = []
    por_id = {p["employee_id"]: p for p in nossos}
    for eid, lista in transf.items():
        for t in lista:
            if t["id"] in casadas:
                continue
            p = por_id.get(eid, {})
            so_no_sistema.append(
                {
                    "transferencia_id": t["id"],
                    "employee_id": eid,
                    "cpf": p.get("cpf") or "",
                    "nome": p.get("nome") or "(colaborador removido)",
                    "quando_aqui": str(t["data"]),
                    "motivo": t["motivo"],
                    "destino": t["empresa_destino_cnpj"],
                }
            )

    return {
        "so_no_governo": sorted(so_no_governo, key=lambda x: x["quando_no_governo"], reverse=True),
        "so_no_sistema": sorted(so_no_sistema, key=lambda x: x["quando_aqui"], reverse=True),
        "casados": casados,
        "espelho_de": str(ultima) if ultima else None,
        "limite": (
            "A consulta ao eSocial é por CPF e o governo bloqueia os dias 1 a 7: ausência de evento no "
            "espelho não prova que não houve transferência. A data acima é a da última leitura."
        ),
    }

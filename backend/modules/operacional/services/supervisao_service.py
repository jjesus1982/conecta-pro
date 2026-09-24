"""Supervisão do posto (paridade DGX, F8): livro de ocorrências, checklist de supervisão,
chamados e avisos. Regras aqui; a pintura fica em `_dgx_f8_operacional.py`.

· LIVRO — não é tabela nova: é a UNIÃO, por posto e dia (hora de Manaus), do que já se grava
  no posto: `occurrences` (ocorrência), `operacional_passagens_turno` (passagem de turno),
  `visitas` de acompanhamento interno (check-in do gerente) e `operacional_post_orders`
  (instrução). Cada linha diz quem registrou. O oráculo reconta a união com SQL próprio.
· CHECKLIST — usa `checklist_templates/itens/preenchido/respostas` (do módulo Campo, 0 linhas
  em 24/09/2026). Supervisão não tem OS: `ordem_servico_id` deixa de ser NOT NULL e o
  preenchido ganha `post_id`, `executado_por_nome`, `ocorrencia_id`. O "tipo" do DGX
  (posto|veiculo|ronda|supervisao) vai em `categoria_equipamento` (coluna livre que já existia);
  `tipo_servico` fica 'vistoria' (valor do enum do Campo — não quebra a leitura de lá).
  Item obrigatório reprovado → UMA ocorrência por execução (`occurrences`, mesmo caminho da
  ocorrência rápida), nunca duas.
· CHAMADOS — `op_chamados` (nova) + união com `client_portal_tickets` (o cliente já abre
  ticket pelo portal; a tela lê de lá também, só leitura, em vez de duplicar). SLA em minutos
  por prioridade; vencido = aberto/em atendimento além do prazo.
· AVISOS — `communication_announcements` pelo serviço que já existe (`create_announcement` +
  `publish_announcement`). Público `posto` grava `destinatarios_postos`; `funcao` resolve os
  colaboradores do cargo em `destinatarios_funcionarios`. Destinatários/lidos recontados por SQL
  com a MESMA régua do `AnnouncementService._get_recipient_user_ids` (employees.posto_atual_id).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import text

TZ = ZoneInfo("America/Manaus")
SEED_CODIGO = "CHK-SUP-001"
TIPOS_CHECKLIST = {"posto": "Posto", "veiculo": "Veículo", "ronda": "Ronda", "supervisao": "Supervisão"}
# tipo do item (DGX) → `tipo_resposta` (enum do Campo)
TIPOS_ITEM = {"sim_nao": "Sim / Não", "nota": "Nota (0–10)", "texto": "Texto", "foto": "Foto (URL)"}
NOTA_MINIMA = 7.0
PRIORIDADES = {"urgente": 60, "alta": 240, "normal": 1440, "baixa": 4320}  # SLA em minutos
STATUS_CHAMADO = {
    "aberto": "Aberto",
    "em_atendimento": "Em atendimento",
    "resolvido": "Resolvido",
    "cancelado": "Cancelado",
}
ABERTO_POR = {"cliente": "Cliente", "supervisor": "Supervisor", "colaborador": "Colaborador", "sistema": "Sistema"}
CANAIS = {"whatsapp": "WhatsApp", "telefone": "Telefone", "app": "App", "portal": "Portal do cliente"}
CATEGORIAS_CHAMADO = {
    "falta_efetivo": "Falta de efetivo",
    "conduta": "Conduta do colaborador",
    "equipamento": "Equipamento / infraestrutura",
    "acesso": "Controle de acesso",
    "limpeza": "Limpeza / conservação",
    "seguranca": "Segurança",
    "administrativo": "Administrativo",
    "outro": "Outro",
}
PUBLICOS = {"todos": "Todos", "posto": "Posto", "funcao": "Função"}

SEED_ITENS = [
    ("Uniforme completo e em bom estado", "sim_nao", True),
    ("Crachá de identificação visível", "sim_nao", True),
    ("Livro de ocorrências atualizado e assinado", "sim_nao", True),
    ("Rádio / telefone do posto funcionando", "sim_nao", True),
    ("Iluminação da portaria e do perímetro", "sim_nao", True),
    ("Câmeras gravando (verificar no DVR)", "sim_nao", True),
    ("Portão / cancela operando e trancando", "sim_nao", True),
    ("Extintor dentro da validade e desobstruído", "sim_nao", True),
    ("Banheiro do posto limpo e abastecido", "sim_nao", False),
    ("Instruções de posto conhecidas pelo colaborador", "nota", True),
]

_DDL = [
    # checklist do Campo → supervisão sem OS
    "ALTER TABLE checklist_preenchido ALTER COLUMN ordem_servico_id DROP NOT NULL",
    "ALTER TABLE checklist_preenchido ADD COLUMN IF NOT EXISTS post_id uuid",
    "ALTER TABLE checklist_preenchido ADD COLUMN IF NOT EXISTS executado_por_nome varchar(200)",
    "ALTER TABLE checklist_preenchido ADD COLUMN IF NOT EXISTS ocorrencia_id uuid",
    "CREATE INDEX IF NOT EXISTS ix_checklist_preenchido_post ON checklist_preenchido (post_id)",
    # chamados
    "CREATE SEQUENCE IF NOT EXISTS op_chamados_numero_seq",
    """CREATE TABLE IF NOT EXISTS op_chamados (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        numero integer NOT NULL DEFAULT nextval('op_chamados_numero_seq'),
        post_id uuid,
        condominio_id uuid,
        aberto_por varchar(20) NOT NULL DEFAULT 'supervisor',
        solicitante_nome varchar(120),
        canal varchar(20),
        categoria varchar(40),
        prioridade varchar(10) NOT NULL DEFAULT 'normal',
        descricao text NOT NULL,
        status varchar(20) NOT NULL DEFAULT 'aberto',
        atribuido_a uuid,
        aberto_em timestamp NOT NULL DEFAULT (now() AT TIME ZONE 'America/Manaus'),
        atendido_em timestamp,
        resolvido_em timestamp,
        sla_min integer NOT NULL DEFAULT 1440,
        resolucao text,
        created_by uuid
    )""",
    "CREATE INDEX IF NOT EXISTS ix_op_chamados_status ON op_chamados (status, aberto_em)",
]


class SupervisaoErro(ValueError):  # noqa: N818 — nome em PT-BR, padrão da casa
    def __init__(self, status: int, msg: str) -> None:
        super().__init__(msg)
        self.status = status


def agora_manaus() -> datetime:
    return datetime.now(TZ).replace(tzinfo=None)


def hoje_manaus() -> date:
    return datetime.now(TZ).date()


async def _ensure(db) -> None:
    for sql in _DDL:
        await db.execute(text(sql))
    await _seed_checklist(db)
    await db.commit()


async def _seed_checklist(db) -> None:
    tid = (
        await db.execute(
            text(
                "INSERT INTO checklist_templates (id, codigo, nome, descricao, tipo_servico, categoria_equipamento, versao, "
                " is_padrao, is_ativo, is_obrigatorio, tempo_estimado_minutos, created_at, updated_at) "
                "VALUES (gen_random_uuid(), :c, 'Supervisão de posto', 'Checklist padrão da visita do supervisor ao posto (DGX F8)', "
                " 'vistoria', 'supervisao', '1.0', true, true, true, 15, now(), now()) "
                "ON CONFLICT (codigo) DO NOTHING RETURNING id::text"
            ),
            {"c": SEED_CODIGO},
        )
    ).scalar()
    if not tid:
        return
    for ordem, (pergunta, tipo, obrig) in enumerate(SEED_ITENS, start=1):
        await db.execute(
            text(
                "INSERT INTO checklist_itens (id, template_id, ordem, pergunta, tipo_resposta, categoria, obrigatorio, "
                " is_ativo, created_at, updated_at) VALUES (gen_random_uuid(), CAST(:t AS uuid), :o, :p, :tr, 'verificacao', :ob, "
                " true, now(), now())"
            ),
            {"t": tid, "o": ordem, "p": pergunta, "tr": _tipo_resposta(tipo), "ob": obrig},
        )


def _tipo_resposta(tipo: str) -> str:
    return {"sim_nao": "sim_nao", "nota": "numero", "texto": "texto", "foto": "foto"}[tipo]


def tipo_item(tipo_resposta: str) -> str:
    return {"sim_nao": "sim_nao", "numero": "nota", "texto": "texto", "foto": "foto"}.get(tipo_resposta or "", "texto")


# ───────────────────────── livro de ocorrências do posto ─────────────────────────
# Hora de Manaus em todas as fontes: occurred_at/checkin_at são naive-UTC (convenção da casa),
# criada_em/updated_at das passagens e instruções são timestamptz.
SQL_LIVRO = """
SELECT * FROM (
  SELECT 'ocorrencia' AS tipo, o.post_id::text AS post_id,
         (o.occurred_at AT TIME ZONE 'UTC') AT TIME ZONE 'America/Manaus' AS quando,
         coalesce(u.name, u.email, '—') AS quem, o.title AS titulo, o.description AS detalhe,
         o.severity AS grau, o.status AS situacao, o.code AS ref, o.id::text AS ref_id
  FROM occurrences o LEFT JOIN users u ON u.id = o.inspector_id
  WHERE o.is_active AND o.occurred_at >= :desde_utc AND o.occurred_at < :ate_utc
  UNION ALL
  SELECT 'passagem', pt.post_id::text, pt.criada_em AT TIME ZONE 'America/Manaus', pt.author_nome,
         'Passagem de turno — ' || coalesce(pt.turno, '—'),
         concat_ws(' · Pendências: ', pt.resumo, nullif(pt.pendencias, '')), NULL, NULL, NULL, pt.id::text
  FROM operacional_passagens_turno pt WHERE coalesce(pt.is_active, true) AND pt.criada_em >= :desde_tz AND pt.criada_em < :ate_tz
  UNION ALL
  SELECT 'checkin', p.id::text, (v.checkin_at AT TIME ZONE 'UTC') AT TIME ZONE 'America/Manaus',
         coalesce(v.responsavel_nome, '—'),
         'Check-in do gerente' || CASE WHEN v.checkout_at IS NOT NULL THEN ' (saiu ' || to_char((v.checkout_at AT TIME ZONE 'UTC') AT TIME ZONE 'America/Manaus', 'HH24:MI') || ')' ELSE ' (no posto)' END,
         coalesce(v.objetivo, v.endereco, '—'), NULL, NULL, v.numero, v.id::text
  FROM visitas v
  JOIN LATERAL (SELECT p.id FROM posts p WHERE p.client_id = v.cliente_id AND p.is_active ORDER BY p.name LIMIT 1) p ON true
  WHERE v.tipo = 'acompanhamento' AND v.origem = 'interna' AND coalesce(v.ativo, true) AND v.checkin_at IS NOT NULL
    AND v.checkin_at >= :desde_utc AND v.checkin_at < :ate_utc
  UNION ALL
  SELECT 'instrucao', po.post_id::text, po.updated_at AT TIME ZONE 'America/Manaus', coalesce(po.updated_by_nome, '—'),
         'Instrução de posto v' || po.versao || ' — ' || po.titulo, left(po.conteudo, 300), NULL, NULL, NULL, po.id::text
  FROM operacional_post_orders po WHERE po.updated_at >= :desde_tz AND po.updated_at < :ate_tz
) livro ORDER BY quando DESC NULLS LAST LIMIT 800
"""


async def livro(db, desde: datetime | None = None, ate: datetime | None = None) -> list:
    """Linhas do livro entre `desde` e `ate` (hora de Manaus, naive). Default: últimos 30 dias."""
    ate = ate or (agora_manaus() + timedelta(days=1))
    desde = desde or (agora_manaus() - timedelta(days=30))
    return (
        await db.execute(
            text(SQL_LIVRO),
            {
                "desde_utc": desde + timedelta(hours=4),
                "ate_utc": ate + timedelta(hours=4),
                "desde_tz": desde.replace(tzinfo=TZ),
                "ate_tz": ate.replace(tzinfo=TZ),
            },
        )
    ).fetchall()


async def criar_ocorrencia(
    db,
    *,
    user_id: str,
    post_id: str,
    titulo: str,
    descricao: str,
    tipo: str = "incidente",
    gravidade: str = "moderada",
    categoria: str = "operacional",
    employee_id: str | None = None,
    envolvidos: str | None = None,
    quando: datetime | None = None,
    foto_url: str | None = None,
):
    """Grava em `occurrences` pelo MESMO caminho da ocorrência rápida (repositório + schema)."""
    from modules.operacional.occurrences.repositories.occurrence_repository import OccurrenceRepository
    from modules.operacional.occurrences.schemas.occurrence import OccurrenceCreate

    if len((descricao or "").strip()) < 10:
        raise SupervisaoErro(400, "A descrição precisa de ao menos 10 caracteres.")
    titulo = (titulo or descricao).strip()[:120]
    if len(titulo) < 5:
        titulo = (titulo + " · ocorrência")[:120]
    try:
        data = OccurrenceCreate(
            title=titulo,
            description=descricao.strip(),
            occurrence_type=tipo,
            severity=gravidade,
            category=categoria,
            post_id=str(post_id),
            employee_id=employee_id or None,
            witnesses=(envolvidos or "").strip() or None,
            occurred_at=(quando + timedelta(hours=4)) if quando else None,  # Manaus → UTC (convenção do repo)
        )
    except Exception as exc:  # noqa: BLE001
        raise SupervisaoErro(400, f"Dados inválidos: {exc}") from exc
    occ = await OccurrenceRepository(db).create(data, inspector_id=str(user_id))
    if foto_url:
        await db.execute(
            text("UPDATE occurrences SET attachments = CAST(:a AS jsonb) WHERE id = CAST(:i AS uuid)"),
            {"a": '[{"type":"image","url":' + _json_str(foto_url) + ',"name":"foto"}]', "i": str(occ.id)},
        )
        await db.commit()
    return occ


def _json_str(s: str) -> str:
    import json

    return json.dumps(str(s)[:500])


# ───────────────────────── checklist de supervisão ─────────────────────────
SQL_MODELOS = """
SELECT t.id::text, t.codigo, t.nome, coalesce(t.categoria_equipamento, 'supervisao'), coalesce(t.is_ativo, true),
       coalesce(t.is_padrao, false),
       (SELECT count(*) FROM checklist_itens i WHERE i.template_id = t.id AND coalesce(i.is_ativo, true)),
       (SELECT count(*) FROM checklist_itens i WHERE i.template_id = t.id AND coalesce(i.is_ativo, true) AND coalesce(i.obrigatorio, false)),
       (SELECT count(*) FROM checklist_preenchido c WHERE c.template_id = t.id)
FROM checklist_templates t WHERE t.categoria_equipamento IN ('posto','veiculo','ronda','supervisao')
ORDER BY coalesce(t.is_padrao, false) DESC, t.nome
"""
SQL_ITENS = """
SELECT i.id::text, i.template_id::text, i.ordem, i.pergunta, i.tipo_resposta, coalesce(i.obrigatorio, false)
FROM checklist_itens i JOIN checklist_templates t ON t.id = i.template_id
WHERE coalesce(i.is_ativo, true) AND coalesce(t.is_ativo, true)
  AND t.categoria_equipamento IN ('posto','veiculo','ronda','supervisao')
ORDER BY coalesce(t.is_padrao, false) DESC, t.nome, i.ordem
"""


async def criar_modelo(db, *, nome: str, tipo: str, itens_texto: str, user_id: str | None = None) -> dict:
    """Itens: uma linha por item — `pergunta | sim_nao|nota|texto|foto | obrigatório(s/n)`."""
    await _ensure(db)
    nome = (nome or "").strip()
    if len(nome) < 3:
        raise SupervisaoErro(400, "Nome do modelo com ao menos 3 caracteres.")
    if tipo not in TIPOS_CHECKLIST:
        raise SupervisaoErro(400, f"Tipo inválido: use {', '.join(TIPOS_CHECKLIST)}.")
    itens = []
    for n, linha in enumerate((itens_texto or "").splitlines(), start=1):
        if not linha.strip():
            continue
        partes = [p.strip() for p in linha.split("|")]
        pergunta = partes[0]
        t_item = (
            (partes[1].lower() if len(partes) > 1 and partes[1] else "sim_nao")
            .replace("sim/não", "sim_nao")
            .replace("sim/nao", "sim_nao")
        )
        obrig = (partes[2].lower() if len(partes) > 2 and partes[2] else "s") in ("s", "sim", "true", "1", "x")
        if len(pergunta) < 3:
            raise SupervisaoErro(400, f"Linha {n}: pergunta curta demais.")
        if t_item not in TIPOS_ITEM:
            raise SupervisaoErro(400, f"Linha {n}: tipo '{t_item}' inválido (use {', '.join(TIPOS_ITEM)}).")
        itens.append((pergunta[:500], t_item, obrig))
    if not itens:
        raise SupervisaoErro(400, "Informe ao menos um item (uma linha por item).")
    seq = (
        await db.execute(text("SELECT count(*) + 1 FROM checklist_templates WHERE codigo LIKE 'CHK-SUP-%'"))
    ).scalar()
    codigo = f"CHK-SUP-{int(seq):03d}"
    tid = (
        await db.execute(
            text(
                "INSERT INTO checklist_templates (id, codigo, nome, tipo_servico, categoria_equipamento, versao, is_padrao, is_ativo, "
                " is_obrigatorio, tempo_estimado_minutos, created_by, created_at, updated_at) "
                "VALUES (gen_random_uuid(), :c, :n, 'vistoria', :t, '1.0', false, true, true, 15, CAST(:u AS uuid), now(), now()) "
                "RETURNING id::text"
            ),
            {"c": codigo, "n": nome, "t": tipo, "u": user_id or None},
        )
    ).scalar()
    for ordem, (pergunta, t_item, obrig) in enumerate(itens, start=1):
        await db.execute(
            text(
                "INSERT INTO checklist_itens (id, template_id, ordem, pergunta, tipo_resposta, categoria, obrigatorio, is_ativo, "
                " created_at, updated_at) VALUES (gen_random_uuid(), CAST(:t AS uuid), :o, :p, :tr, 'verificacao', :ob, true, now(), now())"
            ),
            {"t": tid, "o": ordem, "p": pergunta, "tr": _tipo_resposta(t_item), "ob": obrig},
        )
    await db.commit()
    return {"id": tid, "codigo": codigo, "itens": len(itens)}


def avaliar(tipo_resposta: str, valor) -> tuple[bool | None, dict]:
    """(conforme|None se N.A./vazio, colunas da resposta). Nota ≥ 7 conforme; texto/foto vazios = sem resposta."""
    v = str(valor).strip() if valor is not None else ""
    t_item = tipo_item(tipo_resposta)
    if t_item == "sim_nao":
        if v.lower() in ("sim", "conforme", "true", "1", "s"):
            return True, {"resposta_boolean": True}
        if v.lower() in ("nao", "não", "nao_conforme", "false", "0", "n"):
            return False, {"resposta_boolean": False}
        return None, {}
    if t_item == "nota":
        if v == "":
            return None, {}
        try:
            n = float(v.replace(",", "."))
        except ValueError:
            raise SupervisaoErro(400, f"Nota inválida: {v!r}.") from None
        if not 0 <= n <= 10:
            raise SupervisaoErro(400, f"Nota fora de 0–10: {n}.")
        return n >= NOTA_MINIMA, {"resposta_numero": n}
    if t_item == "foto":
        return (True, {"foto_url": v[:500]}) if v else (None, {})
    return (True, {"resposta_texto": v}) if v else (None, {})


async def executar(
    db,
    *,
    template_id: str,
    post_id: str,
    respostas: dict,
    observacoes: str | None = None,
    user_id: str | None = None,
    user_nome: str = "redesign",
) -> dict:
    """Grava a execução (`checklist_preenchido` + `checklist_respostas`). Item obrigatório sem
    resposta conta como NÃO conforme. Se houver obrigatório reprovado → 1 ocorrência (e só 1)."""
    await _ensure(db)
    if not template_id or not post_id:
        raise SupervisaoErro(400, "Modelo e posto são obrigatórios.")
    itens = [r for r in (await db.execute(text(SQL_ITENS))).fetchall() if r[1] == template_id]
    if not itens:
        raise SupervisaoErro(404, "Modelo sem itens ativos (ou não é de supervisão).")
    modelo = (
        await db.execute(text("SELECT nome FROM checklist_templates WHERE id = CAST(:t AS uuid)"), {"t": template_id})
    ).scalar()
    posto = (
        await db.execute(text("SELECT name FROM posts WHERE id = CAST(:p AS uuid) AND is_active"), {"p": post_id})
    ).scalar()
    if not posto:
        raise SupervisaoErro(404, "Posto não encontrado ou inativo.")

    agora = agora_manaus()
    linhas: list[tuple] = []  # (item, conforme|None, cols)
    reprovados_obrig: list[str] = []
    for it in itens:
        conforme, cols = avaliar(it[4], respostas.get(f"r_{it[0]}", respostas.get(it[0])))
        if conforme is None and it[5]:
            conforme = False  # obrigatório sem resposta = não conforme
        if conforme is False and it[5]:
            reprovados_obrig.append(it[3])
        linhas.append((it, conforme, cols))
    conformes = sum(1 for _, c, _ in linhas if c is True)
    nao_conf = sum(1 for _, c, _ in linhas if c is False)
    respondidos = sum(1 for _, c, cols in linhas if cols or c is not None)
    pct = round(100.0 * conformes / (conformes + nao_conf), 1) if (conformes + nao_conf) else 0.0

    pid = str(uuid.uuid4())
    await db.execute(
        text(
            "INSERT INTO checklist_preenchido (id, ordem_servico_id, template_id, status, iniciado_at, finalizado_at, total_itens, "
            " itens_respondidos, itens_conformes, itens_nao_conformes, percentual_conformidade, observacoes_gerais, created_at, updated_at, "
            " created_by, post_id, executado_por_nome) "
            "VALUES (CAST(:id AS uuid), NULL, CAST(:t AS uuid), 'finalizado', :a, :a, :tot, :resp, :conf, :nc, :pct, :obs, :a, :a, "
            " CAST(:u AS uuid), CAST(:p AS uuid), :nome)"
        ),
        {
            "id": pid,
            "t": template_id,
            "a": agora,
            "tot": len(itens),
            "resp": respondidos,
            "conf": conformes,
            "nc": nao_conf,
            "pct": pct,
            "obs": (observacoes or "").strip() or None,
            "u": user_id or None,
            "p": post_id,
            "nome": user_nome,
        },
    )
    for it, conforme, cols in linhas:
        await db.execute(
            text(
                "INSERT INTO checklist_respostas (id, checklist_preenchido_id, item_id, resposta_texto, resposta_numero, resposta_boolean, "
                " foto_url, is_conforme, respondido_at, respondido_por) VALUES (gen_random_uuid(), CAST(:c AS uuid), CAST(:i AS uuid), "
                " :rt, :rn, :rb, :fu, :ok, :a, CAST(:u AS uuid))"
            ),
            {
                "c": pid,
                "i": it[0],
                "rt": cols.get("resposta_texto"),
                "rn": cols.get("resposta_numero"),
                "rb": cols.get("resposta_boolean"),
                "fu": cols.get("foto_url"),
                "ok": conforme,
                "a": agora,
                "u": user_id or None,
            },
        )
    ocorrencia = None
    if reprovados_obrig and user_id:
        occ = await criar_ocorrencia(  # commita
            db,
            user_id=user_id,
            post_id=post_id,
            titulo=f"Checklist reprovado — {modelo} — {posto}"[:120],
            descricao=(
                f"Checklist '{modelo}' em {posto} ({agora:%d/%m/%Y %H:%M}, por {user_nome}): "
                f"{len(reprovados_obrig)} item(ns) obrigatório(s) não conforme(s): " + "; ".join(reprovados_obrig) + "."
            ),
            tipo="nao_conformidade_documental",
            gravidade="grave" if len(reprovados_obrig) >= 3 else "moderada",
            categoria="operacional",
            quando=agora,
        )
        ocorrencia = str(occ.id)
        await db.execute(
            text("UPDATE checklist_preenchido SET ocorrencia_id = CAST(:o AS uuid) WHERE id = CAST(:i AS uuid)"),
            {"o": ocorrencia, "i": pid},
        )
    await db.commit()
    return {
        "id": pid,
        "conformes": conformes,
        "nao_conformes": nao_conf,
        "percentual": pct,
        "reprovados_obrigatorios": reprovados_obrig,
        "ocorrencia_id": ocorrencia,
    }


# ───────────────────────── chamados ─────────────────────────
async def abrir_chamado(
    db,
    *,
    descricao: str,
    post_id: str | None = None,
    aberto_por: str = "supervisor",
    solicitante_nome: str | None = None,
    canal: str | None = None,
    categoria: str | None = None,
    prioridade: str = "normal",
    user_id: str | None = None,
) -> dict:
    await _ensure(db)
    if len((descricao or "").strip()) < 10:
        raise SupervisaoErro(400, "Descreva o chamado (mín. 10 caracteres).")
    if aberto_por not in ABERTO_POR or prioridade not in PRIORIDADES:
        raise SupervisaoErro(400, "Aberto por / prioridade inválidos.")
    if canal and canal not in CANAIS:
        raise SupervisaoErro(400, f"Canal inválido: {canal!r}.")
    cond = None
    if post_id:
        cond = (
            await db.execute(
                text(
                    "SELECT c.id::text FROM posts p LEFT JOIN condominios c ON c.client_id = p.client_id AND c.ativo "
                    "WHERE p.id = CAST(:p AS uuid) AND p.is_active LIMIT 1"
                ),
                {"p": post_id},
            )
        ).fetchone()
        if cond is None:
            raise SupervisaoErro(404, "Posto não encontrado ou inativo.")
    r = (
        await db.execute(
            text(
                "INSERT INTO op_chamados (post_id, condominio_id, aberto_por, solicitante_nome, canal, categoria, prioridade, descricao, "
                " sla_min, created_by, aberto_em) VALUES (CAST(:p AS uuid), CAST(:c AS uuid), :ab, :sn, :ca, :cat, :pr, :d, :sla, "
                " CAST(:u AS uuid), :agora) RETURNING id::text, numero"
            ),
            {
                "p": post_id or None,
                "c": (cond[0] if cond else None),
                "ab": aberto_por,
                "sn": (solicitante_nome or "").strip() or None,
                "ca": canal or None,
                "cat": categoria or None,
                "pr": prioridade,
                "d": descricao.strip(),
                "sla": PRIORIDADES[prioridade],
                "u": user_id or None,
                "agora": agora_manaus(),
            },
        )
    ).fetchone()
    await db.commit()
    return {"id": r[0], "numero": r[1], "sla_min": PRIORIDADES[prioridade]}


async def assumir_chamado(db, *, chamado_id: str, employee_id: str | None, user_id: str | None = None) -> dict:
    await _ensure(db)
    row = (
        await db.execute(text("SELECT status FROM op_chamados WHERE id = CAST(:i AS uuid)"), {"i": chamado_id})
    ).fetchone()
    if not row:
        raise SupervisaoErro(404, "Chamado não encontrado.")
    if row[0] != "aberto":
        raise SupervisaoErro(409, f"Chamado está '{STATUS_CHAMADO.get(row[0], row[0])}' — só se assume chamado aberto.")
    if not employee_id:
        employee_id = (
            (
                await db.execute(
                    text("SELECT employee_id::text FROM users WHERE id = CAST(:u AS uuid)"), {"u": user_id}
                )
            ).scalar()
            if user_id
            else None
        )
    await db.execute(
        text(
            "UPDATE op_chamados SET status='em_atendimento', atendido_em=:a, atribuido_a=CAST(:e AS uuid) WHERE id=CAST(:i AS uuid)"
        ),
        {"a": agora_manaus(), "e": employee_id or None, "i": chamado_id},
    )
    await db.commit()
    return {"id": chamado_id, "status": "em_atendimento"}


async def resolver_chamado(db, *, chamado_id: str, resolucao: str, cancelar: bool = False) -> dict:
    await _ensure(db)
    row = (
        await db.execute(
            text("SELECT status, aberto_em, atendido_em, sla_min FROM op_chamados WHERE id = CAST(:i AS uuid)"),
            {"i": chamado_id},
        )
    ).fetchone()
    if not row:
        raise SupervisaoErro(404, "Chamado não encontrado.")
    if row[0] in ("resolvido", "cancelado"):
        raise SupervisaoErro(409, f"Chamado já está '{STATUS_CHAMADO[row[0]]}'.")
    if len((resolucao or "").strip()) < 5:
        raise SupervisaoErro(400, "Descreva a resolução (mín. 5 caracteres).")
    agora = agora_manaus()
    await db.execute(
        text(
            "UPDATE op_chamados SET status=:s, resolvido_em=:a, atendido_em=coalesce(atendido_em, :a), resolucao=:r "
            "WHERE id=CAST(:i AS uuid)"
        ),
        {"s": "cancelado" if cancelar else "resolvido", "a": agora, "r": resolucao.strip(), "i": chamado_id},
    )
    await db.commit()
    no_prazo = agora <= row[1] + timedelta(minutes=int(row[3] or 0))
    return {"id": chamado_id, "status": "cancelado" if cancelar else "resolvido", "sla_cumprido": no_prazo}


# ───────────────────────── avisos ─────────────────────────
# Régua de destinatários = a do AnnouncementService (todos = ativos; posto = employees.posto_atual_id;
# funcionário = lista). Lido = communication_announcement_reads via users.employee_id.
SQL_AVISOS = """
WITH viv AS (
  SELECT a.id, a.titulo, a.prioridade, a.tipo, a.destinatarios_tipo, a.destinatarios_postos, a.destinatarios_funcionarios,
         a.data_publicacao, a.data_expiracao, a.requer_confirmacao, a.status, a.extra_data, a.created_at
  FROM communication_announcements a
  WHERE coalesce(a.is_active, true) AND lower(a.status) IN ('published', 'publicado', 'scheduled', 'agendado')
    AND (a.data_expiracao IS NULL OR a.data_expiracao >= :agora)
), dest AS (
  SELECT v.id AS aid, e.id AS eid, e.nome, u.id AS uid
  FROM viv v JOIN employees e ON e.status = 'ativo' AND coalesce(e.is_homologacao, false) = false
   AND ( v.destinatarios_tipo IN ('all', 'todos')
      OR (v.destinatarios_tipo IN ('post', 'posto') AND e.posto_atual_id = ANY(coalesce(v.destinatarios_postos, ARRAY[]::uuid[])))
      OR (v.destinatarios_tipo IN ('employee', 'funcionario') AND e.id = ANY(coalesce(v.destinatarios_funcionarios, ARRAY[]::uuid[]))) )
  LEFT JOIN users u ON u.employee_id = e.id
), lidos AS (
  -- agrupa por PESSOA, não por usuário: um colaborador com 2 logins contava 2 vezes (o oráculo pegou: 14 ≠ 12)
  SELECT d.aid, d.eid, d.nome, bool_or(r.read_at IS NOT NULL) AS leu, bool_or(r.confirmed_at IS NOT NULL) AS confirmou,
         bool_or(d.uid IS NOT NULL) AS tem_usuario
  FROM dest d LEFT JOIN communication_announcement_reads r ON r.announcement_id = d.aid AND r.user_id = d.uid AND coalesce(r.is_active, true)
  GROUP BY d.aid, d.eid, d.nome
)
SELECT v.id::text, v.titulo, v.prioridade, v.tipo, v.destinatarios_tipo,
       (v.data_publicacao AT TIME ZONE 'UTC') AT TIME ZONE 'America/Manaus',
       (v.data_expiracao AT TIME ZONE 'UTC') AT TIME ZONE 'America/Manaus', v.requer_confirmacao, v.status,
       (SELECT string_agg(p.name, ', ') FROM posts p WHERE p.id = ANY(coalesce(v.destinatarios_postos, ARRAY[]::uuid[]))) AS postos,
       v.extra_data->>'funcao' AS funcao,
       (SELECT count(*) FROM lidos l WHERE l.aid = v.id) AS destinatarios,
       (SELECT count(*) FROM lidos l WHERE l.aid = v.id AND l.leu) AS lidos,
       (SELECT count(*) FROM lidos l WHERE l.aid = v.id AND l.confirmou) AS confirmados,
       (SELECT count(*) FROM lidos l WHERE l.aid = v.id AND NOT l.tem_usuario) AS sem_usuario,
       (SELECT string_agg(l.nome, ', ' ORDER BY l.nome) FROM lidos l WHERE l.aid = v.id AND NOT l.leu) AS nao_leram
FROM viv v ORDER BY v.data_publicacao DESC NULLS LAST, v.created_at DESC
"""


async def avisos(db) -> list:
    return (await db.execute(text(SQL_AVISOS), {"agora": agora_manaus()})).fetchall()


async def criar_aviso(
    db,
    *,
    current_user,
    titulo: str,
    conteudo: str,
    publico: str,
    post_id: str | None = None,
    funcao: str | None = None,
    inicio=None,
    fim=None,
    prioridade: str = "normal",
    categoria: str = "informativo",
    requer_confirmacao: bool = False,
) -> dict:
    """Grava pelo serviço de comunicados que já existe e publica (agora, ou agendado no início)."""
    from modules.operacional.communication.controllers.announcement_controller import (
        create_announcement,
        publish_announcement,
    )
    from modules.operacional.communication.schemas.communication_schemas import (
        AnnouncementCreate,
        AnnouncementPublishRequest,
    )

    titulo = (titulo or "").strip()
    conteudo = (conteudo or "").strip()
    if len(titulo) < 3 or len(conteudo) < 10:
        raise SupervisaoErro(400, "Título (mín. 3) e conteúdo (mín. 10) são obrigatórios.")
    if publico not in PUBLICOS:
        raise SupervisaoErro(400, f"Público inválido: use {', '.join(PUBLICOS)}.")
    hoje = hoje_manaus()
    d_ini = date.fromisoformat(str(inicio)[:10]) if inicio else hoje
    d_fim = date.fromisoformat(str(fim)[:10]) if fim else None
    if d_fim and d_fim < d_ini:
        raise SupervisaoErro(422, "Fim da vigência anterior ao início.")
    target_type, target_ids, extra = "all", None, {}
    if publico == "posto":
        if not post_id:
            raise SupervisaoErro(400, "Escolha o posto.")
        target_type = "post"
    elif publico == "funcao":
        if not funcao:
            raise SupervisaoErro(400, "Escolha a função.")
        ids = [
            r[0]
            for r in (
                await db.execute(
                    text(
                        "SELECT id::text FROM employees WHERE status = 'ativo' AND coalesce(is_homologacao,false) = false "
                        "AND upper(coalesce(cargo,'')) = upper(:c)"
                    ),
                    {"c": funcao},
                )
            ).fetchall()
        ]
        if not ids:
            raise SupervisaoErro(422, f"Nenhum colaborador ativo com a função {funcao}.")
        target_type, target_ids, extra = "employee", ids, {"funcao": funcao.upper()}
    # expiração no fim do dia de Manaus, em UTC (o serviço compara com utcnow)
    expira = datetime.combine(d_fim, datetime.max.time()).replace(microsecond=0) + timedelta(hours=4) if d_fim else None
    agenda = datetime.combine(d_ini, datetime.min.time()) + timedelta(hours=4) if d_ini > hoje else None
    data = AnnouncementCreate(
        title=titulo,
        content=conteudo,
        target_type=target_type,
        target_ids=target_ids,
        priority=prioridade or "normal",
        category=categoria or "informativo",
        requires_acknowledgment=bool(requer_confirmacao),
        publish_at=agenda,
        expires_at=expira,
    )
    res = await create_announcement(data=data, current_user=current_user, db=db)
    aid = str(res.id)
    # o repositório só conhece destinatarios_funcionarios: posto e função entram aqui
    await db.execute(
        text(
            "UPDATE communication_announcements SET destinatarios_postos = CASE WHEN :tp = 'post' THEN ARRAY[CAST(:p AS uuid)] ELSE destinatarios_postos END, "
            " destinatarios_funcionarios = CASE WHEN :tp = 'post' THEN NULL ELSE destinatarios_funcionarios END, "
            # o repositório grava jsonb 'null' (não SQL NULL): coalesce não pega, e null || {} vira ARRAY
            " extra_data = (CASE WHEN jsonb_typeof(extra_data) = 'object' THEN extra_data ELSE '{}'::jsonb END) || CAST(:x AS jsonb), "
            " data_expiracao = :exp, total_destinatarios = :n WHERE id = CAST(:i AS uuid)"
        ),
        {
            "tp": target_type,
            "p": post_id if publico == "posto" else None,
            "x": __import__("json").dumps(
                extra
                | {
                    "publico": publico,
                    "vigencia_inicio": d_ini.isoformat(),
                    "vigencia_fim": d_fim.isoformat() if d_fim else None,
                }
            ),
            "exp": expira,
            "n": await _conta_destinatarios(db, target_type, post_id, target_ids),
            "i": aid,
        },
    )
    await db.commit()
    publicado = False
    if agenda is None:
        await publish_announcement(
            announcement_id=uuid.UUID(aid), request_data=AnnouncementPublishRequest(), current_user=current_user, db=db
        )
        publicado = True
    return {"id": aid, "publicado": publicado, "agendado_para": d_ini.isoformat() if agenda else None}


async def _conta_destinatarios(db, target_type: str, post_id: str | None, ids: list | None) -> int:
    if target_type == "post":
        sql, p = (
            "SELECT count(*) FROM employees WHERE status='ativo' AND coalesce(is_homologacao,false)=false AND posto_atual_id = CAST(:p AS uuid)",
            {"p": post_id},
        )
    elif target_type == "employee":
        return len(ids or [])
    else:
        sql, p = "SELECT count(*) FROM employees WHERE status='ativo' AND coalesce(is_homologacao,false)=false", {}
    return int((await db.execute(text(sql), p)).scalar() or 0)

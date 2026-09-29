"""Quem entra no kit de cada condomínio, numa competência. FONTE ÚNICA da regra.

Nasceu em 29/09/2026 de um script em `scripts/qa/`. Virou serviço porque a tela da Pyetra
precisa da MESMA regra, e a regra mudou **três vezes em um dia** — cada vez por uma correção do
Jordan. Duas cópias teriam divergido na primeira.

## A âncora é o posto gravado NA BATIDA. Três fontes foram descartadas, cada uma por medição

1. **`employee_alocacoes` não serve como histórico.** Diz onde a pessoa está HOJE. Medido: a
   alocação do RILEM ao GREEN HILLS traz `data_inicio = 2026-01-01` e a do MAURICIO
   `2026-03-01` — num condomínio que **começou em 01/09/2026**. ⭐ As datas são ficção; usá-las
   importa o condomínio de hoje para dentro do mês passado. Foi o erro que o Jordan pegou.

2. **`shifts` perde gente em silêncio.** Descobrir o condomínio atravessando a escala deixa de
   fora quem bateu SEM turno lançado: medido em agosto/2026, 4 pessoas com **84, 57, 49 e 33
   batidas** e nenhum turno. Sairiam caladas do kit do cliente.

3. **`employees.status` não serve como população.** Dizia 66 ativos e **nenhum tinha data de
   demissão** — 13 saídas nunca foram registradas.

Sobra `gp_clock_punches.posto_id`, gravado no momento do fato: resolveu **60 de 63** pessoas em
agosto/2026. As que sobram vão para `kit_condominio_manual`, onde um humano decide pela tela —
com nome e data. **Nunca deduzir:** deduzir foi o Green Hills.

⚠️ Postos da própria CONECTAMAIS ELETRONICA (os «— Conecta Village») ficam FORA: o kit é
documento do CLIENTE. Doze pessoas trabalhavam lá e a operação encerrou em 31/08/2026.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date

from sqlalchemy import text

#: Postos da própria empresa — o que é nosso não entra em kit de cliente.
CASA = "CONECTAMAIS ELETRONICA LTDA"
#: Onde a resolução humana mora (criada por `scripts/qa/criar_kit_condominio_manual.py`).
TABELA_MANUAL = "kit_condominio_manual"
#: Kits que não são de condomínio de cliente. Ficam fora da reconciliação, de propósito.
NAO_CLIENTE = ("CONECTA VILLAGE", "CONECTA MAIS", "CONECTAMAIS", "PATRIMONIAL", "VEGA MANAUS")

#: Fontes que o espelho conta como MEDIÇÃO. Espelha `espelho_service.FONTES_MEDIDAS`.
FONTES_MEDIDAS = ("mobile", "contingencia", "facial", "biometria", "app", "relogio")


def canon(nome: str) -> str:
    """«Condomínio Ideal Flores da Cidade» e «IDEAL FLORES» viram a mesma chave.

    Existem DOIS vocabulários no banco para o mesmo prédio: `posts.name` usa o nome longo e
    `condominios.nome` o curto. Sem canonizar, o mesmo condomínio rende dois kits.

    NÃO inventa correspondência: quem não casar sai com o nome original e aparece separado no
    relatório, para um humano olhar. Casar por aproximação silenciosa é como dois clientes
    passam a dividir um PDF.
    """
    s = unicodedata.normalize("NFKD", nome or "").encode("ascii", "ignore").decode().upper()
    s = re.sub(r"\b(CONDOMINIO|RESIDENCIAL|COND|EDIFICIO|DO|DA|DE|DOS|DAS|CIDADE|VILLAGE)\b", " ", s)
    s = re.sub(r"[^A-Z0-9]+", " ", s).strip()
    return re.sub(r"\s+", " ", s)


def _bounds(competencia: date) -> tuple[str, str]:
    """(primeiro dia, primeiro dia do mês seguinte) em ISO — janela semiaberta."""
    ini = competencia.replace(day=1)
    fim = date(ini.year + (ini.month == 12), 1 if ini.month == 12 else ini.month + 1, 1)
    return ini.isoformat(), fim.isoformat()


def resolucao_humana(db, competencia: date) -> dict[str, tuple[str, str]]:
    """`{employee_id: (condomínio, quem definiu)}` — o que só um humano podia dizer.

    Tabela AUSENTE devolve vazio em vez de estourar: banco sem a tabela ainda tem de montar o
    roster, e o relatório mostra quem ficou sem condomínio — a falta aparece, não vira silêncio.
    """
    try:
        rows = db.execute(
            text(
                "SELECT employee_id::text, condominio, definido_por "
                f"  FROM {TABELA_MANUAL} WHERE competencia = :c"  # noqa: S608 — constante do módulo
            ),
            {"c": competencia.replace(day=1)},
        ).all()
    except Exception:  # noqa: BLE001 — tabela pode não existir
        return {}
    return {r[0]: (r[1], r[2]) for r in rows}


def roster(db, competencia: date) -> tuple[dict[str, set[str]], dict[str, str], dict[str, str]]:
    """`(por_condomínio, nomes, motivo_por_pessoa)` da competência.

    `motivo_por_pessoa` existe para a TELA: sem o motivo, a conferência pede fé em vez de
    permitir discordância. É o que deixa a Pyetra dizer «esse aí não é do Mirante».
    """
    ini, fim = _bounds(competencia)
    por_cond: dict[str, set[str]] = {}
    nomes: dict[str, str] = {}
    motivo: dict[str, str] = {}
    for r in db.execute(
        text(
            "SELECT p.employee_id::text AS eid, e.nome, po.name AS cond, count(*) AS n "
            "  FROM gp_clock_punches p "
            "  JOIN employees e ON e.id = p.employee_id "
            "  JOIN posts po ON po.id::text = p.posto_id "
            "  JOIN clients c ON c.id = po.client_id "
            " WHERE p.punch_timestamp >= :i AND p.punch_timestamp < :f AND c.name <> :casa "
            " GROUP BY 1, 2, 3"
        ),
        {"i": ini, "f": fim, "casa": CASA},
    ).mappings():
        por_cond.setdefault(r["cond"], set()).add(r["eid"])
        nomes[r["eid"]] = r["nome"]
        motivo[f"{canon(r['cond'])}|{r['eid']}"] = f"{r['n']} batida(s) com este posto gravado"
    # 🔴 29/09/2026 — AUSÊNCIA DOCUMENTADA TAMBÉM PERTENCE AO KIT.
    #
    # O roster era ancorado só na batida, e isso excluía quem estava AFASTADO ou de FÉRIAS: essas
    # pessoas não batem, e a folha de ponto que mostra o afastamento **é** a documentação daquele
    # mês para o cliente. Medido em 08/2026: dos alocados sem batida, ARYELTON (suspenso) e CINTIA
    # (afastado_inss) têm afastamento SST registrado — pertencem ao kit; só o `candidato` não.
    #
    # ⭐ Sem isto o roster brigaria com o montador: `kit_builder_service` (que passou a respeitar a
    # mesma regra hoje) põe a pessoa de noite e a conferência da Pyetra a tiraria de manhã, todo
    # dia. Duas fontes discordando sobre o documento de alguém é pior que uma fonte imperfeita.
    # ⚠️ LÊ `allocations`, NÃO `employee_alocacoes` — e isto foi um erro meu, corrigido na
    # comparação com o builder. Existem DUAS tabelas de alocação e elas DISCORDAM:
    #
    #   FRANCISCO RAMON em agosto/2026:
    #     `allocations`         → Laranjeiras (01/03 → 25/09)   ← concorda com as batidas dele
    #     `employee_alocacoes`  → Villa dos Pássaros (desde 01/03)
    #
    # A primeira versão deste laço usava `employee_alocacoes` e o colocou no condomínio ERRADO.
    # Medido: `allocations` cobre 93 pessoas, `employee_alocacoes` 65, com 28 só na primeira e
    # ZERO só na segunda — ela é a fonte mais completa, e é a que `kit_builder_service` usa.
    # Duas fontes para a mesma pergunta, e a escolha errada põe gente no kit do cliente errado.
    for r in db.execute(
        text(
            "SELECT DISTINCT a.employee_id::text AS eid, e.nome, po.name AS cond "
            "  FROM allocations a "
            "  JOIN employees e ON e.id = a.employee_id "
            "  JOIN posts po ON po.id = a.post_id "
            "  JOIN clients c ON c.id = po.client_id "
            " WHERE c.name <> :casa "
            "   AND a.start_date < (CAST(:i AS date) + INTERVAL '1 month') "
            "   AND (a.end_date IS NULL OR a.end_date >= CAST(:i AS date)) "
            "   AND (EXISTS (SELECT 1 FROM sst_afastamentos sa "
            "                 WHERE sa.employee_id::varchar = a.employee_id::varchar "
            "                   AND sa.data_inicio < (CAST(:i AS date) + INTERVAL '1 month') "
            "                   AND coalesce(sa.data_retorno, sa.data_fim_prevista, CAST(:i AS date)) "
            "                       >= CAST(:i AS date)) "
            "     OR EXISTS (SELECT 1 FROM hr_vacation_requests vr "
            "                 WHERE vr.employee_id::varchar = a.employee_id::varchar "
            "                   AND lower(coalesce(vr.status,'')) IN "
            "                       ('aprovada','approved','hr_approved','gozando','concluida') "
            "                   AND vr.start_date < (CAST(:i AS date) + INTERVAL '1 month') "
            "                   AND vr.end_date >= CAST(:i AS date)))"
        ),
        {"i": ini, "casa": CASA},
    ).mappings():
        if not r["cond"]:
            continue
        # Reaproveita a chave já presente quando canonizam igual: `posts.name` (longo) e
        # `condominios.nome` (curto) são dois vocabulários para o mesmo prédio, e sem isto o
        # mesmo condomínio vira DOIS no roster — medido e corrigido hoje.
        chave = next((c for c in por_cond if canon(c) == canon(r["cond"])), r["cond"])
        por_cond.setdefault(chave, set()).add(r["eid"])
        nomes[r["eid"]] = r["nome"]
        motivo[f"{canon(chave)}|{r['eid']}"] = "alocado com ausência documentada (afastamento/férias)"

    for eid, (cond, quem) in resolucao_humana(db, competencia).items():
        nome = db.execute(text("SELECT nome FROM employees WHERE id::text = :e"), {"e": eid}).scalar()
        if not nome:
            continue  # pessoa apagada depois da decisão; o relatório mostra a falta
        por_cond.setdefault(cond, set()).add(eid)
        nomes[eid] = nome
        motivo[f"{canon(cond)}|{eid}"] = f"definido à mão por {quem}"
    return por_cond, nomes, motivo


def sem_condominio(db, competencia: date) -> dict[str, tuple[str, int]]:
    """`{employee_id: (nome, batidas_no_mes)}` — bateu no mês e não se sabe onde.

    Só entram quem NÃO bateu em posto nosso: quem só trabalhou no «Conecta Village» não
    pertence a kit de cliente nenhum, e pedir condomínio para essas pessoas seria pedir que a
    Pyetra inventasse vínculo que não existe.
    """
    ini, fim = _bounds(competencia)
    por_cond, _, _ = roster(db, competencia)
    colocados = {e for v in por_cond.values() for e in v}
    na_casa = {
        r[0]
        for r in db.execute(
            text(
                "SELECT DISTINCT p.employee_id::text FROM gp_clock_punches p "
                "  JOIN posts po ON po.id::text = p.posto_id JOIN clients c ON c.id = po.client_id "
                " WHERE p.punch_timestamp >= :i AND p.punch_timestamp < :f AND c.name = :casa"
            ),
            {"i": ini, "f": fim, "casa": CASA},
        ).all()
    }
    out: dict[str, tuple[str, int]] = {}
    for r in db.execute(
        text(
            "SELECT p.employee_id::text, e.nome, count(*) FROM gp_clock_punches p "
            "  JOIN employees e ON e.id = p.employee_id "
            " WHERE p.punch_timestamp >= :i AND p.punch_timestamp < :f "
            " GROUP BY 1, 2"
        ),
        {"i": ini, "f": fim},
    ).all():
        if r[0] in colocados or r[0] in na_casa:
            continue
        out[r[0]] = (r[1], int(r[2]))
    return out


def condominios_conhecidos(db, competencia: date) -> list[str]:
    """Nomes de condomínio de CLIENTE com batida na competência, canônicos e ordenados.

    A lista da tela sai daqui e não de `condominios`/`condominiums`: oferecer condomínio que não
    teve ninguém no mês convida a erro, e o Green Hills (aberto em 01/09) é o exemplo vivo —
    ele não pode aparecer como opção de agosto.
    """
    ini, fim = _bounds(competencia)
    vistos = {
        r[0]
        for r in db.execute(
            text(
                "SELECT DISTINCT po.name FROM gp_clock_punches p "
                "  JOIN posts po ON po.id::text = p.posto_id JOIN clients c ON c.id = po.client_id "
                " WHERE p.punch_timestamp >= :i AND p.punch_timestamp < :f AND c.name <> :casa"
            ),
            {"i": ini, "f": fim, "casa": CASA},
        ).all()
        if r[0]
    }
    return sorted(vistos)


def plano_reconciliacao(db, competencia: date) -> dict:
    """O que sai de qual kit, e POR QUÊ. Não escreve nada.

    Devolve `{linhas: [...], resumo: {...}, sem_condominio: [...]}`. Cada linha traz o motivo,
    porque conferência sem motivo pede fé em vez de permitir discordância.
    """
    comp1 = competencia.replace(day=1)
    por_cond, nomes, motivo = roster(db, competencia)
    roster_canon: dict[str, set[str]] = {}
    for c, eids in por_cond.items():
        roster_canon.setdefault(canon(c), set()).update(eids)

    kits = db.execute(
        text(
            "SELECT g.id::text AS kid, coalesce(cd.name, cd2.nome, gc.name, '?') AS cond "
            "  FROM ged_document_kits g "
            "  LEFT JOIN condominiums cd ON cd.id = g.client_id "
            "  LEFT JOIN condominios  cd2 ON cd2.id = g.client_id "
            "  LEFT JOIN ged_clients  gc ON gc.id = g.client_id "
            " WHERE g.reference_month = :c"
        ),
        {"c": comp1},
    ).mappings().all()

    linhas: list[dict] = []
    for k in kits:
        nome_cond = k["cond"]
        if any(tag in nome_cond.upper() for tag in NAO_CLIENTE):
            continue
        ck = canon(nome_cond)
        esperados = roster_canon.get(ck)
        if esperados is None:
            # Kit sem roster: NÃO adivinha e NÃO remove. Falha aberto, para o humano.
            linhas.append(
                {
                    "condominio": nome_cond,
                    "kit_id": k["kid"],
                    "pessoa": "—",
                    "employee_id": None,
                    "tipo": "kit_sem_roster",
                    "acao": "nada — precisa de conferência humana",
                    "motivo": (
                        "este kit não casou com nenhum condomínio que teve batida na "
                        "competência. Pode ser nome diferente, ou contrato que começou depois "
                        "(o Green Hills abriu em 01/09 e não tem agosto). Nada foi tocado."
                    ),
                }
            )
            continue
        for r in db.execute(
            text(
                "SELECT DISTINCT k.employee_id::text AS eid, e.nome "
                "  FROM ged_kit_documents k JOIN employees e ON e.id = k.employee_id "
                " WHERE k.kit_id::text = :kid AND k.employee_id IS NOT NULL"
            ),
            {"kid": k["kid"]},
        ).mappings():
            if r["eid"] in esperados:
                continue
            n_docs = db.execute(
                text(
                    "SELECT count(*) FROM ged_kit_documents "
                    " WHERE kit_id::text = :kid AND employee_id::text = :e"
                ),
                {"kid": k["kid"], "e": r["eid"]},
            ).scalar() or 0
            onde = sorted(c for c, eids in por_cond.items() if r["eid"] in eids)
            linhas.append(
                {
                    "condominio": nome_cond,
                    "kit_id": k["kid"],
                    "pessoa": r["nome"],
                    "employee_id": r["eid"],
                    "tipo": "remover",
                    "acao": f"remover {n_docs} vínculo(s) deste kit",
                    "motivo": (
                        f"trabalhou em {' e '.join(onde)} nesta competência, não aqui"
                        if onde
                        else "não tem nenhuma batida em posto de cliente nesta competência"
                    ),
                }
            )
    pendentes = sem_condominio(db, competencia)
    faltando = [
        {"employee_id": e, "pessoa": n, "batidas": q}
        for e, (n, q) in sorted(pendentes.items(), key=lambda x: -x[1][1])
    ]
    # 🔴 29/09/2026, achado pelo TESTE de ida-e-volta: quem está apenas SEM RESOLUÇÃO não pode
    # ser removido. «Sei que essa pessoa é de outro condomínio» e «não sei onde essa pessoa
    # trabalhou» levam à mesma linha no relatório e a consequências opostas: a primeira é
    # correção, a segunda apagaria o vínculo por ignorância nossa.
    #
    # ⭐ A ignorância do sistema não pode virar ato sobre o documento de ninguém. Estas linhas
    # viram «nada» e explicam o que fazer — e `a_remover` deixa de contá-las, senão a mensagem
    # promete uma remoção que não acontece.
    for ln in linhas:
        if ln["employee_id"] in pendentes:
            ln["acao"] = "nada — defina o condomínio dela primeiro"
            ln["motivo"] = (
                f"{pendentes[ln['employee_id']][1]} batida(s) no mês e nenhuma gravou o posto: o "
                "sistema NÃO sabe onde ela trabalhou, e não vai apagar vínculo por não saber. "
                "Use «Definir condomínio de quem ficou sem» e confira de novo."
            )
            ln["employee_id"] = None  # sai do lote de remoção
            ln["tipo"] = "pendente"    # e NÃO é "kit sem roster": contadores separados
    return {
        "linhas": linhas,
        "sem_condominio": faltando,
        "resumo": {
            "competencia": f"{comp1:%m/%Y}",
            "kits": len([k for k in kits if not any(t in k["cond"].upper() for t in NAO_CLIENTE)]),
            "pessoas_no_roster": len({e for v in por_cond.values() for e in v}),
            # Contar por TIPO explícito, não por "employee_id é nulo": três situações
            # diferentes caíam no mesmo balde e a mensagem prometia remoção que não haveria.
            "a_remover": len([x for x in linhas if x.get("tipo") == "remover"]),
            "kits_sem_roster": len([x for x in linhas if x.get("tipo") == "kit_sem_roster"]),
            "pendentes_no_kit": len([x for x in linhas if x.get("tipo") == "pendente"]),
            "sem_condominio": len(faltando),
        },
    }


def aplicar_reconciliacao(db, competencia: date, quem: str) -> dict:
    """Remove os vínculos indevidos do plano. UMA fonte para a tela e para o terminal.

    ⭐ 29/09/2026 — nasceu para acabar com duas cópias do MESMO ato destrutivo: a ação da tela
    tinha um bloco de apagar e `scripts/qa/reconciliar_kit_agosto.py` tinha outro. Duas cópias de
    um `DELETE` divergem na primeira correção, e a que fica atrás é a que apaga errado.

    Remove apenas o VÍNCULO pessoa×kit em `ged_kit_documents`. O PDF no disco não é tocado e o
    documento continua existindo para a pessoa: o que estava errado era ele estar no kit de
    OUTRO condomínio (medido: uma pessoa aparecia em TRÊS kits, e dois clientes recebiam a folha
    de pagamento de um estranho).

    Nunca remove quem está apenas SEM RESOLUÇÃO — `plano_reconciliacao` já marca essas linhas
    como `pendente` e as tira do lote. Ignorância do sistema não vira ato sobre documento.

    Devolve o plano com `aplicado` (linhas removidas) e `backup` (tabela de volta).
    """
    import uuid as _uuid

    plano = plano_reconciliacao(db, competencia)
    alvo = [(x["kit_id"], x["employee_id"]) for x in plano["linhas"] if x.get("tipo") == "remover"]
    if not alvo:
        plano["aplicado"] = 0
        plano["backup"] = None
        return plano

    bkp = f"ged_kit_documents_removidos_{date.today():%Y%m%d}_recon"
    par = {"k": [a[0] for a in alvo], "e": [a[1] for a in alvo]}
    onde = (
        " WHERE (kit_id::text, employee_id::text) IN "
        "  (SELECT * FROM unnest(CAST(:k AS text[]), CAST(:e AS text[])))"
    )
    n_antes = db.execute(text(f"SELECT count(*) FROM ged_kit_documents {onde}"), par).scalar() or 0  # noqa: S608
    db.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {bkp} AS "  # noqa: S608 — nome derivado da data
            "SELECT *, now() AS removido_em, ''::text AS removido_por "
            "  FROM ged_kit_documents WHERE false"
        )
    )
    db.execute(
        text(f"INSERT INTO {bkp} SELECT *, now(), :q FROM ged_kit_documents {onde}"),  # noqa: S608
        {**par, "q": quem},
    )
    guardadas = db.execute(text(f"SELECT count(*) FROM {bkp}")).scalar() or 0  # noqa: S608
    if guardadas < n_antes:
        # ABORTA antes de apagar. Backup menor que o alvo significa que a cópia não pegou tudo,
        # e remoção sem cópia de volta não acontece nesta casa.
        raise RuntimeError(
            f"ABORTADO antes de remover: o backup guardou {guardadas} e eu ia apagar {n_antes}."
        )
    db.execute(text(f"DELETE FROM ged_kit_documents {onde}"), par)  # noqa: S608
    db.execute(
        text(
            "INSERT INTO gp_audit_logs (id, timestamp, action, entity, entity_id, description, "
            "  source_module, actor_user_id, actor_user_name, actor_user_role, actor_user_module) "
            "VALUES (:id, now(), 'kit.vinculos_removidos', 'ged_kit_documents', :ent, :d, "
            "  'people_management.ged', '00000000-0000-0000-0000-000000000000', :q, 'dp', 'ged')"
        ),
        {
            "id": str(_uuid.uuid4()),
            "ent": f"{competencia:%Y-%m}",
            "q": quem,
            "d": (
                f"{len(alvo)} vínculo(s) pessoa×kit e {n_antes} linha(s) de documento removidos da "
                f"competência {competencia:%m/%Y}. Motivo por linha: a pessoa trabalhou em outro "
                f"condomínio no mês. Reversível em {bkp}. PDFs no disco intactos."
            ),
        },
    )
    db.commit()

    # PROVA POR LEITURA POSTERIOR — depois do commit, nunca pela linha «DELETE n».
    sobrou = db.execute(text(f"SELECT count(*) FROM ged_kit_documents {onde}"), par).scalar() or 0  # noqa: S608
    if sobrou:
        raise RuntimeError(f"A remoção não se confirmou na leitura: restaram {sobrou} linha(s).")
    plano["aplicado"] = n_antes
    plano["backup"] = bkp
    return plano

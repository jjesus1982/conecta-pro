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

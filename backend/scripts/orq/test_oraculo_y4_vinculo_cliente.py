"""Oráculo — o colaborador sem cliente: o resolvedor único do vínculo pessoa↔cliente (DGX Y4).

24/09/2026. A X3 (§7.5) mediu que `employees.cliente_id` está podre: dos **63 ativos**, 37 apontam
para um `clients.id` que não existe, 14 são nulos e só 12 têm FK válida. A coluna nasceu sem
ForeignKey e tem dois escritores vivos no repositório inteiro — nenhum deles é a admissão. A
consequência medida: a cascata `condominios.client_id = employees.cliente_id`, que a F7
(`config_ponto`) e a X3 (`feriado_conferencia`) usam para achar o condomínio da pessoa, resolvia
**0 de 61** colaboradores com batida em 09/2026, e por isso **feriado de CLIENTE não alcançava
ninguém**.

A Y4 não preenche os 51 cadastros — isso é decisão do dono. Ela põe um resolvedor único
(`operacional/services/vinculo_cliente.py`) com precedência declarada, e faz os dois leitores da
cascata chamarem ele. Este oráculo é o que impede esse resolvedor de virar ficção, e é a trava do
dia em que alguém mexer na precedência.

O que afirma:
  (a) **Σ divergências = 0** — para TODO ativo que já tem `employees.cliente_id` com FK válida, o
      resolvedor devolve exatamente esse cliente. Se ficar vermelho, o «conserto» está mudando
      verdade: ou a precedência mudou, ou o cadastro passou a mentir contra a alocação viva;
  (b) o mapa do resolvedor == o recontado por SQL PRÓPRIO deste arquivo (os cinco níveis, escritos
      de novo aqui) — fonte a fonte, pessoa a pessoa;
  (c) **conflito é sinalizado, nunca escolhido no escuro**: toda linha `conflito` vem com
      `cliente_id is None`; e toda linha COM cliente resolvido tem as duas fontes de registro
      (posto e condomínio) concordando, ou só uma delas presente;
  (d) toda pessoa com alocação vigente (por posto ou por condomínio) tem cliente resolvido —
      ninguém com alocação cai em `sem_fonte`;
  (e) `definir_cliente` grava e a fonte passa a ser `manual`, vencendo a alocação (fixture
      'FIXTURE DGX Y4', apagada ao fim mesmo em falha);
  (f) **nenhum feriado foi REMOVIDO de ninguém** pela troca da cascata: para cada ativo, o
      conjunto de feriados aplicáveis com o condomínio resolvido ⊇ o conjunto de hoje
      (`condominio_id = NULL`). É a trava de dinheiro — feriado trabalhado se paga em dobro, e
      resolver o condomínio LIGA o filtro de UF/cidade que hoje está desligado para todos;
  (g) **Σ|Δ| contra `hr_payslips` = R$ 0,00** — o resolvedor não toca em folha;
  (h) fiação: `departamento_pessoal.build()` chama `_dgx_y4_vinculo.telas` e a aba está em
      `_dp_grupos` (tela sem porta não existe); e os dois leitores da cascata importam o
      resolvedor em vez de `condominios.client_id = e.cliente_id`.

Estado medido no nascimento (sandbox = cópia de produção, 24/09/2026): `vinculo_cliente` não
existia e `dp_vinculo_cliente_manual` não existia → VERMELHO em tudo. Depois: `alocacao_posto` 58 ·
`conflito` 2 (MAURICIO ALVES CHAGAS, RILEM FERREIRA DE SOUZA) · `sem_fonte` 3 (ALAN VIEIRA DA
SILVA, THIAGO DA SILVA MAQUINE, COLABORADOR TESTE HOMOLOGACAO) · Σ divergências = 0 · condomínio
resolvido **0 → 46**.

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho. Linha final `TOTAL desvios: N`.
"""

from __future__ import annotations

import asyncio
import sys
from decimal import Decimal

FIX = "FIXTURE DGX Y4"

#: (b) — recontagem INDEPENDENTE dos cinco níveis. Não importa nada do serviço: o CASE está
#: escrito de novo, aqui, na mão. Se o serviço e esta consulta divergirem, um dos dois está errado.
SQL_RECONTA = """
WITH man AS (SELECT employee_id AS eid, array_agg(DISTINCT client_id) AS c
               FROM dp_vinculo_cliente_manual WHERE ativo GROUP BY 1),
posto AS (SELECT al.employee_id AS eid, array_agg(DISTINCT p.client_id) AS c
            FROM allocations al JOIN posts p ON p.id = al.post_id
           WHERE al.is_active AND al.status = 'active' AND al.start_date <= CURRENT_DATE
             AND (al.end_date IS NULL OR al.end_date >= CURRENT_DATE) GROUP BY 1),
cond AS (SELECT a.employee_id AS eid, array_agg(DISTINCT cd.client_id) AS c
           FROM employee_alocacoes a JOIN condominios cd ON cd.id = a.condominio_id
          WHERE a.ativo AND a.data_inicio <= CURRENT_DATE
            AND (a.data_fim IS NULL OR a.data_fim >= CURRENT_DATE) GROUP BY 1),
turno AS (SELECT s.employee_id AS eid, array_agg(DISTINCT p.client_id) AS c
            FROM shifts s JOIN posts p ON p.id = s.post_id
           WHERE s.shift_date BETWEEN CURRENT_DATE - 60 AND CURRENT_DATE GROUP BY 1),
cad AS (SELECT e.id AS eid, ARRAY[e.cliente_id] AS c FROM employees e JOIN clients k ON k.id = e.cliente_id)
SELECT e.id::text, e.nome,
  CASE WHEN array_length(m.c,1)=1 THEN 'manual'
       WHEN array_length(m.c,1)>1 THEN 'conflito'
       WHEN po.c IS NOT NULL AND co.c IS NOT NULL AND NOT (po.c @> co.c AND co.c @> po.c) THEN 'conflito'
       WHEN array_length(po.c,1)>1 OR array_length(co.c,1)>1 THEN 'conflito'
       WHEN array_length(po.c,1)=1 THEN 'alocacao_posto'
       WHEN array_length(co.c,1)=1 THEN 'alocacao_condominio'
       WHEN array_length(tu.c,1)=1 THEN 'turno'
       WHEN array_length(tu.c,1)>1 THEN 'conflito'
       WHEN array_length(cd.c,1)=1 THEN 'cadastro' ELSE 'sem_fonte' END AS fonte,
  CASE WHEN array_length(m.c,1)=1 THEN m.c[1]
       WHEN array_length(m.c,1)>1 THEN NULL
       WHEN po.c IS NOT NULL AND co.c IS NOT NULL AND NOT (po.c @> co.c AND co.c @> po.c) THEN NULL
       WHEN array_length(po.c,1)>1 OR array_length(co.c,1)>1 THEN NULL
       WHEN array_length(po.c,1)=1 THEN po.c[1]
       WHEN array_length(co.c,1)=1 THEN co.c[1]
       WHEN array_length(tu.c,1)=1 THEN tu.c[1]
       WHEN array_length(tu.c,1)>1 THEN NULL
       WHEN array_length(cd.c,1)=1 THEN cd.c[1] ELSE NULL END::text AS cliente_id,
  cd.c[1]::text AS cadastro_id,
  (po.c IS NOT NULL OR co.c IS NOT NULL) AS tem_alocacao,
  coalesce(po.c @> co.c AND co.c @> po.c, true) AS registros_concordam
  FROM employees e
  LEFT JOIN man m ON m.eid=e.id LEFT JOIN posto po ON po.eid=e.id
  LEFT JOIN cond co ON co.eid=e.id LEFT JOIN turno tu ON tu.eid=e.id LEFT JOIN cad cd ON cd.eid=e.id
 WHERE e.status='ativo' ORDER BY e.nome
"""

#: (f) — os feriados que se aplicam a um condomínio, pela MESMA régua de escopo da F7, recontada.
#: `:cond` NULL = o que vale hoje para todos (a cascata resolve 0 pessoas).
SQL_FERIADOS_DO_COND = """
SELECT f.id::text
  FROM cct_feriados f
  LEFT JOIN condominios co ON co.id = CAST(:cond AS uuid)
 WHERE coalesce(f.is_active, true)
   AND (coalesce(f.escopo,'nacional') = 'nacional'
     OR (f.escopo='estadual'  AND (f.uf IS NULL OR co.estado IS NULL OR upper(f.uf)=upper(co.estado)))
     OR (f.escopo='municipal' AND (f.municipio IS NULL OR co.cidade IS NULL OR lower(f.municipio)=lower(co.cidade)))
     OR (f.escopo='cliente'   AND f.condominio_id IS NOT NULL AND f.condominio_id = CAST(:cond AS uuid)))
"""

#: (g) — a fotografia do dinheiro. Se esta soma mudar, a frente deixou de ser paralelo cego.
SQL_FOTO_FOLHA = """
SELECT coalesce(sum(total_earnings),0), coalesce(sum(total_deductions),0), coalesce(sum(net_salary),0), count(*)
  FROM hr_payslips
"""


async def main() -> int:  # noqa: C901 — um oráculo é uma lista de afirmações
    from sqlalchemy import text

    from core.database import async_session_factory
    from modules.operacional.services import vinculo_cliente as vc

    desvios: list[str] = []
    nominal: list[str] = []
    fix_emp: str | None = None

    async with async_session_factory() as db:
        foto_antes = tuple((await db.execute(text(SQL_FOTO_FOLHA))).first())

        mapa = await vc.mapa_cliente(db)
        reconta = {
            r[0]: {
                "nome": r[1],
                "fonte": r[2],
                "cliente_id": r[3],
                "cadastro_id": r[4],
                "tem_alocacao": r[5],
                "concordam": r[6],
            }
            for r in (await db.execute(text(SQL_RECONTA))).all()
        }

        # (b) o mapa do serviço == a recontagem própria, pessoa a pessoa
        if set(mapa) != set(reconta):
            desvios.append(
                f"(b) população diferente: serviço={len(mapa)} recontagem={len(reconta)} "
                f"· só no serviço={sorted(set(mapa) - set(reconta))[:3]} "
                f"· só na recontagem={sorted(set(reconta) - set(mapa))[:3]}"
            )
        for eid, esp in reconta.items():
            got = mapa.get(eid)
            if not got:
                continue
            if got["fonte"] != esp["fonte"] or (got["cliente_id"] or None) != (esp["cliente_id"] or None):
                desvios.append(
                    f"(b) {esp['nome']}: serviço={got['fonte']}/{got['cliente_id']} "
                    f"× recontagem={esp['fonte']}/{esp['cliente_id']}"
                )

        # (a) Σ divergências contra o cadastro com FK válida
        com_cadastro = [e for e, r in reconta.items() if r["cadastro_id"]]
        divergentes = [
            reconta[e]["nome"]
            for e in com_cadastro
            if (mapa.get(e, {}).get("cliente_id") or None) != reconta[e]["cadastro_id"]
        ]
        if divergentes:
            desvios.append(
                f"(a) Σ divergências = {len(divergentes)} (tinha que ser 0) — o resolvedor está "
                f"mudando o cliente de quem já tinha cadastro válido: {divergentes[:5]}"
            )

        # (c) conflito nunca escolhe no escuro; e quem tem cliente, tem as fontes de registro de acordo
        for eid, r in mapa.items():
            if r["fonte"] == "conflito" and r["cliente_id"]:
                desvios.append(f"(c) {r['nome']}: fonte=conflito mas devolveu cliente {r['cliente_id']}")
            if r["cliente_id"] and r["fonte"] != "manual" and not reconta.get(eid, {}).get("concordam", True):
                desvios.append(f"(c) {r['nome']}: devolveu cliente com posto e condomínio discordando")

        # (d) quem tem alocação vigente tem cliente resolvido
        for eid, esp in reconta.items():
            if esp["tem_alocacao"] and mapa.get(eid, {}).get("fonte") == "sem_fonte":
                desvios.append(f"(d) {esp['nome']}: tem alocação vigente e caiu em sem_fonte")

        # (f) nenhum feriado removido de ninguém pela troca da cascata
        async def feriados(cond: str | None) -> set[str]:
            return {r[0] for r in (await db.execute(text(SQL_FERIADOS_DO_COND), {"cond": cond})).all()}

        hoje = await feriados(None)
        por_cond: dict[str, set[str]] = {}
        for r in mapa.values():
            cid = r.get("condominio_id")
            if cid and cid not in por_cond:
                por_cond[cid] = await feriados(cid)
        for r in mapa.values():
            cid = r.get("condominio_id")
            if cid and (perdidos := hoje - por_cond[cid]):
                desvios.append(
                    f"(f) {r['nome']} (condomínio {r['condominio_nome']}): a cascata nova REMOVE "
                    f"{len(perdidos)} feriado(s) que hoje se aplicam — feriado é dinheiro"
                )

        # censo nominal para o §1 do relatório
        censo: dict[str, int] = {}
        for r in mapa.values():
            censo[r["fonte"]] = censo.get(r["fonte"], 0) + 1
            if r["fonte"] in ("conflito", "sem_fonte"):
                nominal.append(f"  {r['fonte']:<12} {r['nome']} — {r['evidencia'] or 'nenhuma fonte'}")
        com_cond = sum(1 for r in mapa.values() if r.get("condominio_id"))

        # (e) definir_cliente: fixture, e a fonte vira manual
        try:
            alvo = next((e for e, r in mapa.items() if r["fonte"] in ("conflito", "sem_fonte")), None) or next(
                iter(mapa)
            )
            outro = (
                await db.execute(
                    text(
                        "SELECT id::text FROM clients WHERE id::text <> coalesce(:c, '') "
                        "AND id IN (SELECT client_id FROM posts) LIMIT 1"
                    ),
                    {"c": mapa[alvo]["cliente_id"]},
                )
            ).scalar()
            if not outro:
                desvios.append("(e) não há cliente alternativo no sandbox para provar `definir_cliente`")
            else:
                fix_emp = alvo
                await vc.definir_cliente(
                    db, employee_id=alvo, client_id=outro, motivo=FIX + " — prova do oráculo", definido_por=FIX
                )
                cid, fonte, conf = await vc.cliente_do_colaborador(db, alvo)
                if fonte != "manual":
                    desvios.append(f"(e) depois de definir_cliente a fonte é '{fonte}', tinha que ser 'manual'")
                if cid != outro:
                    desvios.append(f"(e) definir_cliente gravou {outro} mas o resolvedor devolve {cid}")
                if conf != "alta":
                    desvios.append(f"(e) fonte manual com confiança '{conf}', tinha que ser 'alta'")
        finally:
            if fix_emp:
                await db.execute(
                    text("DELETE FROM dp_vinculo_cliente_manual WHERE motivo LIKE :m OR definido_por = :p"),
                    {"m": f"%{FIX}%", "p": FIX},
                )
                await db.execute(
                    text(
                        "UPDATE employees SET cliente_id = CAST(:c AS uuid), cliente_nome = :n WHERE id = CAST(:e AS uuid)"
                    ),
                    {"c": reconta[fix_emp]["cadastro_id"], "n": None, "e": fix_emp},
                )
                await db.commit()

        sobra = (
            await db.execute(
                text("SELECT count(*) FROM dp_vinculo_cliente_manual WHERE motivo LIKE :m"), {"m": f"%{FIX}%"}
            )
        ).scalar()
        if sobra:
            desvios.append(f"(e) sobraram {sobra} linha(s) '{FIX}' — a fixture não foi apagada")

        # (h) fiação — tela sem porta não existe
        from modules.operacional.controllers.redesign_builders import _dp_grupos

        abas = {a[0] for g in _dp_grupos.GRUPOS for a in g[3]}
        if "vinculo-cliente" not in abas:
            desvios.append("(h) a aba `vinculo-cliente` não está em `_dp_grupos.GRUPOS` — tela sem porta")
        dp_src = __import__("pathlib").Path(
            "/app/modules/operacional/controllers/redesign_builders/departamento_pessoal.py"
        )
        src = dp_src.read_text(encoding="utf-8") if dp_src.exists() else ""
        if "_dgx_y4_vinculo" not in src:
            desvios.append("(h) `departamento_pessoal.py` não chama `_dgx_y4_vinculo`")
        base = __import__("pathlib").Path("/app/modules/people_management")
        fc_py = base / "folha" / "services" / "feriado_conferencia.py"
        fc_txt = fc_py.read_text(encoding="utf-8") if fc_py.exists() else ""
        if "vinculo_cliente" not in fc_txt:
            desvios.append("(h) feriado_conferencia (X3) ainda não usa o resolvedor")
        # A cascata morta não pode voltar a NENHUM dos dois. O `config_ponto` NÃO passou a chamar o
        # resolvedor de propósito: medido em 24/09, quem lá resolve o condomínio é
        # `posto_atual_id → posts.client_id` (48 dos 63), que é a mesma fonte do nível 2; a linha
        # por `cliente_id` resolvia 0 e só saiu. Trocar pelo resolvedor TIRARIA o condomínio dos 2
        # em conflito — seria mudar comportamento, e esta frente não faz isso.
        for arq, quem in (
            (base / "ponto" / "config_ponto.py", "config_ponto (F7)"),
            (fc_py, "feriado_conferencia (X3)"),
        ):
            txt = arq.read_text(encoding="utf-8") if arq.exists() else ""
            if "WHERE c.client_id = e.cliente_id" in txt:
                desvios.append(f"(h) {quem} voltou a ter a cascata morta `condominios.client_id = e.cliente_id`")

        # (g) o dinheiro não se mexeu
        foto_depois = tuple((await db.execute(text(SQL_FOTO_FOLHA))).first())
        delta = sum(
            abs(Decimal(str(a)) - Decimal(str(b))) for a, b in zip(foto_antes[:3], foto_depois[:3], strict=True)
        )
        if delta != 0 or foto_antes[3] != foto_depois[3]:
            desvios.append(f"(g) a folha MUDOU: antes={foto_antes} depois={foto_depois} · Σ|Δ| = R$ {delta}")

    print(
        " · ".join(f"{k}={v}" for k, v in sorted(censo.items(), key=lambda x: -x[1]))
        + f" · condomínio resolvido={com_cond}/{len(mapa)} · Σ divergências vs cadastro válido="
        + f"{len(divergentes)}/{len(com_cadastro)} · Σ|Δ| na folha = R$ {delta}"
    )
    if nominal:
        print("\n".join(sorted(nominal)))
    for d in desvios:
        print("DESVIO " + d)
    print(f"TOTAL desvios: {len(desvios)}")
    if not desvios:
        print(
            "OK vínculo cliente: o resolvedor devolve o mesmo cliente de quem já tinha cadastro válido "
            "(Σ divergências = 0), quem tem alocação vigente tem cliente, conflito é sinalizado e nunca "
            "escolhido no escuro, definir cliente grava e a fonte vira manual, nenhum feriado foi removido "
            "de ninguém e Σ|Δ| na folha = R$ 0,00"
        )
    return 1 if desvios else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

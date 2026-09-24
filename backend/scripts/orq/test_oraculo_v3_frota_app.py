"""Oráculo — DGX V3: frota como no APP Frotas (manutenção, multa→conta/recurso, vistoria
configurável, grupos hierárquicos). 24/09/2026.

POR QUE EXISTE
As quatro coisas desta frente são quatro jeitos de escrever no mesmo lugar por um caminho novo, e
cada um tem um jeito próprio de mentir:
  · manutenção que "gera a troca de óleo" pode gerar DUAS leituras (a função da F10 e uma cópia
    local), e aí o painel «Restam» da frente 10 passa a contar a troca errada;
  · "Gerar conta" clicado duas vezes pode criar DOIS títulos — dinheiro duplicado no Financeiro;
  · recurso deferido pode "cancelar" a conta com um UPDATE direto, passando por fora do serviço
    que sabe que conta PAGA não se cancela;
  · a vistoria, ao virar tabela, pode mudar de forma sem ninguém pedir — o formulário de ontem
    tem de continuar sendo o de hoje enquanto a tabela não for editada;
  · e grupo hierárquico sem trava vira pai apontando para o nada, ou material apontando para um
    grupo que não existe.

O QUE AFIRMA (recontado por SQL próprio e por comparação de dicionário, nunca pelo status da tela)
  1. Toda manutenção CONCLUÍDA cujos itens mencionam uma troca tem EXATAMENTE UMA `frota_leituras`
     daquele tipo no KM da conclusão, e essa leitura tem `proxima_km` maior que o KM.
  2. Nenhum `payable_id` aparece em duas manutenções, nem em duas multas, nem numa multa e numa
     manutenção ao mesmo tempo: a conta é idempotente por origem.
  3. Multa com recurso DEFERIDO não tem título PENDENTE pendurado — ou o título está `cancelada`,
     ou não havia título. E nenhuma multa "cancelou" um título PAGO.
  4. O formulário de vistoria montado com a tabela VAZIA é, campo a campo e endpoint incluído,
     idêntico ao da frente 10; e os campos montados com a tabela SEMEADA (as 5 áreas) são os mesmos
     campos do de ontem.
  5. Veículo cuja última vistoria reprovou item que impede locomoção é recusado por `frota_saida`
     com 409 nomeando o item (exercitado de verdade, com fixture, e desfeito).
  6. Nenhum `sup_grupos.pai_id` órfão (nem ciclo) e todo `nfe_compras_estoque.grupo` não vazio tem
     grupo correspondente.

ESTADO MEDIDO NO NASCIMENTO (sandbox `conecta_pro_staging`, 24/09): `frota_manutencoes`,
`frota_vistoria_itens`, `frota_vistoria_respostas` e `sup_grupos` não existiam; `frota_multas` sem
`payable_id`/`recurso_*`; `frota_veiculos` com 0 linhas; `nfe_compras_estoque` com 147 itens e
grupo NULO em todos. VERMELHO por ausência do mecanismo.

COMO RODA (container efêmero contra o sandbox, ver docs/dgx/CONTRATO_AGENTE.md):
  docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" -e PYTHONPATH=/app \\
    --tmpfs /app/logs:rw,mode=1777 --tmpfs /app/uploads:rw,uid=999,gid=999 \\
    --env-file /opt/conecta-pro/.env -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= $ENVS \\
    conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_v3_frota_app.py
Sai 0 = verde; 1 = vermelho. Linha final `TOTAL v3_frota_app: N`.
"""

from __future__ import annotations

import asyncio
import sys

FIXTURE = "FIXTURE DGX V3"


async def main() -> int:  # noqa: PLR0912, PLR0915 — um oráculo, seis afirmações, sem indireção
    from sqlalchemy import text

    from core.database import async_session_factory

    falhas: list[str] = []
    try:
        from modules.operacional.controllers.redesign_builders import _dgx_v3_frota_app as v3
        from modules.operacional.controllers.redesign_builders import _frente_10 as fr10
    except Exception as e:  # noqa: BLE001
        print(f"FALHOU: builder _dgx_v3_frota_app não importa: {e}")
        print("TOTAL v3_frota_app: 1")
        return 1

    async with async_session_factory() as db:
        await v3._ensure(db)  # o mesmo DDL idempotente que o 1º acesso à tela aplica

        # ── 1) manutenção concluída com troca → exatamente UMA leitura tipada com proxima_km ──
        manuts = (
            await db.execute(
                text(
                    "SELECT id, veiculo_id, km_conclusao, itens FROM frota_manutencoes "
                    "WHERE status = 'concluida' AND km_conclusao IS NOT NULL ORDER BY id"
                )
            )
        ).fetchall()
        n_trocas = 0
        for mid, vid, km, itens in manuts:
            for tipo in v3.trocas_da_manutencao(itens if isinstance(itens, list) else []):
                n_trocas += 1
                leituras = (
                    await db.execute(
                        text(
                            "SELECT id, proxima_km FROM frota_leituras WHERE veiculo_id = :v AND tipo = :t AND km = :k"
                        ),
                        {"v": vid, "t": tipo, "k": km},
                    )
                ).fetchall()
                if len(leituras) != 1:
                    falhas.append(
                        f"manutenção #{mid}: {len(leituras)} leituras '{tipo}' a {km} km — tem de ser exatamente 1"
                    )
                    continue
                prox = leituras[0][1]
                if prox is None or prox <= km:
                    falhas.append(f"manutenção #{mid}: leitura '{tipo}' com proxima_km {prox} (KM da troca {km})")

        # ── 2) conta idempotente: nenhum título compartilhado entre origens ──
        dup = (
            await db.execute(
                text(
                    "SELECT payable_id::text, count(*) FROM ("
                    "  SELECT payable_id FROM frota_manutencoes WHERE payable_id IS NOT NULL"
                    "  UNION ALL SELECT payable_id FROM frota_multas WHERE payable_id IS NOT NULL) x "
                    "GROUP BY 1 HAVING count(*) > 1"
                )
            )
        ).fetchall()
        for pid, n in dup:
            falhas.append(f"título {pid[:8]}… usado por {n} origens — «Gerar conta» duplicou")
        n_contas = (
            await db.execute(
                text(
                    "SELECT count(*) FROM (SELECT payable_id FROM frota_manutencoes WHERE payable_id IS NOT NULL "
                    "UNION ALL SELECT payable_id FROM frota_multas WHERE payable_id IS NOT NULL) x"
                )
            )
        ).scalar()

        # ── 3) recurso deferido cancela o título pendente, e nunca toca em título pago ──
        deferidas = (
            await db.execute(
                text(
                    "SELECT m.id, m.payable_id::text, p.status FROM frota_multas m "
                    "LEFT JOIN payable_accounts p ON p.id = m.payable_id WHERE m.recurso_resultado = 'deferido'"
                )
            )
        ).fetchall()
        for mid, pid, st in deferidas:
            if pid and st == "pendente":
                falhas.append(
                    f"multa #{mid}: recurso deferido e o título {pid[:8]}… segue PENDENTE — não foi cancelado"
                )
            if pid and st == "pago":
                falhas.append(f"multa #{mid}: recurso deferido sobre título já PAGO ({pid[:8]}…) — acerto é manual")

        # ── 4) formulário de vistoria: vazio == frente 10; semeado == mesmos campos ──
        antigo = (await fr10.telas(db, "equipamentos"))["frota-vistoria-nova"]
        vazio = await v3.form_vistoria(db, [])
        if vazio != antigo:
            falhas.append("formulário de vistoria com a tabela VAZIA difere do da frente 10")
        # a tabela pode ter ganhado itens novos (é para isso que ela existe); o que NÃO pode mudar é o
        # par de campos que cada uma das 5 áreas semeadas rende — esse é o formulário de ontem
        por_cod = {i["codigo"]: i for i in await v3.itens_vistoria(db)}
        for cod, lbl in fr10._AREAS:
            esperado = [
                {
                    "key": f"aval_{cod}",
                    "label": f"{lbl} — avaliação",
                    "type": "select",
                    "options": [{"value": "bom", "label": "Bom"}, {"value": "ruim", "label": "Ruim"}],
                },
                {"key": f"foto_{cod}", "label": f"{lbl} — foto", "type": "file", "accept": "image/*"},
            ]
            it = por_cod.get(cod)
            if it is None:
                falhas.append(f"área «{cod}» da frente 10 sumiu de frota_vistoria_itens")
            elif v3.campos_do_item(it) != esperado:
                falhas.append(f"área «{cod}»: os campos do formulário mudaram em relação aos da frente 10")

        # ── 5) item que impede locomoção reprovado bloqueia a saída (exercitado e desfeito) ──
        from fastapi import HTTPException

        from modules.operacional.controllers.redesign_builders import _dgx_f10_frotas as f10

        class _U:  # usuário mínimo para a ação (só `email`/`id` são lidos)
            email = "oraculo-v3@conectamais.pro"
            id = None

        vid_fx = (
            await db.execute(
                text(
                    "INSERT INTO frota_veiculos (placa, modelo, ativo) VALUES (:p, :m, true) "
                    "ON CONFLICT (placa) DO NOTHING RETURNING id"
                ),
                {"p": "V3X0001", "m": FIXTURE},
            )
        ).scalar()
        if vid_fx is None:
            vid_fx = (await db.execute(text("SELECT id FROM frota_veiculos WHERE placa = 'V3X0001'"))).scalar()
        emp = (await db.execute(text("SELECT id FROM employees WHERE status = 'ativo' LIMIT 1"))).scalar()
        item_id = (
            await db.execute(
                text(
                    "INSERT INTO frota_vistoria_itens (codigo, grupo, ordem, texto, tipo_dado, impede_locomocao, created_by) "
                    "VALUES ('v3_freio_fx', :g, 99, 'Freio de serviço (FIXTURE DGX V3)', 'sim_nao', true, :g) "
                    "ON CONFLICT (codigo) DO UPDATE SET impede_locomocao = true RETURNING id"
                ),
                {"g": FIXTURE},
            )
        ).scalar()
        vist_id = (
            await db.execute(
                text(
                    "INSERT INTO frota_vistorias (veiculo_id, tipo, os_ref, condutor_id, km, checklist, created_by) "
                    "VALUES (:v, 'chegada', 'OS-V3-FX', :c, 1000, 'avariado', :u) RETURNING id"
                ),
                {"v": vid_fx, "c": emp, "u": FIXTURE},
            )
        ).scalar()
        await db.execute(
            text(
                "INSERT INTO frota_vistoria_respostas (vistoria_id, item_id, valor, reprovado) VALUES (:v, :i, 'nao', true) "
                "ON CONFLICT (vistoria_id, item_id) DO UPDATE SET reprovado = true"
            ),
            {"v": vist_id, "i": item_id},
        )
        await db.commit()
        bloqueio = await v3.bloqueio_locomocao(db, vid_fx)
        if bloqueio is None:
            falhas.append("item que impede locomoção reprovado NÃO bloqueia — bloqueio_locomocao devolveu nada")
        try:
            await f10.frota_saida(
                _U(),
                {"veiculo_id": vid_fx, "motorista_employee_id": str(emp), "km_saida": 1000, "motivo": "supervisao"},
                db,
            )
            falhas.append("«Registrar saída» ACEITOU o veículo com item que impede locomoção reprovado")
            await db.execute(text("DELETE FROM frota_saidas WHERE veiculo_id = :v"), {"v": vid_fx})
        except HTTPException as e:
            if e.status_code != 409 or "Freio de serviço" not in str(e.detail):
                falhas.append(f"saída recusada, mas sem nomear o item: {e.status_code} {e.detail}")
        # desfaz a fixture (só o que este oráculo criou)
        await db.execute(text("DELETE FROM frota_vistoria_respostas WHERE vistoria_id = :v"), {"v": vist_id})
        await db.execute(text("DELETE FROM frota_vistorias WHERE id = :v"), {"v": vist_id})
        await db.execute(text("DELETE FROM frota_vistoria_itens WHERE codigo = 'v3_freio_fx'"))
        await db.execute(text("DELETE FROM frota_veiculos WHERE placa = 'V3X0001' AND modelo = :m"), {"m": FIXTURE})
        await db.commit()

        # ── 6) grupos: nenhum pai órfão, nenhum ciclo, nenhum material sem grupo resolvido ──
        orfaos = (
            (
                await db.execute(
                    text(
                        "SELECT g.codigo FROM sup_grupos g WHERE g.pai_id IS NOT NULL "
                        "AND NOT EXISTS (SELECT 1 FROM sup_grupos p WHERE p.id = g.pai_id)"
                    )
                )
            )
            .scalars()
            .all()
        )
        for c in orfaos:
            falhas.append(f"grupo «{c}»: pai_id aponta para grupo que não existe")
        ciclos = (
            (
                await db.execute(
                    text(
                        "WITH RECURSIVE sobe AS ("
                        "  SELECT id, pai_id, 1 AS n, ARRAY[id] AS caminho FROM sup_grupos WHERE pai_id IS NOT NULL"
                        "  UNION ALL SELECT s.id, g.pai_id, s.n + 1, s.caminho || g.id FROM sobe s "
                        "    JOIN sup_grupos g ON g.id = s.pai_id WHERE NOT g.id = ANY(s.caminho) AND s.n < 20)"
                        " SELECT DISTINCT id FROM sobe WHERE n >= 20"
                    )
                )
            )
            .scalars()
            .all()
        )
        for i in ciclos:
            falhas.append(f"grupo id {i}: hierarquia com mais de 20 níveis — provável ciclo")
        sem_grupo = (
            await db.execute(
                text(
                    "SELECT e.item_code, e.grupo FROM nfe_compras_estoque e WHERE coalesce(trim(e.grupo),'') <> '' "
                    "AND NOT EXISTS (SELECT 1 FROM sup_grupos g WHERE g.codigo = e.grupo) LIMIT 5"
                )
            )
        ).fetchall()
        for code, g in sem_grupo:
            falhas.append(f"material {code}: grupo «{g}» não existe em sup_grupos")
        n_grupos = (await db.execute(text("SELECT count(*) FROM sup_grupos"))).scalar()
        n_itens = (await db.execute(text("SELECT count(*) FROM frota_vistoria_itens WHERE ativo"))).scalar()

        print(
            f"manutenções concluídas: {len(manuts)} · trocas conferidas: {n_trocas} · contas geradas: {n_contas} · "
            f"recursos deferidos: {len(deferidas)} · itens de vistoria: {n_itens} · grupos: {n_grupos}"
        )
        sobra = (
            await db.execute(
                text(
                    "SELECT (SELECT count(*) FROM frota_vistoria_itens WHERE created_by = :f) + "
                    "(SELECT count(*) FROM frota_veiculos WHERE modelo = :f)"
                ),
                {"f": FIXTURE},
            )
        ).scalar()
        if sobra:
            falhas.append(f"{sobra} fixture(s) '{FIXTURE}' sobraram no banco")

    for f in falhas:
        print("FALHOU:", f)
    print(f"TOTAL v3_frota_app: {len(falhas)}")
    if falhas:
        raise AssertionError(f"{len(falhas)} desvio(s) na frota do APP")
    print(
        "OK v3_frota_app: uma troca por manutenção, conta idempotente, recurso deferido cancela sem pagar, "
        "vistoria igual à de ontem, item que impede locomoção bloqueia a saída, grupos sem órfão"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print("VERMELHO:", e)
        sys.exit(1)

"""Oráculo — conciliação da NFS-e com o fisco e a parametrização com fonte (DGX AA4, 24/09/2026).

Por que existe
--------------
Em 24/09/2026 o dono subiu 8 DANFSe de 08/2026 e o cronograma de emissão de setembro.
Conferindo PDF contra banco, a régua certa — **a numeração por CNPJ, consecutiva por
emitente** — mostrou o buraco (produção, só leitura):

    conecta_eletronica   nº   2 a 123 · temos 89 · FALTAM 33
    conecta_patrimonial  nº   3 a  32 · temos 26 · FALTAM  4

**37 notas emitidas no fisco sem uma linha no ERP.** Medir pelo NSU do ADN acusaria 419 e
seria mentira: o NSU carrega nota recebida como tomador, evento e cancelamento, não só nota
emitida. E um número ausente ainda pode ser legítimo — nota cancelada, número pulado.
**Quem diz é o fisco, não a aritmética.**

Ao mesmo tempo, o emissor chutava três números fiscais: série `900` chumbada (a real é
**70000**, nas duas empresas), `<cNBS>120032900</cNBS>` chumbado em TODA nota (certo só para
`14.06.01`) e alíquota de ISS onde o Simples Nacional não tem ISS nenhum. E o cliente de
consulta ao fisco era um **stub simulado** que devolvia `{"status": "preparacao"}` sem bater
em URL nenhuma — texto inventado num caminho de dinheiro.

O que afirma
------------
  a) **nenhum número da sequência de cada CNPJ fica «ausente e nunca conferido»**: todo
     número que a régua acusa tem linha no livro-razão da conciliação, com um estado; e
     nenhum número é fechado por dedução aritmética — só pelo fisco (recuperado, ou negado
     depois que a varredura de DPS daquele CNPJ terminou);
  b) **nada gravado em ambiente de produção por esta frente**: nenhuma NFS-e e nenhum
     contador de produção em `nfse_numeracao` (mesma régua da Z7, que não pode ser afrouxada);
     e o caminho da conciliação não chama emissão — é só GET;
  c) **todo código de serviço usado tem NBS com fonte citada**, e **nenhum NBS é aplicado a
     código que não é o dele** — um NBS pertence a exatamente um código, e o literal
     `120032900`/`1.2003.29.00` não volta chumbado para dentro do montador da DPS;
  d) **a base da retenção de INSS é sempre bruto menos VA e VT**, recontada aqui por SQL
     próprio, e a regra de quando ela se aplica é o **EMITENTE**, não palavra na descrição:
     CONECTAMAIS PATRIMONIAL é sempre cessão de mão de obra; CONECTAMAIS ELETRONICA nunca —
     «Portaria Remota» tem a palavra portaria e não é cessão. Além disso: a **descrição da
     nota carrega VA, VT e a base escritos** (sem isso o fisco glosa a dedução e a economia
     vira autuação), e **VA/VT ausente não vira zero silencioso** — a nota sai sem dedução
     e com aviso em voz alta;
  e) **a Patrimonial nunca sai com ISS preenchido e a Eletrônica nunca sai sem** — e o zero
     não conta como «preenchido»: ISS 0,00% numa nota de Simples é mentira, não isenção;
  f) **os tributos calculados batem com as nove notas que o fisco emitiu** em 08–09/2026:
     ISS, exclusões da base, base do IBS/CBS (= valor menos ISS), IBS, CBS e CSLL, valor a
     valor. É o mandato do dono («não podemos pagar a mais») virado em teste;
  g) **PIS e COFINS não são retidos em nenhuma das duas empresas** — na Eletrônica por
     decisão judicial citada na própria NFS-e 121 (processo nº 1038495-94.2024.4.01.3200);
  h) **o IRRF sai desligado, e desligado por DADO** — nenhuma nota sai com IRRF enquanto
     `irrf_reter` estiver falso (decisão de Jordan Jesus em 24/09/2026: «vamos usar daqui pra
     frente sem a retenção do irrf»), **e volta a sair** quando alguém ligar o parâmetro. As
     duas direções são afirmadas: oráculo que só testa o estado de hoje é fotografia, não
     régua. O dia em que o contador reverter tem de ser um UPDATE, não um deploy;
  i) **a série da DPS é a medida (70000) e o piso da numeração é o maior nº de DPS que o
     fisco mostrou** — 125 na Eletrônica, 75 na Patrimonial —, nunca zero;
  j) **o cliente de consulta ao fisco é real**: `consultar_nfse` e `consultar_por_dps`
     existem, batem em URL do host do ambiente, e nenhum deles devolve texto simulado;
  k) **um 404 sem o código de erro do FISCO nunca é lido como «não existe»**. Medido em
     24/09/2026: o endpoint estava escrito `/nfse/DPS/{chave}`, que **não é rota**, e
     devolvia 404 com a página HTML do IIS para TUDO — inclusive para uma DPS que existe.
     Lido como «o fisco disse que não existe», isso fecharia as 37 notas ausentes com a
     tela verde e o dinheiro perdido. O caminho medido é `/dps/{id}` e o «não existe» de
     verdade vem como 404 `application/json` com `erro.codigo = "E2404"`.

Estado medido no nascimento (código anterior a esta frente): não existem
`modules.fiscal.services.nfse_conciliacao`, `nfse_parametros` nem `nfse_lote`; as tabelas
`nfse_conciliacao`, `nfse_parametros_empresa`, `nfse_servico_nbs` e `nfse_cronograma` não
existem; `NFSeNacionalService.consultar_dps` devolve `{"status": "preparacao"}` →
VERMELHO em (a)…(j).

Como roda (container, PYTHONPATH=/app):
    python3 /app/scripts/orq/test_oraculo_aa4_nfse_conciliacao.py
Sai 0 = verde; 1 = vermelho.
"""

from __future__ import annotations

import asyncio
import inspect
import sys
from decimal import Decimal
from pathlib import Path

#: As telas desta frente entram na régua do `checar_nao_vigiado.py`: tela é vigiada quando
#: um oráculo CITA o slug dela. Citar num comentário enganaria o contador — `conferir_telas`
#: monta o builder e prova que a tela existe e não é casca.
TELAS_DA_FRENTE = (
    "aa4-nfse-conciliacao",
    "aa4-nfse-emitir-do-mes",
    "aa4-nfse-livro",
    "aa4-nfse-lote",
    "aa4-nfse-parametros",
    "aa4-nfse-servicos",
)
MODULO_DA_FRENTE = "fiscal"

CNPJ_ELETRONICA = "35710481000103"
CNPJ_PATRIMONIAL = "66014833000110"

#: As nove NFS-e que o fisco emitiu em 08–09/2026, campo a campo, lidas dos DANFSe que o
#: dono subiu para `uploads/_entrada/NFs/`. É contra ISTO que o cálculo é conferido.
#: (nº, CNPJ, valor, ISS, exclusões, base IBS/CBS, IBS-UF, CBS, CSLL, INSS, ISS retido)
NOTAS_DO_FISCO = (
    ("116", CNPJ_ELETRONICA, "3800.00", 190.00, 190.00, 3610.00, 3.61, 32.49, 38.00, None, False),
    ("119", CNPJ_ELETRONICA, "6000.00", 300.00, 300.00, 5700.00, 5.70, 51.30, 60.00, None, False),
    ("120", CNPJ_ELETRONICA, "2000.00", 100.00, 100.00, 1900.00, 1.90, 17.10, 20.00, None, True),
    ("121", CNPJ_ELETRONICA, "1800.00", 90.00, 90.00, 1710.00, 1.71, 15.39, 18.00, None, False),
    ("27", CNPJ_PATRIMONIAL, "12061.50", None, 0.00, 12061.50, 12.06, 108.55, None, 1326.76, False),
    ("28", CNPJ_PATRIMONIAL, "28694.30", None, 0.00, 28694.30, 28.69, 258.25, None, 3156.37, False),
    ("29", CNPJ_PATRIMONIAL, "33538.33", None, 0.00, 33538.33, 33.54, 301.84, None, 3689.21, False),
    ("30", CNPJ_PATRIMONIAL, "25592.71", None, 0.00, 25592.71, 25.59, 230.33, None, 2815.20, False),
    ("31", CNPJ_PATRIMONIAL, "8346.70", None, 0.00, 8346.70, 8.35, 75.12, None, 918.13, False),
)

#: Piso da numeração, medido no DANFSe. «NÚMERO DA DPS» da nota mais recente de cada CNPJ.
PISO_DPS = {CNPJ_ELETRONICA: 125, CNPJ_PATRIMONIAL: 75}
SERIE_MEDIDA = "70000"


def _perto(a, b, tol=0.005) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) <= tol


async def main() -> int:
    sys.path.insert(0, "/app")
    from sqlalchemy import text

    from core.database import async_session_factory
    from modules.fiscal.services import nfse_conciliacao as cc
    from modules.fiscal.services import nfse_lote as lote
    from modules.fiscal.services import nfse_parametros as par
    from modules.government_integrations.core import nfse_nacional as nn
    from modules.operacional.controllers.redesign_builders import _dgx_aa4_nfse_conciliacao as tela

    falhas: list[str] = []
    medidas: list[str] = []

    async with async_session_factory() as db:
        from _telas import conferir_telas  # noqa: PLC0415 — irmão em scripts/orq

        falhas.extend(await conferir_telas(db, MODULO_DA_FRENTE, TELAS_DA_FRENTE))
        await cc._ensure(db)
        await lote._ensure(db)
        # Carregados cedo: (d) precisa deles para saber quem é cessão de mão de obra.
        p_ele = await par.parametros_de(db, CNPJ_ELETRONICA)
        p_pat = await par.parametros_de(db, CNPJ_PATRIMONIAL)

        # ── (a) nenhum número «ausente e nunca conferido» fora do livro ──────────────
        await cc.semear(db)
        furo = await cc.medir_furo(db)
        total_faltam = 0
        for f in furo:
            faltam = list(f["faltam"] or [])
            total_faltam += len(faltam)
            registrados = {
                int(r[0])
                for r in (
                    await db.execute(
                        text("SELECT numero FROM nfse_conciliacao WHERE tipo = 'nfse' AND prestador_cnpj = :c"),
                        {"c": f["cnpj"]},
                    )
                ).all()
            }
            orfaos = sorted(set(map(int, faltam)) - registrados)
            if orfaos:
                falhas.append(
                    f"(a) {f['slug']}: {len(orfaos)} número(s) ausente(s) SEM linha no livro-razão "
                    f"(ex.: {orfaos[:8]}) — «ausente e nunca conferido» invisível é como 37 notas sumiram"
                )
        # nenhum número fechado sem o fisco ter falado
        fechado_no_escuro = (
            await db.execute(
                text(
                    "SELECT count(*) FROM nfse_conciliacao c WHERE c.tipo = 'nfse'"
                    " AND c.estado = 'inexistente'"
                    " AND EXISTS (SELECT 1 FROM nfse_conciliacao d WHERE d.tipo = 'dps'"
                    "              AND d.prestador_cnpj = c.prestador_cnpj"
                    "              AND d.estado IN ('pendente','erro'))"
                )
            )
        ).scalar() or 0
        if fechado_no_escuro:
            falhas.append(
                f"(a) {fechado_no_escuro} número(s) marcado(s) «não existe» com varredura de DPS "
                "ainda aberta — isso é fechar por aritmética, não pelo fisco"
            )
        placar = (
            await db.execute(
                text("SELECT estado, count(*) FROM nfse_conciliacao WHERE tipo = 'nfse' GROUP BY 1 ORDER BY 1")
            )
        ).all()
        medidas.append(
            f"furo: {total_faltam} número(s) ausente(s) · livro: "
            + (", ".join(f"{e}={n}" for e, n in placar) or "vazio")
        )

        # ── (b) nada em produção, e a conciliação não emite ──────────────────────────
        n_prod = (await db.execute(text("SELECT count(*) FROM nfses WHERE ambiente = 'producao'"))).scalar() or 0
        n_cont = (
            await db.execute(text("SELECT count(*) FROM nfse_numeracao WHERE ambiente = 'producao'"))
        ).scalar() or 0
        if n_prod or n_cont:
            falhas.append(f"(b) há NFS-e/contador em PRODUÇÃO: {n_prod} nota(s), {n_cont} contador(es)")
        fonte_cc = inspect.getsource(cc)
        for proibido in ("emitir_dps(", "nfse_emissao import emitir", "from modules.fiscal.services.nfse_emissao"):
            if proibido in fonte_cc:
                falhas.append(f"(b) a conciliação toca no caminho de EMISSÃO: «{proibido}»")
        fonte_task = Path("/app/modules/fiscal/tasks.py").read_text(encoding="utf-8")
        if "emitir(" in fonte_task or "emitir_dps" in fonte_task:
            falhas.append("(b) a task agendada chama emissão — nada pode sair sem clique humano")
        medidas.append(f"produção: {n_prod} notas, {n_cont} contadores · conciliação só GET")

        # ── (c) NBS com fonte, um por código, e nenhum literal de volta no montador ──
        servs = await par.servicos(db)
        if not servs:
            falhas.append("(c) catálogo de códigos de serviço vazio — sem NBS, sem fonte")
        vistos: dict[str, str] = {}
        for s in servs:
            if not (s["fonte"] or "").strip():
                falhas.append(f"(c) código {s['codigo_formatado']} sem fonte citada")
            if s["nbs"]:
                if s["nbs"] in vistos:
                    falhas.append(
                        f"(c) NBS {s['nbs']} aplicado a DOIS códigos ({vistos[s['nbs']]} e "
                        f"{s['codigo_formatado']}) — foi exatamente esse o defeito do literal chumbado"
                    )
                vistos[s["nbs"]] = s["codigo_formatado"]
        # o NBS de 14.06.01 não pode valer para mais ninguém
        if await par.nbs_de(db, "110201") == await par.nbs_de(db, "140601"):
            falhas.append("(c) vigilância (11.02.01) e instalação (14.06.01) com o MESMO NBS")
        fonte_xml = inspect.getsource(nn.NFSeNacionalManager._build_dps_xml)
        for literal in ("120032900", "1.2003.29.00", "<cNBS>1"):
            if literal in fonte_xml:
                falhas.append(f"(c) número fiscal chumbado de volta no montador da DPS: «{literal}»")
        medidas.append(f"NBS: {len(servs)} código(s), {len(vistos)} NBS distinto(s), todos com fonte")

        # ── (d) base do INSS = bruto − VA − VT, recontada por SQL próprio ────────────
        propostas = await lote.propor(db, "2026-09")
        if not propostas:
            falhas.append("(d) cronograma de 09/2026 vazio — não há o que conferir")
        meu_va_vt = {
            r[0]: (r[1], r[2])
            for r in (
                await db.execute(
                    text(
                        "SELECT regexp_replace(cl.document_number,'\\D','','g'),"
                        "  sum(f.total) FILTER (WHERE f.beneficio = 'VR'),"
                        "  sum(f.total) FILTER (WHERE f.beneficio = 'VT')"
                        " FROM folha_beneficio_conferencia f"
                        " JOIN employee_alocacoes a ON a.employee_id = f.employee_id"
                        "   AND a.data_inicio <= (date_trunc('month', f.competencia)"
                        "                         + interval '1 month -1 day')::date"
                        "   AND (a.data_fim IS NULL OR a.data_fim >= date_trunc('month', f.competencia)::date)"
                        " JOIN condominios co ON co.id = a.condominio_id"
                        " JOIN clients cl ON cl.id = co.client_id"
                        " WHERE to_char(f.competencia,'YYYY-MM') = '2026-08' GROUP BY 1"
                    )
                )
            ).all()
        }
        # (d.1) o gatilho é o EMITENTE — e é DADO, não palavra na descrição
        fonte_lote = inspect.getsource(lote)
        for palavra in ('"portaria"', '"vigilância"', '"vigilancia"', '"mão de obra" in', '"limpeza" in'):
            if palavra in fonte_lote.lower() and "cessao_de_mao_de_obra" in fonte_lote:
                falhas.append(
                    f"(d) a cessão de mão de obra é classificada por palavra na descrição ({palavra}) "
                    "— «Portaria Remota» do Gelain tem a palavra e NÃO é cessão; quem decide é o CNPJ"
                )
        if not lote.cessao_de_mao_de_obra(p_pat):
            falhas.append("(d) a Patrimonial NÃO está marcada como cessão de mão de obra")
        if lote.cessao_de_mao_de_obra(p_ele):
            falhas.append("(d) a Eletrônica está marcada como cessão — nenhuma das 4 notas dela tem Art. 31")

        # (d.2) a conta e o texto: bruto − VA − VT, com os dois valores e a base ESCRITOS
        b = lote.bloco_inss("29600.00", p_pat, va="1804.00", vt="880.00", competencia_beneficio="08/2026", pessoas=8)
        if not _perto(b["base"], 26916.00) or not _perto(b["inss"], 2960.76):
            falhas.append(
                f"(d) 29.600,00 − (1.804,00 + 880,00) deveria dar base 26.916,00 e INSS 2.960,76; "
                f"veio base {b['base']} e INSS {b['inss']}"
            )
        for exigido in ("1.804,00", "880,00", "26.916,00", "Art. 31", "2.960,76"):
            if exigido not in b["texto"]:
                falhas.append(
                    f"(d) a descrição da nota não escreve «{exigido}» — dedução sem VA, VT e base "
                    "discriminados na própria nota é glosável, e a economia vira autuação"
                )
        if lote.montar_descricao("REFERENTE A SERVICOS.", b) == "REFERENTE A SERVICOS.":
            falhas.append("(d) o bloco do INSS não entra na descrição da nota")

        # (d.3) VA/VT ausente NÃO vira zero silencioso
        vazio = lote.bloco_inss("12061.50", p_pat)
        if not _perto(vazio["inss"], 1326.77) and not _perto(vazio["inss"], 1326.76):
            falhas.append(f"(d) sem VA/VT o INSS deveria ser 11% do bruto; veio {vazio['inss']}")
        if vazio["deducao"]:
            falhas.append("(d) sem VA/VT informado o sistema inventou uma dedução")
        if not vazio["aviso"]:
            falhas.append(
                "(d) nota de cessão saindo SEM dedução e SEM aviso — campo vazio virou zero em silêncio, "
                "e o dono paga mais imposto sem ninguém dizer"
            )
        meio = lote.bloco_inss("29600.00", p_pat, va="1804.00")
        if not meio["aviso"]:
            falhas.append("(d) só um dos dois benefícios informado e nenhum aviso")

        # (d.4) a Eletrônica nunca sai com retenção do Art. 31
        ele = lote.bloco_inss("3879.60", p_ele, va="500.00", vt="200.00")
        if ele["aplica"] or ele["inss"] is not None:
            falhas.append(
                f"(d) nota da Eletrônica saiu com retenção do Art. 31 ({ele['inss']}) — nenhuma das "
                "4 notas dela no fisco tem retenção previdenciária"
            )

        for p in propostas:
            va, vt = meu_va_vt.get(p["tomador_cnpj"], (None, None))
            esperado = float(Decimal(str(p["valor_bruto"])) - Decimal(str(va or 0)) - Decimal(str(vt or 0)))
            if not _perto(esperado, p["base_com_deducao"], 0.005):
                falhas.append(
                    f"(d) {p['tomador_nome']}: base de INSS com dedução {p['base_com_deducao']} ≠ "
                    f"bruto {p['valor_bruto']} − VA {va or 0} − VT {vt or 0} = {esperado}"
                )
            if not _perto(p["valor_bruto"], p["base_sem_deducao"], 0.005):
                falhas.append(f"(d) {p['tomador_nome']}: base sem dedução ≠ valor bruto")
            if p["inss_com_deducao"] is None or p["inss_sem_deducao"] is None:
                falhas.append(f"(d) {p['tomador_nome']}: proposta sem as DUAS contas de INSS")
        n_cessao = sum(1 for p in propostas if p["cessao_de_mao_de_obra"])
        medidas.append(
            f"cronograma: {len(propostas)} nota(s) propostas, {n_cessao} de cessão de mão de obra "
            "(gatilho = emitente) · base de INSS recontada por SQL próprio · VA/VT vazio avisa"
        )

        # ── (e) ISS: Patrimonial nunca preenchido, Eletrônica nunca vazio ────────────
        if not p_ele or not p_pat:
            falhas.append("(e) falta parametrização de uma das duas empresas")
        else:
            if p_pat["iss_aliquota"] is not None:
                falhas.append(
                    f"(e) Patrimonial (Simples) com ISS preenchido ({p_pat['iss_aliquota']}) — "
                    "o fisco devolve o bloco de ISSQN VAZIO nela; 0% é mentira e 5% paga duas vezes"
                )
            if p_ele["iss_aliquota"] is None or float(p_ele["iss_aliquota"]) <= 0:
                falhas.append("(e) Eletrônica (lucro real) SEM alíquota de ISS — as 4 notas dela têm 5,00%")
        for p in propostas:
            if p["empresa_cnpj"] == CNPJ_PATRIMONIAL and p["iss_aliquota"] is not None:
                falhas.append(f"(e) proposta da Patrimonial ({p['tomador_nome']}) sai com ISS preenchido")
            if p["empresa_cnpj"] == CNPJ_ELETRONICA and not p["iss_aliquota"]:
                falhas.append(f"(e) proposta da Eletrônica ({p['tomador_nome']}) sai SEM ISS")
        # o zero não conta como preenchido em lugar nenhum
        zeros = (
            await db.execute(
                text(
                    "SELECT count(*) FROM nfse_emitidas_nacional n JOIN empresas e ON e.id = n.empresa_id"
                    " WHERE regexp_replace(e.cnpj,'\\D','','g') = :c AND n.fonte = 'conciliacao_fisco'"
                    "   AND n.iss_aliquota IS NOT NULL AND n.iss_aliquota = 0"
                ),
                {"c": CNPJ_PATRIMONIAL},
            )
        ).scalar() or 0
        if zeros:
            falhas.append(f"(e) {zeros} nota(s) da Patrimonial gravadas com ISS = 0% em vez de nulo")
        medidas.append("ISS: Patrimonial nulo, Eletrônica 5,00%")

        # ── (f)(g)(h) os tributos contra as nove notas do fisco ──────────────────────
        pars = {CNPJ_ELETRONICA: p_ele, CNPJ_PATRIMONIAL: p_pat}
        conferidas = 0
        for num, cnpj, valor, iss, exc, base, ibs, cbs, csll, inss, ret in NOTAS_DO_FISCO:
            pp = pars.get(cnpj)
            if not pp:
                continue
            t = par.calcular_tributos(valor, pp, iss_retido_pelo_tomador=ret)
            for campo, esperado, obtido in (
                ("ISS", iss, t["iss_valor"]),
                ("exclusões da base", exc, t["exclusoes_base"]),
                ("base IBS/CBS", base, t["base_ibs_cbs"]),
                ("IBS-UF", ibs, t["ibs_uf"]),
                ("CBS", cbs, t["cbs"]),
                ("CSLL", csll, t["csll"]),
            ):
                if not _perto(esperado, obtido):
                    falhas.append(f"(f) NFS-e {num}: {campo} calculado {obtido} ≠ {esperado} do DANFSe")
            if inss is not None:
                # `vRetCP` é DIGITADO na DPS: das 5 notas, 4 batem por truncamento e 1 por
                # arredondamento. Basta bater com uma das duas — o centavo é do dono.
                if not (_perto(inss, t["inss"]) or _perto(inss, t["inss_truncado"])):
                    falhas.append(
                        f"(f) NFS-e {num}: INSS {t['inss']}/{t['inss_truncado']} não bate com "
                        f"{inss} do DANFSe por nenhum dos dois arredondamentos"
                    )
            if t["pis_retido"] or t["cofins_retido"]:
                falhas.append(
                    f"(g) NFS-e {num}: PIS/COFINS retidos — a Justiça dispensou (proc. 1038495-94.2024.4.01.3200)"
                )
            if t["irrf"] is not None:
                falhas.append(
                    f"(h) NFS-e {num}: saiu com IRRF de {t['irrf']} com `irrf_reter` desligado — "
                    "o dono decidiu em 24/09/2026 que a NFS-e sai SEM retenção de IRRF"
                )
            conferidas += 1
        for nome, pp in (("Eletrônica", p_ele), ("Patrimonial", p_pat)):
            if pp and pp.get("retem_pis_cofins"):
                falhas.append(f"(g) {nome} parametrizada para RETER PIS/COFINS")
            if pp and pp.get("irrf_reter"):
                falhas.append(f"(h) {nome} com `irrf_reter` LIGADO — a decisão do dono de 24/09/2026 é sair sem IRRF")

        # (h), a outra direção: a chave tem de FUNCIONAR. Ligar o parâmetro (em memória,
        # sem tocar no banco) tem de fazer o IRRF voltar — senão o que existe não é um
        # parâmetro desligado, é um campo morto, e reverter exigiria mexer em código.
        if p_ele:
            ligado = {**dict(p_ele), "irrf_reter": True}
            t_on = par.calcular_tributos("1800.00", ligado)
            t_off = par.calcular_tributos("1800.00", p_ele)
            if t_off["irrf"] is not None:
                falhas.append("(h) com a chave desligada o IRRF ainda sai")
            if not _perto(t_on["irrf"], 18.00):
                falhas.append(
                    f"(h) ligando `irrf_reter` o IRRF NÃO volta ({t_on['irrf']} em vez de 18,00 sobre "
                    "R$ 1.800,00, que é o que o fisco aplicou na NFS-e 121) — a chave é decorativa e "
                    "reverter a decisão exigiria mexer em código"
                )
            if not _perto(t_on["total_retencoes"], float(t_off["total_retencoes"]) + 18.00):
                falhas.append("(h) o IRRF ligado não entra no total das retenções")
            # e a chave tem de ser DADO, lida do parâmetro — não um literal no cálculo
            fonte_calc = inspect.getsource(par.calcular_tributos)
            if 'par.get("irrf_reter")' not in fonte_calc:
                falhas.append(
                    "(h) o cálculo não lê `irrf_reter` do parâmetro — se o IRRF está desligado, "
                    "está desligado no CÓDIGO, e reverter a decisão do dono exigiria deploy"
                )
        medidas.append(
            f"tributos: {conferidas} nota(s) do fisco reconferidas campo a campo · IRRF desligado "
            "por parâmetro e religável (as duas direções provadas)"
        )

        # ── (i) série medida e piso da numeração ─────────────────────────────────────
        for cnpj, piso in PISO_DPS.items():
            serie = await par.serie_de(db, cnpj)
            if serie != SERIE_MEDIDA:
                falhas.append(f"(i) série da DPS de {cnpj} é «{serie}» e o DANFSe mostra {SERIE_MEDIDA}")
            visto = await cc.piso_de_numeracao(db, cnpj)
            if visto < piso:
                falhas.append(
                    f"(i) piso da numeração de {cnpj} é {visto}, abaixo do nº de DPS {piso} que o "
                    "fisco já mostrou — começar dali queima números com E0141, um a um"
                )
        medidas.append(f"série {SERIE_MEDIDA} · piso DPS " + ", ".join(f"{c[-6:]}={p}" for c, p in PISO_DPS.items()))

        # ── (j) o cliente de consulta é real, não simulado ───────────────────────────
        for nome in ("consultar_nfse", "consultar_por_dps", "_get"):
            if not hasattr(nn.NFSeNacionalManager, nome):
                falhas.append(f"(j) `NFSeNacionalManager.{nome}` não existe — sem ela não há conciliação")
        fonte_get = inspect.getsource(nn.NFSeNacionalManager._get) if hasattr(nn.NFSeNacionalManager, "_get") else ""
        if "requests.get" not in fonte_get:
            falhas.append("(j) a consulta ao fisco não faz GET nenhum")
        from modules.government_integrations.services import nfse_nacional_service as svc_mod

        # Caça o VALOR devolvido, não a prosa: um docstring que conta o que o stub fazia é
        # memória; um `return {"status": "preparacao"}` é a mentira ainda viva.
        fonte_svc = inspect.getsource(svc_mod)
        for simulado in (
            '"status": "preparacao"',
            '"status_api": "preparacao"',
            "Retorna informacoes simuladas",
            '"mensagem": "Consulta de',
        ):
            if simulado in fonte_svc:
                falhas.append(f"(j) o serviço de NFS-e ainda DEVOLVE valor simulado: «{simulado}»")
        # e o que ele recusa tem de recusar dizendo a verdade, não fingindo indisponibilidade
        svc_cls = svc_mod.NFSeNacionalService
        if getattr(svc_cls, "_NAO_IMPLEMENTADO", {}).get("status") != "nao_implementado":
            falhas.append("(j) cancelamento/substituição não recusam com estado honesto")
        # a chave de DPS tem de ter 42 dígitos e conter CNPJ, série e número
        ch = nn.chave_dps(CNPJ_PATRIMONIAL, SERIE_MEDIDA, 75)
        if len(ch) != 42 or not ch.isdigit():
            falhas.append(f"(j) chave de DPS malformada: «{ch}» ({len(ch)} caracteres, esperado 42 dígitos)")
        if CNPJ_PATRIMONIAL not in ch or "00075" not in ch:
            falhas.append(f"(j) chave de DPS não carrega CNPJ e número: «{ch}»")
        # ── (k) o 404 que mente ──────────────────────────────────────────────────────
        if nn.NFSeNacionalManager.ENDPOINTS.get("consultar_dps") != "/dps/{chave}":
            falhas.append(
                "(k) o caminho da consulta de DPS não é o medido `/dps/{chave}` — "
                f"está «{nn.NFSeNacionalManager.ENDPOINTS.get('consultar_dps')}». "
                "`/nfse/DPS/{chave}` não é rota e devolve 404 de HTML para tudo."
            )

        class _Resp:
            def __init__(self, texto, ct):
                self.text, self.headers = texto, {"content-type": ct}

        html404 = _Resp("<!DOCTYPE html><html><head><title>The resource cannot be found.</title>", "text/html")
        json404 = _Resp(
            '{"tipoAmbiente":0,"erro":{"codigo":"E2404","descricao":"Não foi gerada uma NFS-e '
            'com o identificador de DPS informado"}}',
            "application/json",
        )
        if nn._erro_do_fisco(html404) is not None:
            falhas.append(
                "(k) uma página HTML de erro está sendo lida como recusa do fisco — é rota errada, "
                "não «documento não existe», e confundir os dois fecha nota fiscal no escuro"
            )
        erro_json = nn._erro_do_fisco(json404)
        if not erro_json or erro_json.get("codigo") != "E2404":
            falhas.append("(k) o código de erro do fisco (E2404) não está sendo lido do JSON")
        fonte_get = inspect.getsource(nn.NFSeNacionalManager._get)
        if "_erro_do_fisco" not in fonte_get:
            falhas.append(
                "(k) `_get` decide «inexistente» sem exigir o código de erro do fisco — qualquer 404 fecharia o número"
            )
        # e a conciliação só fecha com `status == 'inexistente'`, nunca com http 404 cru
        if "http_status" in fonte_cc and 'r.get("http_status") == 404' in fonte_cc:
            falhas.append("(k) a conciliação fecha número olhando o HTTP 404 cru em vez do estado")
        medidas.append(f"consulta real: GET /dps/{{id}} no fisco · chave de DPS {ch} · 404 de HTML não fecha número")

        # a função pura da tela não pode chamar de «conferido» o que ninguém conferiu
        if tela.conferido("pendente") or not tela.conferido("inexistente"):
            falhas.append("(a) a tela trata «pendente» como conferido (ou «inexistente» como não conferido)")
        if "NÃO conferido" not in tela.rotulo_do_estado("nfse", "pendente"):
            falhas.append("(a) a tela não diz em PT-BR que o número ausente ainda não foi conferido")

    print(" · ".join(medidas))
    for f in falhas:
        print("FALHA " + f)
    if not falhas:
        print(
            "OK NFS-e: todo número ausente tem linha no livro-razão e só fecha pelo fisco, nada em "
            "produção, NBS com fonte e um por código, base do INSS = bruto − VA − VT, ISS nulo no "
            "Simples e 5% no lucro real, tributos batendo com as 9 notas do fisco, PIS/COFINS não "
            "retidos, IRRF desligado por parâmetro e religável, série 70000 com o piso certo e "
            "consulta real ao fisco"
        )
    print(f"TOTAL desvios: {len(falhas)}")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

"""Oráculo — NFS-e de serviço: só em homologação, e «autorizada» só com prova (DGX Z7, 24/09/2026).

Por que existe
--------------
Em 24/09/2026 a tabela `nfses` tinha **27 linhas dizendo `status='autorizada'` e ZERO com
protocolo, código de verificação, XML enviado ou XML de retorno** — em produção e no sandbox,
o mesmo número. Todas criadas no mesmo batch de 23/03/2026. «Autorizada» era palavra escrita
localmente, não fato do órgão; a tela repetia a palavra.

E o transmissor (`government_integrations/core/nfse_nacional.py`) emitia sem guardar nada:
sem linha, sem XML, sem numeração — o número da DPS era `int(time.time())`, buraco permanente
garantido. Não havia trava de produção nenhuma no caminho da NFS-e: bastava `empresas.
nfse_ambiente = 'producao'` para sair documento fiscal irreversível com ISS devido.

Este oráculo trava as três coisas: **ambiente**, **prova** e **guarda**.

O que afirma
------------
  a) o ambiente de teste do Padrão Nacional é um HOST PRÓPRIO (produção restrita) e o código
     não confunde os dois — `url_para('homologacao') != url_para('producao')`;
  b) nenhuma NFS-e de PRODUÇÃO dita «autorizada» sem chave do órgão, cStat 100 e XML de
     retorno, e nenhum contador de produção adiante das notas (número fiscal queimado);
  c) nenhuma linha que o sistema chame de «autorizada» sem protocolo E sem XML de retorno —
     as linhas vêm de SQL próprio deste arquivo e passam pela função pura da tela;
  d) o XML guardado existe EM DISCO e bate com a linha do banco (chave de acesso dentro do
     arquivo), e o banco também tem o XML — os dois lugares, nunca um só;
  e) a CONECTAMAIS PATRIMONIAL é recusada na NF-e modelo 55 pelo motivo CERTO (decisão do
     dono: ela só vende serviço) e não por «cadastro incompleto / falta inscrição estadual»;
     e a Eletrônica NÃO é recusada;
  f) as duas camadas da trava de produção levantam de verdade quando exercidas COM O GATE
     FECHADO (o estado do gate é decisão do dono, não desvio): ambiente,
     XML com `tpAmb=1`, XML sem `tpAmb`, XML divergente do pedido e host divergente do XML;
  g) a numeração da NFS-e é por (CNPJ + série + ambiente), com índice único no banco, sem
     repetir e sem buraco — e duas reservas concorrentes recebem números distintos e
     consecutivos (fixture 'FIXTURE DGX Z7', criada e apagada aqui dentro);
  h) nenhum número fiscal chumbado no caminho da NFS-e: sem `cNBS` literal, sem inscrição
     municipal literal, sem alíquota de ISS literal no XML;
  i) prova viva: há pelo menos UMA NFS-e autorizada em homologação para CADA um dos dois
     CNPJs, com chave de acesso do órgão e `cStat 100`;
  j) `espiar_numero` não consome: duas espiadas dão o mesmo número e a reserva seguinte
     dá exatamente esse — a prévia mostra o número que vai ser enviado, não um timestamp;
  k) a série de quem EMITE (`empresas.nfse_serie_rps`) não é a série do portal da
     contabilidade (`nfse_parametros_empresa.serie_dps`) — iguais, colidem no fisco.

Estado medido no nascimento (sandbox, 24/09/2026): `nfses` com 27 linhas 'autorizada', sem
coluna `ambiente`, sem `chave_acesso`, sem `xml_path`, sem `nfse_numeracao`, sem trava de
produção e sem política de documento por empresa → VERMELHO em (a)…(i).

Como roda (container, PYTHONPATH=/app):
    python3 /app/scripts/orq/test_oraculo_z7_nfse.py
Sai 0 = verde; 1 = vermelho.
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
from pathlib import Path

MARCA_FIXTURE = "FIXTURE DGX Z7"
CNPJ_FIXTURE = "00000000000191"
CNPJS_DA_CASA = ("35710481000103", "66014833000110")


def _xml_dps(tp_amb: str | None) -> str:
    """DPS mínima só para exercer a trava. Nunca vai a lugar nenhum."""
    tag = f"<tpAmb>{tp_amb}</tpAmb>" if tp_amb else ""
    return f'<?xml version="1.0"?><DPS><infDPS>{tag}<nDPS>1</nDPS></infDPS></DPS>'


async def main() -> int:  # noqa: PLR0912, PLR0915 — nove afirmações, lineares
    from sqlalchemy import text

    from core.database import async_session_factory

    falhas: list[str] = []
    medidas: list[str] = []
    raiz = Path("/app")

    from modules.fiscal.services import nfse_emissao as em
    from modules.government_integrations.core import nfse_nacional as nn
    from modules.operacional.controllers.redesign_builders._dgx_z7_nfse import estado_real

    # ── (a) os dois ambientes são hosts DIFERENTES ────────────────────────────────────
    u_hml, u_prd = nn.url_para("homologacao"), nn.url_para("producao")
    if u_hml == u_prd:
        falhas.append(
            f"(a) homologação e produção apontam para o MESMO host ({u_hml}) — o ambiente de "
            "teste do Padrão Nacional é a produção restrita, que tem endereço próprio"
        )
    if "producaorestrita" not in u_hml:
        falhas.append(f"(a) o host de homologação não é o de produção restrita: {u_hml}")
    if "producaorestrita" in u_prd:
        falhas.append(f"(a) o host de PRODUÇÃO aponta para a produção restrita: {u_prd}")
    medidas.append(f"hosts: hml={u_hml.split('//')[-1].split('/')[0]} prd={u_prd.split('//')[-1].split('/')[0]}")

    async with async_session_factory() as db:
        await em._ensure(db)

        # ── (b) produção só com prova do órgão ────────────────────────────────────────
        # Esta afirmação já foi «nada em produção». Virou errada em 26/09/2026, quando o
        # dono liberou a emissão real e saiu a NFS-e 124 (Hawk Eye, R$ 1.000). Uma régua
        # que reprova o que o dono autorizou ensina a ignorar o painel — o que ela tem de
        # travar é nota de produção INVENTADA: sem chave do órgão, sem cStat 100, sem XML.
        prod = (
            (
                await db.execute(
                    text(
                        "SELECT id::text, coalesce(chave_acesso,'') AS chave,"
                        " coalesce(c_stat,'') AS cstat, length(coalesce(xml_retorno,'')) AS n,"
                        " coalesce(status,'') AS status"
                        " FROM nfses WHERE ambiente = 'producao'"
                    )
                )
            )
            .mappings()
            .all()
        )
        sem_prova = [
            r["id"]
            for r in prod
            if r["status"] == "autorizada" and (not r["chave"] or r["cstat"] != "100" or not r["n"])
        ]
        if sem_prova:
            falhas.append(
                f"(b) {len(sem_prova)} NFS-e de PRODUÇÃO dita «autorizada» sem chave do órgão,"
                f" sem cStat 100 ou sem XML de retorno: {sem_prova[:5]}"
            )
        # Contador de produção aberto sem nota é número fiscal queimado — isso continua erro.
        abertos = (
            (
                await db.execute(
                    text(
                        "SELECT c.prestador_cnpj, c.serie, c.ultimo,"
                        " coalesce((SELECT count(*) FROM nfses n WHERE n.prestador_cnpj = c.prestador_cnpj"
                        "   AND n.serie_rps = c.serie AND n.ambiente = 'producao'), 0) AS notas"
                        " FROM nfse_numeracao c WHERE c.ambiente = 'producao' AND c.ultimo > 0"
                    )
                )
            )
            .mappings()
            .all()
        )
        for r in abertos:
            if r["ultimo"] > r["notas"]:
                falhas.append(
                    f"(b) contador de produção {r['prestador_cnpj']}/{r['serie']} em {r['ultimo']}"
                    f" com só {r['notas']} nota(s) gravada(s) — número fiscal queimado"
                )
        medidas.append(f"produção: {len(prod)} notas, {len(abertos)} contador(es) abertos")

        # ── (c) «autorizada» só com prova ─────────────────────────────────────────────
        linhas = (
            (
                await db.execute(
                    text(
                        "SELECT id::text, status, coalesce(protocolo,'') AS prot,"
                        " coalesce(xml_retorno,'') AS xret, coalesce(chave_acesso,'') AS chave,"
                        " coalesce(ambiente,'') AS amb"
                        " FROM nfses WHERE coalesce(active, true)"
                    )
                )
            )
            .mappings()
            .all()
        )
        mentiras = []
        n_aut = n_sem = 0
        for r in linhas:
            codigo, _rot = estado_real(r["status"], r["prot"], r["xret"])
            if codigo == "autorizada":
                n_aut += 1
                if not r["prot"].strip() or not r["xret"].strip():
                    mentiras.append(r["id"])
            elif codigo == "sem_comprovacao":
                n_sem += 1
        if mentiras:
            falhas.append(f"(c) {len(mentiras)} linha(s) exibidas como «autorizada» sem protocolo+XML: {mentiras[:5]}")
        medidas.append(f"nfses: {len(linhas)} linhas · {n_aut} com prova · {n_sem} sem comprovação")

        # ── (d) o XML está nos DOIS lugares ───────────────────────────────────────────
        guardadas = [r for r in linhas if r["chave"]]
        com_path = (
            (
                await db.execute(
                    text(
                        "SELECT chave_acesso, xml_path, length(coalesce(xml_retorno,'')) AS n"
                        " FROM nfses WHERE coalesce(chave_acesso,'') <> ''"
                    )
                )
            )
            .mappings()
            .all()
        )
        sem_disco, sem_banco = [], []
        for r in com_path:
            if not (r["n"] or 0):
                sem_banco.append(r["chave_acesso"])
            p = Path(r["xml_path"] or "")
            if not r["xml_path"] or not p.exists():
                sem_disco.append(r["chave_acesso"])
            elif r["chave_acesso"] not in p.read_text(encoding="utf-8", errors="ignore"):
                falhas.append(f"(d) o XML em {p} não contém a chave {r['chave_acesso']} da linha do banco")
        if sem_disco:
            falhas.append(f"(d) {len(sem_disco)} nota(s) com chave e SEM XML em disco: {sem_disco[:3]}")
        if sem_banco:
            falhas.append(f"(d) {len(sem_banco)} nota(s) com chave e SEM XML no banco: {sem_banco[:3]}")
        medidas.append(f"XML guardado: {len(guardadas) - len(sem_disco)}/{len(guardadas)} em disco e no banco")

        # ── (e) a recusa da Patrimonial ensina a decisão, não um cadastro ─────────────
        from modules.fiscal.services.documentos_da_empresa import (
            DocumentoNaoPermitido,
            exigir_nfe_produto,
        )

        try:
            await exigir_nfe_produto(db, slug="conecta_patrimonial")
            falhas.append("(e) a Patrimonial PASSOU na NF-e modelo 55 — a decisão do dono não está valendo")
        except DocumentoNaoPermitido as e:
            texto = str(e).lower()
            if e.code != "DOCUMENTO_NAO_E_DESTA_EMPRESA":
                falhas.append(f"(e) a recusa veio com o código errado: {e.code}")
            if "inscrição estadual" in texto or "cadastro" in texto and "incompleto" in texto:
                falhas.append(f"(e) a recusa ainda fala em cadastro/IE incompleto: {str(e)[:120]}")
            if "nfs-e" not in texto:
                falhas.append("(e) a recusa não aponta a NFS-e como o documento dela")
            if not e.tela:
                falhas.append("(e) a recusa não aponta tela nenhuma para agir")
        try:
            await exigir_nfe_produto(db, slug="conecta_eletronica")
        except DocumentoNaoPermitido as e:
            falhas.append(f"(e) a Eletrônica foi recusada na NF-e 55, e ela emite produto: {e}")

        # ── (g) numeração: índice único, sem buraco, concorrência ─────────────────────
        idx = (
            await db.execute(
                text("SELECT count(*) FROM pg_indexes WHERE indexname = 'ux_nfses_prestador_serie_numero'")
            )
        ).scalar() or 0
        if not idx:
            falhas.append("(g) falta o índice único ux_nfses_prestador_serie_numero — número pode repetir")
        buracos = (
            (
                await db.execute(
                    text(
                        "SELECT prestador_cnpj, serie_rps, ambiente, min(numero_rps) AS a, max(numero_rps) AS b,"
                        " count(*) AS q FROM nfses WHERE ambiente IS NOT NULL AND numero_rps IS NOT NULL"
                        " GROUP BY 1,2,3 HAVING max(numero_rps) - min(numero_rps) + 1 <> count(*)"
                    )
                )
            )
            .mappings()
            .all()
        )
        if buracos:
            falhas.append(f"(g) buraco na numeração da NFS-e: {[dict(x) for x in buracos]}")
        # Todo número reservado tem de ter linha. Um contador à FRENTE do maior número
        # gravado significa número de nota queimado em silêncio — que é exatamente o
        # buraco fiscal que só se fecha com explicação ao fisco.
        queimados = (
            (
                await db.execute(
                    text(
                        "SELECT c.prestador_cnpj, c.serie, c.ambiente, c.ultimo,"
                        " coalesce((SELECT max(n.numero_rps) FROM nfses n"
                        "   WHERE n.prestador_cnpj = c.prestador_cnpj AND n.serie_rps = c.serie"
                        "     AND n.ambiente = c.ambiente), 0) AS maior"
                        " FROM nfse_numeracao c"
                    )
                )
            )
            .mappings()
            .all()
        )
        for r in queimados:
            if r["ultimo"] > r["maior"]:
                falhas.append(
                    f"(g) {r['ultimo'] - r['maior']} número(s) reservado(s) sem linha em"
                    f" {r['prestador_cnpj']}/{r['serie']}/{r['ambiente']}: contador {r['ultimo']},"
                    f" maior gravado {r['maior']} — número de nota queimado em silêncio"
                )

        n1 = await em.proximo_numero(db, CNPJ_FIXTURE, em.SERIE_PADRAO, "homologacao")
        n2 = await em.proximo_numero(db, CNPJ_FIXTURE, em.SERIE_PADRAO, "homologacao")
        await db.commit()
        if n2 != n1 + 1:
            falhas.append(f"(g) duas reservas seguidas não são consecutivas: {n1} e {n2}")
        await db.execute(text("DELETE FROM nfse_numeracao WHERE prestador_cnpj = :c"), {"c": CNPJ_FIXTURE})
        await db.commit()
        medidas.append(f"numeração: reservas {n1}→{n2} ({MARCA_FIXTURE}, apagada)")

        # ── (j) espiar não consome ────────────────────────────────────────────────────
        e1 = await em.espiar_numero(db, CNPJ_FIXTURE, em.SERIE_PADRAO, "homologacao")
        e2 = await em.espiar_numero(db, CNPJ_FIXTURE, em.SERIE_PADRAO, "homologacao")
        r1 = await em.proximo_numero(db, CNPJ_FIXTURE, em.SERIE_PADRAO, "homologacao")
        await db.commit()
        if e1 != e2:
            falhas.append(f"(j) duas espiadas seguidas deram números diferentes: {e1} e {e2}")
        if r1 != e1:
            falhas.append(f"(j) a espiada disse {e1} e a reserva deu {r1} — a prévia mente sobre o número")
        await db.execute(text("DELETE FROM nfse_numeracao WHERE prestador_cnpj = :c"), {"c": CNPJ_FIXTURE})
        await db.commit()
        medidas.append(f"espiada: {e1}={e2} e reserva {r1}")

        # ── (k) a série de quem EMITE não é a série de quem o portal usa ──────────────
        # As duas vivem em tabelas diferentes e querem dizer coisas diferentes. Confundi-las
        # custou uma investigação inteira em 26/09/2026, e emitir na série do portal colide
        # com a numeração dele (E0014). Se um dia forem iguais, é bug de cadastro.
        from modules.fiscal.services.nfse_parametros import serie_de  # noqa: PLC0415

        for cnpj in CNPJS_DA_CASA:
            emp = (
                (
                    await db.execute(
                        text(
                            "SELECT nullif(trim(coalesce(nfse_serie_rps,'')),'') AS nfse_serie_rps"
                            " FROM empresas WHERE regexp_replace(cnpj,'[^0-9]','','g') = :c"
                        ),
                        {"c": cnpj},
                    )
                )
                .mappings()
                .first()
            )
            if not emp:
                continue
            minha = em.serie_da(dict(emp))
            do_portal = await serie_de(db, cnpj)
            if minha == do_portal:
                falhas.append(
                    f"(k) {cnpj} emite na mesma série do portal da contabilidade ({minha})"
                    " — a numeração vai colidir no fisco (E0014)"
                )
            medidas.append(f"série {cnpj}: ERP={minha} portal={do_portal}")

        # ── (i) prova viva: uma nota autorizada por CNPJ ──────────────────────────────
        vivas = (
            (
                await db.execute(
                    text(
                        "SELECT prestador_cnpj, count(*) AS q FROM nfses"
                        " WHERE ambiente = 'homologacao' AND status = 'autorizada'"
                        "   AND coalesce(chave_acesso,'') <> '' AND c_stat = '100'"
                        " GROUP BY 1"
                    )
                )
            )
            .mappings()
            .all()
        )
        tem = {r["prestador_cnpj"]: r["q"] for r in vivas}
        for cnpj in CNPJS_DA_CASA:
            if not tem.get(cnpj):
                falhas.append(f"(i) o CNPJ {cnpj} não tem NFS-e autorizada em homologação com chave e cStat 100")
        medidas.append("autorizadas em homologação: " + (", ".join(f"{k}={v}" for k, v in tem.items()) or "nenhuma"))

    # ── (f) as travas levantam de verdade ─────────────────────────────────────────────
    # A frase do gate é do DONO, não do oráculo. Até 25/09/2026 esta afirmação também
    # reprovava `NFSE_PRODUCAO_LIBERADA` aberta — e virou errada no dia em que ele liberou
    # a emissão real. Uma régua que reprova o que o dono autorizou ensina a ignorar o
    # painel. O que se afirma aqui é o MECANISMO: com o gate FECHADO, as travas levantam.
    # O estado atual do gate é medida, não desvio.
    gate_aberto = nn.producao_nfse_liberada()
    senha = os.environ.pop(nn.ENV_GATE_PRODUCAO_NFSE, None)
    try:
        exercicios = [
            ("ambiente de produção sem gate", lambda: nn._exigir_ambiente_nfse("1", "teste")),
            ("ambiente inválido", lambda: nn._exigir_ambiente_nfse("7", "teste")),
            ("XML sem tpAmb", lambda: nn._conferir_tp_amb(_xml_dps(None), "2", nn.URL_PRODUCAO_RESTRITA, "teste")),
            (
                "XML tpAmb=1 pedindo 2",
                lambda: nn._conferir_tp_amb(_xml_dps("1"), "2", nn.URL_PRODUCAO_RESTRITA, "teste"),
            ),
            ("XML tpAmb=1 sem gate", lambda: nn._conferir_tp_amb(_xml_dps("1"), "1", nn.URL_PRODUCAO, "teste")),
            (
                "host de produção com XML de teste",
                lambda: nn._conferir_tp_amb(_xml_dps("2"), "2", nn.URL_PRODUCAO, "teste"),
            ),
        ]
        for nome, fn in exercicios:
            try:
                fn()
                falhas.append(f"(f) com o gate FECHADO, a trava não levantou: {nome}")
            except nn.NFSeAmbienteError:
                pass
        # e o caminho legítimo tem de passar, senão a trava é só um muro
        try:
            nn._exigir_ambiente_nfse("2", "teste")
            nn._conferir_tp_amb(_xml_dps("2"), "2", nn.URL_PRODUCAO_RESTRITA, "teste")
        except nn.NFSeAmbienteError as e:
            falhas.append(f"(f) a trava barrou a HOMOLOGAÇÃO, que é o caminho legítimo: {e}")
    finally:
        if senha is not None:
            os.environ[nn.ENV_GATE_PRODUCAO_NFSE] = senha
    # e o gate tem de voltar exatamente como estava: um oráculo que destrava produção e
    # esquece de retravar é pior que o defeito que procura.
    if nn.producao_nfse_liberada() != gate_aberto:
        falhas.append("(f) o oráculo não devolveu o gate de produção ao estado em que o achou")
    medidas.append(
        f"travas exercidas: {len(exercicios)} com o gate fechado · "
        f"gate de produção hoje: {'ABERTO (decisão do dono)' if gate_aberto else 'fechado'}"
    )

    # ── (h) nada de número fiscal chumbado no caminho da NFS-e ────────────────────────
    fonte = (raiz / "modules/government_integrations/core/nfse_nacional.py").read_text(encoding="utf-8")
    montagem = fonte[fonte.index("def _build_dps_xml") : fonte.index("def emitir_dps")]
    literais = []
    if re.search(r"<cNBS>\d", montagem):
        literais.append("cNBS")
    if re.search(r"<IM>\d", montagem) or "45177801" in montagem:
        literais.append("inscrição municipal")
    if re.search(r"<pAliq\w*>\d", montagem):
        literais.append("alíquota de ISS")
    if literais:
        falhas.append(f"(h) número fiscal chumbado na montagem da DPS: {literais}")
    if "int(datetime.now().timestamp())" in (raiz / "modules/fiscal/services/nfse_emissao.py").read_text(
        encoding="utf-8"
    ):
        falhas.append("(h) o emissor da NFS-e voltou a usar timestamp como número de nota")

    print(" · ".join(medidas))
    for f in falhas:
        print("FALHOU:", f)
    if falhas:
        raise AssertionError(f"{len(falhas)} desvio(s) na NFS-e")
    print(
        "OK NFS-e: homologação é produção restrita com host próprio, produção só com chave e "
        "cStat 100 do órgão, «autorizada» só com protocolo e XML, XML no disco E no banco, "
        "Patrimonial recusada na NF-e 55 pela decisão do dono, travas levantando com o gate "
        "fechado, numeração sem buraco, prévia mostrando o número que vai ser enviado, e a "
        "série do ERP separada da série do portal da contabilidade"
    )
    print(f"TOTAL desvios: {len(falhas)}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, "/app")
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print(e)
        print("TOTAL desvios: >0")
        sys.exit(1)

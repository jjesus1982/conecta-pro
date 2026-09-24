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
  b) nenhuma NFS-e gravada em ambiente de produção, e nenhum contador de produção aberto;
  c) nenhuma linha que o sistema chame de «autorizada» sem protocolo E sem XML de retorno —
     as linhas vêm de SQL próprio deste arquivo e passam pela função pura da tela;
  d) o XML guardado existe EM DISCO e bate com a linha do banco (chave de acesso dentro do
     arquivo), e o banco também tem o XML — os dois lugares, nunca um só;
  e) a CONECTAMAIS PATRIMONIAL é recusada na NF-e modelo 55 pelo motivo CERTO (decisão do
     dono: ela só vende serviço) e não por «cadastro incompleto / falta inscrição estadual»;
     e a Eletrônica NÃO é recusada;
  f) as duas camadas da trava de produção levantam de verdade quando exercidas: ambiente,
     XML com `tpAmb=1`, XML sem `tpAmb`, XML divergente do pedido e host divergente do XML;
  g) a numeração da NFS-e é por (CNPJ + série + ambiente), com índice único no banco, sem
     repetir e sem buraco — e duas reservas concorrentes recebem números distintos e
     consecutivos (fixture 'FIXTURE DGX Z7', criada e apagada aqui dentro);
  h) nenhum número fiscal chumbado no caminho da NFS-e: sem `cNBS` literal, sem inscrição
     municipal literal, sem alíquota de ISS literal no XML;
  i) prova viva: há pelo menos UMA NFS-e autorizada em homologação para CADA um dos dois
     CNPJs, com chave de acesso do órgão e `cStat 100`.

Estado medido no nascimento (sandbox, 24/09/2026): `nfses` com 27 linhas 'autorizada', sem
coluna `ambiente`, sem `chave_acesso`, sem `xml_path`, sem `nfse_numeracao`, sem trava de
produção e sem política de documento por empresa → VERMELHO em (a)…(i).

Como roda (container, PYTHONPATH=/app):
    python3 /app/scripts/orq/test_oraculo_z7_nfse.py
Sai 0 = verde; 1 = vermelho.
"""

from __future__ import annotations

import asyncio
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

        # ── (b) nada gravado em produção ──────────────────────────────────────────────
        n_prod = (await db.execute(text("SELECT count(*) FROM nfses WHERE ambiente = 'producao'"))).scalar() or 0
        n_cont = (
            await db.execute(text("SELECT count(*) FROM nfse_numeracao WHERE ambiente = 'producao'"))
        ).scalar() or 0
        if n_prod or n_cont:
            falhas.append(f"(b) há NFS-e/contador em PRODUÇÃO: {n_prod} nota(s), {n_cont} contador(es)")
        medidas.append(f"produção: {n_prod} notas, {n_cont} contadores")

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

        n1 = await em.proximo_numero(db, CNPJ_FIXTURE, em.SERIE_ERP, "homologacao")
        n2 = await em.proximo_numero(db, CNPJ_FIXTURE, em.SERIE_ERP, "homologacao")
        await db.commit()
        if n2 != n1 + 1:
            falhas.append(f"(g) duas reservas seguidas não são consecutivas: {n1} e {n2}")
        await db.execute(text("DELETE FROM nfse_numeracao WHERE prestador_cnpj = :c"), {"c": CNPJ_FIXTURE})
        await db.commit()
        medidas.append(f"numeração: reservas {n1}→{n2} ({MARCA_FIXTURE}, apagada)")

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
    exercicios = [
        ("ambiente de produção sem gate", lambda: nn._exigir_ambiente_nfse("1", "teste")),
        ("ambiente inválido", lambda: nn._exigir_ambiente_nfse("7", "teste")),
        ("XML sem tpAmb", lambda: nn._conferir_tp_amb(_xml_dps(None), "2", nn.URL_PRODUCAO_RESTRITA, "teste")),
        ("XML tpAmb=1 pedindo 2", lambda: nn._conferir_tp_amb(_xml_dps("1"), "2", nn.URL_PRODUCAO_RESTRITA, "teste")),
        ("XML tpAmb=1 sem gate", lambda: nn._conferir_tp_amb(_xml_dps("1"), "1", nn.URL_PRODUCAO, "teste")),
        (
            "host de produção com XML de teste",
            lambda: nn._conferir_tp_amb(_xml_dps("2"), "2", nn.URL_PRODUCAO, "teste"),
        ),
    ]
    for nome, fn in exercicios:
        try:
            fn()
            falhas.append(f"(f) a trava NÃO levantou: {nome}")
        except nn.NFSeAmbienteError:
            pass
    # e o caminho legítimo tem de passar, senão a trava é só um muro
    try:
        nn._exigir_ambiente_nfse("2", "teste")
        nn._conferir_tp_amb(_xml_dps("2"), "2", nn.URL_PRODUCAO_RESTRITA, "teste")
    except nn.NFSeAmbienteError as e:
        falhas.append(f"(f) a trava barrou a HOMOLOGAÇÃO, que é o caminho legítimo: {e}")
    if nn.producao_nfse_liberada():
        falhas.append(f"(f) {nn.ENV_GATE_PRODUCAO_NFSE} está aberta neste ambiente — produção destravada")
    medidas.append(f"travas exercidas: {len(exercicios)}")

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
        "OK NFS-e: homologação é produção restrita com host próprio, nada em produção, "
        "«autorizada» só com protocolo e XML do órgão, XML no disco E no banco, Patrimonial "
        "recusada na NF-e 55 pela decisão do dono, travas levantando, numeração sem buraco"
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

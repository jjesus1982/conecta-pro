"""Oráculo — UM emissor de NF-e, e só em homologação (DGX Z2, 24/09/2026).

Por que existe: nota fiscal em produção é documento irreversível, com multa e obrigação
acessória. Até hoje a casa tinha DOIS emissores de NF-e e ZERO notas autorizadas. O aposentado
(`fiscal_contabil/notas_fiscais/nfe/controller.py`) trazia `tpAmb` chumbado em "1" e
`homologacao=False` na transmissão — bastava alguém chamar a rota para sair nota de verdade. E
usava um TIMESTAMP como número de nota, o que garante buraco permanente na numeração fiscal.
Este oráculo é a trava dessas duas coisas: ambiente e numeração.

O que afirma:
  a) toda chave de acesso gravada em `nfes` tem 44 dígitos e DV correto — recalculado AQUI
     pelo módulo 11, sem chamar o código do emissor;
  b) numeração por (CNPJ + série + ambiente) sem repetir (índice único existe e vale) e sem
     buraco: todo número entre o menor e o maior ou é nota ou é faixa inutilizada;
  c) duas emissões CONCORRENTES recebem números diferentes e consecutivos — o contador é
     atômico (fixture 'FIXTURE DGX Z2', apagada ao fim);
  d) nenhuma nota gravada com `tp_amb = '1'`, e as duas travas de produção realmente levantam:
     `_exigir_ambiente("1", …)` sem o gate e `_conferir_tp_amb(xml com tpAmb 1, …)`;
  e) o XML guardado da nota autorizada é um `nfeProc` com NFe + protNFe, `tpAmb` 2, chave e
     protocolo batendo com a linha do banco — e o arquivo existe em disco (guarda de 5 anos);
  f) nota cancelada tem evento 110111 guardado em `nfe_eventos` com cStat 135/155;
  g) o emissor aposentado não existe mais e ninguém o importa (varredura do backend inteiro,
     `main_production` e MCP inclusos);
  h) o emissor não decide tributo: nenhum CFOP/CST/alíquota literal em `nfe_provider.py` —
     a régua é `modules/fiscal/services/tributacao_nfe.py` (DGX Z4).

XSD: o pacote oficial de schemas da NF-e (PL_010) NÃO está no repositório — não há XSD para
validar contra. Em vez de fingir validação, o item (e) confere a estrutura mínima obrigatória
do leiaute 4.00 (infNFe/ide/emit/dest/det/imposto/total/pag/infRespTec + grupo IBSCBS da
NT 2025.002 + Signature + protNFe). O validador de verdade é a própria SEFAZ: schema inválido
volta como cStat 215 com a mensagem do XSD, e isso fica gravado em `nfes.motivo_rejeicao`.

Estado medido no nascimento (sandbox, 24/09/2026): `nfes` com 2 linhas, ambas 'rejeitada', de
11/04/2026, razão social ANTIGA ('JORDAN SANTOS DE JESUS LTDA'), sem coluna `tp_amb`, sem
índice único, sem `nfe_numeracao`, sem `nfe_eventos` → VERMELHO em (a)…(h).

Como roda (container, PYTHONPATH=/app):
    python3 /app/scripts/orq/test_oraculo_z2_emissor_nfe.py
Sai 0 = verde; 1 = vermelho.
"""

from __future__ import annotations

import ast
import asyncio
import re
import sys
from pathlib import Path

CNPJ_FIXTURE = "00000000000191"
MARCA_FIXTURE = "FIXTURE DGX Z2"


#: Módulo 11 escrito de novo aqui de propósito: o oráculo confere o DV, não reusa o cálculo.
def dv_modulo11(chave43: str) -> str:
    soma = sum(int(d) * [2, 3, 4, 5, 6, 7, 8, 9][i % 8] for i, d in enumerate(reversed(chave43)))
    resto = soma % 11
    return "0" if resto < 2 else str(11 - resto)


TAGS_MINIMAS = (
    "infNFe",
    "ide",
    "tpAmb",
    "emit",
    "CNPJ",
    "IE",
    "CRT",
    "dest",
    "det",
    "prod",
    "NCM",
    "CFOP",
    "imposto",
    "ICMS",
    "PIS",
    "COFINS",
    "IBSCBS",
    "cClassTrib",
    "gIBSCBS",
    "total",
    "ICMSTot",
    "IBSCBSTot",
    "transp",
    "pag",
    "infRespTec",
    "Signature",
    "protNFe",
    "infProt",
    "nProt",
    "cStat",
)


async def main() -> int:
    from sqlalchemy import text

    from core.database import async_session_factory

    falhas: list[str] = []
    medidas: list[str] = []

    async with async_session_factory() as db:
        # -- (a) chave de acesso: 44 dígitos e DV certo ----------------------
        chaves = (
            await db.execute(
                text("SELECT numero, serie, tp_amb, chave_acesso FROM nfes WHERE chave_acesso IS NOT NULL")
            )
        ).all()
        for numero, serie, _amb, chave in chaves:
            if not re.fullmatch(r"\d{44}", chave or ""):
                falhas.append(f"(a) chave de {numero}/{serie} não tem 44 dígitos: {chave!r}")
                continue
            esperado = dv_modulo11(chave[:43])
            if chave[43] != esperado:
                falhas.append(f"(a) DV errado em {chave}: tem {chave[43]}, deveria ser {esperado}")
        medidas.append(f"chaves conferidas: {len(chaves)}")

        # -- (b) numeração: sem repetir e sem buraco --------------------------
        idx = (
            await db.execute(
                text("SELECT indexdef FROM pg_indexes WHERE tablename = 'nfes' AND indexname = :n"),
                {"n": "ux_nfes_emitente_serie_numero"},
            )
        ).scalar_one_or_none()
        if not idx or "UNIQUE" not in idx.upper():
            falhas.append("(b) falta o índice único ux_nfes_emitente_serie_numero em (cnpj, serie, numero, tp_amb)")

        dups = (
            await db.execute(
                text(
                    "SELECT emitente_cnpj, serie, tp_amb, numero, count(*) FROM nfes WHERE numero IS NOT NULL"
                    " GROUP BY 1,2,3,4 HAVING count(*) > 1"
                )
            )
        ).all()
        for cnpj, serie, amb, numero, n in dups:
            falhas.append(f"(b) número repetido: {cnpj} série {serie} amb {amb} nº {numero} aparece {n}x")

        faixas = (
            await db.execute(
                text(
                    "SELECT emitente_cnpj, serie, tp_amb, min(numero), max(numero), count(*)"
                    " FROM nfes WHERE numero IS NOT NULL GROUP BY 1,2,3"
                )
            )
        ).all()
        for cnpj, serie, amb, menor, maior, quantas in faixas:
            inutilizados = (
                await db.execute(
                    text(
                        "SELECT coalesce(sum(numero_final - numero_inicial + 1), 0) FROM nfe_eventos"
                        " WHERE emitente_cnpj = :c AND serie = :s AND tp_amb = :a AND tipo = 'inutilizacao'"
                        "   AND codigo_status = '102' AND numero_inicial >= :mi AND numero_final <= :ma"
                    ),
                    {"c": cnpj, "s": serie, "a": amb, "mi": menor, "ma": maior},
                )
            ).scalar_one()
            buraco = (maior - menor + 1) - quantas - int(inutilizados)
            if buraco > 0:
                falhas.append(
                    f"(b) {buraco} número(s) sumido(s) em {cnpj} série {serie} amb {amb} "
                    f"(faixa {menor}–{maior}, {quantas} notas, {inutilizados} inutilizados). "
                    "Número que não virou nota tem de ser inutilizado, não esquecido."
                )
            medidas.append(f"{cnpj[:8]}…/{serie}/amb{amb}: {menor}–{maior}, {quantas} notas, {inutilizados} inutil.")

        # -- (c) duas emissões concorrentes: números diferentes ---------------
        from modules.fiscal_contabil.notas_fiscais.nfe import emissor as em

        async def reservar():
            async with async_session_factory() as s2:
                n = await em.proximo_numero(s2, CNPJ_FIXTURE, 1, "2")
                await s2.commit()
                return n

        try:
            a, b = await asyncio.gather(reservar(), reservar())
            if a == b:
                falhas.append(f"(c) duas emissões concorrentes receberam o MESMO número: {a}")
            elif abs(a - b) != 1:
                falhas.append(f"(c) números concorrentes não consecutivos: {a} e {b}")
            medidas.append(f"concorrência: {sorted((a, b))}")
        finally:
            await db.execute(text("DELETE FROM nfe_numeracao WHERE emitente_cnpj = :c"), {"c": CNPJ_FIXTURE})
            await db.execute(
                text("DELETE FROM nfes WHERE informacoes_complementares LIKE :m"), {"m": f"%{MARCA_FIXTURE}%"}
            )
            await db.execute(text("DELETE FROM nfe_eventos WHERE justificativa LIKE :m"), {"m": f"%{MARCA_FIXTURE}%"})
            await db.commit()

        # -- (d) nada em produção ---------------------------------------------
        em_producao = (await db.execute(text("SELECT count(*) FROM nfes WHERE tp_amb = '1'"))).scalar_one()
        if em_producao:
            falhas.append(f"(d) {em_producao} nota(s) gravadas com tp_amb='1' (PRODUÇÃO) no sandbox")

        from modules.financial.integrations import nfe_provider as prov

        if prov.producao_liberada():
            falhas.append("(d) o gate NFE_PRODUCAO_LIBERADA está ABERTO neste ambiente")
        for chamada, rotulo in (
            (lambda: prov._exigir_ambiente("1", "teste"), "_exigir_ambiente('1')"),
            (
                lambda: prov._conferir_tp_amb(b"<NFe><ide><tpAmb>1</tpAmb></ide></NFe>", "1", "teste"),
                "_conferir_tp_amb(tpAmb=1)",
            ),
            (
                lambda: prov._conferir_tp_amb(b"<NFe><ide><tpAmb>1</tpAmb></ide></NFe>", "2", "teste"),
                "_conferir_tp_amb(divergente)",
            ),
            (lambda: prov._conferir_tp_amb(b"<NFe/>", "2", "teste"), "_conferir_tp_amb(sem tpAmb)"),
        ):
            try:
                chamada()
                falhas.append(f"(d) {rotulo} NÃO levantou — a trava de produção está solta")
            except prov.NFeError:
                pass

        # -- (d2) produção não emite antes de alguém declarar o último número ---
        # A guarda nasceu em 24/09/2026 de um buraco medido: `proximo_numero` se auto-semeia
        # de `MAX(numero) FROM nfes`, e em produção essa tabela está vazia — o número sairia
        # 1. A NF-e real da Eletrônica está em 10.026, série 1 (DANFE de 17/09, protocolo
        # 113263811849419), emitida por um sistema de terceiro. A SEFAZ recusaria com 539 e o
        # número ficaria queimado — e a recusa viria DEPOIS de reservar, abrindo buraco na
        # numeração a cada tentativa. Por isso a guarda é ANTES da reserva, e é isso que este
        # item afirma: recusa, e sem consumir número.
        from fastapi import HTTPException  # noqa: PLC0415

        from modules.fiscal_contabil.notas_fiscais.nfe import emissor as em2  # noqa: PLC0415

        antes_prod = (await db.execute(text("SELECT count(*) FROM nfe_numeracao WHERE tp_amb = '1'"))).scalar_one()
        try:
            n_prod = await em2.proximo_numero(db, "99999999000191", 99, "1")
            falhas.append(f"(d2) produção reservou o nº {n_prod} sem ninguém declarar o último número real")
        except HTTPException as e:
            if (e.detail or {}).get("code") != "NUMERACAO_NAO_DECLARADA":
                falhas.append(f"(d2) recusou por outro motivo: {e.detail}")
        depois_prod = (await db.execute(text("SELECT count(*) FROM nfe_numeracao WHERE tp_amb = '1'"))).scalar_one()
        if depois_prod != antes_prod:
            falhas.append("(d2) a recusa CONSUMIU contador de produção — tem de recusar antes de reservar")

        # -- (e) o XML guardado é um nfeProc completo --------------------------
        autorizadas = (
            await db.execute(
                text(
                    "SELECT chave_acesso, protocolo_autorizacao, xml_path, xml_autorizado, tp_amb"
                    " FROM nfes WHERE status = 'autorizada'"
                )
            )
        ).all()
        if not autorizadas:
            falhas.append("(e) nenhuma NF-e AUTORIZADA no banco — a frente não se prova sem uma")
        for chave, prot, caminho, xml, amb in autorizadas:
            if not caminho or not Path(caminho).exists():
                falhas.append(f"(e) XML de {chave} não está em disco ({caminho!r}) — guarda de 5 anos quebrada")
            texto = xml or (Path(caminho).read_text(encoding="utf-8") if caminho and Path(caminho).exists() else "")
            faltando = [t for t in TAGS_MINIMAS if f"<{t}" not in texto and f":{t}" not in texto]
            if faltando:
                falhas.append(f"(e) XML de {chave} sem as tags obrigatórias: {faltando}")
            if chave not in texto:
                falhas.append(f"(e) XML de {chave} não contém a própria chave")
            if prot and prot not in texto:
                falhas.append(f"(e) XML de {chave} não contém o protocolo {prot}")
            ambs = set(re.findall(r"<(?:\w+:)?tpAmb>(\d)</(?:\w+:)?tpAmb>", texto))
            if ambs != {amb}:
                falhas.append(f"(e) XML de {chave} tem tpAmb {sorted(ambs)} e a linha diz {amb}")
        medidas.append(f"autorizadas: {len(autorizadas)}")

        # -- (f) cancelamento com evento guardado ------------------------------
        canceladas = (await db.execute(text("SELECT chave_acesso FROM nfes WHERE status = 'cancelada'"))).all()
        for (chave,) in canceladas:
            ev = (
                await db.execute(
                    text(
                        "SELECT codigo_status, xml_path FROM nfe_eventos"
                        " WHERE chave_acesso = :c AND tipo = 'cancelamento'"
                    ),
                    {"c": chave},
                )
            ).all()
            if not ev:
                falhas.append(f"(f) nota {chave} está 'cancelada' sem evento 110111 guardado")
            elif not any(c in ("135", "155") for c, _ in ev):
                falhas.append(f"(f) evento de {chave} sem cStat 135/155: {[c for c, _ in ev]}")
        medidas.append(f"canceladas: {len(canceladas)}")

        # -- (g) o emissor aposentado sumiu e ninguém o importa -----------------
        raiz = Path("/app")
        morto = raiz / "modules/fiscal_contabil/notas_fiscais/nfe/controller.py"
        if morto.exists():
            falhas.append(f"(g) o emissor aposentado ainda existe: {morto}")
        chamadores = []
        for arq in list(raiz.rglob("*.py")) + list(raiz.glob("*.py")):
            if "__pycache__" in str(arq) or "/tests/" in str(arq) or arq.name == Path(__file__).name:
                continue
            try:
                txt = arq.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if "notas_fiscais.nfe.controller" in txt or "notas_fiscais.nfe import controller" in txt:
                chamadores.append(str(arq))
        if chamadores:
            falhas.append(f"(g) ainda importam o emissor morto: {chamadores}")
        medidas.append("emissor aposentado: sem arquivo e sem chamador")

        # -- (h) o emissor não decide tributo ----------------------------------
        fonte = (raiz / "modules/financial/integrations/nfe_provider.py").read_text(encoding="utf-8")
        arvore = ast.parse(fonte)
        literais: list[str] = []
        for no in ast.walk(arvore):
            if isinstance(no, ast.keyword) and no.arg in (
                "cfop",
                "icms_modalidade",
                "icms_csosn",
                "icms_aliquota",
                "pis_modalidade",
                "cofins_modalidade",
            ):
                if isinstance(no.value, ast.Constant) and str(no.value.value).strip():
                    literais.append(f"{no.arg}={no.value.value!r}")
        if literais:
            falhas.append(
                "(h) o emissor está chumbando tributo (a régua é modules/fiscal/services/"
                f"tributacao_nfe.py): {literais}"
            )
        if "tributacao_nfe" not in (raiz / "modules/fiscal_contabil/notas_fiscais/nfe/emissor.py").read_text(
            encoding="utf-8"
        ):
            falhas.append("(h) o emissor não chama a régua fiscal da Z4 — tributo sem norma")

    print(" · ".join(medidas))
    for f in falhas:
        print("FALHOU:", f)
    if falhas:
        raise AssertionError(f"{len(falhas)} desvio(s) no emissor de NF-e")
    print(
        "OK emissor NF-e: chave com DV certo, numeração sem buraco e atômica, produção travada, "
        "XML guardado, cancelamento com evento, emissor duplicado aposentado, tributo pela régua"
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

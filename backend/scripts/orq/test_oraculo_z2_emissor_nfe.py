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

        # -- (d) o gate é um INTERRUPTOR, e nota de produção nunca fica fantasma --
        #
        # RÉGUA REESCRITA em 25/09/2026, no dia em que o dono autorizou produção
        # («pode ir» / «tem toda a minha autorização»). A régua anterior afirmava
        # *«o gate está fechado»* e *«não existe nota com tp_amb=1»* — e ficou
        # vermelha na hora em que o sistema passou a fazer a coisa CERTA. Uma régua
        # que reprova o estado autorizado não é rigor, é alarme quebrado: quem vê
        # vermelho todo dia para de olhar, e o dia em que a trava afrouxar de
        # verdade passa despercebido.
        #
        # O que NÃO muda com a autorização, e é o que este item passa a afirmar:
        #   1. com o gate FECHADO, produção é recusada — provado fechando o gate
        #      aqui dentro, em vez de torcer para que esteja fechado;
        #   2. com o gate ABERTO, produção passa — é isso que faz dele um
        #      interruptor e não enfeite;
        #   3. divergência e ausência de <tpAmb> são recusadas SEMPRE, com gate
        #      aberto ou fechado — elas não são sobre permissão, são sobre o XML
        #      dizer uma coisa e o pedido dizer outra;
        #   4. nenhuma nota de produção fica FANTASMA: gravada com tp_amb='1' sem
        #      chave/protocolo e sem status de erro. Esse é o risco real agora —
        #      número reservado, nota perdida, buraco na numeração. Aconteceu duas
        #      vezes em 25/09 (buracos 3 e 4), por falha de disco no `_guardar_xml`.
        import os  # noqa: PLC0415

        from modules.financial.integrations import nfe_provider as prov

        fantasmas = (
            await db.execute(
                text(
                    "SELECT count(*) FROM nfes WHERE tp_amb = '1'"
                    "   AND coalesce(chave_acesso,'') = '' AND coalesce(protocolo_autorizacao,'') = ''"
                    "   AND coalesce(status,'') NOT IN ('rejeitada','erro','cancelada','denegada')"
                )
            )
        ).scalar_one()
        if fantasmas:
            falhas.append(
                f"(d) {fantasmas} nota(s) em PRODUÇÃO sem chave, sem protocolo e sem status de erro "
                f"— número reservado e nota perdida"
            )

        # (3) recusa que independe do gate
        for chamada, rotulo in (
            (
                lambda: prov._conferir_tp_amb(b"<NFe><ide><tpAmb>1</tpAmb></ide></NFe>", "2", "teste"),
                "_conferir_tp_amb(divergente)",
            ),
            (lambda: prov._conferir_tp_amb(b"<NFe/>", "2", "teste"), "_conferir_tp_amb(sem tpAmb)"),
        ):
            try:
                chamada()
                falhas.append(f"(d) {rotulo} NÃO levantou — isso não depende de gate nenhum")
            except prov.NFeError:
                pass

        # (1) e (2): o gate mandando dos dois lados. Mexe na env DESTE processo e devolve
        # como estava — nunca no `.env` e nunca nos contêineres.
        _gate_antes = os.environ.get(prov._ENV_GATE_PRODUCAO)
        try:
            os.environ[prov._ENV_GATE_PRODUCAO] = "frase-errada-de-proposito"
            if prov.producao_liberada():
                falhas.append("(d) `producao_liberada()` diz SIM com a frase errada — o gate não confere nada")
            for chamada, rotulo in (
                (lambda: prov._exigir_ambiente("1", "teste"), "_exigir_ambiente('1')"),
                (
                    lambda: prov._conferir_tp_amb(b"<NFe><ide><tpAmb>1</tpAmb></ide></NFe>", "1", "teste"),
                    "_conferir_tp_amb(tpAmb=1)",
                ),
            ):
                try:
                    chamada()
                    falhas.append(f"(d) com o gate FECHADO, {rotulo} NÃO levantou — a trava está solta")
                except prov.NFeError:
                    pass

            os.environ[prov._ENV_GATE_PRODUCAO] = prov._SENHA_GATE_PRODUCAO
            if not prov.producao_liberada():
                falhas.append("(d) `producao_liberada()` diz NÃO com a frase CERTA — o gate não abre nunca")
            for chamada, rotulo in (
                (lambda: prov._exigir_ambiente("1", "teste"), "_exigir_ambiente('1')"),
                (
                    lambda: prov._conferir_tp_amb(b"<NFe><ide><tpAmb>1</tpAmb></ide></NFe>", "1", "teste"),
                    "_conferir_tp_amb(tpAmb=1)",
                ),
            ):
                try:
                    chamada()
                except prov.NFeError as e:
                    falhas.append(f"(d) com o gate ABERTO, {rotulo} recusou mesmo assim: {e}")
        finally:
            if _gate_antes is None:
                os.environ.pop(prov._ENV_GATE_PRODUCAO, None)
            else:
                os.environ[prov._ENV_GATE_PRODUCAO] = _gate_antes

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

        # -- (d3) produção NÃO se herda de variável de ambiente -----------------
        # Medido em 25/09/2026, minutos depois de o dono ligar `NFE_AMBIENTE=1`: os endpoints
        # `emitir` e `inutilizar` não passavam `tp_amb`, então caíam em `ambiente_atual()` — que
        # lê a variável. Da hora em que produção foi ligada, QUALQUER chamada a
        # `POST /fiscal/nfe/emitir` sem dizer nada emitiria documento fiscal DE VERDADE,
        # irreversível. Um teste, um script, um clique errado, o MCP.
        #
        # A régua aqui é a DIFERENÇA: mesmo com a variável dizendo produção, o default do
        # request tem de continuar homologação. Afirmar só «o default é homologação» passaria
        # verde num ambiente de teste onde a variável nem existe — e é justamente em produção
        # que o defeito mora.
        from modules.fiscal_contabil.notas_fiscais.nfe.emissor import (  # noqa: PLC0415
            EmitirRequest,
            InutilizarRequest,
            ambiente_atual,
        )

        _item = [
            {
                "codigo": "X",
                "descricao": "Y",
                "ncm": "85258919",
                "unidade": "UN",
                "quantidade": 1,
                "valor_unitario": 10,
            }
        ]
        # Campo AUSENTE tem de RECUSAR, não cair em default. Crítica da sessão do t6, aceita:
        # os dois defaults erram — o «homologacao» faz quem queria emitir de verdade entregar um
        # DANFE «SEM VALOR FISCAL» ao cliente; o «producao» emite sem ninguém pedir. Exigir não erra.
        for rotulo, fabrica in (
            ("EmitirRequest", lambda: EmitirRequest(items=_item)),
            (
                "InutilizarRequest",
                lambda: InutilizarRequest(numero_inicial=1, numero_final=2, justificativa="faixa nao utilizada 1"),
            ),
        ):
            try:
                fabrica()
                falhas.append(f"(d3) {rotulo} SEM ambiente foi aceito — campo ausente tem de recusar, não ter default")
            except Exception:  # noqa: BLE001, S110 — ValidationError do pydantic é o esperado
                pass
        if EmitirRequest(ambiente="producao", items=_item).ambiente != "producao":
            falhas.append("(d3) EmitirRequest não aceita produção quando PEDIDA explicitamente")
        if EmitirRequest(ambiente="homologacao", items=_item).ambiente != "homologacao":
            falhas.append("(d3) EmitirRequest não aceita homologação quando PEDIDA explicitamente")
        try:
            EmitirRequest(ambiente="qualquer", items=_item)
            falhas.append("(d3) EmitirRequest aceitou ambiente inválido — o padrão deve recusar")
        except Exception:  # noqa: BLE001, S110 — ValidationError do pydantic é o esperado
            pass
        # A régua é a DIFERENÇA: mesmo com a variável dizendo produção, o pedido manda.
        if ambiente_atual() == "1" and EmitirRequest(ambiente="homologacao", items=_item).ambiente != "homologacao":
            falhas.append("(d3) com NFE_AMBIENTE=1 o pedido de homologação foi ignorado")

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

"""C6 — a EFD ICMS/IPI declara a NF-e que existe, e não inventa documento para não ficar oca.

Nasceu em 25/09/2026, do loop de contabilidade. O gerador de EFD ICMS/IPI existia, rodava, e
o que ele produzia era uma declaração falsa:

    def carregar_documentos_do_periodo(...):
        '''... os documentos reais são refletidos aqui para não gerar arquivo oco.'''
        SELECT chave_acesso, numero, competencia, ... FROM nfse_emitidas_nacional

Ele lia **NOTAS DE SERVIÇO** e as declarava como `tipo: "55"` (NF-e de mercadoria) com CFOP
5933. NFS-e é documento MUNICIPAL de ISS: não entra em escrituração de ICMS. Medido na
competência 09/2026 antes da correção: **9 documentos, todos NFS-e**, com chave começando
em `1302603` — que é o código IBGE de Manaus, não uma chave de NF-e. E o arquivo **omitia a
única NF-e de verdade**: nº 1 série 2, Villa Dei Fiori, R$ 2.581,00, autorizada pela SEFAZ
em 25/09/2026. Exatamente ao contrário.

**Arquivo oco é honesto. Arquivo que declara nota de serviço como mercadoria, não.**

O QUE ELE AFIRMA

 (a) **Nenhuma NFS-e entra.** Nenhuma chave declarada no arquivo pertence a
     `nfse_emitidas_nacional`, e nenhuma começa pelo código IBGE do município (a assinatura
     da chave de nota de serviço).

 (b) **Todo documento declarado existe.** Cada chave do C100 está em `nfes` com
     `status='autorizada'`, `tp_amb='1'` e emitente igual ao CNPJ do arquivo.

 (c) **Nada de NF-e autorizada fica de fora** do período declarado.

 (d) **O campo do DESCONTO não é o valor da nota.** `VL_DESC` recebia `doc.valor_total`: uma
     NF-e de R$ 2.581,00 saía declarando R$ 2.581,00 de desconto, e R$ 0,00 de mercadoria.

 (e) **Cada item vira C170, e todo C170 tem cadastro no 0200.** O perfil A exige o detalhe
     por item; o campo `itens` do documento existia e nunca era preenchido nem lido.

 (f) **O C190 traz ALÍQUOTA no campo da alíquota.** Ele recebia `doc.valor_icms` — o VALOR —
     no campo da alíquota, com CST fixo "00" e um único registro por documento.

 (g) **Os encerradores contam LINHAS**, não chaves distintas do dicionário. (O 9999 encerra
     o ARQUIVO, não o bloco 9: contá-lo dentro do 9990 reprova o arquivo correto.)

 (h) **O participante leva o documento dele.** O 0150 saía com `00000000000000` no CNPJ e o
     CNPJ certo só no código.

VERMELHO ANTES: com o carregador anterior, (a) acusava 9 chaves de NFS-e, (b) acusava 9
documentos que não existem em `nfes`, (c) acusava a NF-e real ausente, (d) acusava desconto
igual ao total, (e) acusava zero C170, (f) acusava alíquota fora de faixa.
"""

from __future__ import annotations

import asyncio
import collections
import re
import sys
from datetime import date as _date

#: Janela conferida: o mês em que a primeira NF-e de produção foi autorizada.
PERIODO = ("2026-09-01", "2026-09-30")


def _registros(linhas: list[str]) -> collections.Counter:
    return collections.Counter(ln.split("|")[1] for ln in linhas if ln.startswith("|"))


async def main() -> int:
    from sqlalchemy import text

    from core.database import async_session_factory
    from modules.government_integrations.services.sped_fiscal_service import SPEDFiscalService

    falhas: list[str] = []
    medidas: list[str] = []

    svc = SPEDFiscalService()
    r = svc.gerar_arquivo(*PERIODO)
    conteudo = r.get("conteudo") or ""
    linhas = conteudo.split("\r\n") if "\r\n" in conteudo else conteudo.split("\n")
    regs = _registros(linhas)
    c100 = [ln.split("|") for ln in linhas if ln.startswith("|C100|")]
    medidas.append(f"EFD {PERIODO[0][:7]}: {len(linhas)} linhas, {len(c100)} documento(s)")

    chaves_arquivo = {p[9] for p in c100 if len(p) > 9 and p[9]}

    async with async_session_factory() as db:
        nfse = {
            r0[0] for r0 in (
                await db.execute(text("SELECT chave_acesso FROM nfse_emitidas_nacional"))
            ).all() if r0[0]
        }
        reais = {
            r0[0]: r0
            for r0 in (
                await db.execute(
                    text(
                        "SELECT chave_acesso, numero, valor_total_nota, data_emissao::date "
                        "  FROM nfes "
                        " WHERE status = 'autorizada' AND coalesce(tp_amb,'') = '1' "
                        "   AND coalesce(active, TRUE) IS TRUE "
                        "   AND regexp_replace(coalesce(emitente_cnpj,''),'\\D','','g') = :c "
                        "   AND data_emissao::date BETWEEN :i AND :f"
                    ),
                    # asyncpg exige objeto `date` no parâmetro: string aqui levanta
                    # «'str' object has no attribute 'toordinal'», e um CAST no SQL não
                    # salva — ele deduz o tipo pelo cast e tenta codificar a string assim
                    # mesmo.
                    {
                        "c": re.sub(r"\D", "", svc.cnpj),
                        "i": _date.fromisoformat(PERIODO[0]),
                        "f": _date.fromisoformat(PERIODO[1]),
                    },
                )
            ).all() if r0[0]
        }

    # (a) nenhuma NFS-e entra
    intrusas = chaves_arquivo & nfse
    if intrusas:
        falhas.append(
            f"(a) {len(intrusas)} chave(s) de NFS-e declarada(s) como NF-e: {sorted(intrusas)[:2]}"
        )
    ibge = (svc.cod_municipio or "").strip()
    if ibge:
        por_ibge = [k for k in chaves_arquivo if k.startswith(ibge)]
        if por_ibge:
            falhas.append(
                f"(a) {len(por_ibge)} chave(s) começam pelo código IBGE {ibge} — assinatura de "
                "chave de nota de SERVIÇO, não de NF-e"
            )
    medidas.append(f"chaves no arquivo: {len(chaves_arquivo)}")

    # (b) e (c) o arquivo e o banco dizem a mesma coisa
    fantasmas = chaves_arquivo - set(reais)
    if fantasmas:
        falhas.append(f"(b) {len(fantasmas)} documento(s) declarado(s) sem NF-e correspondente")
    ausentes = set(reais) - chaves_arquivo
    if ausentes:
        falhas.append(
            f"(c) {len(ausentes)} NF-e autorizada(s) de produção FORA do arquivo: "
            f"{[reais[k][1] for k in sorted(ausentes)][:3]}"
        )
    medidas.append(f"NF-e reais no período: {len(reais)}")

    # (d) desconto não é o total
    for p in c100:
        if len(p) < 17:
            continue
        total, desconto, merc = p[12], p[14], p[16]
        if desconto and desconto not in ("0", "0.00") and desconto == total:
            falhas.append(f"(d) C100 com VL_DESC igual ao VL_DOC ({total}) — campo trocado")
        if merc in ("0", "0.00") and total not in ("0", "0.00"):
            falhas.append(f"(d) C100 com VL_MERC zerado e VL_DOC {total}")

    # (e) item vira C170 e tem 0200
    cad_0200 = {ln.split("|")[2] for ln in linhas if ln.startswith("|0200|")}
    c170 = [ln.split("|") for ln in linhas if ln.startswith("|C170|")]
    if reais and not c170:
        falhas.append("(e) há NF-e no período e nenhum C170 — perfil A exige o item")
    sem_cadastro = {p[3] for p in c170 if len(p) > 3 and p[3] and p[3] not in cad_0200}
    if sem_cadastro:
        falhas.append(f"(e) C170 aponta para item sem 0200: {sorted(sem_cadastro)[:3]}")
    medidas.append(f"C170={len(c170)} · 0200={len(cad_0200)}")

    # (f) alíquota no campo da alíquota
    for ln in linhas:
        if not ln.startswith("|C190|"):
            continue
        p = ln.split("|")
        if len(p) < 6:
            continue
        try:
            aliq, opr = float(p[4] or 0), float(p[5] or 0)
        except ValueError:
            falhas.append(f"(f) C190 com alíquota não numérica: {p[4]!r}")
            continue
        if aliq > 100:
            falhas.append(
                f"(f) C190 com alíquota {aliq} — maior que 100%: o campo está recebendo VALOR"
            )
        if opr > 0 and aliq == opr:
            falhas.append("(f) C190 com alíquota igual ao valor da operação — campos trocados")
    medidas.append(f"C190={regs.get('C190', 0)}")

    # (g) encerradores contam linhas
    for reg, bloco in [("0990", "0"), ("C990", "C"), ("E990", "E"), ("H990", "H"), ("9990", "9")]:
        ln = next((x for x in linhas if x.startswith(f"|{reg}|")), None)
        if not ln:
            falhas.append(f"(g) o arquivo não tem {reg}")
            continue
        declarado = int(ln.split("|")[2] or 0)
        # 9999 encerra o ARQUIVO, não o bloco 9.
        contado = sum(v for k, v in regs.items() if k.startswith(bloco) and k != "9999")
        if declarado != contado:
            falhas.append(f"(g) {reg} declara {declarado} e o bloco tem {contado} linha(s)")
    ln9999 = next((x for x in linhas if x.startswith("|9999|")), None)
    if not ln9999 or int(ln9999.split("|")[2] or 0) != len(linhas):
        falhas.append("(g) 9999 não bate com o total de linhas do arquivo")

    # (h) participante com documento
    for ln in linhas:
        if ln.startswith("|0150|") and ln.split("|")[5] in ("00000000000000", "00000000000"):
            falhas.append(f"(h) 0150 com CNPJ de placeholder: {ln[:70]}")

    print(" · ".join(medidas))
    for f in falhas:
        print("FALHOU:", f)
    if falhas:
        raise AssertionError(f"{len(falhas)} desvio(s) na EFD ICMS/IPI")
    print(
        "OK EFD: só NF-e real e autorizada, nenhuma nota de serviço, nada de fora, desconto "
        "no campo do desconto, item com C170 e 0200, alíquota no campo da alíquota e "
        "encerradores contando linhas"
    )
    print(f"TOTAL desvios C6: {len(falhas)}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, "/app")
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print(e)
        print("TOTAL desvios C6: >0")
        sys.exit(1)

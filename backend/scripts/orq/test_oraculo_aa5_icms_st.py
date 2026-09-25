#!/usr/bin/env python3
"""Oráculo AA5 — o ICMS que já foi pago não se cobra de novo (24/09/2026).

**Por que existe.** Até 24/09/2026 a régua de tributação devolvia CFOP 5102 / CST 00 / ICMS 20%
para TODA venda interna no Amazonas. Medido nos seis produtos da NF-e nº 10.026 da própria
empresa: **5102 nos seis**. A nota real, autorizada pela SEFAZ-AM (protocolo 113263811849419,
17/09/2026), saiu com **CFOP 5405 · CST 060 · BC ICMS 0,00 · V.ICMS 0,00** nos seis — CST 060 é
*ICMS cobrado anteriormente por substituição tributária*. O sistema cobraria o imposto duas
vezes, em 43 dos 95 produtos do catálogo fiscal.

**O que este oráculo afirma**

  (a) os SEIS itens da NF-e 10.026 saem com CFOP 5405, CST 060 e ICMS 0,00 — item a item,
      contra os valores transcritos da DANFE, somando os R$ 2.518,00 da nota;
  (b) NENHUM produto que entrou com CST/CSOSN de ST sai com ICMS cobrado — varre `fin_produtos`
      inteiro, produto a produto, pela régua;
  (c) produto sem entrada conhecida NÃO sai com CFOP chutado: a régua recusa, e a recusa nomeia
      o produto e ensina o que fazer;
  (d) recontagem por parser PRÓPRIO dos itens de `nfe_entradas.xml_raw`: o número de itens que
      entraram com ICMS-ST não pode mudar sem alguém saber;
  (e) a coluna `fin_produtos.icms_entrada_cst` existe, está preenchida para todo produto que tem
      entrada no XML, e a tela não tem régua própria (o que ela mostra é o que o serviço diz).

**Estado medido no nascimento** (sandbox `conecta_pro_staging`, cópia de produção de 23/09, e
conferido igual em produção em 24/09): `nfe_entradas` = 84 notas, 51 com XML, **209 itens**;
CST de ICMS na entrada 60 → 97 · 00 → 73 · 20 → 5 · 50 → 5 · 41 → 4; CSOSN 102 → 13 · 500 → 9 ·
400 → 1; 2 itens sem grupo de ICMS. **106 dos 209 (50,7%) com ICMS já retido por ST.**
`fin_produtos` = 95 linhas, todas casando por `codigo` com um `cProd` das notas de entrada:
**43 com ST · 43 tributadas · 9 sem tratamento com fonte**. `products` = 867, dos quais **810**
que não casam por código com nenhuma NF-e de entrada nossa.

> Nota sobre uma contagem que circulou na onda: «CST 60 → 97 · 00 → 74 · 53 → 13 · 06 → 6 ·
> 20 → 5 · 50 → 5 · 41 → 4 · 99 → 3; 97 de 207 = 47% com ST». Aquela leitura pegou o `<CST>` de
> QUALQUER imposto do item — 53 é CST de IPI, 06 e 99 são de PIS/COFINS. Restrita ao grupo
> `det/imposto/ICMS`, que é o que importa aqui, a conta é a de cima: **106 de 209 = 50,7%**.

**Como roda**

    docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" \\
      -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env \\
      -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= $ENVS \\
      conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_aa5_icms_st.py
"""

from __future__ import annotations

import asyncio
import sys
from decimal import Decimal
from pathlib import Path

#: As telas desta frente entram na régua do `checar_nao_vigiado.py`: tela é vigiada quando
#: um oráculo CITA o slug dela. Citar num comentário enganaria o contador — `conferir_telas`
#: monta o builder e prova que a tela existe e não é casca.
TELAS_DA_FRENTE = ("nfe-icms-entrada", "nfe-icms-entrada-registro")
MODULO_DA_FRENTE = "fiscal"

sys.path.insert(0, str(Path(__file__).resolve().parents[1].parent))

CNPJ_ELETRONICA = "35.710.481/0001-03"

#: Os SEIS itens da NF-e nº 10.026, série 1 — transcritos da DANFE que o dono subiu
#: (`uploads/_entrada/NFs/DANFE 10.026 - CONDOMINIO RESIDENCIAL PARQUE DOS FRANCESES 09 2026.pdf`).
#: Protocolo 113263811849419, autorizada em 17/09/2026. É a régua de fora do sistema.
NOTA_10026 = [
    # descrição,                              NCM,        qtd, valor unit., total
    ("CABO LAN CAT5E 305M 100% COBRE", "85444900", 1, "895.00", "895.00"),
    ("CENTRAL FONTE SUSPENSA INTELBRAS", "85044021", 1, "365.00", "365.00"),
    ("BOTOEIRA PORTA", "85365090", 2, "90.00", "180.00"),
    ("FECHADURA ELETRONICA PAPAIZ", "83014000", 2, "389.00", "778.00"),
    ("CONECTOR POWER BALUN", "85369090", 2, "105.00", "210.00"),
    ("CANALETA 10X10 COM FITA", "39162000", 9, "10.00", "90.00"),
]
TOTAL_10026 = Decimal("2518.00")
CFOP_10026 = "5405"
CST_10026 = "60"  # a DANFE imprime «060» = origem 0 + CST 60

#: destinatário da nota real: condomínio em Manaus, não contribuinte do ICMS.
DEST_10026 = {"uf": "AM", "contribuinte": False, "suframa": None}

#: medido no nascimento — se mudar, alguém precisa saber POR QUÊ.
ESPERADO_ITENS_ENTRADA = 209
ESPERADO_ITENS_ST = 106

_ST = {"10", "30", "60", "70", "201", "202", "203", "500"}


def _cst_icms_dos_itens(xml: str) -> list[str]:
    """Parser PRÓPRIO — não importa nada do serviço. Devolve o CST/CSOSN de ICMS por item.

    Só o grupo `det/imposto/ICMS`. Ler `<CST>` solto pega CST de IPI (53) e de PIS/COFINS
    (06, 99) e inventa uma distribuição que não é de ICMS — foi exatamente o que aconteceu com
    a contagem «97 de 207» que circulou na onda.
    """
    from defusedxml.ElementTree import fromstring

    try:
        raiz = fromstring(xml)
    except Exception:  # noqa: BLE001 — XML torto de fornecedor não derruba a recontagem
        return []
    curto = lambda tag: tag.split("}")[-1]  # noqa: E731
    out: list[str] = []
    for det in raiz.iter():
        if curto(det.tag) != "det":
            continue
        imposto = next((c for c in det if curto(c.tag) == "imposto"), None)
        if imposto is None:
            out.append("")  # item É item mesmo sem grupo de imposto — 2 assim, medidos
            continue
        icms = next((c for c in imposto if curto(c.tag) == "ICMS"), None)
        if icms is None or not len(icms):
            out.append("")
            continue
        achou = ""
        for c in icms[0]:
            if curto(c.tag) in ("CST", "CSOSN"):
                achou = (c.text or "").strip()
                break
        out.append(achou)
    return out


async def main() -> int:  # noqa: PLR0912, PLR0915
    from sqlalchemy import text

    from core.database import async_session_factory
    from modules.fiscal.services import tributacao_nfe as tn

    falhas: list[str] = []
    # O serviço do fato pode não existir (é o que acontece quando este oráculo roda contra o
    # código de ANTES da frente). Nesse caso a falha é registrada e o resto continua: um oráculo
    # que só estoura no import não diz QUAL número está errado.
    try:
        from modules.fiscal.services import icms_entrada as ie
    except ImportError as exc:
        falhas.append(f"serviço do fato «como a mercadoria entrou» não existe: {exc}")
        ie = None
    if not hasattr(tn, "classificar_entrada"):
        falhas.append(
            "a régua não sabe classificar como a mercadoria entrou (tributacao_nfe.classificar_entrada "
            "ausente) — ela decide o CFOP de saída sem olhar a entrada"
        )
    async with async_session_factory() as db:
        from _telas import conferir_telas  # noqa: PLC0415 — irmão em scripts/orq

        falhas.extend(await conferir_telas(db, MODULO_DA_FRENTE, TELAS_DA_FRENTE))
        empresa = (
            await db.execute(
                text(
                    "SELECT cnpj, razao_social, regime_tributario, coalesce(inscricao_estadual,''), "
                    "codigo_municipio_ibge FROM empresas WHERE replace(replace(replace(cnpj,'.',''),'/',''),'-','') "
                    "= :c"
                ),
                {"c": "35710481000103"},
            )
        ).first()
        if not empresa:
            print("FALHOU: CONECTAMAIS ELETRONICA não está em `empresas` — sem emitente não há régua")
            print("TOTAL desvios AA5: 1")
            return 1
        emit = {
            "cnpj": empresa[0],
            "razao_social": empresa[1],
            "regime_tributario": empresa[2],
            "inscricao_estadual": empresa[3],
            "codigo_municipio_ibge": empresa[4],
        }

        # ───────────────────────────────── (d) a recontagem ─────────────────────────────────
        xmls = (
            await db.execute(
                text("SELECT xml_raw FROM nfe_entradas WHERE xml_raw IS NOT NULL AND length(xml_raw) > 500 ORDER BY id")
            )
        ).fetchall()
        csts: list[str] = []
        for (xml,) in xmls:
            csts.extend(_cst_icms_dos_itens(xml))
        itens_entrada = len(csts)
        itens_st = sum(1 for c in csts if c in _ST)
        if itens_entrada != ESPERADO_ITENS_ENTRADA:
            falhas.append(
                f"itens de NF-e de entrada: {itens_entrada}, medido no nascimento {ESPERADO_ITENS_ENTRADA}. "
                "Se chegaram notas novas isto é esperado — atualize a constante DE PROPÓSITO, olhando "
                "a contagem de ST junto."
            )
        if itens_st != ESPERADO_ITENS_ST:
            falhas.append(
                f"itens que entraram com ICMS já retido por ST: {itens_st}, medido no nascimento "
                f"{ESPERADO_ITENS_ST}. Este número manda na tributação de metade do catálogo — "
                "não pode mudar sem alguém saber."
            )

        # ───────────────── (e) a coluna existe e o fato está no catálogo ─────────────────
        sincronia = await ie.sincronizar(db) if ie else {"(serviço ausente)": 0}
        col = (
            await db.execute(
                text(
                    "SELECT count(*) FROM information_schema.columns WHERE table_name = 'fin_produtos' "
                    "AND column_name IN ('icms_entrada_cst','icms_entrada_fonte')"
                )
            )
        ).scalar() or 0
        if col != 2:
            falhas.append(
                f"`fin_produtos` tem {col} das 2 colunas do fato (icms_entrada_cst, icms_entrada_fonte) — "
                "sem elas a régua recusa TODA nota"
            )
        resumo = (
            await ie.resumo(db)
            if ie
            else {"fin_produtos": 0, "st": 0, "normal": 0, "sem_fonte": 0, "products": 0, "products_sem_fato": 0}
        )
        try:
            produtos = (
                await db.execute(
                    text(
                        "SELECT codigo, coalesce(ncm,''), icms_entrada_cst, coalesce(icms_entrada_fonte,'') "
                        "FROM fin_produtos ORDER BY codigo"
                    )
                )
            ).fetchall()
        except Exception as exc:  # noqa: BLE001 — coluna ausente é justamente o defeito
            await db.rollback()
            falhas.append(f"não dá para ler o fato no catálogo: {exc}")
            produtos = []
        if not produtos:
            falhas.append("`fin_produtos` está vazia — não dá para afirmar nada sobre o catálogo")
        sem_fonte_registrada = [c for c, _n, cst, f in produtos if cst and not f.strip()]
        if sem_fonte_registrada:
            falhas.append(
                f"{len(sem_fonte_registrada)} produto(s) com CST de entrada e SEM fonte escrita "
                f"(ex.: {sem_fonte_registrada[:3]}) — número fiscal sem de-onde-veio"
            )

        # ─────────── (a) os seis itens da nota real: 5405 / CST 060 / ICMS zero ───────────
        soma = Decimal("0.00")
        for desc, ncm, qtd, unit, total in NOTA_10026:
            r = tn.calcular_puro(
                emit,
                {
                    "codigo": f"NF10026-{ncm}",
                    "ncm": ncm,
                    "valor": unit,
                    "quantidade": qtd,
                    "origem": "0",
                    # o fato, como o catálogo o entregaria: a nota 10.026 é o documento que prova
                    "icms_entrada_cst": "60",
                    "icms_entrada_fonte": "NF-e 10.026 série 1, protocolo 113263811849419, 17/09/2026",
                },
                DEST_10026,
            )
            soma += Decimal(total)
            if r.get("cfop") != CFOP_10026:
                falhas.append(f"NF 10.026 «{desc[:28]}» (NCM {ncm}): CFOP {r.get('cfop')!r}, a nota real diz 5405")
            if r.get("cst_ou_csosn") != CST_10026:
                falhas.append(f"NF 10.026 «{desc[:28]}»: CST {r.get('cst_ou_csosn')!r}, a nota real diz 060")
            if r.get("valor") not in (0, 0.0):
                falhas.append(f"NF 10.026 «{desc[:28]}»: V.ICMS {r.get('valor')!r}, a nota real diz 0,00")
            if r.get("base") not in (0, 0.0):
                falhas.append(f"NF 10.026 «{desc[:28]}»: BC ICMS {r.get('base')!r}, a nota real diz 0,00")
            if r.get("aliquota") is not None:
                falhas.append(f"NF 10.026 «{desc[:28]}»: %ICMS {r.get('aliquota')!r}, a nota real diz 0,00")
            if r.get("bloqueios"):
                falhas.append(f"NF 10.026 «{desc[:28]}»: régua bloqueou uma nota que a SEFAZ já autorizou")
            if Decimal(unit) * qtd != Decimal(total):
                falhas.append(f"NF 10.026 «{desc[:28]}»: transcrição da DANFE não fecha ({unit} × {qtd} ≠ {total})")
        if soma != TOTAL_10026:
            falhas.append(f"soma dos 6 itens transcritos = {soma}, a DANFE diz {TOTAL_10026}")

        # ─── (b) nenhum produto que entrou com ST sai com ICMS cobrado — o catálogo inteiro ───
        com_st = com_normal = sem_tratamento = 0
        classificar = getattr(tn, "classificar_entrada", lambda _c: None)
        for codigo, ncm, cst, _fonte in produtos:
            situacao = classificar(cst)
            r = tn.calcular_puro(
                emit,
                {"codigo": codigo, "ncm": ncm, "valor": 100, "quantidade": 1, "origem": "0", "icms_entrada_cst": cst},
                DEST_10026,
            )
            if situacao == "st":
                com_st += 1
                if r.get("valor") not in (0, 0.0) or r.get("aliquota") is not None:
                    falhas.append(
                        f"produto {codigo} entrou com CST {cst} (ICMS já retido) e a régua cobrou "
                        f"ICMS de novo: {r.get('aliquota')!r}% = {r.get('valor')!r}"
                    )
                if r.get("cfop") != CFOP_10026 or r.get("cst_ou_csosn") != CST_10026:
                    falhas.append(
                        f"produto {codigo} (ST): saiu {r.get('cfop')}/{r.get('cst_ou_csosn')}, esperado 5405/60"
                    )
            elif situacao == "normal":
                com_normal += 1
                if r.get("cfop") != "5102" or r.get("cst_ou_csosn") != "00":
                    falhas.append(f"produto {codigo} (entrou tributado): saiu {r.get('cfop')}/{r.get('cst_ou_csosn')}")
            else:
                sem_tratamento += 1
                if r.get("cfop"):
                    falhas.append(
                        f"produto {codigo} tem CST de entrada {cst!r}, sem tratamento com fonte, e "
                        f"mesmo assim a régua escolheu CFOP {r['cfop']} — isso é chute"
                    )
        if com_st == 0 and produtos:
            falhas.append("nenhum produto do catálogo classificado como «entrou com ST» — a medição diz que há 43")

        # ───────────── (c) produto sem entrada conhecida não sai com CFOP chutado ─────────────
        r = tn.calcular_puro(
            emit,
            {"codigo": "PRODUTO-QUE-NINGUEM-REGISTROU", "ncm": "85444900", "valor": 895, "quantidade": 1},
            DEST_10026,
        )
        if r.get("cfop") or r.get("cst_ou_csosn") or r.get("aliquota") is not None:
            falhas.append(
                f"produto sem entrada conhecida saiu com CFOP {r.get('cfop')!r} / CST "
                f"{r.get('cst_ou_csosn')!r} / alíquota {r.get('aliquota')!r} — deveria recusar"
            )
        texto_recusa = " ".join(r.get("bloqueios") or [])
        if "Não sei como esta mercadoria entrou" not in texto_recusa:
            falhas.append("a recusa não diz o que está faltando — mensagem que não ensina não serve")
        if "PRODUTO-QUE-NINGUEM-REGISTROU" not in texto_recusa:
            falhas.append("a recusa não nomeia o produto — quem lê não sabe onde mexer")
        if "5405" not in texto_recusa or "5102" not in texto_recusa:
            falhas.append("a recusa não mostra as duas saídas possíveis — não ensina a decidir")

        # ───────────── (e continua) a tela existe e não tem régua própria ─────────────
        try:
            from modules.operacional.controllers.redesign_builders import _dgx_aa5_icms_st as aa5
        except ImportError as exc:
            falhas.append(f"tela «Como a mercadoria entrou (ICMS-ST)» não existe: {exc}")
            aa5 = None
        if aa5 is not None:
            telas = await aa5.telas(db)
            tela = telas.get("nfe-icms-entrada")
            if not tela:
                falhas.append("telas() não devolve 'nfe-icms-entrada'")
            elif len(tela.get("rows") or []) != len(produtos):
                falhas.append(
                    f"a tela mostra {len(tela.get('rows') or [])} produtos e o banco tem {len(produtos)} — "
                    "a tela filtrou por conta própria"
                )
            if not telas.get("nfe-icms-entrada-registro", {}).get("fields"):
                falhas.append("não há formulário para uma pessoa registrar o fato — a régua recusa e ninguém resolve")
            if resumo["st"] + resumo["normal"] + resumo["sem_fonte"] != resumo["fin_produtos"]:
                falhas.append("os três baldes do resumo não somam o total de produtos")

        # ───────────────────── fixtures desta frente: nenhuma deve sobrar ─────────────────────
        n = (
            await db.execute(text("SELECT count(*) FROM fin_produtos WHERE observacao LIKE '%FIXTURE DGX AA5%'"))
        ).scalar() or 0
        await db.rollback()
        if n:
            falhas.append(f"{n} fixture(s) 'FIXTURE DGX AA5' esquecida(s) em fin_produtos")

    print(f"itens de NF-e de entrada relidos: {itens_entrada} · com ICMS já retido por ST: {itens_st}")
    print(
        f"catálogo fiscal: {len(produtos)} produtos — {com_st} com ST · {com_normal} tributados · {sem_tratamento} sem fonte"
    )
    print(f"sincronização do fato: {sincronia}")
    print(f"products (Bling): {resumo['products']} — {resumo['products_sem_fato']} sem nenhuma NF-e de entrada nossa")
    print(f"NF-e 10.026 conferida item a item: {len(NOTA_10026)} itens, R$ {TOTAL_10026}")
    for f in falhas:
        print("FALHOU:", f)
    if falhas:
        print(f"TOTAL desvios AA5: {len(falhas)}")
        return 1
    print(
        "OK ICMS-ST na saída: os 6 itens da NF-e 10.026 saem 5405/060/ICMS zero; nenhum produto "
        "que entrou com ST é tributado de novo; produto sem entrada conhecida é recusado com "
        "mensagem que ensina; a recontagem dos itens de entrada bate."
    )
    print("TOTAL desvios AA5: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

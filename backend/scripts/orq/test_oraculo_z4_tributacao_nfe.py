"""Oráculo — a tributação da NF-e de mercadoria (frente DGX Z4, 24/09/2026).

**Por que existe.** A nota pode ser aceita pela SEFAZ e ainda assim estar errada em tributo — e
aí o problema aparece meses depois, com multa. O risco aqui não é a tela quebrar: é ela devolver
um NÚMERO CERTO DE FORMATO e ERRADO DE ORIGEM. O pré-mortem listou cinco jeitos de isso acontecer:
(a) uma alíquota plausível chutada sem norma; (b) a empresa do Simples saindo com CST de regime
normal (ou a do lucro real saindo com CSOSN) — é o erro que a SEFAZ ACEITA e o fisco autua;
(c) venda para a ZFM sem a desoneração e sem a mensagem fiscal, que é justamente a prova do
benefício; (d) a tela criando régua própria e divergindo do serviço; (e) uma combinação
empresa × operação devolvendo silêncio em vez de «sem fonte».

**O que afirma:**
  1. As 30 combinações (3 emitentes × 5 destinos × 2 operações) devolvem CFOP e CST/CSOSN — ou
     dizem explicitamente «sem fonte — decisão do contador». Nunca silêncio.
  2. Nenhuma alíquota sem `origem_regra`, e nenhuma LINHA do cálculo sem `norma` + `origem_regra`.
  3. A empresa do Simples nunca sai com CST de lucro real, e a do lucro real nunca sai com CSOSN.
     Conferido contra a tabela oficial de CST/CSOSN, recontada aqui (não importada do serviço).
  4. Venda para a ZFM com SUFRAMA traz `vICMSDeson` > 0, `motDesICMS` = 7 e a mensagem fiscal com
     as normas (Convênio ICM 65/88, DL 288/1967, Lei 10.996/2004, RIPI art. 84) e o número SUFRAMA.
  5. O simulador e o serviço dão o MESMO número — a tela não tem régua própria. Conferido lendo
     a tela montada e comparando célula a célula com o retorno do serviço.
  6. O regime e a IE vêm do BANCO (`empresas`), não de constante no código: recontados por SQL
     próprio deste oráculo.
  7. Nenhuma fixture 'FIXTURE DGX Z4' sobrou no banco.

**Estado medido no nascimento** (sandbox, 24/09/2026): serviço `tributacao_nfe` e tela
`nfe-tributacao-simulador` não existiam → VERMELHO em tudo. Nenhuma fixture foi criada por esta
frente: o cálculo é puro e as duas empresas já existem em `empresas` com dado real.

**Como roda** (container efêmero, PYTHONPATH=/app):
    python3 /app/scripts/orq/test_oraculo_z4_tributacao_nfe.py
Sai 0 = verde; 1 = vermelho.
"""

from __future__ import annotations

import asyncio
import sys

#: Tabela B do Ajuste SINIEF 07/2005 — recontada aqui de propósito. O oráculo confere a régua,
#: não a importa do serviço.
CST_REGIME_NORMAL = {"00", "10", "20", "30", "40", "41", "50", "51", "60", "70", "90"}
CSOSN_SIMPLES = {"101", "102", "103", "201", "202", "203", "300", "400", "500", "900"}

#: as normas que a mensagem da ZFM tem que carregar para a nota provar o benefício
NORMAS_ZFM = ("65/88", "288/1967", "10.996/2004", "7.212/2010")

CNPJ_ELETRONICA = "35.710.481/0001-03"
CNPJ_PATRIMONIAL = "66.014.833/0001-10"

DESTINOS = {
    "am_contribuinte": {"uf": "AM", "contribuinte": True, "suframa": None},
    "am_nao_contribuinte": {"uf": "AM", "contribuinte": False, "suframa": None},
    "sp_contribuinte": {"uf": "SP", "contribuinte": True, "suframa": None},
    "sp_nao_contribuinte": {"uf": "SP", "contribuinte": False, "suframa": None},
    "zfm_suframa": {"uf": "AM", "contribuinte": True, "suframa": "210140500"},
}
#: AA5 (24/09/2026): a régua passou a depender de COMO A MERCADORIA ENTROU. Este produto de
#: teste declara que entrou tributada (CST 00 na nota do fornecedor) — é o caso que este oráculo
#: sempre mediu. O caso «entrou com ICMS-ST» e o caso «não se sabe» são do oráculo da AA5
#: (`test_oraculo_aa5_icms_st.py`), que é quem afirma a regra nova.
PRODUTO = {"ncm": "85311000", "valor": 1000, "quantidade": 1, "origem": "0", "icms_entrada_cst": "00"}


async def main() -> int:
    from sqlalchemy import text

    from core.database import async_session_factory
    from modules.fiscal.services import tributacao_nfe as tn

    falhas: list[str] = []
    combinacoes = 0

    async with async_session_factory() as db:
        # ── (6) o regime e a IE vêm do BANCO. SQL próprio, sem passar pelo serviço.
        linhas = (
            await db.execute(
                text(
                    "SELECT cnpj, regime_tributario, coalesce(inscricao_estadual,''), "
                    "coalesce(inscricao_suframa,''), codigo_municipio_ibge "
                    "FROM empresas WHERE status='ativa' ORDER BY cnpj"
                )
            )
        ).fetchall()
        por_cnpj = {r[0]: r for r in linhas}
        if CNPJ_ELETRONICA not in por_cnpj or CNPJ_PATRIMONIAL not in por_cnpj:
            falhas.append(f"empresas ativas no banco: {sorted(por_cnpj)} — faltam os dois CNPJs da casa")
        for cnpj, esperado in ((CNPJ_ELETRONICA, "lucro_real"), (CNPJ_PATRIMONIAL, "simples_nacional")):
            r = por_cnpj.get(cnpj)
            if r and r[1] != esperado:
                falhas.append(f"{cnpj}: empresas.regime_tributario = {r[1]!r}, esperado {esperado!r}")
            if r and not str(r[4] or "").startswith("13"):
                falhas.append(f"{cnpj}: codigo_municipio_ibge {r[4]!r} não é do Amazonas (cUF 13)")

        # ── (1,2,3,4) as combinações, pelo serviço, contra o banco
        emitentes = [(CNPJ_ELETRONICA, "3"), (CNPJ_PATRIMONIAL, "1")]
        guardado: dict[tuple, dict] = {}
        for cnpj, crt_esperado in emitentes:
            for dnome, dest in DESTINOS.items():
                for op in ("revenda", "producao"):
                    combinacoes += 1
                    tag = f"{cnpj}/{dnome}/{op}"
                    try:
                        r = await tn.calcular(db, cnpj, PRODUTO, dest, op)
                    except Exception as exc:  # noqa: BLE001
                        falhas.append(f"{tag}: calcular() levantou {exc!r}")
                        continue
                    guardado[(cnpj, dnome, op)] = r

                    # (1) CFOP e CST/CSOSN, ou «sem fonte» explícito
                    if not r.get("cfop"):
                        falhas.append(f"{tag}: sem CFOP")
                    if not r.get("cst_ou_csosn") and tn.SEM_FONTE not in (r.get("origem_regra") or ""):
                        falhas.append(f"{tag}: sem CST/CSOSN e sem dizer «{tn.SEM_FONTE}»")

                    # (2) nenhuma alíquota sem origem, nenhuma linha sem norma
                    if r.get("aliquota") is not None and not (r.get("origem_regra") or "").strip():
                        falhas.append(f"{tag}: alíquota {r['aliquota']} SEM origem_regra")
                    for ln in r.get("linhas") or []:
                        if not (ln.get("norma") or "").strip() or not (ln.get("origem_regra") or "").strip():
                            falhas.append(f"{tag}: linha «{ln.get('rotulo')}» sem norma/origem")

                    # (3) o erro que a SEFAZ aceita e o fisco autua
                    codigo = str(r.get("cst_ou_csosn") or "")
                    if r.get("crt") != crt_esperado:
                        falhas.append(f"{tag}: CRT {r.get('crt')!r}, esperado {crt_esperado!r}")
                    if crt_esperado == "1" and codigo and codigo not in CSOSN_SIMPLES:
                        falhas.append(f"{tag}: empresa do SIMPLES saiu com {codigo!r} — não é CSOSN")
                    if crt_esperado == "3" and codigo and codigo not in CST_REGIME_NORMAL:
                        falhas.append(f"{tag}: empresa do LUCRO REAL saiu com {codigo!r} — não é CST")
                    if crt_esperado == "1" and r.get("aliquota") is not None:
                        falhas.append(
                            f"{tag}: Simples destacou alíquota de ICMS {r['aliquota']} — o ICMS está no "
                            "DAS (LC 123/2006, art. 18)"
                        )

                    # a IE do banco manda no bloqueio: sem IE, a NF-e 55 não pode existir
                    ie_banco = (por_cnpj.get(cnpj) or ("", "", "", "", ""))[2]
                    tem_bloqueio_ie = any("Inscrição Estadual" in x for x in r.get("bloqueios") or [])
                    if not ie_banco.strip() and not tem_bloqueio_ie:
                        falhas.append(f"{tag}: empresa sem IE no banco e a nota NÃO foi bloqueada")
                    if ie_banco.strip() and tem_bloqueio_ie:
                        falhas.append(f"{tag}: empresa TEM IE ({ie_banco}) e mesmo assim foi bloqueada")

        # (4) ZFM: o emitente da casa está DENTRO da ZFM — não pode desonerar
        for cnpj, _ in emitentes:
            r = guardado.get((cnpj, "zfm_suframa", "revenda")) or {}
            if r.get("destino") == "zfm_entrante":
                falhas.append(
                    f"{cnpj}: emitente de Manaus classificado como venda PARA a ZFM — o Convênio ICM "
                    "65/88 é para quem vende de fora (achado da frente Z4)"
                )
            if r.get("deson"):
                falhas.append(f"{cnpj}: desoneração de ZFM numa operação interna do Amazonas")

        # (4) e o caminho que DE FATO desonera — emitente fora do AM, função pura
        z = tn.calcular_puro(tn.EMPRESAS_DEMO["_de_fora"], PRODUTO, DESTINOS["zfm_suframa"])
        if z.get("destino") != "zfm_entrante":
            falhas.append("emitente fora do AM + SUFRAMA não foi classificado como venda para a ZFM")
        deson = z.get("deson") or {}
        if not deson.get("vICMSDeson"):
            falhas.append("venda para a ZFM sem vICMSDeson")
        if deson.get("motDesICMS") != "7":
            falhas.append(f"motDesICMS = {deson.get('motDesICMS')!r}, esperado '7' (SUFRAMA)")
        msg = z.get("mensagem_fiscal") or ""
        for n in NORMAS_ZFM:
            if n not in msg:
                falhas.append(f"mensagem fiscal da ZFM não cita {n}")
        if "210140500" not in msg:
            falhas.append("mensagem fiscal da ZFM não traz a inscrição SUFRAMA do destinatário")
        if z.get("cst_ou_csosn") != "40":
            falhas.append(f"venda para a ZFM com CST {z.get('cst_ou_csosn')!r}, esperado '40' (isenta)")

        # ── (5) o simulador e o serviço dão o MESMO número
        try:
            from modules.operacional.controllers.redesign_builders import _dgx_z4_tributacao as z4
        except ImportError as exc:
            falhas.append(f"tela do simulador não existe: {exc}")
            z4 = None
        if z4 is not None:
            telas = await z4.telas(db)
            scr = telas.get("nfe-tributacao-simulador")
            if not scr:
                falhas.append("telas() não devolve 'nfe-tributacao-simulador'")
            elif scr.get("type") != "form":
                falhas.append(f"simulador não é form: type={scr.get('type')!r}")
            # a régua: a tela recalcula via o MESMO serviço, célula a célula
            for cnpj, _ in emitentes:
                for dnome, dest in DESTINOS.items():
                    svc = guardado.get((cnpj, dnome, "revenda")) or {}
                    tela = await z4.simular(
                        db,
                        {
                            "empresa_cnpj": cnpj,
                            "uf": dest["uf"],
                            "contribuinte": "sim" if dest["contribuinte"] else "nao",
                            "suframa": dest["suframa"] or "",
                            "operacao": "revenda",
                            "ncm": PRODUTO["ncm"],
                            "valor": PRODUTO["valor"],
                            "quantidade": PRODUTO["quantidade"],
                            "origem": PRODUTO["origem"],
                            "icms_entrada_cst": PRODUTO["icms_entrada_cst"],  # AA5
                        },
                    )
                    for campo in ("cfop", "cst_ou_csosn", "base", "aliquota", "valor", "origem_regra"):
                        if tela.get(campo) != svc.get(campo):
                            falhas.append(
                                f"{cnpj}/{dnome}: a TELA diz {campo}={tela.get(campo)!r} e o SERVIÇO diz "
                                f"{svc.get(campo)!r} — a tela criou régua própria"
                            )
                    if len(tela.get("linhas") or []) != len(svc.get("linhas") or []):
                        falhas.append(f"{cnpj}/{dnome}: tela mostra número de linhas diferente do serviço")
                    if (tela.get("mensagem_fiscal") or "") != (svc.get("mensagem_fiscal") or ""):
                        falhas.append(f"{cnpj}/{dnome}: mensagem fiscal da tela difere da do serviço")

        # ── (7) nenhuma fixture desta frente sobrou
        for tabela, coluna in (("empresas", "observacoes"), ("nfe_compras_estoque", "descricao")):
            try:
                n = (
                    await db.execute(text(f"SELECT count(*) FROM {tabela} WHERE {coluna} LIKE '%FIXTURE DGX Z4%'"))
                ).scalar() or 0
            except Exception:  # noqa: BLE001 — tabela ausente não é fixture esquecida
                await db.rollback()
                continue
            if n:
                falhas.append(f"{n} fixture(s) 'FIXTURE DGX Z4' esquecida(s) em {tabela}.{coluna}")

    print(f"combinações empresa × destino × operação conferidas: {combinacoes}")
    print(f"empresas ativas lidas do banco: {len(por_cnpj)}")
    for f in falhas:
        print("FALHOU:", f)
    if falhas:
        raise AssertionError(f"{len(falhas)} desvio(s) na tributação da NF-e")
    print(
        "OK tributação NF-e: toda combinação com CFOP e CST/CSOSN ou «sem fonte» declarado; "
        "nenhuma alíquota sem origem; Simples com CSOSN e lucro real com CST; ZFM com desoneração "
        "e mensagem fiscal; simulador e serviço com o mesmo número."
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print(e)
        sys.exit(1)

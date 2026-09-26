"""C4 — a ECD gerada diz a verdade do razão, e recusa o que não pode afirmar.

Nasceu em 25/09/2026, do loop de contabilidade, quando o dono decidiu rescindir com a
contabilidade terceirizada. A ECD é o bloqueio nº 1: sem ela não há livro diário oficial, e
sem livro diário a escrituração não faz prova perante a Receita.

O gerador de 831 linhas já existia e RODAVA — produzia 17.899 registros a partir do razão
real. O que ele produzia é que não servia:

 · A natureza de cada conta era deduzida do PRIMEIRO DÍGITO do código, com um mapa que
   descrevia o plano APOSENTADO em 13/08/2026 («3=Receita, 4=Despesa»). No plano vigente 3 é
   Patrimônio Líquido, 4 é Receita e 5 é Despesa. Resultado medido: a receita do exercício
   inteiro, R$ 1.581.873,06, saía no I350 como **0 D**, e o Capital Social aparecia como
   conta de resultado.
 · Os encerradores de bloco contavam CHAVES DISTINTAS do dicionário, não linhas:
   `|I990|10|` num bloco de 17.862 linhas.
 · O registro 0000 saía sem UF, IE, código de município e inscrição municipal — não por
   falta de cadastro (a tabela `empresas` tem os quatro), mas porque o construtor do manager
   não os aceitava.
 · O `empresa_id` do razão era uma CONSTANTE no código: a Patrimonial nunca teve como gerar
   a sua ECD, e um singleton de módulo prendia o arquivo ao CNPJ da primeira chamada.
 · O I150 saía um por conta, carregando os campos que pertencem ao I155 e **sem COD_CTA** —
   não havia como saber de que conta era cada saldo. O I155 nunca era emitido.
 · O bloco J tinha J001/J005/J900/J930/J990 e ZERO J100, ZERO J150.

O QUE ELE AFIRMA

 (a) **A natureza vem do plano.** Toda conta no I050 traz a NaturezaConta correspondente ao
     seu `account_type` em `fin_accounting_accounts`. Recontado aqui contra o banco, não
     lido do que o gerador escreveu.

 (b) **A receita do exercício aparece, e com o valor do razão.** O I350 da conta de receita
     tem de trazer o total credor do período, com indicador C.

 (c) **Os encerradores contam linhas.** 0990, I990, J990 e K990 conferem com a contagem real
     de linhas de cada bloco, e o 9999 com o total do arquivo.

 (d) **O 0000 leva o cadastro que existe.** UF e código de município preenchidos; inscrição
     municipal preenchida. (A IE pode ser legitimamente vazia — a Patrimonial só tem
     inscrição municipal —, então ela não é exigida aqui.)

 (e) **I150 só com datas, I155 por conta.** Um I150 no período e um I155 por conta com saldo,
     cada um com seu COD_CTA.

 (f) **Cada CNPJ gera a SUA ECD.** O arquivo da Patrimonial não pode conter lançamento da
     Eletrônica. Provado pela contagem: as duas gerações têm totais diferentes e o 0000 traz
     o CNPJ certo.

 (g) **J100 não sai quando o balanço não pode ser afirmado.** Se o balanço não fechar OU o
     ativo total for negativo, o J100 é omitido e o motivo fica declarado. Hoje a Eletrônica
     cai nessa recusa — ativo de −R$ 244.547,72, porque as 89 contas do plano estão com saldo
     de abertura ZERO. Publicar um balanço assim seria pior que não publicar.

VERMELHO ANTES: com o gerador de até 25/09/2026 restaurado do git, 12 desvios —
(a) 4 contas com natureza errada (3.1.1.01 e 3.9.9.01 saíam 04 no lugar de 03; 4.1.1.01 e
4.9.9.01 saíam 05 no lugar de 04), (b) receita R$ 0,00 D contra R$ 1.581.873,06 no razão,
(c) `I990` declarando 10 num bloco de 17.863 linhas e nenhum K990, (d) UF/COD_MUN/IM
vazios, (e) 27 registros I150 e nenhum I155, (f) o service sem `empresa_slug`, e (g) o
J100 omitido sem motivo declarado.
"""

from __future__ import annotations

import collections
import sys

#: Tradução usada pelo gerador — repetida aqui de propósito: a régua não pergunta ao
#: medido qual é a medida.
NATUREZA_ESPERADA = {
    "ASSET": "01",
    "LIABILITY": "02",
    "EQUITY": "03",
    "REVENUE": "04",
    "EXPENSE": "05",
    "COST": "05",
}


def _registros(linhas: list[str]) -> collections.Counter:
    return collections.Counter(ln.split("|")[1] for ln in linhas if ln.startswith("|"))


def main() -> int:
    import psycopg2

    from modules.government_integrations.services.sped_contabil_service import SPEDContabilService

    falhas: list[str] = []
    medidas: list[str] = []

    svc = SPEDContabilService()
    dsn = svc._db_url()
    if not dsn:
        print("RECUSO: sem DATABASE_URL — a ECD NÃO foi medida; isto não é um verde")
        return 2

    resultado = svc.gerar_arquivo(2026, "2026-01-01", "2026-12-31")
    linhas = resultado["conteudo"].split("\r\n")
    regs = _registros(linhas)
    medidas.append(f"ECD Eletrônica: {len(linhas)} linhas, {resultado['total_lancamentos']} lanç.")

    conn = psycopg2.connect(dsn)
    try:
        cur = conn.cursor()
        cur.execute("SELECT code, upper(coalesce(account_type::text,'')) FROM fin_accounting_accounts")
        plano = dict(cur.fetchall())

        # (a) natureza de cada I050 recontada contra o plano
        erradas = []
        for ln in linhas:
            if not ln.startswith("|I050|"):
                continue
            p = ln.split("|")
            cod_nat, conta = p[3], p[6]
            esperada = NATUREZA_ESPERADA.get(plano.get(conta, ""))
            if esperada and cod_nat != esperada:
                erradas.append(f"{conta}: {cod_nat} (plano diz {esperada})")
        if erradas:
            falhas.append(f"(a) {len(erradas)} conta(s) com natureza errada no I050: {erradas[:4]}")
        medidas.append(f"I050 conferidos: {regs.get('I050', 0)}")

        # (b) a receita do exercício aparece com o valor do razão
        cur.execute(
            """
            WITH mov AS (
                SELECT conta_credito AS conta, valor AS v FROM accounting_entries
                 WHERE status='confirmado' AND empresa_id = %s::uuid
                   AND substr(coalesce(periodo_competencia,''),1,4) = '2026'
                UNION ALL
                SELECT conta_debito, -valor FROM accounting_entries
                 WHERE status='confirmado' AND empresa_id = %s::uuid
                   AND substr(coalesce(periodo_competencia,''),1,4) = '2026'
            )
            SELECT round(sum(v), 2) FROM mov WHERE conta = '4.1.1.01'
            """,
            (svc._empresa_id, svc._empresa_id),
        )
        receita_razao = float(cur.fetchone()[0] or 0)
    finally:
        conn.close()

    i350 = {ln.split("|")[3]: ln.split("|") for ln in linhas if ln.startswith("|I350|")}
    linha_rec = i350.get("4.1.1.01")
    if not linha_rec:
        falhas.append("(b) a conta de receita 4.1.1.01 não tem I350 — a receita do ano sumiu")
    else:
        valor, ind = float(linha_rec[4] or 0), linha_rec[5]
        if ind != "C":
            falhas.append(f"(b) receita saiu com indicador {ind}, deveria ser C")
        if abs(valor - receita_razao) > 0.02:
            falhas.append(
                f"(b) receita no I350 é R$ {valor:,.2f} e o razão tem R$ {receita_razao:,.2f}"
            )
        medidas.append(f"receita no I350: R$ {valor:,.2f} {ind}")

    # (c) encerradores contam linhas
    for reg, prefixo in [("0990", "0"), ("I990", "I"), ("J990", "J"), ("K990", "K")]:
        ln = next((x for x in linhas if x.startswith(f"|{reg}|")), None)
        if not ln:
            falhas.append(f"(c) o arquivo não tem {reg} — bloco sem encerramento")
            continue
        declarado = int(ln.split("|")[2] or 0)
        contado = sum(v for k, v in regs.items() if k.startswith(prefixo))
        if declarado != contado:
            falhas.append(f"(c) {reg} declara {declarado} e o bloco tem {contado} linha(s)")
    ln9999 = next((x for x in linhas if x.startswith("|9999|")), None)
    if not ln9999 or int(ln9999.split("|")[2] or 0) != len(linhas):
        falhas.append(
            f"(c) 9999 declara {ln9999.split('|')[2] if ln9999 else '—'} e o arquivo tem "
            f"{len(linhas)} linha(s)"
        )

    # (d) cadastro no 0000
    p0 = linhas[0].split("|")
    for idx, nome in [(7, "UF"), (9, "COD_MUN"), (10, "IM")]:
        if not (p0[idx] or "").strip():
            falhas.append(f"(d) registro 0000 sem {nome} — o dado existe na tabela `empresas`")
    medidas.append(f"0000: UF={p0[7]} MUN={p0[9]} IM={p0[10]}")

    # (e) I150 só com datas, I155 por conta
    i150 = [ln for ln in linhas if ln.startswith("|I150|")]
    if len(i150) != 1:
        falhas.append(f"(e) há {len(i150)} registros I150; o leiaute pede um por período")
    elif len(i150[0].split("|")) != 5:  # '', I150, DT_INI, DT_FIN, ''
        falhas.append(f"(e) o I150 carrega campos que pertencem ao I155: {i150[0]}")
    if not regs.get("I155"):
        falhas.append("(e) nenhum I155 — os saldos por conta não existem no arquivo")
    else:
        sem_conta = [ln for ln in linhas if ln.startswith("|I155|") and not ln.split("|")[2].strip()]
        if sem_conta:
            falhas.append(f"(e) {len(sem_conta)} I155 sem COD_CTA")
    medidas.append(f"I150={len(i150)} I155={regs.get('I155', 0)}")

    # (f) cada CNPJ gera a sua
    try:
        svc_pat = SPEDContabilService(empresa_slug="conecta_patrimonial")
    except TypeError:
        svc_pat = None
        falhas.append(
            "(f) o service não aceita `empresa_slug` — a ECD é por CNPJ e a segunda empresa "
            "não tem como gerar a dela"
        )
    if svc_pat is None:
        pass
    elif svc_pat.cnpj == svc.cnpj:
        falhas.append("(f) o slug não mudou o CNPJ — as duas empresas gerariam o mesmo arquivo")
    elif not svc_pat._empresa_id:
        falhas.append(f"(f) empresa_id não resolvido para o CNPJ {svc_pat.cnpj}")
    else:
        r_pat = svc_pat.gerar_arquivo(2026, "2026-01-01", "2026-12-31")
        l_pat = r_pat["conteudo"].split("\r\n")
        if svc_pat.cnpj not in l_pat[0]:
            falhas.append("(f) o 0000 da Patrimonial não traz o CNPJ dela")
        if r_pat["total_lancamentos"] == resultado["total_lancamentos"]:
            falhas.append(
                "(f) as duas empresas geraram o MESMO número de lançamentos — o razão não "
                "está sendo separado por CNPJ"
            )
        medidas.append(
            f"Patrimonial: {r_pat['total_lancamentos']} lanç. contra "
            f"{resultado['total_lancamentos']} da Eletrônica"
        )

    # (g) J100 só quando se pode afirmar o balanço
    demo = (resultado.get("veracidade") or {}).get("demonstrativos_bloco_j") or {}
    tem_j100 = regs.get("J100", 0) > 0
    if not demo.get("balanco") and tem_j100:
        falhas.append("(g) o J100 foi emitido mesmo com o balanço recusado")
    if demo.get("balanco") and not tem_j100:
        falhas.append("(g) o balanço foi afirmado e o J100 não saiu")
    if not demo.get("balanco") and not str(demo.get("motivo") or "").strip():
        falhas.append("(g) o J100 foi omitido sem motivo declarado — omissão silenciosa")
    medidas.append(f"J100={regs.get('J100', 0)} J150={regs.get('J150', 0)}")

    # ── (h) o J930 tem DONO, ou não sai ──────────────────────────────────────────────
    # A ECD é assinada por contabilista com CRC ativo e nenhum software substitui isso.
    # Até 26/09/2026 o J930 saía com TODOS os campos em branco e o literal «CONTADOR» no
    # meio — registro oco emitido «para o bloco não faltar», que faz o arquivo parecer
    # completo e ser recusado. É o mesmo defeito do gerador da EFD ICMS/IPI, que declarava
    # nota de serviço como mercadoria pelo mesmo motivo.
    from modules.government_integrations.core.sped_contabil import (  # noqa: E402, PLC0415
        Signatario,
    )

    vazio = Signatario(nome="", cpf="", qualificacao="900")
    sem_crc = Signatario(nome="FULANO", cpf="123.456.789-09", qualificacao="900")
    com_crc = Signatario(nome="FULANO", cpf="123.456.789-09", qualificacao="900",
                         crc="AM-012345/O-1", uf_crc="AM")
    socio = Signatario(nome="DONO", cpf="987.654.321-00", qualificacao="205")
    for rot, sig, esperado in (
        ("signatário vazio", vazio, False),
        ("contabilista SEM CRC", sem_crc, False),
        ("contabilista com CRC", com_crc, True),
        ("sócio (não precisa de CRC)", socio, True),
    ):
        if sig.completo is not esperado:
            falhas.append(f"(h) {rot}: completo={sig.completo}, esperado {esperado}")
    # a UF não pode ir duas vezes, e o sequencial não pode ser cortado
    if com_crc.num_seq_crc != "012345/O-1":
        falhas.append(f"(h) NUM_SEQ_CRC saiu «{com_crc.num_seq_crc}» — a UF tem campo próprio "
                      "e cortar o sequencial em silêncio é como nasce arquivo recusado")

    linhas_j930 = [x for x in linhas if x.startswith("|J930|")]
    for ln in linhas_j930:
        campos = ln.split("|")
        if not campos[2].strip() or not campos[3].strip():
            falhas.append(f"(h) J930 emitido sem nome ou sem CPF: {ln[:60]}")
    medidas.append(f"J930: {len(linhas_j930)} signatário(s) no arquivo")

    print(" · ".join(medidas))
    if not demo.get("balanco"):
        print(f"NOTA (não é falha): J100 recusado — {str(demo.get('motivo'))[:150]}")
    for f in falhas:
        print("FALHOU:", f)
    if falhas:
        raise AssertionError(f"{len(falhas)} desvio(s) na ECD")
    print(
        "OK ECD: natureza vinda do plano, receita presente com o valor do razão, "
        "encerradores contando linhas, cadastro no 0000, I150/I155 no lugar certo, "
        "um arquivo por CNPJ e J100 só quando o balanço se sustenta"
    )
    print(f"TOTAL desvios C4: {len(falhas)}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, "/app")
    try:
        sys.exit(main())
    except AssertionError as e:
        print(e)
        print("TOTAL desvios C4: >0")
        sys.exit(1)

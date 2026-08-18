"""Parcelamento que chega pelo Onvio também entra em `fiscal_parcelamentos`.

O buraco, medido em 18/08/2026: a casa paga **seis parcelamentos mensais** e o módulo fiscal
enxergava dois. Todos na Eletrônica (35.710.481/0001-03):

    ISSQN 100x (SEMEF 41613005/2026)   parcela  3/100    R$   367,92   venc 03/08/2026
    ISSQN  30x (SEMEF 41577140/2026)   parcela  6/30     R$   285,01   venc 24/07/2026
    Dívida Ativa 1 (SISPAR 009523101)  parcela 31/145    R$ 1.050,33   venc 31/07/2026  ✓
    Dívida Ativa 2 (SISPAR 014020428)  parcela 10/145    R$   260,60   venc 31/07/2026  ✓
    Dívida Ativa 3 (SISPAR 016215688)  parcela  2/145    R$ 1.301,40   venc 31/07/2026
    Demais Débitos (SISPAR 016215689)  parcela  2/60     R$ 4.252,69   venc 31/07/2026

Os dois com ✓ já estavam cadastrados. Os outros quatro — **≈ R$ 6.207 por mês** — não
existiam em lugar nenhum do sistema. Perder parcela não é multa de mora: **rescinde o
acordo**, o saldo todo vence de uma vez e a certidão vira positiva.

A causa é a mesma de `baixa_por_recibo_onvio`: a regra existia (`_upsert_parcelamento`) e o
gatilho não. `sync_guias_drive` só olha a pasta do **Drive**, e esses documentos chegam pelo
**Onvio**. O parser federal já lê os quatro DAS de dívida ativa com o SISPAR certo — testado,
não suposto. Só o DAM municipal da SEMEF ele não sabe ler, e é a única coisa nova aqui.

⚠️ **`valor_total` fica NULL nos municipais de propósito.** O DAM traz `3/100` e o valor da
parcela, mas NÃO traz o total do acordo — e cada parcela vem com juros próprios, então
`367,92 × 100` seria um número inventado num campo que diz "total". Quem precisar do saldo
consulta o processo de quitação, que está gravado no `numero_acordo`.

⚠️ DAM emitido prova que a parcela foi EXIGIDA, não paga. `parcelas_pagas` não é tocado aqui.

Roda:
    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 -c \
      "from modules.fiscal_contabil.obrigacoes.parcelamentos_onvio import sincronizar; print(sincronizar())"
"""

from __future__ import annotations

import calendar
import json
import logging
import os
import re
from datetime import date, datetime

from sqlalchemy import text

logger = logging.getLogger(__name__)

#: Documento de parcelamento no acervo do Onvio. A categoria sozinha não basta: os dois DAMs
#: do ISSQN são classificados como `guia_issqn` (são guia de ISSQN mesmo — de parcelamento),
#: então o nome entra na busca. `PARC ` com espaço e não `PARC%` para não pegar "PARCEIRO".
_SQL_DOCS = """
    SELECT nome_arquivo, caminho_local
      FROM onvio_documents
     WHERE caminho_local IS NOT NULL AND caminho_local <> ''
       AND (categoria LIKE 'parcelamento%'
            OR nome_arquivo ILIKE 'PARC %'
            OR nome_arquivo ILIKE 'PARCELA %'
            OR nome_arquivo ILIKE '%PARCELAMENTO%')
     ORDER BY nome_arquivo
"""

#: "PROCESSO DE QUITAÇÃO: 41613005/2026" — a chave do acordo municipal. Sem ela o DAM é uma
#: guia comum de ISSQN e NÃO vira parcelamento; é esta linha que separa os dois casos.
_RE_PROCESSO = re.compile(r"PROCESSO\s+DE\s+QUITA[ÇC][ÃA]O[:\s]*(\d+/\d{4})", re.I)

#: "3/100" logo depois do CMC, na faixa "Tributos Referência Vencimento" do DAM da SEMEF.
#:
#: `(?!/)` no fim é o que separa parcela de DATA: em `03/08/2026` o par "03/08" satisfaz
#: `(?!\d)` — o caractere seguinte é uma barra, não um dígito — e passaria por parcela 3/8.
#: Hoje o número da parcela vem antes da data no DAM e o primeiro match acerta, mas isso é
#: ordem do layout, não regra; bastaria a data de emissão subir para o documento inteiro ser
#: descartado calado. Barra depois do par = data, nunca parcela.
_RE_PARCELA = re.compile(r"(?<!\d)(\d{1,3})/(\d{1,3})(?!\d)(?!/)")

#: "Total: 367,92 R$" — o DAM põe a moeda DEPOIS do número.
_RE_TOTAL = re.compile(r"Total[:\s]*([\d.]+,\d{2})\s*R\$", re.I)

_RE_VENC = re.compile(r"(\d{2}/\d{2}/\d{4})")
_RE_CNPJ = re.compile(r"(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})")


def _dec(s: str | None) -> float | None:
    """'1.301,40' → 1301.4 — formato brasileiro, que é como o emissor escreve."""
    if not s:
        return None
    try:
        return float(s.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def _texto(caminho: str) -> str:
    import fitz

    doc = fitz.open(caminho)
    try:
        return "\n".join(p.get_text() for p in doc)
    finally:
        doc.close()


def ler_dam_municipal(texto: str) -> dict | None:
    """DAM da SEMEF de PARCELAMENTO → campos do acordo. `None` se não for parcelamento.

    Exige as três coisas juntas — processo, parcela e valor. Faltando uma, devolve None em
    vez de completar com palpite: DAM meio lido vira acordo fantasma no painel.
    """
    proc = _RE_PROCESSO.search(texto)
    if not proc:
        return None
    total = _RE_TOTAL.search(texto)
    if not total:
        return None
    valor = _dec(total.group(1))
    if not valor:
        return None

    # Primeiro par PLAUSÍVEL, não o primeiro par. "1/2026-2" é competência e 1/1 é guia
    # avulsa; nenhum dos dois é acordo. Varrer em vez de olhar só o primeiro evita que um
    # par espúrio no começo do texto derrube o documento inteiro.
    atual = quantas = None
    depois = ""
    for m in _RE_PARCELA.finditer(texto):
        a, q = int(m.group(1)), int(m.group(2))
        if 1 <= a <= q and q > 1:
            atual, quantas, depois = a, q, texto[m.end():]
            break
    if atual is None:
        return None

    # O vencimento vem COLADO na parcela ("3/100 03/08/2026"), sob o rótulo "Vencimento".
    # Procurar a partir dali e não no texto todo: o DAM também traz a data de abertura da
    # empresa (05/12/2019) e a de emissão, e "primeira data plausível" pegaria a errada
    # conforme o layout mudasse de ordem.
    venc = None
    m_venc = _RE_VENC.search(depois)
    if m_venc:
        try:
            venc = datetime.strptime(m_venc.group(1), "%d/%m/%Y").date()
        except ValueError:
            venc = None

    cnpj = _RE_CNPJ.search(texto)
    return {
        "processo": proc.group(1),
        "parcela_atual": atual,
        "num_parcelas": quantas,
        "valor": valor,
        "vencimento": venc,
        "cnpj": cnpj.group(1) if cnpj else None,
    }


def _upsert_municipal(db, dados: dict, arquivo: str) -> str:
    """Grava o acordo municipal, chaveado pelo processo de quitação."""
    numero = f"SEMEF {dados['processo']}"
    row = db.execute(text(
        "SELECT id, observacao FROM fiscal_parcelamentos WHERE numero_acordo=:n LIMIT 1"),
        {"n": numero}).first()

    conhecidas: set[str] = set()
    if row and row[1] and row[1].strip().startswith("{"):
        try:
            conhecidas = set(json.loads(row[1]).get("parcelas_vistas", []))
        except (ValueError, TypeError):
            conhecidas = set()
    conhecidas.add(f"{dados['parcela_atual']}/{dados['num_parcelas']}")

    corrente = (f"{dados['vencimento'].month:02d}/{dados['vencimento'].year}"
                if dados["vencimento"] else None)
    if row and not corrente:
        try:
            corrente = json.loads(row[1] or "{}").get("competencia_corrente")
        except (ValueError, TypeError):
            corrente = None

    obs = json.dumps({
        "nota": "Parcelamento de ISSQN — SEMEF/Prefeitura de Manaus, Lei 3537/2025. "
                "valor_total NÃO consta do DAM (cada parcela tem juros próprios) e por isso "
                "fica nulo; o saldo se consulta pelo processo de quitação.",
        "processo_quitacao": dados["processo"],
        "competencia_corrente": corrente,
        "cnpj": dados["cnpj"],
        "parcela_valor_ultimo_dam": dados["valor"],
        "parcelas_vistas": sorted(conhecidas, key=lambda p: int(p.split("/")[0])),
        "ultimo_arquivo": arquivo,
        "sync_em": datetime.utcnow().isoformat(),
    }, ensure_ascii=False)

    dia = dados["vencimento"].day if dados["vencimento"] else 10
    if row:
        db.execute(text(
            "UPDATE fiscal_parcelamentos SET parcela_valor=:pv, num_parcelas=:np, "
            "dia_vencimento=:dv, status='ativo', observacao=:obs, fonte='onvio_semef', "
            "updated_at=now() WHERE id=:id"),
            {"pv": dados["valor"], "np": dados["num_parcelas"], "dv": dia,
             "obs": obs, "id": row[0]})
        return "atualizado"

    comp = (f"{dados['vencimento'].month:02d}/{dados['vencimento'].year}"
            if dados["vencimento"] else "")
    db.execute(text(
        "INSERT INTO fiscal_parcelamentos (orgao,numero_acordo,descricao,valor_total,"
        "num_parcelas,parcela_valor,dia_vencimento,competencia_inicio,parcelas_pagas,status,"
        "observacao,fonte,created_by,created_at,updated_at) "
        "VALUES ('SEMEF',:na,:desc,NULL,:np,:pv,:dv,:ci,0,'ativo',:obs,'onvio_semef',"
        "'onvio_parcelamentos',now(),now())"),
        {"na": numero,
         "desc": f"Parcelamento ISSQN — SEMEF Manaus, processo {dados['processo']} "
                 f"({dados['num_parcelas']} parcelas)",
         "np": dados["num_parcelas"], "pv": dados["valor"], "dv": dia,
         "ci": comp, "obs": obs})
    return "criado"


def parcela_atrasada(competencia_corrente: str | None, dia_vencimento: int,
                     hoje: date) -> bool:
    """A parcela do mês corrente já devia ter aparecido e não apareceu?

    Existe porque **o sync do Onvio não tem beat** — depende de alguém autenticar (OTP por
    e-mail, sessão de 16h). Sem este guarda, um mês em que ninguém rodou o sync fica idêntico
    a um mês em que o acordo foi quitado: silêncio. E silêncio, aqui, é acordo rescindido.
    [[feedback_verde_que_nao_prova_nada]]
    """
    if not competencia_corrente:
        return False                      # acordo sem competência conhecida — nada a comparar
    try:
        mes, ano = (int(p) for p in competencia_corrente.split("/"))
    except (ValueError, TypeError):
        return False

    atraso = (hoje.year * 12 + hoje.month) - (ano * 12 + mes)
    if atraso <= 0:
        return False                      # o documento do mês já chegou
    if atraso >= 2:
        return True                       # dois meses sem documento não depende de dia nenhum

    # Um mês de atraso: só cobra depois do dia do vencimento. O DAM costuma sair na virada, e
    # cobrar no dia 1º geraria um alarme falso por mês — a forma mais rápida de ensinar alguém
    # a ignorar o sino.
    #
    # ⚠️ O dia é CLAMPADO ao último dia do mês. Os DAS de dívida ativa vencem no fim do mês e
    # gravam `dia_vencimento = 31`; comparar `hoje.day > 31` é uma condição que nunca ocorre —
    # os quatro acordos PGFN nunca disparariam alerta, e o guarda inteiro seria decorativo.
    ultimo = calendar.monthrange(hoje.year, hoje.month)[1]
    return hoje.day > min(dia_vencimento, ultimo)


def alertar_parcelas_ausentes(db, hoje: date | None = None) -> list[dict]:
    """Publica no sino os acordos ativos cuja parcela do mês não apareceu."""
    from modules.fiscal_contabil.obrigacoes.guias_drive_service import (
        _emitir_notificacao_fiscal,
    )

    hoje = hoje or date.today()
    faltando = []
    linhas = db.execute(text(
        "SELECT numero_acordo, orgao, dia_vencimento, parcela_valor, observacao "
        "  FROM fiscal_parcelamentos WHERE lower(coalesce(status,'')) = 'ativo'")).fetchall()
    for numero, orgao, dia, valor, obs in linhas:
        try:
            corrente = json.loads(obs or "{}").get("competencia_corrente")
        except (ValueError, TypeError):
            corrente = None
        if parcela_atrasada(corrente, int(dia or 31), hoje):
            faltando.append({"acordo": numero, "orgao": orgao,
                             "ultima_competencia": corrente,
                             "parcela_valor": float(valor or 0)})
    if faltando:
        linhas_txt = "\n".join(
            f"• {f['orgao']} {f['acordo']} — última parcela vista em {f['ultima_competencia']}, "
            f"R$ {f['parcela_valor']:.2f}".replace(".", ",")
            for f in faltando)
        _emitir_notificacao_fiscal(
            db,
            f"{len(faltando)} parcelamento(s) sem a parcela deste mês",
            "O documento da parcela do mês corrente não chegou ao acervo. Parcela em atraso "
            "não gera multa de mora: RESCINDE o acordo, e o saldo vence de uma vez.\n\n"
            + linhas_txt,
            "/modulos/fiscal")
    return faltando


def sincronizar(db=None) -> dict:
    """Varre os parcelamentos do acervo Onvio e cadastra cada acordo."""
    from modules.fiscal_contabil.obrigacoes.guias_drive_service import (
        _upsert_parcelamento,
        parse_pdf_guia,
    )

    proprio = db is None
    if proprio:
        from core.database.session import SyncSessionLocal
        db = SyncSessionLocal()

    rel: dict = {"federais": [], "municipais": [], "sem_arquivo": 0, "ignorados": 0}
    try:
        for nome, caminho in db.execute(text(_SQL_DOCS)).fetchall():
            if not os.path.exists(caminho):
                rel["sem_arquivo"] += 1
                continue
            try:
                texto_pdf = _texto(caminho)
            except Exception as exc:  # noqa: BLE001
                logger.warning("[parc_onvio] %s ilegível: %s", nome, exc)
                rel["ignorados"] += 1
                continue

            # 1) DAS/DARF de dívida ativa — o parser federal já lê, com SISPAR. Reusar.
            try:
                g = parse_pdf_guia(caminho, nome)
            except Exception:  # noqa: BLE001
                g = None
            if g is not None and g.tipo == "PARCELAMENTO_PGFN":
                acao = _upsert_parcelamento(
                    db, g, {"file_id": None, "nome": nome, "fonte": "onvio_pgfn"})
                rel["federais"].append({"arquivo": nome,
                                        "sispar": (g.detalhe or {}).get("sispar"),
                                        "valor": g.valor, "acao": acao})
                continue

            # 2) DAM municipal de parcelamento — o único caso que o parser federal não cobre.
            dados = ler_dam_municipal(texto_pdf)
            if dados:
                acao = _upsert_municipal(db, dados, nome)
                rel["municipais"].append({"arquivo": nome, "processo": dados["processo"],
                                          "parcela": f"{dados['parcela_atual']}/{dados['num_parcelas']}",
                                          "valor": dados["valor"], "acao": acao})
                continue

            rel["ignorados"] += 1

        rel["parcelas_ausentes"] = alertar_parcelas_ausentes(db)
        db.commit()
        logger.info("[parc_onvio] %s federal(is) · %s municipal(is) · %s sem arquivo",
                    len(rel["federais"]), len(rel["municipais"]), rel["sem_arquivo"])
        return rel
    finally:
        if proprio:
            db.close()


if __name__ == "__main__":
    # Self-check sem banco: a leitura do DAM é onde um layout novo passa calado.
    dam = ("DOCUMENTO DE ARRECADAÇÃO MUNICIPAL - D.A.M SEMEF PREFEITURA DE MANAUS "
           "CONECTAMAIS ELETRONICA LTDA 1848897748/2026 ISSQN MENSAL - 2026 "
           "35.710.481/0001-03 45177801 3/100 03/08/2026 11000003754730652 "
           "05/12/2019 Data de Abertura: LEI 3537/2025, PARCELAMENTO E REPARCELAMENTO DE "
           "CRÉDITOS TRIBUTÁRIOS. PROCESSO DE QUITAÇÃO: 41613005/2026 "
           "ISSQN MENSAL 323,40 R$ Total: 367,92 R$")
    d = ler_dam_municipal(dam)
    assert d is not None, "DAM de parcelamento tem de ser lido"
    assert d["processo"] == "41613005/2026", d
    assert (d["parcela_atual"], d["num_parcelas"]) == (3, 100), d
    assert d["valor"] == 367.92, d
    assert d["vencimento"] == date(2026, 8, 3), d["vencimento"]
    assert d["cnpj"] == "35.710.481/0001-03", d

    # A data de ABERTURA (05/12/2019) aparece ANTES do vencimento no texto corrido. Se o
    # filtro de ano cair, o acordo nasce com dia_vencimento 5 e o painel cobra na data errada.
    assert d["vencimento"].year == 2026

    # Guia comum de ISSQN — sem processo de quitação — NÃO é parcelamento.
    assert ler_dam_municipal(
        "D.A.M SEMEF ISSQN MENSAL - 2026 35.710.481/0001-03 45177801 "
        "1/1 10/08/2026 Total: 740,25 R$") is None, "sem processo não é acordo"

    # Parcela impossível (a competência "1/2026-2" casa o regex de parcela) é recusada.
    assert ler_dam_municipal(
        "PROCESSO DE QUITAÇÃO: 41577140/2026 Mês/Ano-Seq.: 1/2026-1 Total: 285,01 R$") is None

    # Data ANTES da parcela: o par "27/01" de uma data de emissão não pode ser lido como
    # parcela 27/1 nem fazer o DAM inteiro ser descartado. Foi por isto que `(?!/)` entrou.
    d2 = ler_dam_municipal(
        "Emissão: 27/01/2026 PROCESSO DE QUITAÇÃO: 41577140/2026 "
        "45177801 6/30 24/07/2026 Total: 285,01 R$")
    assert d2 is not None and (d2["parcela_atual"], d2["num_parcelas"]) == (6, 30), d2
    assert d2["vencimento"] == date(2026, 7, 24), d2["vencimento"]

    assert _dec("1.301,40") == 1301.4 and _dec("367,92") == 367.92
    assert _dec(None) is None and _dec("") is None and _dec("abc") is None

    # O guarda de parcela ausente. Sem ele, "ninguém rodou o sync do Onvio" e "o acordo foi
    # quitado" são o mesmo silêncio.
    assert parcela_atrasada("07/2026", 3, date(2026, 8, 18)) is True
    assert parcela_atrasada("08/2026", 3, date(2026, 8, 18)) is False, "o mês já chegou"
    assert parcela_atrasada("09/2026", 3, date(2026, 8, 18)) is False, "adiantado não é atraso"
    assert parcela_atrasada("07/2026", 24, date(2026, 8, 18)) is False, \
        "antes do dia do vencimento não se cobra — o DAM costuma sair na virada"
    assert parcela_atrasada("07/2026", 24, date(2026, 8, 25)) is True
    assert parcela_atrasada(None, 3, date(2026, 8, 18)) is False, "sem competência, nada a comparar"
    assert parcela_atrasada("lixo", 3, date(2026, 8, 18)) is False
    # Virada de ano: dezembro do ano anterior é atraso em janeiro, não o contrário.
    assert parcela_atrasada("12/2025", 3, date(2026, 1, 18)) is True
    assert parcela_atrasada("01/2026", 3, date(2025, 12, 18)) is False

    # ⚠️ dia 31 é o caso que fazia o guarda inteiro ser decorativo: os DAS de dívida ativa
    # gravam `dia_vencimento = 31` e `hoje.day > 31` nunca acontece.
    assert parcela_atrasada("07/2026", 31, date(2026, 9, 30)) is True, \
        "30/09 é o último dia de setembro — o dia 31 tem de ser clampado"
    assert parcela_atrasada("08/2026", 31, date(2026, 9, 15)) is False, "meio do mês, ainda não"
    # Dois meses sem documento dispara independentemente do dia.
    assert parcela_atrasada("06/2026", 31, date(2026, 8, 1)) is True
    assert parcela_atrasada("07/2026", 31, date(2026, 8, 1)) is False
    print("self-check OK")

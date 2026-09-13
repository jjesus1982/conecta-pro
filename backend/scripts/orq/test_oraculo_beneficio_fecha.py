"""Oráculo — o benefício FECHA: o que o portal pagou é o que o motor calculou (frente 03, 12/09/2026).

Por que existe: o VT/VR era pedido no olho (a Pyetra conta os dias) e conferido no olho. O
relatório do Sólides (VA + mobilidade) e o do SINETRAM (VT) dizem o que FOI PAGO por pessoa;
o motor `folha/services/beneficio_ponto.py` diz o que DEVERIA ser pago pelo ponto e pela
escala. Este oráculo é a régua do paralelo cego: enquanto os dois não fecharem dois meses
seguidos, ninguém publica.

O que afirma, por competência que tenha relatório de portal, e por pessoa × benefício:
  1. O motor EXISTE e calculou para todo mundo que o portal pagou — ausência é vermelho.
  2. O que a conferência guardou como "portal" é o que o parser lê do PDF (fidelidade).
  3. Aritmética: total = quantidade × unitário; unitário é o do BANCO (cct_benefit_configs /
     cct_beneficios), nunca chumbado; quantidade = previsão + crédito/débito.
  4. Quando o motor tem o anterior (estado 'ok'): |calculado − portal| ≤ R$ 0,01, senão vermelho.
     Quando NÃO tem ('sem_anterior' — primeira competência), a diferença é IMPRESSA e
     atribuída ao anterior desconhecido: comparar aí seria assumir ajuste = 0, o erro exato
     que o pré-mortem (frente 3, item 4) proíbe. O resumo diz quantas linhas ficaram sem
     comparar — se for todas, a igualdade ainda não foi exercitada e o relatório tem de dizer.
  5. Ninguém que o portal pagou fica em 'sem_parametro' / 'sem_escala': motor sem insumo é ausência.

Estado medido no nascimento (12/09/2026, staging): o motor não existia; 12 pessoas no Sólides
(Agosto/2026, R$ 6.546,00) e 1 no SINETRAM (R$ 270,00) sem nenhuma linha de conferência.

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho.
"""
from __future__ import annotations

import asyncio
import glob
import os
import re
import sys
from decimal import Decimal

#: Onde os relatórios dos portais moram. Em produção `/app/uploads` é o volume `uploads/`;
#: no staging não há volume — copie os PDFs para lá (o relatório da frente diz como).
PDF_DIRS = [os.environ.get("BENEFICIO_PDF_DIR", ""), "/app/uploads/referencia_kits", "/app/uploads/kits"]
TOLERANCIA = Decimal("0.01")


def _dig(v: str | None) -> str:
    return re.sub(r"\D", "", v or "")


def _pdfs() -> list[str]:
    out: list[str] = []
    for d in PDF_DIRS:
        if d and os.path.isdir(d):
            out += glob.glob(os.path.join(d, "**", "*.pdf"), recursive=True)
    return sorted(set(out))


async def main() -> int:
    from sqlalchemy import text

    from core.database import get_db

    falhas: list[str] = []
    try:
        from modules.people_management.folha.services import beneficio_ponto as motor
        from modules.people_management.folha.services.beneficios_importer import ler_pedidos_em
    except ImportError as e:
        print(f"FALHOU: o motor de benefício ligado ao ponto não existe ({e})")
        raise AssertionError("1 desvio: motor ausente")

    pedidos = ler_pedidos_em(_pdfs())
    if not pedidos:
        print(f"FALHOU: nenhum relatório de portal (Sólides/SINETRAM) em {[d for d in PDF_DIRS if d]} — sem portal não há paralelo")
        raise AssertionError("1 desvio: sem relatório de portal")

    # portal[(competencia, cpf, beneficio)] = valor
    portal: dict[tuple[str, str, str], Decimal] = {}
    sem_comp = 0
    for p in pedidos:
        if not p.competencia:
            sem_comp += 1
            continue
        for ln in p.linhas:
            if ln.alimentacao:
                portal[(p.competencia, ln.cpf, "VR")] = portal.get((p.competencia, ln.cpf, "VR"), Decimal(0)) + ln.alimentacao
            if ln.mobilidade:
                portal[(p.competencia, ln.cpf, "VT")] = portal.get((p.competencia, ln.cpf, "VT"), Decimal(0)) + ln.mobilidade
    if sem_comp:
        falhas.append(f"{sem_comp} relatório(s) sem competência identificável — não dá para casar com o motor")

    gen = get_db()
    db = await gen.__anext__()
    existe = (await db.execute(text("SELECT to_regclass('public.folha_beneficio_conferencia')"))).scalar()
    if not existe:
        print("FALHOU: tabela folha_beneficio_conferencia não existe — o motor nunca gravou")
        raise AssertionError("1 desvio: sem tabela de conferência")

    comps = sorted({k[0] for k in portal})
    linhas = {}
    for comp in comps:
        rows = (await db.execute(text(
            "SELECT regexp_replace(coalesce(e.cpf,''),'[^0-9]','','g'), c.beneficio, c.estado, c.previsao, "
            "c.credito_debito, c.quantidade, c.unitario, c.total, c.portal_valor, e.nome "
            "FROM folha_beneficio_conferencia c JOIN employees e ON e.id = c.employee_id "
            "WHERE c.competencia = CAST(:c AS date)"), {"c": comp + "-01"})).fetchall()
        for r in rows:
            linhas[(comp, r[0], r[1])] = r

    params = await motor.parametros(db)
    comparaveis = divergentes = 0
    delta_anterior = Decimal(0)
    sem_anterior = 0
    for chave, pago in sorted(portal.items()):
        comp, cpf, ben = chave
        r = linhas.get(chave)
        if r is None:
            falhas.append(f"{comp} CPF …{cpf[-4:]} {ben}: portal pagou R$ {pago} e o motor NÃO calculou (ausência)")
            continue
        _, _, estado, previsao, cred, qtd, unit, total, pval, nome = r
        if estado in ("sem_parametro", "sem_escala"):
            falhas.append(f"{comp} {nome} {ben}: motor em '{estado}' para alguém que o portal pagou — é ausência com outro nome")
            continue
        if pval is None or abs(Decimal(pval) - pago) > TOLERANCIA:
            falhas.append(f"{comp} {nome} {ben}: conferência guardou portal={pval} e o PDF diz {pago} (fidelidade)")
        esperado = params.unitarios.get(ben)  # {Decimal, ...} — VT tem um por operadora
        if unit is None or not esperado or Decimal(unit) not in esperado:
            falhas.append(f"{comp} {nome} {ben}: unitário {unit} não é nenhum dos do banco {sorted(map(str, esperado or []))}")
        if qtd is None or total is None or Decimal(total) != Decimal(qtd) * Decimal(unit or 0):
            falhas.append(f"{comp} {nome} {ben}: total {total} ≠ quantidade {qtd} × unitário {unit}")
        if estado == "sem_anterior":
            if qtd != previsao:
                falhas.append(f"{comp} {nome} {ben}: sem anterior, quantidade {qtd} deveria ser a previsão {previsao} (ajuste inventado)")
            sem_anterior += 1
            delta_anterior += Decimal(total or 0) - pago
            continue
        if qtd != (previsao or 0) + (cred or 0):
            falhas.append(f"{comp} {nome} {ben}: quantidade {qtd} ≠ previsão {previsao} + crédito/débito {cred}")
        comparaveis += 1
        if abs(Decimal(total) - pago) > TOLERANCIA:
            divergentes += 1
            falhas.append(f"{comp} {nome} {ben}: motor R$ {total} × portal R$ {pago} (Δ {Decimal(total) - pago})")

    print(f"competências com portal: {len(comps)} · pessoa×benefício no portal: {len(portal)} · "
          f"casadas no motor: {sum(1 for k in portal if k in linhas)} · comparáveis (com anterior): {comparaveis} · "
          f"divergentes: {divergentes} · sem anterior: {sem_anterior} (Δ motor−portal acumulada R$ {delta_anterior})")
    if comparaveis == 0:
        print("AVISO: nenhuma linha tinha o anterior — a igualdade motor = portal ainda NÃO foi exercitada; "
              "vale a partir da 2ª competência com relatório.")
    for f in falhas:
        print("FALHOU:", f)
    if falhas:
        raise AssertionError(f"{len(falhas)} desvio(s) no fechamento do benefício")
    print("OK benefício fecha: todo pago tem cálculo, o portal guardado é o do PDF, a aritmética bate e o unitário é o do banco")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print(e)
        sys.exit(1)

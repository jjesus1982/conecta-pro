#!/usr/bin/env python3
"""KPIs das telas que o dono abre todo dia == consulta INDEPENDENTE ao banco.

Nasceu no loop de 07/09/2026 ("telas do financeiro e do DP e demais"): 302 telas sem vigia,
e cada KPI de cabeçalho é um número que alguém decide olhando. Este oráculo é uma TABELA:
(módulo, caminho do KPI na tela construída de verdade, rótulo, SQL de verdade, tolerância).
Acrescentar um KPI é acrescentar uma linha — não um arquivo.

Regras da casa que ele cumpre: compara com a VERDADE (SQL escrito aqui, não copiado do
builder); afirma a REGRA (o rótulo e a fonte), não a fotografia; imprime o número dos dois
lados; sem escrita.

    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_oraculo_kpis_telas.py
"""
import asyncio
import os
import re
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/app")
import main_production  # noqa: E402,F401 — primeiro, sempre

MANAUS = "(now() AT TIME ZONE 'America/Manaus')::date"

#: (módulo, caminho na tela, rótulo exato, SQL escalar, tolerância relativa)
KPIS = [
    # ── Financeiro · Visão Geral ──
    ("financeiro", "g-visao/tabs[0]", "Saldo consolidado (2 bancos)",
     "SELECT coalesce(sum(current_balance),0) FROM bank_accounts WHERE bank_code IN ('077','403')", 0.0),
    ("financeiro", "g-visao/tabs[0]", "A pagar (próx. 7 dias)",
     "SELECT coalesce(sum(coalesce(net_value, gross_value)),0) FROM payable_accounts WHERE status='pendente' "
     f"AND due_date BETWEEN {MANAUS} AND {MANAUS} + 7", 0.01),
    ("financeiro", "g-visao/tabs[1]", "A receber (aberto)",
     "SELECT coalesce(sum(gross_value - coalesce(paid_value,0)),0) FROM receivable_accounts WHERE status='pendente'", 0.01),
    ("financeiro", "g-visao/tabs[1]", "A pagar (aberto)",
     "SELECT coalesce(sum(coalesce(net_value, gross_value)),0) FROM payable_accounts WHERE status='pendente'", 0.01),
    ("financeiro", "g-visao/tabs[1]", "Clientes ativos", "SELECT count(*) FROM clients WHERE status='active'", 0.0),
    ("financeiro", "g-visao/tabs[3]", "Base recorrente (MRR)",
     "SELECT coalesce(sum(monthly_value),0) FROM contracts WHERE status='active'", 0.01),
    # ── DP · Visão ──
    ("departamento-pessoal", "g-visao/tabs[0]", "Colaboradores ativos", "SELECT count(*) FROM employees WHERE status='ativo'", 0.0),
    # A tela conta hr_vacation_requests INTEIRA (20, inclusive canceladas/rejeitadas) — "mesma
    # fonte do clássico"; existe uma segunda tabela, employee_vacation_requests (15), com outro
    # dataset. Duas tabelas para a mesma coisa é achado de mapa, não deste oráculo.
    ("departamento-pessoal", "g-visao/tabs[0]", "Solicitações de férias", "SELECT count(*) FROM hr_vacation_requests", 0.0),
    ("departamento-pessoal", "g-visao/tabs[0]", "Admissões em processo", "SELECT count(*) FROM admission_processes", 0.0),
    # ── Operacional · Visão ──
    ("operacional", "g-visao/tabs[0]", "Postos ativos", "SELECT count(*) FROM posts WHERE status='active'", 0.0),
    ("operacional", "g-visao/tabs[0]", "Colaboradores", "SELECT count(*) FROM employees WHERE status='ativo'", 0.0),
    ("operacional", "g-visao/tabs[0]", "Alocações ativas", "SELECT count(*) FROM employee_alocacoes WHERE ativo", 0.0),
    ("operacional", "g-visao/tabs[0]", "Ocorrências (7d)",
     "SELECT count(*) FROM occurrences WHERE occurred_at >= now() - interval '7 days'", 0.0),
    # Definição do serviço (operacional/ai/controller): ENTRADAS do dia civil de Manaus. À 1h
    # da manhã dá 0 com o turno noturno inteiro trabalhando — o rótulo é fraco para uma
    # empresa de portaria 12x36; o oráculo afirma a definição, o mapa registra a fraqueza.
    ("operacional", "g-visao/tabs[10]", "Presentes hoje",
     f"SELECT count(DISTINCT employee_id) FROM gp_clock_punches WHERE punch_type='entrada' AND punch_timestamp::date = {MANAUS}", 0.0),
    # ── CRM · dashboard ──
    ("crm", "dashboard", "Leads", "SELECT count(*) FROM leads", 0.0),
    ("crm", "dashboard", "Propostas", "SELECT count(*) FROM proposals", 0.0),
    ("crm", "dashboard", "Contratos", "SELECT count(*) FROM contracts", 0.0),
    # ── RH · dashboard ──
    ("rh", "dashboard", "Colaboradores ativos", "SELECT count(*) FROM employees WHERE status='ativo'", 0.0),
    ("rh", "dashboard", "Candidatos", "SELECT count(*) FROM candidates", 0.0),
    ("rh", "dashboard", "Entrevistas", "SELECT count(*) FROM interviews", 0.0),
    # ── Gestão de pessoas · visão ──
    ("gestao-de-pessoas", "visao", "Documentos GED", "SELECT count(*) FROM ged_kit_documents", 0.0),
    ("gestao-de-pessoas", "visao", "ASOs", "SELECT count(*) FROM gp_asos", 0.0),
    ("gestao-de-pessoas", "visao", "EPIs entregues", "SELECT count(*) FROM gp_epi_deliveries", 0.0),
    ("gestao-de-pessoas", "visao", "Batidas de ponto", "SELECT count(*) FROM gp_clock_punches", 0.0),
    # ── Fiscal · painel ──
    ("fiscal", "painel", "Obrigações em aberto", "SELECT count(*) FROM fiscal_obligations WHERE status='pendente'", 0.0),
    ("fiscal", "painel", "NFS-e Emitidas", "SELECT count(*) FROM nfse_emitidas_nacional", 0.0),
    # 12 meses = NFS-e Manaus (histórico, até 12/2025) + NFS-e nacional (desde 01/2026). Medido
    # em 07/09/2026: nenhum mês com as duas fontes ao mesmo tempo e 0 notas em comum — somar
    # é correto, não dobra.
    ("fiscal", "painel", "Faturamento (12m)",
     "SELECT coalesce((SELECT sum(valor_servicos) FROM nfse_manaus_historico WHERE data_emissao >= current_date - interval '12 months'),0)"
     " + coalesce((SELECT sum(valor_servicos) FROM nfse_emitidas_nacional WHERE data_emissao >= current_date - interval '12 months'),0)", 0.02),
    # ── Financeiro · faturamento do mês (NFS-e emitidas na competência corrente) ──
    ("financeiro", "g-visao/tabs[0]", "Faturamento 2026-09",
     "SELECT coalesce(sum(valor_servicos),0) FROM nfse_emitidas_nacional WHERE date_trunc('month', data_emissao) = date_trunc('month', current_date)", 0.02),
    # ── CRM · comissões ──
    ("crm", "dashboard", "Comissões a pagar",
     "SELECT coalesce(sum(coalesce(final_commission, base_commission, 0)),0) FROM commissions WHERE status='pending' AND is_active", 0.01),
    # Documentos · "Kits do mês" NÃO entra: o builder lê do Google Drive (competência = mês
    # anterior), fonte de fora — é domínio do checar_oraculo_externo. Medido em 07/09/2026: o
    # Drive diz 15 kits de agosto; ged_document_kits tem 9 (em_montagem, 76,7%). Achado de mapa.
]


def _num(v) -> Decimal:
    if isinstance(v, (int, float, Decimal)):
        return Decimal(str(v))
    t = re.sub(r"[^\d,.\-]", "", str(v or ""))
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(\.\d{3})+", t):
        t = t.replace(".", "")  # "3.292" é milhar em pt-BR, não 3,29 (pegou 2 falsos em 07/09)
    return Decimal(t or "0")


def _no_caminho(scr: dict, caminho: str):
    """'g-visao/tabs[3]' → screen['tabs'][3]['screen']['kpis']; 'dashboard' → screen['kpis']."""
    partes = caminho.split("/")[1:]
    cur = scr
    for p in partes:
        m = re.match(r"(\w+)\[(\d+)\]", p)
        cur = cur[m.group(1)][int(m.group(2))] if m else cur[p]
        if isinstance(cur, dict) and "screen" in cur:
            cur = cur["screen"]
    return cur.get("kpis") or []


async def main() -> None:
    from sqlalchemy import text

    from core.database import async_session_factory
    from modules.operacional.controllers import redesign_data_controller as RD

    falhas, ok = [], 0
    async with async_session_factory() as db:
        telas = {}
        for mod in sorted({k[0] for k in KPIS}):
            telas[mod] = await RD.BUILDERS[mod](db)
        for mod, caminho, rotulo, sql, tol in KPIS:
            slug = caminho.split("/")[0]
            try:
                kpis = _no_caminho(telas[mod][slug], caminho)
            except Exception as exc:  # noqa: BLE001
                falhas.append(f"{mod}/{caminho} [{rotulo}]: caminho não resolve ({type(exc).__name__})"); continue
            achado = next((k for k in kpis if (k.get("l") or "").startswith(rotulo)), None)
            if achado is None:
                falhas.append(f"{mod}/{caminho} [{rotulo}]: KPI não existe mais na tela (rótulos: {[k.get('l') for k in kpis][:5]})"); continue
            tela = _num(achado.get("v"))
            banco = _num((await db.execute(text(sql))).scalar())
            dif = abs(tela - banco) / (abs(banco) or Decimal(1))
            if dif <= Decimal(str(tol)) or (tela == banco):
                ok += 1
                print(f"OK {mod}/{slug} · {rotulo}: {tela:,.2f}")
            else:
                falhas.append(f"{mod}/{caminho} · {rotulo}: tela {tela:,.2f} × banco {banco:,.2f}")
    for f in falhas:
        print("FALHOU " + f)
    print(f"{ok} KPI(s) conferem · {len(falhas)} divergem")
    assert not falhas, f"{len(falhas)} KPI(s) divergem do banco"
    print("TEST oraculo_kpis_telas PASS")


if __name__ == "__main__":
    asyncio.run(main())

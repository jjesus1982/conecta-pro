#!/usr/bin/env python3
"""Captura as telas do redesign para o MANUAL do sistema (13/09/2026).

Faz login de verdade, espera a tela parar de dizer "carregando…" e salva o PNG em
uploads/manual_prints/ — que é `/app/uploads/manual_prints` dentro do backend, o caminho que
`gerar_apresentacao` lê no bloco {"tipo":"imagem"}.

Uso: python3 scripts/qa/_capturar_telas_manual.py [modulo ...]
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = os.getenv("MANUAL_BASE", "https://erp.conectamais.pro")
USER = os.getenv("MANUAL_USER", "jjesus@conectamais.pro")
PWD = os.getenv("MANUAL_PWD", "")
OUT = Path("/opt/conecta-pro/uploads/manual_prints")

#: Telas cujo filtro abre no PRIMEIRO item e mostram pouca coisa: escolhe a opção que
#: representa melhor a tela no manual (não é maquiagem — é a mesma tela, outro filtro).
ESCOLHER: dict[str, str] = {
    "op-mapa-de-ponto": "Residencial Laranjeiras Village",
}

#: (arquivo, módulo, aba). Aba vazia = tela inicial do módulo.
#: A lista saiu do inventário REAL do redesign (GET /api/v1/redesign/data/<slug>),
#: não de memória: são as abas que existem e têm dado para mostrar no manual.
TELAS: list[tuple[str, str, str]] = [
    ("op-visao-geral", "operacional", ""),
    ("op-kpi", "operacional", "kpi"),
    ("op-cobertura-risco", "operacional", "cobertura-risco"),
    ("op-mapa", "operacional", "mapa"),
    ("op-campo", "operacional", "campo"),
    ("op-escalas-mes", "operacional", "escalas-mes"),
    ("op-escalas-grade", "operacional", "escalas-grade"),
    ("op-escalas-visual", "operacional", "escalas-visual"),
    ("op-alocacoes", "operacional", "alocacoes"),
    ("op-postos", "operacional", "postos"),
    ("op-presenca", "operacional", "presenca"),
    ("op-gerente-hoje", "operacional", "gerente-hoje"),
    ("op-banco-horas-apuracao", "operacional", "banco-horas-apuracao"),
    ("op-diarias", "operacional", "diarias"),
    ("op-rondas", "operacional", "rondas"),
    ("op-ocorrencias", "operacional", "ocorrencias"),
    ("op-comunicados", "operacional", "comunicados"),
    ("op-grid-real-contratual", "operacional", "grid-real-contratual"),
    ("dp-visao-geral", "departamento-pessoal", ""),
    ("dp-funcionarios", "departamento-pessoal", "funcionarios"),
    ("dp-headcount", "departamento-pessoal", "headcount"),
    ("dp-cct-conformidade", "departamento-pessoal", "cct-conformidade"),
    ("dp-admissao", "departamento-pessoal", "admissao"),
    ("dp-ponto", "departamento-pessoal", "ponto"),
    ("dp-fechamento-ponto", "departamento-pessoal", "fechamento-ponto"),
    ("dp-folha", "departamento-pessoal", "folha"),
    ("dp-folha-por-condominio", "departamento-pessoal", "folha-por-condominio"),
    ("dp-pareamento-folha", "departamento-pessoal", "pareamento-folha"),
    ("dp-folha-rubricas", "departamento-pessoal", "folha-rubricas"),
    ("dp-ferias", "departamento-pessoal", "ferias"),
    ("dp-mapa-ferias", "departamento-pessoal", "mapa-ferias"),
    ("dp-saldo-ferias", "departamento-pessoal", "saldo-ferias"),
    ("dp-beneficios", "departamento-pessoal", "beneficios"),
    ("dp-beneficio-conferencia", "departamento-pessoal", "beneficio-conferencia"),
    ("dp-esocial", "departamento-pessoal", "esocial"),
    ("dp-rescisao", "departamento-pessoal", "rescisao"),
    ("gp-visao-geral", "gestao-de-pessoas", ""),
    ("gp-ged", "gestao-de-pessoas", "ged"),
    ("gp-ged-kits", "gestao-de-pessoas", "ged-kits"),
    ("gp-ged-assinaturas", "gestao-de-pessoas", "ged-assinaturas"),
    ("gp-ponto", "gestao-de-pessoas", "ponto"),
    ("gp-ponto-espelho", "gestao-de-pessoas", "ponto-espelho"),
    ("gp-ponto-banco", "gestao-de-pessoas", "ponto-banco"),
    ("gp-saude-exames", "gestao-de-pessoas", "saude-exames"),
    ("gp-sst", "gestao-de-pessoas", "sst"),
    ("gp-vigilante-aptidao", "gestao-de-pessoas", "vigilante-aptidao"),
    ("gp-vigilante-equipamentos", "gestao-de-pessoas", "vigilante-equipamentos"),
    ("gp-uniforme-grade", "gestao-de-pessoas", "uniforme-grade"),
    ("gp-uniforme-entregas", "gestao-de-pessoas", "uniforme-entregas"),
    ("gp-rh-treinamentos", "gestao-de-pessoas", "rh-treinamentos"),
    ("fin-visao-geral", "financeiro", ""),
    ("fin-fluxo-caixa", "financeiro", "fluxo-caixa"),
    ("fin-dre-inline", "financeiro", "dre-inline"),
    ("fin-indicadores", "financeiro", "indicadores"),
    ("fin-contas-receber", "financeiro", "contas-receber"),
    ("fin-cobrancas", "financeiro", "cobrancas"),
    ("fin-boletos", "financeiro", "boletos"),
    ("fin-contas-pagar", "financeiro", "contas-pagar"),
    ("fin-pagamentos-diaristas", "financeiro", "pagamentos-diaristas"),
    ("fin-saldos", "financeiro", "saldos"),
    ("fin-conciliacao-bancaria", "financeiro", "conciliacao-bancaria"),
    ("fin-balancete", "financeiro", "balancete"),
    ("fin-balanco-patrimonial", "financeiro", "balanco-patrimonial"),
    ("fin-rentabilidade", "financeiro", "rentabilidade"),
    ("fin-custeio-cct", "financeiro", "custeio-cct"),
    ("fin-precificacao", "financeiro", "precificacao"),
    ("fin-fornecedores", "financeiro", "fornecedores"),
    ("fin-estoque-real", "financeiro", "estoque-real"),
    ("fis-visao-geral", "fiscal", ""),
    ("fis-nfse", "fiscal", "nfse"),
    ("fis-guias", "fiscal", "guias"),
    ("fis-dctfweb", "fiscal", "dctfweb"),
    ("fis-reinf", "fiscal", "reinf"),
    ("fis-certidoes", "fiscal", "certidoes"),
    ("fis-apuracao-lucro-real", "fiscal", "apuracao-lucro-real"),
    ("fis-dre-mensal", "fiscal", "dre-mensal"),
    ("fis-parcelamentos", "fiscal", "parcelamentos"),
    ("fis-calc-comparativo", "fiscal", "calc-comparativo"),
    ("fis-nfse-tomadas", "fiscal", "nfse-tomadas"),
    ("fis-kpis-financeiros", "fiscal", "kpis-financeiros"),
    ("com-visao-geral", "crm", ""),
    ("com-leads", "crm", "leads"),
    ("com-oportunidades", "crm", "oportunidades"),
    ("com-propostas", "crm", "propostas"),
    ("com-contratos", "crm", "contratos"),
    ("com-clientes", "crm", "clientes"),
    ("com-precificacao", "crm", "precificacao"),
    ("com-comissoes", "crm", "comissoes"),
    ("com-atividades", "crm", "atividades"),
    ("com-growth", "crm", "growth"),
    ("com-contratos-a-emitir", "crm", "contratos-a-emitir"),
    ("com-consumo-ia", "crm", "consumo-ia"),
    ("eq-visao-geral", "equipamentos", ""),
    ("eq-patrimonio", "equipamentos", "patrimonio"),
    ("eq-comodatos", "equipamentos", "comodatos"),
    ("eq-manutencoes", "equipamentos", "manutencoes"),
    ("eq-frota-painel", "equipamentos", "frota-painel"),
    ("eq-frota-abastecimentos", "equipamentos", "frota-abastecimentos"),
    ("eq-frota-vistorias", "equipamentos", "frota-vistorias"),
    ("eq-avaliacao-dashboard", "equipamentos", "avaliacao-dashboard"),
    ("eq-avaliacao-ambientes", "equipamentos", "avaliacao-ambientes"),
    ("eq-avaliacao-links", "equipamentos", "avaliacao-links"),
    ("ged-visao-geral", "documentos", ""),
    ("ged-arquivos", "documentos", "arquivos"),
    ("ged-kits", "documentos", "kits"),
    ("ged-pastas", "documentos", "pastas"),
    ("ged-intercorrencias", "documentos", "intercorrencias"),
    ("ged-kits-conferencia", "documentos", "kits-conferencia"),
    ("ged-kits-assinaturas-pendentes", "documentos", "kits-assinaturas-pendentes"),
    ("ged-kits-entrega-status", "documentos", "kits-entrega-status"),
    ("ged-ged-coleta-automatica", "documentos", "ged-coleta-automatica"),
    ("ged-gedeon-panorama", "documentos", "gedeon-panorama"),
    ("ged-kit-documentos", "documentos", "kit-documentos"),
    ("ged-ged-tipos-documento", "documentos", "ged-tipos-documento"),
    ("jur-visao-geral", "juridico", ""),
    ("jur-processos", "juridico", "processos"),
    ("jur-det-comunicacoes", "juridico", "det-comunicacoes"),
    ("jur-contratos", "juridico", "contratos"),
    ("jur-riscos", "juridico", "riscos"),
    ("jur-prazos", "juridico", "prazos"),
    ("jur-analise", "juridico", "analise"),
    ("jur-conhecimento", "juridico", "conhecimento"),
    ("jur-escritorio-consultas", "juridico", "escritorio-consultas"),
    ("jur-playbook", "juridico", "playbook"),
    ("jur-det-status", "juridico", "det-status"),
    ("rh-visao-geral", "rh", ""),
    ("rh-vagas", "rh", "vagas"),
    ("rh-candidatos", "rh", "candidatos"),
    ("rh-entrevistas", "rh", "entrevistas"),
    ("rh-onboarding", "rh", "onboarding"),
    ("rh-treinamentos", "rh", "treinamentos"),
    ("rh-avaliacoes", "rh", "avaliacoes"),
    ("rh-carreira", "rh", "carreira"),
    ("rh-clima", "rh", "clima"),
    ("rh-turnover", "rh", "turnover"),
    ("rh-disc-medidas", "rh", "disc-medidas"),
    ("rh-certificados", "rh", "certificados"),
    ("sst-visao-geral", "saude-ocupacional", ""),
    ("sst-exames", "saude-ocupacional", "exames"),
    ("sst-epi", "saude-ocupacional", "epi"),
    ("sst-riscos", "saude-ocupacional", "riscos"),
    ("sst-cat", "saude-ocupacional", "cat"),
    ("sst-afastamentos", "saude-ocupacional", "afastamentos"),
    ("sst-estabilidade", "saude-ocupacional", "estabilidade"),
    ("sst-alertas", "saude-ocupacional", "alertas"),
    ("sst-asos-vencendo", "saude-ocupacional", "asos-vencendo"),
    ("sst-cipa-membros", "saude-ocupacional", "cipa-membros"),
    ("sst-ltcat", "saude-ocupacional", "ltcat"),
    ("sst-pcmso-esteira", "saude-ocupacional", "pcmso-esteira"),
    ("lic-visao-geral", "licitacoes", ""),
    ("lic-oportunidades", "licitacoes", "oportunidades"),
    ("lic-editais", "licitacoes", "editais"),
    ("lic-propostas", "licitacoes", "propostas"),
    ("lic-contratos", "licitacoes", "contratos"),
    ("lic-certidoes", "licitacoes", "certidoes"),
    ("lic-disputas", "licitacoes", "disputas"),
    ("lic-resultados", "licitacoes", "resultados"),
    ("lic-contratos-publicos", "licitacoes", "contratos-publicos"),
    ("lic-medicoes", "licitacoes", "medicoes"),
    ("por-visao-geral", "portal-do-funcionario", ""),
    ("por-contracheque", "portal-do-funcionario", "contracheque"),
    ("por-ferias", "portal-do-funcionario", "ferias"),
    ("por-ponto", "portal-do-funcionario", "ponto"),
    ("por-beneficios", "portal-do-funcionario", "beneficios"),
    ("por-escalas", "portal-do-funcionario", "escalas"),
    ("por-documentos", "portal-do-funcionario", "documentos"),
    ("por-treinamentos", "portal-do-funcionario", "treinamentos"),
    ("por-comunicados", "portal-do-funcionario", "comunicados"),
    ("por-bater-ponto", "portal-do-funcionario", "bater-ponto"),
    ("por-meus-direitos-cct", "portal-do-funcionario", "meus-direitos-cct"),
    ("por-calculadora-rescisao", "portal-do-funcionario", "calculadora-rescisao"),
    ("por-assinaturas-pendentes", "portal-do-funcionario", "assinaturas-pendentes"),
    ("cli-visao-geral", "area-do-cliente", ""),
    ("cli-operacao", "area-do-cliente", "operacao"),
    ("cli-chamados", "area-do-cliente", "chamados"),
    ("cli-financeiro", "area-do-cliente", "financeiro"),
    ("cli-kits", "area-do-cliente", "kits"),
    ("cli-analytics", "area-do-cliente", "analytics"),
    ("cli-ged-clientes", "area-do-cliente", "ged-clientes"),
]


def main() -> int:
    if not PWD:
        print("defina MANUAL_PWD"); return 2
    OUT.mkdir(parents=True, exist_ok=True)
    alvo = sys.argv[1:] or None
    with sync_playwright() as pw:
        nav = pw.chromium.launch(args=["--no-sandbox"])
        ctx = nav.new_context(viewport={"width": 1600, "height": 1000}, device_scale_factor=2)
        pg = ctx.new_page()
        pg.goto(f"{BASE}/login", wait_until="domcontentloaded", timeout=90_000)
        pg.fill("input[type=email], input[name=email], input[name=username]", USER)
        pg.fill("input[type=password]", PWD)
        pg.click("button[type=submit]")
        pg.wait_for_timeout(9_000)
        print("login:", pg.url)
        for nome, mod, aba in TELAS:
            # o argumento casa por MÓDULO ou por NOME do print (recaptura pontual)
            if alvo and mod not in alvo and nome not in alvo:
                continue
            url = f"{BASE}/redesign/{mod}" + (f"?t={aba}" if aba else "")
            try:
                pg.goto(url, wait_until="domcontentloaded", timeout=90_000)
                # a tela do redesign monta em duas fases: espera sumir o "carregando…"
                # MANUAL_ESPERA: ciclos de 1,2 s esperando o "carregando…" sumir. O padrão (40 ≈ 48 s)
                # não bastou para o cockpit do financeiro nem para a visão geral do DP — telas que
                # montam em duas fases e demoram. Recaptura usa valor maior.
                for _ in range(int(os.getenv("MANUAL_ESPERA", "40"))):
                    if "carregando…" not in (pg.inner_text("body") or ""):
                        break
                    pg.wait_for_timeout(1_200)
                if (op := ESCOLHER.get(nome)):
                    for sel in pg.query_selector_all("select"):
                        if any(op in (o.inner_text() or "") for o in sel.query_selector_all("option")):
                            sel.select_option(label=op)
                            pg.wait_for_timeout(2_500)
                            break
                pg.wait_for_timeout(2_500)
                dest = OUT / f"{nome}.png"
                pg.screenshot(path=str(dest))
                print(f"  ok {nome}.png  ({dest.stat().st_size // 1024} KB)")
            except Exception as e:  # noqa: BLE001 — uma tela ruim não derruba as outras
                print(f"  x  {nome}: {e}")
        nav.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

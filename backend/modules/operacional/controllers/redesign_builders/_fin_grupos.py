"""F0 — composição dos 7 grupos do financeiro (fundação tabs). Mapeia TODA tela antiga
para (grupo, aba); o oráculo da fase acusa órfãos (tela fora de grupo) — nada se perde.
Prefixo _ = o discovery de builders pula este arquivo (é helper, não módulo)."""
from modules.operacional.controllers.redesign_data_controller import grp, moved

GRUPOS = [
    ("g-visao", "Visão Geral", "Resumo executivo do financeiro", [
        ("dashboard", "Resumo"), ("fluxo-caixa", "Fluxo de Caixa"),
        ("projecao", "Projeção & Insights"), ("dre-inline", "DRE"), ("raio-x", "Raio-X"),
        ("cfo", "CFO IA"), ("agentes", "Agentes"), ("relatorios", "Relatórios")]),
    ("g-receber", "Receber", "Contas a receber, cobrança e faturamento", [
        ("contas-receber", "Contas a Receber"), ("cobrancas", "Cobranças"),
        ("regua", "Régua"), ("recorrencia", "Recorrência (MRR)"), ("boletos", "Boletos"),
        ("emitir-boleto", "Emitir boleto"), ("cobrar-pix", "Cobrar PIX"),
        ("faturamento", "Faturamento"), ("clientes", "Clientes"),
        ("registrar-conta-receber", "Registrar")]),
    ("g-pagar", "Pagar", "Contas a pagar, folha e pagamentos (gated OTP)", [
        ("contas-pagar", "Contas a Pagar"), ("fila-aprovacao", "Aprovação"),
        ("audit-log", "Audit log"), ("pagamentos-inter", "Pagamentos Inter"),
        ("pagamentos-pj", "Folha PJ"), ("pagar-folha-pj", "Pagar folha PJ"),
        ("pagamentos-diaristas", "Diaristas"), ("pagar-diaristas", "Pagar diaristas"),
        ("pagar-boleto", "Pagar boleto"), ("enviar-pix", "PIX / Transferir"),
        ("transferir-ted", "TED"), ("pagar-darf", "DARF"), ("pagar-gps", "GPS / INSS"),
        ("cancelar-pagamento", "Cancelar pagto"), ("registrar-conta-pagar", "Registrar")]),
    ("g-bancos", "Bancos & Conciliação", "Saldos, extratos e conciliação", [
        ("saldos", "Saldos"), ("contas-bancarias", "Contas"), ("inter", "Banco Inter"),
        ("cora", "Banco Cora"), ("banking", "Extrato"),
        ("conciliacao-bancaria", "Conciliação (extrato)"), ("conciliar-auto", "Rodar conciliação"),
        ("conciliacao", "Conciliação de folha"), ("inter-pagamentos", "Inter (pagtos)")]),
    ("g-fiscal", "Fiscal & Contábil", "Notas, guias e contabilidade", [
        ("fiscal", "Fiscal"), ("nfse-entrada", "NFS-e entrada"),
        ("plano-contas", "Plano de contas"), ("lancamentos", "Lançamentos"),
        ("balancete", "Balancete"), ("contabilidade", "Extrato categorizado"),
        ("cancelar-boleto", "Cancelar boleto")]),
    ("g-custos", "Custos & Orçamento", "Custos, custeio, precificação e orçamento", [
        ("custos", "Custos"), ("custeio-abc", "Custeio ABC"),
        ("custeio-contratos", "Margem por contrato"), ("custeio", "Simulador CCT"), ("custeio-cct", "Custeio CCT"),
        ("precificacao", "Precificação"), ("orcamentos", "Orçamentos")]),
    ("g-cadastros", "Cadastros & Suprimentos", "Fornecedores, contratos, compras e estoque", [
        ("fornecedores", "Fornecedores"), ("contratos", "Contratos"),
        ("compras-reais", "Compras"), ("compras", "Compras (NF-e)"),
        ("estoque-real", "Estoque"), ("estoque", "Estoque (NF-e)")]),
]


def montar_grupos(out: dict) -> None:
    """Compõe os grupos a partir das telas JÁ montadas em out e stub-a as antigas (redirect).
    Ordem importa: capturar as referências ANTES de stubar."""
    novos = {}
    for gid, titulo, sub, tabs in GRUPOS:
        novos[gid] = grp(titulo, sub, [(tid, lbl, out.get(tid)) for tid, lbl in tabs])
    for gid, _t, _s, tabs in GRUPOS:
        for tid, _l in tabs:
            if tid in out:
                out[tid] = moved(gid, tid)
    out.update(novos)

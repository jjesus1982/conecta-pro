"""Mapa categoria da saída → conta contábil. Regra pura, sem banco.

A decisão que carrega o plano inteiro: **onde a despesa já foi lançada na
competência, o pagamento debita o PASSIVO**. A folha lança D 5.1.1.01 /
C 2.1.1.01 quando fecha; se o pagamento pelo banco debitasse 5.1.1.01 de novo,
a despesa dobraria. Isso não é hipótese — aconteceu hoje e custou R$692.818,98
de despesa de pessoal inexistente, com o razão mostrando prejuízo em meses
lucrativos.

Contas que o razão JÁ usa como contrapartida (medido em 2026-08-11):
  2.1.1.01 Salários a Pagar (543 lanç.) · 2.1.1.02 FGTS (355)
  2.1.4.01 Fornecedores a Pagar (330)   · 2.1.2.01 ISS (85)
  2.1.1.03 INSS (14)                    · 2.1.2.04 Parcelamento Simples (5)
"""

from __future__ import annotations

# Conta contábil de cada conta bancária (ids reais de `bank_accounts`).
CONTA_BANCO: dict[str, str] = {
    "20663dc9-805c-4721-bc1f-62a041cee3c1": "1.1.1.01",  # Banco Inter
    "1268590a-0a2b-4b16-b959-6c14fe838d93": "1.1.1.02",  # Cora SCD
}

# Transitórias: o lançamento SEMPRE acontece; o que falta classificar fica à
# vista numa conta própria em vez de virar omissão.
CONTA_SAIDA_A_CLASSIFICAR = "5.9.9.01"
CONTA_ENTRADA_A_CLASSIFICAR = "4.9.9.01"

# categoria → (conta, motivo). Passivo quando a despesa já foi provisionada.
_MAPA_SAIDA: dict[str, tuple[str, str]] = {
    "salario": ("2.1.1.01", "quita salário já provisionado pela folha"),
    "fornecedor": ("2.1.4.01", "quita fornecedor já lançado pela NFS-e tomada"),
    "beneficio_vtvr": ("5.1.1.03", "benefício pago direto, sem provisão"),
    "diarista": ("5.1.1.07", "diária paga direto, sem provisão"),
    "pj_prolabore": ("5.2.1.04", "serviço de terceiro pago direto"),
    "socio": ("2.1.5.01", "conta corrente do sócio — não é despesa"),
    "transferencia_interna": ("1.1.9.01", "transferência entre empresas do grupo"),
    "taxa_bancaria": ("5.2.3.01", "tarifa bancária"),
    "diversos": (CONTA_SAIDA_A_CLASSIFICAR, "miúdo sem enquadramento"),

    # ── dialeto legado ──────────────────────────────────────────────────────
    # O campo era livre antes da lista fechada, então a base tem categorias que
    # não estão em CATEGORIAS. Ignorá-las jogaria R$307.471,72 na transitória
    # por questão de vocabulário, não por falta de informação.
    "servico_sem_nf": ("5.2.1.04", "serviço de terceiro sem NF — sem provisão, é despesa direta"),
    "diaristas_vtvr": ("5.1.1.03", "VT/VR de diarista"),
    # Antecipação de salário reduz o que se deve, não cria despesa nova: a folha
    # já lançou o salário cheio em 2.1.1.01.
    "adiantamento": ("2.1.1.01", "adiantamento de salário — abate o passivo da folha"),
    # 'outros'/'outro'/'reembolso' seguem para a transitória de propósito: são o
    # "não sei" que já estava gravado. Chutar conta aqui seria fabricar.
    "outros": (CONTA_SAIDA_A_CLASSIFICAR, "categoria legada 'outros' — sem enquadramento"),
    "outro": (CONTA_SAIDA_A_CLASSIFICAR, "categoria legada 'outro' — sem enquadramento"),
    "reembolso": (CONTA_SAIDA_A_CLASSIFICAR, "reembolso sem destino informado"),
}

# 'imposto' é guarda-chuva: o passivo certo depende do tributo. Sem afinar,
# FGTS cairia em ISS a Recolher e o passivo ficaria errado nos dois.
_TRIBUTO: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (("FGTS", "CAIXA ECONOMICA", "CEF "), "2.1.1.02", "FGTS a recolher"),
    (("INSS", "GPS", "PREVID"), "2.1.1.03", "INSS a recolher"),
    # " ISS" com espaço e ISSQN de propósito: "ISS" solto casa dentro de
    # "COMISSAO" e mandaria comissão para ISS a Recolher.
    ((" ISS", "ISSQN", "ISS "), "2.1.2.01", "ISS a recolher"),
    (("SIMPLES", "DAS", "PGFN", "SISPAR"), "2.1.2.04", "DAS / parcelamento Simples"),
)
CONTA_TRIBUTO_A_IDENTIFICAR = "2.1.2.09"

_ENTRADA_CLIENTE = ("PIX RECEBIDO", "RECEBIMENTO TITULO", "RECEBIMENTO DE TITULO",
                    "CREDITO", "LIQUIDACAO", "COBRANCA", "BOLETO")


def contrapartida_saida(categoria: str | None, descricao: str) -> tuple[str, str]:
    """(conta, motivo) do lado NÃO-banco de uma saída."""
    cat = (categoria or "").strip().lower()
    if cat in ("imposto", "impostos"):  # o plural é o mesmo dialeto legado
        d = f" {(descricao or '').upper()} "
        for termos, conta, motivo in _TRIBUTO:
            if any(x in d for x in termos):
                return conta, motivo
        return CONTA_TRIBUTO_A_IDENTIFICAR, "tributo não identificado na descrição"
    if cat in _MAPA_SAIDA:
        return _MAPA_SAIDA[cat]
    return CONTA_SAIDA_A_CLASSIFICAR, "saída ainda sem classificação"


def contrapartida_entrada(descricao: str) -> tuple[str, str]:
    """(conta, motivo) do lado NÃO-banco de uma entrada."""
    d = (descricao or "").upper()
    if any(x in d for x in _ENTRADA_CLIENTE):
        return "1.1.2.01", "recebimento de cliente"
    return CONTA_ENTRADA_A_CLASSIFICAR, "entrada ainda sem identificação"

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

import re

# Conta contábil de cada conta bancária (ids reais de `bank_accounts`).
CONTA_BANCO: dict[str, str] = {
    "20663dc9-805c-4721-bc1f-62a041cee3c1": "1.1.1.01",  # Banco Inter
    "1268590a-0a2b-4b16-b959-6c14fe838d93": "1.1.1.02",  # Cora SCD
}

# Transitórias: o lançamento SEMPRE acontece; o que falta classificar fica à
# vista numa conta própria em vez de virar omissão.
#: Rede por CÓDIGO DE BANCO, para quando a conta é nova e ninguém lembrou de
#: colar o uuid acima. A alternativa — cair em "conta bancária desconhecida" — é
#: silenciosa: o dinheiro entra no extrato e não chega ao razão.
#: Toda conta futura da Efí (364) já escritura em 1.1.1.03 sem tocar em código.
CONTA_BANCO_POR_CODIGO: dict[str, str] = {
    "077": "1.1.1.01",  # Inter — Eletrônica
    "403": "1.1.1.02",  # Cora SCD — Patrimonial
    "364": "1.1.1.03",  # Efí — Patrimonial (conta em abertura, 14/08/2026)
}

# ── Leitura do razão (plano de 13/08/2026) ──────────────────────────────────────────
# 3.x é PATRIMÔNIO (capital social, apuração do resultado) — NUNCA receita. 4.x é receita
# (saldo credor), 5.1.x custo de mão de obra, 5.2.2.01 ISS (dedução da receita), 5.2.x
# despesas, 5.9.x transitória. Em 07/09/2026 sete leitores ainda somavam "3.1.1 = receita,
# 4 = despesa" (o plano que morreu em 13/08) e a Apuração Lucro Real tributava o CAPITAL
# SOCIAL de R$ 500 mil como receita. Todo leitor do razão passa por aqui; `checar_dominio`
# proíbe o texto velho em modules/.
FILTRO_RAZAO = "status = 'confirmado' AND coalesce(tipo_lancamento,'') <> 'apuracao'"


def saldo(prefixo: str, pct: str = "%") -> str:
    """Fragmento SQL: saldo DEVEDOR (débito − crédito) das contas que começam com `prefixo`.

    Receita (4.x) sai NEGATIVA — negue no chamador. `pct="%%"` quando a query vai por
    psycopg2 com parâmetros (o driver desdobra `%%`). Encerramento (`apuracao`) fica de
    fora pelo FILTRO_RAZAO, senão o próprio DRE da competência encerrada se anula.
    """
    return (f"COALESCE(SUM(CASE WHEN conta_debito LIKE '{prefixo}{pct}' THEN valor "
            f"WHEN conta_credito LIKE '{prefixo}{pct}' THEN -valor ELSE 0 END), 0)")


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
    "emprestimo": ("2.1.6.01", "devolução de empréstimo — abate o passivo, não é despesa"),
    "aluguel": ("5.2.1.03", "aluguel/condomínio do imóvel da empresa"),
    "comissao": ("5.2.1.05", "comissão sobre venda — despesa comercial"),
    # ATIVO, não despesa: comprar TV em 4 parcelas não vira gasto do mês.
    # ⚠️ nasce sem depreciação — dívida declarada, vai junto com o PL.
    "equipamento": ("1.2.1.01", "equipamento/instalação — ativo imobilizado"),
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
    # Reembolso é despesa da EMPRESA que alguém adiantou — não é remuneração de
    # quem recebe. R$56,85 de "Café treinamento" estava entrando como pró-labore
    # do Eliziel, inflando o que ele ganhou.
    "reembolso": ("5.1.1.08", "despesa da empresa adiantada por colaborador"),
    "folha": ("2.1.1.01", "categoria 'Folha' do banco — salário já provisionado, baixa do passivo"),

    # ── dialeto legado, 2ª leva (11/08/2026) ────────────────────────────────
    # Medido no extrato: mais grafias do MESMO sentido caindo na transitória por
    # vocabulário. Só entram as que têm equivalente exato acima — o resto fica.
    "diaristas": ("5.1.1.07", "diária paga direto — grafia legada de 'diarista'"),
    "diaristas vt+vr": ("5.1.1.03", "VT/VR de diarista — grafia legada"),
    "pró-labore": ("5.2.1.04", "pró-labore — grafia legada de 'pj_prolabore'"),
    "pro-labore": ("5.2.1.04", "pró-labore — grafia legada sem acento"),
    "transferência": ("1.1.9.01", "transferência entre contas próprias — não é despesa"),
    "transferencia": ("1.1.9.01", "transferência entre contas próprias — não é despesa"),
    # NÃO entram, e o motivo importa:
    # • 'folha_pagamento'/'Folha' (R$ 96.246,39) pareceriam quitação de salário
    #   provisionado (2.1.1.01), mas a provisão tem saldo de R$ 44.413,37 — abater
    #   tudo ali deixaria o passivo NEGATIVO em R$ 51 mil. Ou a provisão está
    #   incompleta, ou parte desses pagamentos não é folha. Decisão de contador.
    # • 'pagamento', 'financiamentos', 'Outros' não dizem o que são.
    # • 'combustivel', 'locacao_veiculo', 'ti_telecom' não têm conta no plano.
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

# Dinheiro entre CNPJs NOSSOS não é receita nem despesa — é transferência, e as
# duas pontas se anulam em 1.1.9.01. Sem isto, um PIX de R$10.000 da Patrimonial
# para a Eletrônica era lançado como "retirada do sócio" de um lado e
# "recebimento de cliente" do outro: R$13.800 de distorção em agosto, nas duas
# direções ao mesmo tempo.
# "JORDAN SANTOS DE JESUS LTDA" está aqui porque é a razão social ANTIGA da
# Eletrônica, e é o nome que o Cora ainda devolve no favorecido — o CNPJ
# (35.710.481/0001-03) é que denuncia.
_GRUPO = ("CONECTA MAIS", "CONECTAMAIS", "CONECTA PRO", "CONECTA ELETRONICA",
          "CONECTA PATRIMONIAL", "CONECTA MAIS REDES", "JORDAN SANTOS DE JESUS LTDA")
CNPJS_DO_GRUPO = ("35710481000103", "66014833000110")


def contrapartida_saida(
    categoria: str | None, descricao: str, documento: str | None = None
) -> tuple[str, str]:
    """(conta, motivo) do lado NÃO-banco de uma saída.

    O teste do GRUPO vem PRIMEIRO, como já vinha em `contrapartida_entrada`. A assimetria
    entre as duas tinha preço: dinheiro que a Patrimonial mandou para a Eletrônica saía
    como DESPESA. Medido em 25/09/2026: R$ 86.000 em 4 lançamentos parados em
    «5.9.9.01 Saídas a Classificar», um deles categorizado `imposto` — que o teria mandado
    para «Tributos a Recolher - a identificar». Transferência entre CNPJs nossos não é
    despesa nem tributo; é movimentação entre contas do grupo.
    """
    cat = (categoria or "").strip().lower()
    doc = "".join(c for c in (documento or "") if c.isdigit())
    if doc in CNPJS_DO_GRUPO or any(g in (descricao or "").upper() for g in _GRUPO):
        return "1.1.9.01", "transferência para outra empresa do grupo — não é despesa"
    if cat in ("imposto", "impostos"):  # o plural é o mesmo dialeto legado
        d = f" {(descricao or '').upper()} "
        for termos, conta, motivo in _TRIBUTO:
            if any(x in d for x in termos):
                return conta, motivo
        return CONTA_TRIBUTO_A_IDENTIFICAR, "tributo não identificado na descrição"
    if cat in _MAPA_SAIDA:
        return _MAPA_SAIDA[cat]
    return CONTA_SAIDA_A_CLASSIFICAR, "saída ainda sem classificação"


#: ─────────────────────────────────────────────────────────────────────────────────────
#: CLASSIFICAÇÃO PELA CONTRAPARTE — último recurso, e só desde 26/09/2026
#:
#: Até aqui, categoria «outros» ia para a transitória DE PROPÓSITO: era o «não sei» que já
#: estava gravado, e chutar conta a partir dele seria fabricar. O que mudou não foi o
#: critério, foi a INFORMAÇÃO: a conciliação passou a extrair o nome do favorecido da
#: descrição do extrato e 545 transações que estavam sem contraparte ganharam nome. Quem
#: recebeu o dinheiro é fato do banco, não palpite.
#:
#: A ordem importa e é do mais específico para o mais genérico:
#:   1. o que a DESCRIÇÃO diz («Emprestimo Jean», «Material Fiori») — o mais forte;
#:   2. quem é a CONTRAPARTE (órgão público, banco credor, pessoa física, empresa).
#:
#: Cada regra grava o seu motivo no histórico do lançamento. Reclassificação sem motivo
#: escrito é a mesma coisa que chute com aparência de decisão.

#: (termos na descrição, conta, motivo). Vence a primeira que casar.
_SAIDA_POR_DESCRICAO: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (("EMPRESTIMO", "EMPRÉSTIMO"), "2.1.6.01", "empréstimo na descrição — abate/cria passivo, não é despesa"),
    (("MATERIAL", "MATERIAIS", "EPI"), "5.1.1.06", "material na descrição"),
    # «CONDOMINIO» NÃO entra aqui: todo cliente desta empresa é um condomínio, e a palavra
    # aparece no nome deles. Com ela, um PIX para o CONDOMINIO IDEAL FLORES — que é
    # CLIENTE — virava despesa de aluguel. Só «ALUGUEL» é inequívoco.
    (("ALUGUEL",), "5.2.1.03", "aluguel na descrição"),
    (("COMISSAO", "COMISSÃO"), "5.2.1.05", "comissão na descrição"),
    (("VALE REFEICAO", "VALE ALIMENTACAO", "VA/VT", "VT E VR", "VR E VT"), "5.1.1.03", "benefício de alimentação na descrição"),
    (("VALE TRANSPORTE",), "5.1.1.04", "vale transporte na descrição"),
    (("DIARIA", "DIÁRIA", "DIARIAS", "DIÁRIAS", "COBERTURA"), "5.1.1.07", "diária/cobertura na descrição"),
    (("TARIFA", "IOF"), "5.2.3.01", "tarifa/IOF na descrição"),
)

#: Contraparte que é ÓRGÃO PÚBLICO — o dinheiro é tributo, mesmo sem a categoria dizer.
_CONTRAPARTE_GOVERNO = (
    "RECEITA FEDERAL", "PREFEITURA", "SEFAZ", "SIMPLES NACIONAL", "DARF",
    "MUNICIPAL DE MANAUS", "FAZENDA", "INSS", "PGFN",
)
#: Contraparte que é BANCO CREDOR — parcela de financiamento. Não separa principal de
#: juros: para isso é preciso o contrato, que o sistema não tem. Fica em `5.2.3.02
#: Financiamentos`, que é a conta que o próprio plano criou para isto.
_CONTRAPARTE_BANCO = (
    "BANCO TOYOTA", "BANCO C6", "ITAU UNIBANCO", "ITAÚ UNIBANCO", "BANCO BRADESCO",
    "BANCO SANTANDER", "BANCO VOLKSWAGEN", "BANCO HONDA", "AYMORE", "BV FINANCEIRA",
)
#: Contraparte que é FGTS — a Caixa recebendo é encargo social, não tributo genérico.
_CONTRAPARTE_FGTS = ("CAIXA ECONOMICA", "CEF MATRIZ", "CAIXA MATRIZ")
#: Palavras que denunciam PESSOA JURÍDICA no nome. Sem documento, é o que separa
#: «ERIKA PEREIRA» de «ATLAS SERVICO DE MONITORAMENTO LTDA».
_MARCA_DE_EMPRESA = (
    "LTDA", "S.A", "S/A", " SA ", "EIRELI", "MEI", "EPP", " ME ", "COMERCIO", "COMÉRCIO",
    "SERVICOS", "SERVIÇOS", "TECNOLOGIA", "SISTEMAS", "ADVOG", "CONTABIL", "CONTÁBIL",
    "SINDICATO", "SIND ", "PAGAMENTOS", "MONITORAMENTO", "TELECOM", "INDUSTRIA",
    "INDÚSTRIA", "ASSOCIACAO", "ASSOCIAÇÃO", "CONDOMINIO", "CONDOMÍNIO", "BANCO",
    "SEGURADORA", "SEGUROS", "ODONTOLOG", "PLANO DE ASSISTENCIA", "DISTRIBUIDORA",
    "LOCADORA", "ENGENHARIA", "ELETRICA", "ELÉTRICA", "PROJETOS", "MARKETPLACE",
)


#: Sufixo societário, que é o sinal mais confiável quando não há CNPJ. Precisa ser regex:
#: a mesma razão social aparece como «LWSA S A», «LWSA S.A.» e «LWSA S/A», e testar
#: substring com " SA " deixava a primeira passar por pessoa física.
_SUFIXO_SOCIETARIO = re.compile(r"\b(S[./ ]?A|LTDA|EIRELI|EPP|MEI|ME)\b\.?\s*$|\bS[./ ]?A\b", re.I)


def _e_empresa(nome: str, documento: str | None) -> bool:
    """Contraparte é pessoa JURÍDICA? CNPJ manda; sem ele, o sufixo e a marca no nome."""
    doc = "".join(c for c in (documento or "") if c.isdigit())
    if len(doc) == 14:
        return True
    if len(doc) == 11:
        return False
    n = (nome or "").strip()
    if _SUFIXO_SOCIETARIO.search(n):
        return True
    return any(m in f" {n.upper()} " for m in _MARCA_DE_EMPRESA)


def contrapartida_por_contraparte(
    nome: str,
    documento: str | None = None,
    descricao: str | None = None,
    e_cliente: bool = False,
) -> tuple[str, str] | None:
    """(conta, motivo) deduzidos de QUEM recebeu — ou `None` quando não dá para dizer.

    Devolver `None` é resposta legítima e frequente: contraparte sem nome, ou nome que não
    diz nada, continua na transitória. A conta transitória com 220 linhas é ruim; a conta
    errada com 220 linhas é pior, porque parece resolvida.
    """
    n = f" {(nome or '').strip().upper()} "
    d = f" {(descricao or '').strip().upper()} "
    if not n.strip():
        return None

    for termos, conta, motivo in _SAIDA_POR_DESCRICAO:
        if any(t in d for t in termos):
            return conta, f"{motivo} («{(descricao or '')[:40].strip()}»)"

    if any(g in n for g in _CONTRAPARTE_FGTS):
        return "5.1.1.02", f"pago à Caixa — FGTS/encargo social (contraparte «{nome[:34]}»)"
    if any(g in n for g in _CONTRAPARTE_GOVERNO):
        return CONTA_TRIBUTO_A_IDENTIFICAR, f"pago a órgão público «{nome[:34]}» — é tributo; falta dizer qual"
    if any(b in n for b in _CONTRAPARTE_BANCO):
        return "5.2.3.02", f"parcela de financiamento — contraparte «{nome[:34]}» é banco credor"

    # Dinheiro SAINDO para quem é CLIENTE não é compra de serviço: é estorno, devolução ou
    # repasse, e qual dos três só quem fez sabe. São 7 lançamentos e R$ 2.925,00 em
    # 26/09/2026 — pouco, e ainda assim errado se virasse «serviço de terceiro».
    if e_cliente:
        return None

    if _e_empresa(nome, documento):
        return "5.2.1.04", f"serviço de terceiro — contraparte «{nome[:34]}» é pessoa jurídica"

    # Pessoa física. Decisão de Jordan Jesus em 26/09/2026 sobre as contrapartes que se
    # repetem com R$ 1.000 a R$ 1.700/mês: são cobertura, e o lugar é a folha.
    # ⚠️ Classificar a DESPESA como cobertura não cria vínculo trabalhista nem o resolve —
    # o risco que isso expõe continua sendo decisão do dono, e agora fica visível na conta
    # certa em vez de escondido na transitória.
    return "5.1.1.07", f"pessoa física — cobertura/diária (contraparte «{nome[:34]}»)"


def contrapartida_entrada(descricao: str, documento: str | None = None,
                         categoria: str | None = None) -> tuple[str, str]:
    """(conta, motivo) do lado NÃO-banco de uma entrada.

    O teste do GRUPO vem primeiro: uma transferência entre CNPJs nossos chega
    como "PIX RECEBIDO", e a regra de cliente a capturaria como receita.

    A CATEGORIA do extrato entrou em 11/08/2026. Até então esta função só lia a
    descrição, e o extrato já trazia `recebimento_cliente` classificado — R$ 138.648,89
    de R$ 141.355,52 na transitória de entradas eram informação que o sistema tinha e
    não usava. A descrição continua valendo para o que não vem categorizado.
    """
    doc = "".join(c for c in (documento or "") if c.isdigit())
    d = (descricao or "").upper()
    cat = (categoria or "").strip().lower()
    if doc in CNPJS_DO_GRUPO or any(g in d for g in _GRUPO):
        return "1.1.9.01", "transferência de outra empresa do grupo"
    if cat in ("transferência", "transferencia", "transferencia_interna"):
        return "1.1.9.01", "transferência entre contas próprias — não é receita"
    # Empréstimo RECEBIDO aumenta o passivo; não é cliente pagando. O sistema já
    # sabia classificar a DEVOLUÇÃO (saída → 2.1.6.01) e não sabia a entrada, então
    # dinheiro emprestado virava "recebimento de cliente": R$12.000 da Denise
    # Teixeira em 06/07/2026 entraram assim, e a justificativa da devolução de
    # 11/08 ("Devolução de empréstimo tomado da Denise Teixeira") denuncia. Com a
    # família emprestando para a empresa, isso repete.
    # Dinheiro PESSOAL do sócio entrando na conta da empresa: a empresa passa a
    # dever a ele. Espelho do caso de saída (`socio` em _MAPA_SAIDA), que faltava.
    # Caso real: o Jordan emprestou R$ da conta PESSOAL dele ao Eliziel, e o Eliziel
    # devolveu R$4.300 na conta da EMPRESA. Sem esta linha, dinheiro do sócio virava
    # "recebimento de cliente" — inflando receita e escondendo o que a empresa deve.
    if cat in ("socio", "aporte_socio", "socio_aporte"):
        return "2.1.5.01", "entrada de dinheiro do sócio — a empresa passa a dever a ele"
    if cat in ("emprestimo_tomado", "emprestimo_recebido", "emprestimo"):
        return "2.1.6.01", "empréstimo recebido — aumenta o passivo, não é receita"
    if cat.replace(" ", "_") in ("recebimento_cliente", "receita_cliente", "recebimento_de_cliente"):
        return "1.1.2.01", "recebimento de cliente (categoria do extrato)"
    if any(x in d for x in _ENTRADA_CLIENTE):
        return "1.1.2.01", "recebimento de cliente"
    return CONTA_ENTRADA_A_CLASSIFICAR, "entrada ainda sem identificação"

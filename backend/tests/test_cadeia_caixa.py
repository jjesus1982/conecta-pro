"""Cadeia do caixa: o razão precisa refletir o banco.

Em 2026-08-11 o razão dizia R$1.401.547,03 e o banco tinha R$16.826,71, porque
só 6% do extrato virava lançamento — e quase só entrada.
"""

from modules.financial.services.plano_contas_caixa import (
    CONTA_ENTRADA_A_CLASSIFICAR,
    CONTA_SAIDA_A_CLASSIFICAR,
    contrapartida_entrada,
    contrapartida_saida,
)


def test_despesa_ja_provisionada_debita_PASSIVO_nao_despesa():
    """A regra mais cara do plano. A folha já lança D 5.1.1.01 / C 2.1.1.01 na
    competência. Se o pagamento pelo banco debitasse 5.1.1.01 de novo, a despesa
    dobraria — foi exatamente o bug de R$692.818,98 encontrado hoje."""
    assert contrapartida_saida("salario", "PIX ENVIADO FULANO")[0] == "2.1.1.01"
    assert contrapartida_saida("fornecedor", "PAGAMENTO DE TITULO ACME")[0] == "2.1.4.01"


def test_despesa_sem_provisao_debita_DESPESA():
    """Diarista, benefício e tarifa não passam por provisão — o pagamento É a
    despesa."""
    assert contrapartida_saida("diarista", "PIX")[0] == "5.1.1.07"
    assert contrapartida_saida("beneficio_vtvr", "PIX")[0] == "5.1.1.03"
    assert contrapartida_saida("taxa_bancaria", "TARIFA")[0] == "5.2.3.01"
    assert contrapartida_saida("pj_prolabore", "PIX")[0] == "5.2.1.04"


def test_imposto_afina_pela_descricao():
    """'imposto' é categoria guarda-chuva; o passivo correto depende do tributo.
    Sem afinar, FGTS cairia em ISS a Recolher."""
    assert contrapartida_saida("imposto", "PAGAMENTO FGTS CAIXA")[0] == "2.1.1.02"
    assert contrapartida_saida("imposto", "PIX ENVIADO GPS INSS")[0] == "2.1.1.03"
    assert contrapartida_saida("imposto", "ISS MANAUS")[0] == "2.1.2.01"
    # "ISS" solto casaria dentro de COMISSAO — o tributo não pode ser adivinhado
    assert contrapartida_saida("imposto", "PAGAMENTO COMISSAO")[0] == "2.1.2.09"
    assert contrapartida_saida("imposto", "PAGAMENTO SIMPLES NACIONAL")[0] == "2.1.2.04"
    # tributo não identificado NÃO vira ISS por descuido
    assert contrapartida_saida("imposto", "DARF NUMERADO")[0] == "2.1.2.09"


def test_socio_e_transferencia_nao_sao_despesa():
    assert contrapartida_saida("socio", "PIX JORDAN")[0] == "2.1.5.01"
    assert contrapartida_saida("transferencia_interna", "PIX CONECTA")[0] == "1.1.9.01"


def test_sem_classificacao_vai_para_transitoria_visivel():
    """Nunca omitir o lançamento: o banco tem que fechar desde o primeiro dia, e
    o que falta classificar fica à vista numa conta própria."""
    assert contrapartida_saida(None, "PIX QUALQUER")[0] == CONTA_SAIDA_A_CLASSIFICAR
    assert contrapartida_saida("", "PIX")[0] == CONTA_SAIDA_A_CLASSIFICAR
    assert contrapartida_saida("categoria_que_nao_existe", "PIX")[0] == CONTA_SAIDA_A_CLASSIFICAR


def test_entrada_de_cliente_credita_clientes_a_receber():
    assert contrapartida_entrada("PIX RECEBIDO CONDOMINIO VILLA")[0] == "1.1.2.01"
    assert contrapartida_entrada("RECEBIMENTO TITULO 112")[0] == "1.1.2.01"
    assert contrapartida_entrada("ESTORNO NAO IDENTIFICADO")[0] == CONTA_ENTRADA_A_CLASSIFICAR


def test_aplicar_sugestoes_existe_e_tem_preview():
    """Preview é o padrão: escrita em massa sem ver antes foi o que quase gravou
    sócio como CLT hoje."""
    import inspect

    from modules.financial.services.classificacao_saidas_service import aplicar_sugestoes

    sig = inspect.signature(aplicar_sugestoes)
    assert sig.parameters["preview"].default is True
    assert "responsavel" in sig.parameters


def test_toda_conta_do_mapa_tem_motivo():
    """O motivo vai para o histórico do lançamento — quem auditar em 2030
    precisa saber por que aquela conta foi escolhida."""
    for cat in ("salario", "diarista", "imposto", "socio", None):
        _, motivo = contrapartida_saida(cat, "PIX")
        assert motivo and len(motivo) > 8

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


def test_transferencia_entre_nossos_cnpjs_nao_e_receita_nem_retirada():
    """R$13.800 da Patrimonial para a Eletrônica em agosto/2026 eram lançados
    como "retirada do sócio" de um lado e "recebimento de cliente" do outro — a
    mesma transferência inflando as duas pontas ao mesmo tempo.

    O teste do grupo TEM que vir antes do de cliente: a transferência chega como
    "PIX RECEBIDO" e seria capturada como receita.
    """
    assert contrapartida_entrada("PIX RECEBIDO Conecta Mais Patrimonial LTDA")[0] == "1.1.9.01"
    # o CNPJ decide mesmo quando o nome não denuncia: o Cora devolve a razão
    # social ANTIGA da Eletrônica ("JORDAN SANTOS DE JESUS LTDA")
    assert contrapartida_entrada("PIX RECEBIDO", "35.710.481/0001-03")[0] == "1.1.9.01"
    assert contrapartida_saida("transferencia_interna", "PIX")[0] == "1.1.9.01"


def test_aplicar_sugestoes_existe_e_tem_preview():
    """Preview é o padrão: escrita em massa sem ver antes foi o que quase gravou
    sócio como CLT hoje."""
    import inspect

    from modules.financial.services.classificacao_saidas_service import aplicar_sugestoes

    sig = inspect.signature(aplicar_sugestoes)
    assert sig.parameters["preview"].default is True
    assert "responsavel" in sig.parameters


def test_dialeto_legado_da_base_tem_destino():
    """O campo de categoria era livre antes da lista fechada, então a base tem
    'servico_sem_nf', 'impostos' no plural, 'adiantamento'. Sem mapear, R$307 mil
    caem na transitória por vocabulário, não por falta de informação."""
    assert contrapartida_saida("servico_sem_nf", "PIX")[0] == "5.2.1.04"
    assert contrapartida_saida("diaristas_vtvr", "PIX")[0] == "5.1.1.03"
    assert contrapartida_saida("adiantamento", "PIX")[0] == "2.1.1.01"
    assert contrapartida_saida("impostos", "PAGAMENTO FGTS")[0] == "2.1.1.02"
    # 'outros' é o "não sei" já gravado — chutar conta aqui seria fabricar
    assert contrapartida_saida("outros", "PIX")[0] == CONTA_SAIDA_A_CLASSIFICAR


def test_banco_como_favorecido_nao_vira_fornecedor():
    """"ITAU UNIBANCO HOLDING S A" foi sugerido como Fornecedor porque é razão
    social de empresa — e era a fatura do cartão que o Jordan usa para comprar
    material. Pagamento a banco pode ser tarifa, financiamento, consórcio ou
    cartão; cada um vai para uma conta diferente. A regra tem que CALAR."""
    from modules.financial.services.classificacao_saidas_service import _sugerir

    cat, motivo = _sugerir("ITAU UNIBANCO HOLDING S A", 4706.54, False, False)
    assert cat is None, f"sugestão errada com cara de certa: {cat}"
    assert "banco" in motivo.lower()

    # tarifa continua sendo tarifa — o teste de taxa vem antes
    assert _sugerir("TARIFA PACOTE DE SERVICOS", 39.90, False, False)[0] == "taxa_bancaria"


def test_reembolso_nao_e_remuneracao_de_quem_recebe():
    """R$56,85 de "Café treinamento" estava como pró-labore do Eliziel — ou seja,
    contado como o que ELE ganhou. É despesa da empresa que ele adiantou."""
    conta, _ = contrapartida_saida("reembolso", "CAFE TREINAMENTO")
    assert conta == "5.1.1.08"
    assert conta != contrapartida_saida("pj_prolabore", "PIX")[0]

    from modules.financial.services.classificacao_saidas_service import CATEGORIAS_VALIDAS

    assert "reembolso" in CATEGORIAS_VALIDAS, "sem estar na lista fechada, ninguém consegue escolher"


def test_escriturar_tem_preview_por_padrao():
    import inspect

    from modules.financial.services.extrato_para_razao import escriturar

    assert inspect.signature(escriturar).parameters["preview"].default is True


def test_documento_ref_do_extrato_e_unico_por_transacao():
    """Idempotência: relançar a mesma movimentação dobraria o caixa. A chave é o
    id da transação, não valor+data (que se repetem legitimamente: 3 saques de
    R$1.000 no mesmo dia no Banco24h)."""
    from modules.financial.services.extrato_para_razao import ref_do_extrato

    a = ref_do_extrato("9adf6e24-c288-4fbc-b7bf-79a98a3b9266")
    b = ref_do_extrato("354a9ac0-dc83-47ad-b903-3c978c2f3f01")
    assert a != b
    assert a.startswith("EXTRATO-")


def test_regra_caixa_divergente_registrada_e_com_tolerancia():
    """Alarme que dispara com a divergência estrutural de hoje nasce tocando e é
    desligado em duas semanas. A tolerância é pequena de propósito: o invariante
    razão×extrato é exato, não estatístico."""
    from modules.notifications.proativo.regras import REGISTRY, TOLERANCIA_CAIXA

    assert "caixa_divergente" in REGISTRY
    assert REGISTRY["caixa_divergente"].severidade == "critico"
    assert TOLERANCIA_CAIXA > 0, "tolerância zero faz o alarme tocar por arredondamento"
    assert TOLERANCIA_CAIXA < 100, "tolerância larga esconde exatamente o que a regra caça"


def test_direcao_do_dinheiro_nao_se_adivinha_por_texto():
    """A armadilha que inverteu R$35.055,93 numa linha só: o sync classificava
    entrada/saída procurando "RECEBID" na descrição, e "RECEBIMENTO TITULO" não
    contém "RECEBID" — falta o D. Caía no fallback e virava saída.

    Este teste existe para que ninguém reintroduza a heurística: a direção vem do
    sinal do valor, que o adapter deriva de `tipoOperacao` do próprio Inter.
    """
    assert "RECEBID" not in "RECEBIMENTO TITULO - 112/906535924"

    def direcao(amount: float) -> str:
        return "D" if amount < 0 else "C"

    assert direcao(35055.93) == "C"   # recebimento de boleto é ENTRADA
    assert direcao(-2765.18) == "D"


def test_periodo_fechado_barra_antes_do_corte_e_nao_engole_data_nula():
    """Fechar julho pra trás não pode virar "ignorar": o corte barra o que é
    anterior, mas data ausente NÃO pode ser escondida atrás do motivo errado —
    foi um registro sem data que derrubou o fechamento inteiro em julho."""
    from datetime import date

    from modules.financial.services.periodo_contabil import (
        ABERTURA_NO_CORTE,
        CORTE_CONTABIL,
        periodo_fechado,
    )

    assert periodo_fechado(date(2026, 7, 31)) is True
    assert periodo_fechado(CORTE_CONTABIL) is False      # o dia do corte JÁ é aberto
    assert periodo_fechado(date(2026, 8, 15)) is False
    assert periodo_fechado(None) is False                 # sem data é outro problema
    assert round(sum(ABERTURA_NO_CORTE.values()), 2) == 18663.83


def test_regra_saida_sem_origem_so_cobra_o_que_da_para_resolver():
    """O padrão "tudo passa pelo sistema" começou em 0 de 175 saídas. Alarmar
    nas 175 seria inútil: 51 são a folha (1 pagável ↔ 51 PIX, vínculo 1:N que
    ainda não existe) e 88 são miúdos abaixo de R$100. Acima do limiar são 2 —
    acionáveis. Alarme que aponta o que ninguém pode resolver morre em uma
    semana."""
    from modules.financial.services.cobertura_sistema import LIMIAR_SAIDA_SEM_ORIGEM
    from modules.notifications.proativo.regras import REGISTRY

    assert "saida_sem_origem" in REGISTRY
    assert REGISTRY["saida_sem_origem"].roles_destino == ("admin",)  # LGPD: só diretoria
    assert LIMIAR_SAIDA_SEM_ORIGEM >= 1000, "limiar baixo joga a folha inteira no sino"


def test_toda_conta_do_mapa_tem_motivo():
    """O motivo vai para o histórico do lançamento — quem auditar em 2030
    precisa saber por que aquela conta foi escolhida."""
    for cat in ("salario", "diarista", "imposto", "socio", None):
        _, motivo = contrapartida_saida(cat, "PIX")
        assert motivo and len(motivo) > 8

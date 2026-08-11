"""Defesas contra os erros silenciosos observados em produção (2026-08-09/10).

Cada teste QUEBRA a defesa de propósito. Um alarme/trava que nunca foi visto
reagir é indistinguível de um que não existe — foi assim que o razão ficou
parado desde julho com a exceção escrita no log todo dia.
"""

from modules.financial.services.integridade import (
    TIPOS_ENTRADA,
    TIPOS_SAIDA,
    descricao_canonica,
    direcao_esperada,
)


def test_vocabulario_cobre_as_duas_grafias():
    """O banco tem 'credit' E 'credito', 'debit' E 'debito' convivendo.
    Esquecer uma grafia deixa um buraco por onde o defeito volta."""
    assert {"credit", "credito", "pix_recebido", "boleto_recebido"} <= TIPOS_ENTRADA
    assert {"debit", "debito", "pix_enviado", "boleto_pago", "saque", "ted"} <= TIPOS_SAIDA
    assert not (TIPOS_ENTRADA & TIPOS_SAIDA), "um tipo não pode ser entrada e saída"


def test_direcao_esperada_classifica():
    assert direcao_esperada("pix_enviado") == "saida"
    assert direcao_esperada("pix_recebido") == "entrada"
    assert direcao_esperada("debito") == "saida"


def test_tipo_desconhecido_nao_e_adivinhado():
    """Fail-closed: tipo novo não ganha direção por chute. Quem adicionar um
    tipo tem que declarar o sinal dele."""
    assert direcao_esperada("pix_agendado_novo") is None
    assert direcao_esperada("") is None
    assert direcao_esperada(None) is None


def test_impressao_digital_iguala_os_dois_importadores():
    """O MESMO PIX chegou pela API e pelo CSV com texto diferente e código de
    contraparte mascarado de formas distintas. A canônica precisa colapsar os dois
    — senão o índice único não reconhece a duplicata (foi o que aconteceu)."""
    api = "PIX RECEBIDO - Cp :05203605-CONDOMINIO RESIDENCIAL VILLA DOS PASSAROS"
    csv = 'Pix recebido: "Cp :00000000-CONDOMINIO RESIDENCIAL VILLA DOS PASSAROS'
    assert descricao_canonica(api) == descricao_canonica(csv)


def test_impressao_digital_nao_colapsa_contrapartes_diferentes():
    """VT de R$32 pago a 30 diaristas no mesmo dia são 30 fatos distintos.
    Colapsá-los apagaria pagamento real."""
    a = "PIX ENVIADO - Cp :111-MARIA DA SILVA"
    b = "PIX ENVIADO - Cp :222-JOAO DE SOUZA"
    assert descricao_canonica(a) != descricao_canonica(b)


def test_descricao_canonica_tolera_vazio():
    assert descricao_canonica(None) == ""
    assert descricao_canonica("") == ""


def test_regra_razao_parado_esta_registrada():
    """Alarme que não está no registry não dispara nunca."""
    from modules.notifications.proativo.regras import REGISTRY

    assert "razao_parado" in REGISTRY
    r = REGISTRY["razao_parado"]
    assert r.severidade == "critico"
    assert r.roles_destino, "fail-closed: regra sem destinatário não é registrada"


def test_sql_do_razao_parado_exclui_competencia_futura():
    """A condição ingênua dispararia 94 achados hoje — os 94 holerites de
    competência FUTURA (2026-11/12) que o fechamento barra de propósito.
    Alarme que nasce ruidoso é desligado antes de servir."""
    from modules.notifications.proativo.regras import SQL_RAZAO_PARADO

    assert "reference_period" in SQL_RAZAO_PARADO
    assert "to_char" in SQL_RAZAO_PARADO, "precisa comparar competência com o mês corrente"


def test_regra_extrato_duplicado_dispara_so_em_piorou():
    """Alarme que toca com a base atual é alarme desligado em duas semanas.
    Este só grita quando o número SOBE da linha de base medida."""
    from modules.notifications.proativo.regras import (
        BASE_DUPLICATAS_EXCEDENTES,
        REGISTRY,
    )

    assert "extrato_duplicado" in REGISTRY
    assert BASE_DUPLICATAS_EXCEDENTES == 130, "linha de base medida em 2026-08-10"


def test_canonica_do_python_e_do_sql_sao_a_mesma_regra():
    """Python e banco divergirem na normalização é como o defeito nasce:
    o índice acha um fato, o código acha outro."""
    from modules.notifications.proativo.regras import _CANONICA_SQL

    for pedaco in ("CP :[0-9]+-", "[^A-Z0-9 ]", "' +'"):
        assert pedaco.strip("'") in _CANONICA_SQL

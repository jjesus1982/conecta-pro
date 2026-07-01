"""
modules/fase5/cct_compliance/enums.py - CCT Enums
=================================================
Enumeracoes para compliance CCT SINDCOND 2026
"""

from enum import StrEnum


class TipoCargo(StrEnum):
    """Tipos de cargo conforme CCT SINDCOND."""

    # Portaria
    PORTEIRO = "porteiro"
    PORTEIRO_LIDER = "porteiro_lider"
    CONTROLADOR_ACESSO = "controlador_acesso"
    AGENTE_PORTARIA = "agente_portaria"
    AGENTE_PORTARIA_LIDER = "agente_portaria_lider"

    # Limpeza
    ZELADOR = "zelador"
    FAXINEIRO = "faxineiro"
    AUXILIAR_LIMPEZA = "auxiliar_limpeza"
    ENCARREGADO_LIMPEZA = "encarregado_limpeza"
    JARDINEIRO = "jardineiro"
    PISCINEIRO = "piscineiro"

    # Manutencao
    AUXILIAR_MANUTENCAO = "auxiliar_manutencao"
    ELETRICISTA = "eletricista"
    ENCANADOR = "encanador"
    PINTOR = "pintor"
    PEDREIRO = "pedreiro"
    MARCENEIRO = "marceneiro"

    # Administrativo
    SINDICO_PROFISSIONAL = "sindico_profissional"
    GERENTE_PREDIAL = "gerente_predial"
    AUXILIAR_ADMINISTRATIVO = "auxiliar_administrativo"
    RECEPCIONISTA = "recepcionista"
    SECRETARIA = "secretaria"

    # Especializado
    ASCENSORISTA = "ascensorista"
    GARAGISTA = "garagista"
    MANOBRISTA = "manobrista"
    FOLGUISTA = "folguista"
    MOTORISTA = "motorista"

    # Supervisao
    SUPERVISOR_PORTARIA = "supervisor_portaria"
    SUPERVISOR_LIMPEZA = "supervisor_limpeza"
    SUPERVISOR_MANUTENCAO = "supervisor_manutencao"
    ENCARREGADO_GERAL = "encarregado_geral"

    # Outros
    CASEIRO = "caseiro"
    GOVERNANTA = "governanta"
    COPEIRA = "copeira"
    COZINHEIRA = "cozinheira"


class TipoJornada(StrEnum):
    """Tipos de jornada de trabalho."""

    JORNADA_44H = "44h_semanais"
    ESCALA_12X36 = "12x36"
    ESCALA_6X1 = "6x1"
    ESCALA_5X2 = "5x2"
    MEIO_PERIODO = "meio_periodo"
    INTERMITENTE = "intermitente"


class TipoBeneficio(StrEnum):
    """Tipos de beneficio CCT."""

    VALE_ALIMENTACAO = "vale_alimentacao"
    VALE_REFEICAO = "vale_refeicao"
    VALE_TRANSPORTE = "vale_transporte"
    CESTA_BASICA = "cesta_basica"
    ASSISTENCIA_MEDICA = "assistencia_medica"
    ASSISTENCIA_ODONTOLOGICA = "assistencia_odontologica"
    SEGURO_VIDA = "seguro_vida"
    ADICIONAL_NOTURNO = "adicional_noturno"
    ADICIONAL_PERICULOSIDADE = "adicional_periculosidade"
    ADICIONAL_INSALUBRIDADE = "adicional_insalubridade"
    HORA_EXTRA = "hora_extra"
    DSR = "descanso_semanal_remunerado"
    FERIAS = "ferias"
    DECIMO_TERCEIRO = "decimo_terceiro"


class StatusValidacao(StrEnum):
    """Status de validacao CCT."""

    CONFORME = "conforme"
    NAO_CONFORME = "nao_conforme"
    PENDENTE = "pendente"
    ALERTA = "alerta"
    ERRO = "erro"


class GrauInsalubridade(StrEnum):
    """Graus de insalubridade."""

    MINIMO = "minimo"  # 10%
    MEDIO = "medio"  # 20%
    MAXIMO = "maximo"  # 40%


class GrauPericulosidade(StrEnum):
    """Grau de periculosidade."""

    PADRAO = "padrao"  # 30%

"""
Tipos de eventos do modulo Gestao de Pessoas.
Todos os eventos seguem o padrao: gp.{dominio}.{acao}
"""

from enum import StrEnum


class GPEventTypes(StrEnum):
    """Todos os tipos de eventos de Gestao de Pessoas."""

    # Documento
    DOCUMENTO_CRIADO = "gp.documento.criado"
    DOCUMENTO_ASSINADO = "gp.documento.assinado"
    DOCUMENTO_ARQUIVADO = "gp.documento.arquivado"
    DOCUMENTO_ENVIADO = "gp.documento.enviado"
    DOCUMENTO_REJEITADO = "gp.documento.rejeitado"

    # Ponto
    PONTO_BATIDO = "gp.ponto.batido"
    PONTO_ATRASO = "gp.ponto.atraso"
    PONTO_FALTA = "gp.ponto.falta"
    PONTO_HORA_EXTRA = "gp.ponto.hora_extra"
    PONTO_JUSTIFICADO = "gp.ponto.justificado"
    PONTO_MES_FECHADO = "gp.ponto.mes_fechado"
    PONTO_SYNC_INICIADO = "gp.ponto.sync_iniciado"
    PONTO_SYNC_CONCLUIDO = "gp.ponto.sync_concluido"

    # Folha
    FOLHA_CALCULADA = "gp.folha.calculada"
    FOLHA_CONFERIDA = "gp.folha.conferida"
    FOLHA_FECHADA = "gp.folha.fechada"
    FOLHA_EXPORTADA = "gp.folha.exportada"

    # Funcionario
    FUNCIONARIO_ADMITIDO = "gp.funcionario.admitido"
    FUNCIONARIO_DEMITIDO = "gp.funcionario.demitido"
    FUNCIONARIO_PROMOVIDO = "gp.funcionario.promovido"
    FUNCIONARIO_TRANSFERIDO = "gp.funcionario.transferido"
    FUNCIONARIO_ATUALIZADO = "gp.funcionario.atualizado"
    FUNCIONARIO_FOTO_ATUALIZADA = "gp.funcionario.foto_atualizada"

    # Escala
    ESCALA_CRIADA = "gp.escala.criada"
    ESCALA_PUBLICADA = "gp.escala.publicada"
    ESCALA_ALTERADA = "gp.escala.alterada"

    # Disciplinar
    ADVERTENCIA_APLICADA = "gp.disciplinar.advertencia"
    SUSPENSAO_APLICADA = "gp.disciplinar.suspensao"
    OCORRENCIA_REGISTRADA = "gp.disciplinar.ocorrencia"

    # Treinamento
    TREINAMENTO_AGENDADO = "gp.treinamento.agendado"
    TREINAMENTO_REALIZADO = "gp.treinamento.realizado"
    CERTIFICADO_EMITIDO = "gp.treinamento.certificado"

    # SST
    ASO_AGENDADO = "gp.sst.aso_agendado"
    ASO_REALIZADO = "gp.sst.aso_realizado"
    ASO_VENCENDO = "gp.sst.aso_vencendo"
    EPI_ENTREGUE = "gp.sst.epi_entregue"
    EPI_VENCENDO = "gp.sst.epi_vencendo"
    LAUDO_EMITIDO = "gp.sst.laudo_emitido"
    CAT_ABERTA = "gp.sst.cat_aberta"

    # Kit Documental
    KIT_MONTADO = "gp.kit.montado"
    KIT_ENVIADO = "gp.kit.enviado"
    KIT_APROVADO = "gp.kit.aprovado"
    KIT_REJEITADO = "gp.kit.rejeitado"

    # Notificacao
    NOTIFICACAO_ENVIADA = "gp.notificacao.enviada"
    NOTIFICACAO_LIDA = "gp.notificacao.lida"

    # Sync
    SYNC_INICIADO = "gp.sync.iniciado"
    SYNC_PROGRESSO = "gp.sync.progresso"
    SYNC_CONCLUIDO = "gp.sync.concluido"
    SYNC_ERRO = "gp.sync.erro"

    # Orchestrator
    ORCHESTRATOR_ROUTED = "gp.orchestrator.routed"
    ORCHESTRATOR_CONFLICT = "gp.orchestrator.conflict"
    ORCHESTRATOR_RESOLVED = "gp.orchestrator.resolved"
    ORCHESTRATOR_ALERT = "gp.orchestrator.alert"

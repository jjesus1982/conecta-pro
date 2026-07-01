"""Testes para o modulo de Kits Documentais."""

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from modules.document_kits.models.document_kit import (
    AssignmentStatus,
    DocumentKit,
    DocumentKitAssignment,
    DocumentKitItem,
    DocumentKitItemStatus,
    EntityType,
    ItemPriority,
    ItemStatusEnum,
    ItemType,
    KitStatus,
    KitType,
)


class TestDocumentKitModel:
    """Testes para DocumentKit model."""

    def test_create_kit(self):
        """Testa criacao de kit."""
        kit = DocumentKit(
            id=uuid4(),
            condominio_id=uuid4(),
            codigo="KIT-ADM-001",
            nome="Kit Admissao Vigilante",
            descricao="Documentos para admissao de vigilante",
            tipo=KitType.ADMISSAO,
            status=KitStatus.RASCUNHO,
            prazo_dias=30,
        )

        assert kit.codigo == "KIT-ADM-001"
        assert kit.nome == "Kit Admissao Vigilante"
        assert kit.tipo == KitType.ADMISSAO
        assert kit.status == KitStatus.RASCUNHO
        assert kit.prazo_dias == 30

    def test_kit_is_ativo(self):
        """Testa propriedade is_ativo."""
        kit = DocumentKit(
            id=uuid4(),
            condominio_id=uuid4(),
            codigo="KIT-001",
            nome="Kit Teste",
            status=KitStatus.ATIVO,
        )

        assert kit.is_ativo is True

        kit.status = KitStatus.INATIVO
        assert kit.is_ativo is False

    def test_kit_ativar(self):
        """Testa ativacao de kit."""
        kit = DocumentKit(
            id=uuid4(),
            condominio_id=uuid4(),
            codigo="KIT-001",
            nome="Kit Teste",
            status=KitStatus.RASCUNHO,
        )

        kit.ativar()
        assert kit.status == KitStatus.ATIVO

    def test_kit_desativar(self):
        """Testa desativacao de kit."""
        kit = DocumentKit(
            id=uuid4(),
            condominio_id=uuid4(),
            codigo="KIT-001",
            nome="Kit Teste",
            status=KitStatus.ATIVO,
        )

        kit.desativar()
        assert kit.status == KitStatus.INATIVO

    def test_kit_arquivar(self):
        """Testa arquivamento de kit."""
        kit = DocumentKit(
            id=uuid4(),
            condominio_id=uuid4(),
            codigo="KIT-001",
            nome="Kit Teste",
            status=KitStatus.ATIVO,
        )

        kit.arquivar()
        assert kit.status == KitStatus.ARQUIVADO

    def test_kit_incrementar_uso(self):
        """Testa incremento de uso."""
        kit = DocumentKit(
            id=uuid4(),
            condominio_id=uuid4(),
            codigo="KIT-001",
            nome="Kit Teste",
            uso_count=5,
        )

        kit.incrementar_uso()
        assert kit.uso_count == 6

    def test_kit_percentual_obrigatorio(self):
        """Testa calculo de percentual obrigatorio."""
        kit = DocumentKit(
            id=uuid4(),
            condominio_id=uuid4(),
            codigo="KIT-001",
            nome="Kit Teste",
            total_itens=10,
            itens_obrigatorios=7,
        )

        assert kit.percentual_obrigatorio == 70.0

    def test_kit_percentual_obrigatorio_zero(self):
        """Testa percentual quando nao ha itens."""
        kit = DocumentKit(
            id=uuid4(),
            condominio_id=uuid4(),
            codigo="KIT-001",
            nome="Kit Teste",
            total_itens=0,
            itens_obrigatorios=0,
        )

        assert kit.percentual_obrigatorio == 0.0


class TestDocumentKitItemModel:
    """Testes para DocumentKitItem model."""

    def test_create_item(self):
        """Testa criacao de item."""
        item = DocumentKitItem(
            id=uuid4(),
            kit_id=uuid4(),
            condominio_id=uuid4(),
            codigo="DOC-RG",
            nome="RG ou CNH",
            descricao="Documento de identificacao",
            tipo=ItemType.DOCUMENTO_PESSOAL,
            prioridade=ItemPriority.OBRIGATORIO,
            ordem=1,
        )

        assert item.codigo == "DOC-RG"
        assert item.nome == "RG ou CNH"
        assert item.tipo == ItemType.DOCUMENTO_PESSOAL
        assert item.prioridade == ItemPriority.OBRIGATORIO

    def test_item_is_obrigatorio(self):
        """Testa propriedade is_obrigatorio."""
        item = DocumentKitItem(
            id=uuid4(),
            kit_id=uuid4(),
            condominio_id=uuid4(),
            codigo="DOC-001",
            nome="Documento",
            prioridade=ItemPriority.OBRIGATORIO,
        )

        assert item.is_obrigatorio is True

        item.prioridade = ItemPriority.OPCIONAL
        assert item.is_obrigatorio is False

    def test_item_formatos_display(self):
        """Testa formatos para exibicao."""
        item = DocumentKitItem(
            id=uuid4(),
            kit_id=uuid4(),
            condominio_id=uuid4(),
            codigo="DOC-001",
            nome="Documento",
            formatos_aceitos=["pdf", "jpg", "png"],
        )

        assert item.formatos_display == "pdf, jpg, png"

    def test_item_formatos_display_empty(self):
        """Testa formatos quando vazio."""
        item = DocumentKitItem(
            id=uuid4(),
            kit_id=uuid4(),
            condominio_id=uuid4(),
            codigo="DOC-001",
            nome="Documento",
            formatos_aceitos=[],
        )

        assert item.formatos_display == "Todos"


class TestDocumentKitAssignmentModel:
    """Testes para DocumentKitAssignment model."""

    def test_create_assignment(self):
        """Testa criacao de atribuicao."""
        assignment = DocumentKitAssignment(
            id=uuid4(),
            kit_id=uuid4(),
            condominio_id=uuid4(),
            entity_type=EntityType.FUNCIONARIO,
            entity_id=uuid4(),
            entity_nome="Joao Silva",
            status=AssignmentStatus.PENDENTE,
            data_inicio=datetime.utcnow(),
            data_limite=datetime.utcnow() + timedelta(days=30),
        )

        assert assignment.entity_type == EntityType.FUNCIONARIO
        assert assignment.entity_nome == "Joao Silva"
        assert assignment.status == AssignmentStatus.PENDENTE

    def test_assignment_is_completo(self):
        """Testa propriedade is_completo."""
        assignment = DocumentKitAssignment(
            id=uuid4(),
            kit_id=uuid4(),
            condominio_id=uuid4(),
            entity_type=EntityType.FUNCIONARIO,
            entity_id=uuid4(),
            status=AssignmentStatus.COMPLETO,
        )

        assert assignment.is_completo is True

        assignment.status = AssignmentStatus.PENDENTE
        assert assignment.is_completo is False

    def test_assignment_is_vencido(self):
        """Testa propriedade is_vencido."""
        assignment = DocumentKitAssignment(
            id=uuid4(),
            kit_id=uuid4(),
            condominio_id=uuid4(),
            entity_type=EntityType.FUNCIONARIO,
            entity_id=uuid4(),
            status=AssignmentStatus.PENDENTE,
            data_limite=datetime.utcnow() - timedelta(days=1),
        )

        assert assignment.is_vencido is True

    def test_assignment_dias_restantes(self):
        """Testa calculo de dias restantes."""
        assignment = DocumentKitAssignment(
            id=uuid4(),
            kit_id=uuid4(),
            condominio_id=uuid4(),
            entity_type=EntityType.FUNCIONARIO,
            entity_id=uuid4(),
            data_limite=datetime.utcnow() + timedelta(days=10),
        )

        assert assignment.dias_restantes >= 9

    def test_assignment_iniciar(self):
        """Testa inicio de atribuicao."""
        assignment = DocumentKitAssignment(
            id=uuid4(),
            kit_id=uuid4(),
            condominio_id=uuid4(),
            entity_type=EntityType.FUNCIONARIO,
            entity_id=uuid4(),
            status=AssignmentStatus.PENDENTE,
        )

        assignment.iniciar()
        assert assignment.status == AssignmentStatus.EM_ANDAMENTO

    def test_assignment_aprovar(self):
        """Testa aprovacao de atribuicao."""
        assignment = DocumentKitAssignment(
            id=uuid4(),
            kit_id=uuid4(),
            condominio_id=uuid4(),
            entity_type=EntityType.FUNCIONARIO,
            entity_id=uuid4(),
            status=AssignmentStatus.EM_ANALISE,
        )

        aprovador_id = str(uuid4())
        assignment.aprovar(aprovador_id)

        assert assignment.status == AssignmentStatus.APROVADO
        assert assignment.approved_by == aprovador_id

    def test_assignment_reprovar(self):
        """Testa reprovacao de atribuicao."""
        assignment = DocumentKitAssignment(
            id=uuid4(),
            kit_id=uuid4(),
            condominio_id=uuid4(),
            entity_type=EntityType.FUNCIONARIO,
            entity_id=uuid4(),
            status=AssignmentStatus.EM_ANALISE,
        )

        assignment.reprovar("Documentos incompletos")

        assert assignment.status == AssignmentStatus.REPROVADO
        assert assignment.motivo_reprovacao == "Documentos incompletos"

    def test_assignment_completar(self):
        """Testa conclusao de atribuicao."""
        assignment = DocumentKitAssignment(
            id=uuid4(),
            kit_id=uuid4(),
            condominio_id=uuid4(),
            entity_type=EntityType.FUNCIONARIO,
            entity_id=uuid4(),
            status=AssignmentStatus.EM_ANDAMENTO,
        )

        assignment.completar()

        assert assignment.status == AssignmentStatus.COMPLETO
        assert assignment.percentual_completo == 100
        assert assignment.data_conclusao is not None

    def test_assignment_cancelar(self):
        """Testa cancelamento de atribuicao."""
        assignment = DocumentKitAssignment(
            id=uuid4(),
            kit_id=uuid4(),
            condominio_id=uuid4(),
            entity_type=EntityType.FUNCIONARIO,
            entity_id=uuid4(),
            status=AssignmentStatus.PENDENTE,
        )

        assignment.cancelar()
        assert assignment.status == AssignmentStatus.CANCELADO

    def test_assignment_calcular_progresso(self):
        """Testa calculo de progresso."""
        assignment = DocumentKitAssignment(
            id=uuid4(),
            kit_id=uuid4(),
            condominio_id=uuid4(),
            entity_type=EntityType.FUNCIONARIO,
            entity_id=uuid4(),
            total_itens=10,
            itens_aprovados=7,
        )

        assignment.calcular_progresso()
        assert assignment.percentual_completo == 70

    def test_assignment_registrar_notificacao(self):
        """Testa registro de notificacao."""
        assignment = DocumentKitAssignment(
            id=uuid4(),
            kit_id=uuid4(),
            condominio_id=uuid4(),
            entity_type=EntityType.FUNCIONARIO,
            entity_id=uuid4(),
            notificacoes_count=2,
        )

        assignment.registrar_notificacao()

        assert assignment.notificacao_enviada is True
        assert assignment.notificacoes_count == 3
        assert assignment.ultima_notificacao_at is not None


class TestDocumentKitItemStatusModel:
    """Testes para DocumentKitItemStatus model."""

    def test_create_item_status(self):
        """Testa criacao de status de item."""
        item_status = DocumentKitItemStatus(
            id=uuid4(),
            assignment_id=uuid4(),
            item_id=uuid4(),
            condominio_id=uuid4(),
            status=ItemStatusEnum.PENDENTE,
        )

        assert item_status.status == ItemStatusEnum.PENDENTE

    def test_item_status_is_aprovado(self):
        """Testa propriedade is_aprovado."""
        item_status = DocumentKitItemStatus(
            id=uuid4(),
            assignment_id=uuid4(),
            item_id=uuid4(),
            condominio_id=uuid4(),
            status=ItemStatusEnum.APROVADO,
        )

        assert item_status.is_aprovado is True

    def test_item_status_is_pendente(self):
        """Testa propriedade is_pendente."""
        item_status = DocumentKitItemStatus(
            id=uuid4(),
            assignment_id=uuid4(),
            item_id=uuid4(),
            condominio_id=uuid4(),
            status=ItemStatusEnum.PENDENTE,
        )

        assert item_status.is_pendente is True

    def test_item_status_precisa_reenvio(self):
        """Testa propriedade precisa_reenvio."""
        item_status = DocumentKitItemStatus(
            id=uuid4(),
            assignment_id=uuid4(),
            item_id=uuid4(),
            condominio_id=uuid4(),
            status=ItemStatusEnum.REPROVADO,
        )

        assert item_status.precisa_reenvio is True

    def test_item_status_enviar(self):
        """Testa envio de documento."""
        item_status = DocumentKitItemStatus(
            id=uuid4(),
            assignment_id=uuid4(),
            item_id=uuid4(),
            condominio_id=uuid4(),
            status=ItemStatusEnum.PENDENTE,
            tentativas=0,
        )

        enviado_por = str(uuid4())
        item_status.enviar(
            arquivo_url="https://storage.example.com/doc.pdf",
            arquivo_nome="rg.pdf",
            enviado_por=enviado_por,
        )

        assert item_status.status == ItemStatusEnum.ENVIADO
        assert item_status.arquivo_url == "https://storage.example.com/doc.pdf"
        assert item_status.arquivo_nome == "rg.pdf"
        assert item_status.tentativas == 1
        assert item_status.enviado_at is not None

    def test_item_status_analisar(self):
        """Testa marcacao de analise."""
        item_status = DocumentKitItemStatus(
            id=uuid4(),
            assignment_id=uuid4(),
            item_id=uuid4(),
            condominio_id=uuid4(),
            status=ItemStatusEnum.ENVIADO,
        )

        item_status.analisar()
        assert item_status.status == ItemStatusEnum.EM_ANALISE

    def test_item_status_aprovar(self):
        """Testa aprovacao de documento."""
        item_status = DocumentKitItemStatus(
            id=uuid4(),
            assignment_id=uuid4(),
            item_id=uuid4(),
            condominio_id=uuid4(),
            status=ItemStatusEnum.EM_ANALISE,
        )

        analisado_por = str(uuid4())
        item_status.aprovar(analisado_por, "Documento OK")

        assert item_status.status == ItemStatusEnum.APROVADO
        assert item_status.analisado_por == analisado_por
        assert item_status.observacoes_analise == "Documento OK"
        assert item_status.analisado_at is not None

    def test_item_status_reprovar(self):
        """Testa reprovacao de documento."""
        item_status = DocumentKitItemStatus(
            id=uuid4(),
            assignment_id=uuid4(),
            item_id=uuid4(),
            condominio_id=uuid4(),
            status=ItemStatusEnum.EM_ANALISE,
        )

        analisado_por = str(uuid4())
        item_status.reprovar(analisado_por, "Documento ilegivel")

        assert item_status.status == ItemStatusEnum.REPROVADO
        assert item_status.motivo_reprovacao == "Documento ilegivel"

    def test_item_status_marcar_vencido(self):
        """Testa marcacao de vencido."""
        item_status = DocumentKitItemStatus(
            id=uuid4(),
            assignment_id=uuid4(),
            item_id=uuid4(),
            condominio_id=uuid4(),
            status=ItemStatusEnum.APROVADO,
        )

        item_status.marcar_vencido()

        assert item_status.status == ItemStatusEnum.VENCIDO
        assert item_status.is_vencido is True

    def test_item_status_marcar_nao_aplicavel(self):
        """Testa marcacao de nao aplicavel."""
        item_status = DocumentKitItemStatus(
            id=uuid4(),
            assignment_id=uuid4(),
            item_id=uuid4(),
            condominio_id=uuid4(),
            status=ItemStatusEnum.PENDENTE,
        )

        item_status.marcar_nao_aplicavel("Funcionario nao possui veiculo")

        assert item_status.status == ItemStatusEnum.NAO_APLICAVEL

    def test_item_status_historico(self):
        """Testa registro de historico."""
        item_status = DocumentKitItemStatus(
            id=uuid4(),
            assignment_id=uuid4(),
            item_id=uuid4(),
            condominio_id=uuid4(),
            status=ItemStatusEnum.PENDENTE,
            historico=[],
            tentativas=0,
        )

        enviado_por = str(uuid4())
        item_status.enviar("url", "arquivo.pdf", enviado_por)
        item_status.analisar()

        assert len(item_status.historico) == 2
        assert item_status.historico[0]["acao"] == "ENVIADO"
        assert item_status.historico[1]["acao"] == "EM_ANALISE"


class TestKitEnums:
    """Testes para enums de Kit."""

    def test_kit_type_values(self):
        """Testa valores do enum KitType."""
        assert KitType.ADMISSAO.value == "ADMISSAO"
        assert KitType.DEMISSAO.value == "DEMISSAO"
        assert KitType.PORTARIA.value == "PORTARIA"
        assert KitType.CONTRATO_CLIENTE.value == "CONTRATO_CLIENTE"

    def test_kit_status_values(self):
        """Testa valores do enum KitStatus."""
        assert KitStatus.RASCUNHO.value == "RASCUNHO"
        assert KitStatus.ATIVO.value == "ATIVO"
        assert KitStatus.INATIVO.value == "INATIVO"
        assert KitStatus.ARQUIVADO.value == "ARQUIVADO"

    def test_item_type_values(self):
        """Testa valores do enum ItemType."""
        assert ItemType.DOCUMENTO_PESSOAL.value == "DOCUMENTO_PESSOAL"
        assert ItemType.CERTIFICADO.value == "CERTIFICADO"
        assert ItemType.CONTRATO.value == "CONTRATO"

    def test_item_priority_values(self):
        """Testa valores do enum ItemPriority."""
        assert ItemPriority.OBRIGATORIO.value == "OBRIGATORIO"
        assert ItemPriority.IMPORTANTE.value == "IMPORTANTE"
        assert ItemPriority.DESEJAVEL.value == "DESEJAVEL"
        assert ItemPriority.OPCIONAL.value == "OPCIONAL"

    def test_assignment_status_values(self):
        """Testa valores do enum AssignmentStatus."""
        assert AssignmentStatus.PENDENTE.value == "PENDENTE"
        assert AssignmentStatus.EM_ANDAMENTO.value == "EM_ANDAMENTO"
        assert AssignmentStatus.COMPLETO.value == "COMPLETO"
        assert AssignmentStatus.CANCELADO.value == "CANCELADO"

    def test_item_status_values(self):
        """Testa valores do enum ItemStatusEnum."""
        assert ItemStatusEnum.PENDENTE.value == "PENDENTE"
        assert ItemStatusEnum.ENVIADO.value == "ENVIADO"
        assert ItemStatusEnum.APROVADO.value == "APROVADO"
        assert ItemStatusEnum.REPROVADO.value == "REPROVADO"

    def test_entity_type_values(self):
        """Testa valores do enum EntityType."""
        assert EntityType.FUNCIONARIO.value == "FUNCIONARIO"
        assert EntityType.CANDIDATO.value == "CANDIDATO"
        assert EntityType.CONTRATO.value == "CONTRATO"
        assert EntityType.EQUIPAMENTO.value == "EQUIPAMENTO"

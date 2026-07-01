"""Service de IA para Kits Documentais - Versão Async."""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from modules.document_kits.models.document_kit import (
    AssignmentStatus,
    DocumentKit,
    DocumentKitAssignment,
    EntityType,
    KitStatus,
    KitType,
)
from modules.document_kits.repositories.kit_repository import DocumentKitRepository


class DocumentKitAIService:
    """Service de IA para Kits Documentais."""

    def __init__(self, db: AsyncSession):
        """Inicializa service."""
        self.db = db
        self.repository = DocumentKitRepository(db)

    async def suggest_kits_for_entity(
        self,
        condominio_id: UUID,
        entity_type: EntityType,
        entity_data: dict,
    ) -> list[dict]:
        """Sugere kits para uma entidade baseado em seu perfil."""
        kits = await self.repository.list_kits(
            condominio_id=condominio_id,
            status=KitStatus.ATIVO,
        )

        suggestions = []
        for kit in kits:
            score = self._calculate_relevance_score(kit, entity_type, entity_data)
            if score > 0:
                suggestions.append(
                    {
                        "kit_id": str(kit.id),
                        "kit_nome": kit.nome,
                        "kit_tipo": kit.tipo.value,
                        "relevancia_score": round(score, 2),
                        "motivo": self._get_suggestion_reason(kit, entity_type),
                        "itens_count": kit.total_itens,
                        "prazo_sugerido_dias": kit.prazo_dias or 30,
                    }
                )

        suggestions.sort(key=lambda x: x["relevancia_score"], reverse=True)
        return suggestions[:10]

    def _calculate_relevance_score(
        self,
        kit: DocumentKit,
        entity_type: EntityType,
        entity_data: dict,
    ) -> float:
        """Calcula score de relevancia do kit para a entidade."""
        score = 0.0

        if entity_type.value in (kit.entity_types or []):
            score += 40.0

        if (
            kit.tipo == KitType.ADMISSAO
            and entity_type == EntityType.FUNCIONARIO
            or kit.tipo == KitType.CONTRATO_CLIENTE
            and entity_type == EntityType.CONTRATO
        ):
            score += 30.0
        elif kit.tipo == KitType.PORTARIA and entity_type == EntityType.FUNCIONARIO:
            cargo = entity_data.get("cargo", "").lower()
            if "porteiro" in cargo or "portaria" in cargo or "controlador" in cargo:
                score += 35.0
        elif kit.tipo == KitType.TREINAMENTO and entity_type == EntityType.TREINAMENTO:
            score += 30.0

        departamento = entity_data.get("departamento", "")
        if departamento and departamento in (kit.departamentos or []):
            score += 15.0

        cargo = entity_data.get("cargo", "")
        if cargo and cargo in (kit.cargos or []):
            score += 15.0

        if kit.is_obrigatorio:
            score += 10.0

        return min(score, 100.0)

    def _get_suggestion_reason(
        self,
        kit: DocumentKit,
        entity_type: EntityType,
    ) -> str:
        """Retorna motivo da sugestao."""
        reasons = {
            (KitType.ADMISSAO, EntityType.FUNCIONARIO): ("Kit obrigatorio para admissao de funcionarios"),
            (KitType.DEMISSAO, EntityType.FUNCIONARIO): ("Kit necessario para processo de desligamento"),
            (KitType.CONTRATO_CLIENTE, EntityType.CONTRATO): ("Documentacao essencial para formalizacao do contrato"),
            (KitType.PORTARIA, EntityType.FUNCIONARIO): ("Documentos especificos para funcao de agente de portaria"),
            (KitType.TREINAMENTO, EntityType.TREINAMENTO): ("Comprovantes necessarios para registro de treinamento"),
            (KitType.EQUIPAMENTO, EntityType.EQUIPAMENTO): ("Termos e registros para controle de equipamentos"),
        }

        key = (kit.tipo, entity_type)
        if key in reasons:
            return reasons[key]

        if kit.is_obrigatorio:
            return "Kit marcado como obrigatorio"
        return "Kit recomendado baseado no perfil"

    async def analyze_compliance_risk(
        self,
        condominio_id: UUID,
        entity_type: EntityType,
        entity_id: UUID,
    ) -> dict:
        """Analisa risco de conformidade de uma entidade."""
        assignments = await self.repository.list_assignments(
            condominio_id=condominio_id,
            entity_type=entity_type,
            entity_id=entity_id,
        )

        if not assignments:
            return {
                "risk_level": "unknown",
                "risk_score": 0,
                "issues": ["Nenhum kit atribuido"],
                "recommendations": ["Verificar kits aplicaveis"],
            }

        issues = []
        risk_score = 0

        vencidos = [a for a in assignments if a.is_vencido]
        if vencidos:
            risk_score += 40
            issues.append(f"{len(vencidos)} kit(s) com prazo vencido")

        incompletos = [
            a
            for a in assignments
            if a.status
            in (
                AssignmentStatus.PENDENTE,
                AssignmentStatus.EM_ANDAMENTO,
                AssignmentStatus.AGUARDANDO_DOCUMENTOS,
            )
        ]
        if incompletos:
            risk_score += 20
            issues.append(f"{len(incompletos)} kit(s) incompleto(s)")

        reprovados = [a for a in assignments if a.status == AssignmentStatus.REPROVADO]
        if reprovados:
            risk_score += 30
            issues.append(f"{len(reprovados)} kit(s) reprovado(s)")

        proximos_vencer = [
            a
            for a in assignments
            if a.data_limite and a.data_limite < datetime.utcnow() + timedelta(days=7) and not a.is_completo
        ]
        if proximos_vencer:
            risk_score += 10
            issues.append(f"{len(proximos_vencer)} kit(s) proximo(s) do vencimento")

        risk_level = self._get_risk_level(risk_score)

        recommendations = self._generate_recommendations(vencidos, incompletos, reprovados, proximos_vencer)

        return {
            "risk_level": risk_level,
            "risk_score": min(risk_score, 100),
            "total_kits": len(assignments),
            "kits_completos": sum(1 for a in assignments if a.status == AssignmentStatus.COMPLETO),
            "kits_vencidos": len(vencidos),
            "kits_incompletos": len(incompletos),
            "kits_reprovados": len(reprovados),
            "issues": issues,
            "recommendations": recommendations,
        }

    def _get_risk_level(self, score: int) -> str:
        """Retorna nivel de risco baseado no score."""
        if score >= 70:
            return "critical"
        if score >= 50:
            return "high"
        if score >= 30:
            return "medium"
        if score > 0:
            return "low"
        return "ok"

    def _generate_recommendations(
        self,
        vencidos: list[DocumentKitAssignment],
        incompletos: list[DocumentKitAssignment],
        reprovados: list[DocumentKitAssignment],
        proximos_vencer: list[DocumentKitAssignment],
    ) -> list[str]:
        """Gera recomendacoes baseadas na analise."""
        recommendations = []

        if vencidos:
            recommendations.append("Priorizar regularizacao dos kits vencidos imediatamente")
        if reprovados:
            recommendations.append("Revisar e reenviar documentos reprovados")
        if proximos_vencer:
            recommendations.append("Agilizar conclusao dos kits proximos do vencimento")
        if incompletos and not vencidos:
            recommendations.append("Dar continuidade aos kits em andamento")
        if not recommendations:
            recommendations.append("Manter acompanhamento regular dos kits")

        return recommendations

    async def predict_completion_date(
        self,
        assignment: DocumentKitAssignment,
    ) -> dict:
        """Preve data de conclusao baseado no ritmo atual."""
        if assignment.percentual_completo >= 100:
            return {
                "status": "completed",
                "predicted_date": assignment.data_conclusao,
                "confidence": 100,
            }

        if assignment.percentual_completo == 0:
            days_elapsed = (datetime.utcnow() - assignment.data_inicio).days
            if days_elapsed > 0:
                return {
                    "status": "at_risk",
                    "predicted_date": None,
                    "confidence": 0,
                    "message": "Nenhum progresso registrado",
                }
            return {
                "status": "pending",
                "predicted_date": assignment.data_limite,
                "confidence": 50,
            }

        days_elapsed = (datetime.utcnow() - assignment.data_inicio).days
        if days_elapsed <= 0:
            days_elapsed = 1

        rate = assignment.percentual_completo / days_elapsed
        remaining = 100 - assignment.percentual_completo

        if rate > 0:
            days_remaining = remaining / rate
            predicted = datetime.utcnow() + timedelta(days=days_remaining)
        else:
            days_remaining = 0
            predicted = None

        confidence = min(assignment.percentual_completo, 90)

        status = "on_track"
        if predicted and assignment.data_limite:
            if predicted > assignment.data_limite:
                status = "delayed"
                confidence = max(confidence - 20, 10)

        return {
            "status": status,
            "predicted_date": predicted,
            "days_remaining": int(days_remaining) if rate > 0 else None,
            "confidence": confidence,
            "current_rate": round(rate, 2),
        }

    async def get_priority_assignments(
        self,
        condominio_id: UUID,
        limit: int = 10,
    ) -> list[dict]:
        """Retorna atribuicoes prioritarias baseado em analise."""
        assignments = await self.repository.list_assignments(
            condominio_id=condominio_id,
            status=None,
            limit=500,
        )

        active_assignments = [
            a
            for a in assignments
            if a.status
            not in (
                AssignmentStatus.COMPLETO,
                AssignmentStatus.CANCELADO,
            )
        ]

        scored = []
        for assignment in active_assignments:
            score = self._calculate_priority_score(assignment)
            scored.append(
                {
                    "assignment_id": str(assignment.id),
                    "kit_id": str(assignment.kit_id),
                    "entity_type": assignment.entity_type.value,
                    "entity_nome": assignment.entity_nome,
                    "status": assignment.status.value,
                    "priority_score": score,
                    "dias_restantes": assignment.dias_restantes,
                    "percentual_completo": assignment.percentual_completo,
                    "is_vencido": assignment.is_vencido,
                }
            )

        scored.sort(key=lambda x: x["priority_score"], reverse=True)
        return scored[:limit]

    def _calculate_priority_score(
        self,
        assignment: DocumentKitAssignment,
    ) -> float:
        """Calcula score de prioridade para uma atribuicao."""
        score = 0.0

        if assignment.is_vencido:
            score += 50.0

        if assignment.data_limite:
            days = assignment.dias_restantes
            if days <= 3:
                score += 30.0
            elif days <= 7:
                score += 20.0
            elif days <= 14:
                score += 10.0

        if assignment.itens_reprovados > 0:
            score += 15.0

        if assignment.status == AssignmentStatus.AGUARDANDO_DOCUMENTOS:
            score += 10.0

        incomplete_ratio = 1 - (assignment.percentual_completo / 100)
        score += incomplete_ratio * 10

        return min(score, 100.0)

    async def analyze_kit_usage(
        self,
        condominio_id: UUID,
    ) -> dict:
        """Analisa uso dos kits."""
        kits = await self.repository.list_kits(
            condominio_id=condominio_id,
            status=KitStatus.ATIVO,
        )

        if not kits:
            return {
                "total_kits": 0,
                "usage_analysis": [],
                "recommendations": ["Criar kits documentais para a organizacao"],
            }

        usage = []
        for kit in kits:
            assignments = await self.repository.list_assignments(
                condominio_id=condominio_id,
                kit_id=kit.id,
            )

            total = len(assignments)
            completos = sum(1 for a in assignments if a.status == AssignmentStatus.COMPLETO)
            taxa = (completos / total * 100) if total > 0 else 0

            usage.append(
                {
                    "kit_id": str(kit.id),
                    "kit_nome": kit.nome,
                    "kit_tipo": kit.tipo.value,
                    "total_atribuicoes": total,
                    "atribuicoes_completas": completos,
                    "taxa_conclusao": round(taxa, 2),
                    "uso_count": kit.uso_count,
                }
            )

        usage.sort(key=lambda x: x["taxa_conclusao"])

        recommendations = []
        low_completion = [u for u in usage if u["taxa_conclusao"] < 50 and u["total_atribuicoes"] > 0]
        if low_completion:
            recommendations.append(
                f"Revisar kits com baixa taxa de conclusao: {', '.join(u['kit_nome'] for u in low_completion[:3])}"
            )

        unused = [u for u in usage if u["uso_count"] == 0]
        if unused:
            recommendations.append(
                f"Considerar remover kits nao utilizados: {', '.join(u['kit_nome'] for u in unused[:3])}"
            )

        return {
            "total_kits": len(kits),
            "usage_analysis": usage,
            "recommendations": recommendations,
        }

    async def get_expiring_documents(
        self,
        condominio_id: UUID,
        days_ahead: int = 30,
    ) -> list[dict]:
        """Lista documentos proximos do vencimento."""
        assignments = await self.repository.list_assignments(
            condominio_id=condominio_id,
            status=AssignmentStatus.COMPLETO,
        )

        threshold = datetime.utcnow() + timedelta(days=days_ahead)
        expiring = []

        for assignment in assignments:
            item_statuses = await self.repository.list_item_statuses_by_assignment(
                assignment_id=assignment.id,
                condominio_id=condominio_id,
            )

            for item_status in item_statuses:
                if item_status.data_validade and item_status.data_validade < threshold:
                    days_until = (item_status.data_validade - datetime.utcnow()).days
                    expiring.append(
                        {
                            "item_status_id": str(item_status.id),
                            "assignment_id": str(assignment.id),
                            "entity_nome": assignment.entity_nome,
                            "entity_type": assignment.entity_type.value,
                            "arquivo_nome": item_status.arquivo_nome,
                            "data_validade": item_status.data_validade.isoformat(),
                            "dias_restantes": max(0, days_until),
                            "is_expired": days_until < 0,
                        }
                    )

        expiring.sort(key=lambda x: x["dias_restantes"])
        return expiring

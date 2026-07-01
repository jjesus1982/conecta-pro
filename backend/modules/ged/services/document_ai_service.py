"""Service de IA para Documentos."""

import logging
import re
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from modules.ged.models.document import DocumentCategory, DocumentType
from modules.ged.models.folder import FolderType
from modules.ged.repositories.document_repository import DocumentRepository
from modules.ged.repositories.document_tag_repository import DocumentTagRepository
from modules.ged.repositories.folder_repository import FolderRepository
from modules.ged.schemas.document import DocumentFilter

logger = logging.getLogger(__name__)


class DocumentAIService:
    """Service de IA para análise e classificação de documentos."""

    def __init__(self, session: AsyncSession):
        """Inicializa o service."""
        self.session = session
        self.document_repository = DocumentRepository(session)
        self.folder_repository = FolderRepository(session)
        self.tag_repository = DocumentTagRepository(session)

        # Keywords para classificação por tipo
        self.type_keywords = {
            DocumentType.CONTRATO: [
                "contrato",
                "acordo",
                "termo",
                "pacto",
                "convenção",
                "cláusula",
                "partes",
                "contratante",
                "contratado",
            ],
            DocumentType.PROPOSTA: [
                "proposta",
                "orçamento",
                "cotação",
                "oferta",
                "preço",
            ],
            DocumentType.NOTA_FISCAL: [
                "nota fiscal",
                "nf-e",
                "danfe",
                "cnpj",
                "icms",
                "ipi",
                "valor total",
                "cfop",
                "tributação",
            ],
            DocumentType.BOLETO: [
                "boleto",
                "código de barras",
                "vencimento",
                "pagamento",
                "banco",
                "cedente",
                "sacado",
                "nosso número",
            ],
            DocumentType.CERTIDAO: [
                "certidão",
                "certifica",
                "atesta",
                "negativa",
                "positiva",
                "débitos",
                "tributos",
                "regular",
            ],
            DocumentType.PROCURACAO: [
                "procuração",
                "outorgante",
                "outorgado",
                "poderes",
                "representar",
                "substabelecer",
            ],
            DocumentType.ATA: [
                "ata",
                "reunião",
                "assembleia",
                "deliberação",
                "votação",
                "presentes",
                "ordem do dia",
            ],
            DocumentType.REGULAMENTO: [
                "regulamento",
                "regimento",
                "normas",
                "convenção",
                "proibido",
                "permitido",
                "obrigatório",
            ],
            DocumentType.RELATORIO: [
                "relatório",
                "análise",
                "resultado",
                "conclusão",
                "recomendação",
                "indicadores",
            ],
            DocumentType.LAUDO: [
                "laudo",
                "perícia",
                "vistoria",
                "técnico",
                "parecer",
                "inspeção",
                "avaliação",
            ],
        }

        # Keywords para classificação por categoria
        self.category_keywords = {
            DocumentCategory.FINANCEIRO: [
                "pagamento",
                "recebimento",
                "fatura",
                "nota fiscal",
                "boleto",
                "cobrança",
                "débito",
                "crédito",
                "saldo",
            ],
            DocumentCategory.JURIDICO: [
                "contrato",
                "termo",
                "procuração",
                "advogado",
                "judicial",
                "processo",
                "ação",
                "petição",
                "sentença",
            ],
            DocumentCategory.RH: [
                "funcionário",
                "colaborador",
                "admissão",
                "demissão",
                "férias",
                "folha",
                "ponto",
                "benefício",
                "salário",
            ],
            DocumentCategory.OPERACIONAL: [
                "manutenção",
                "operação",
                "serviço",
                "ordem",
                "equipamento",
                "técnico",
                "instalação",
            ],
            DocumentCategory.TECNICO: [
                "projeto",
                "planta",
                "especificação",
                "técnico",
                "engenharia",
                "dimensionamento",
                "cálculo",
            ],
            DocumentCategory.FISCAL: [
                "imposto",
                "tributo",
                "icms",
                "iss",
                "pis",
                "cofins",
                "declaração",
                "guia",
                "recolhimento",
            ],
            DocumentCategory.SEGURANCA: [
                "segurança",
                "acesso",
                "cftv",
                "alarme",
                "portaria",
                "ocorrência",
                "incidente",
                "risco",
            ],
        }

    async def classify_document(  # pylint: disable=too-many-locals
        self, text: str, file_name: str = None
    ) -> dict:
        """Classifica documento baseado no conteúdo."""
        text_lower = text.lower() if text else ""
        file_lower = file_name.lower() if file_name else ""
        combined = f"{text_lower} {file_lower}"

        # Classifica tipo
        type_scores = {}
        for doc_type, keywords in self.type_keywords.items():
            score = sum(1 for kw in keywords if kw in combined)
            if score > 0:
                type_scores[doc_type] = score

        suggested_type = DocumentType.OUTRO
        type_confidence = 0.0
        if type_scores:
            suggested_type = max(type_scores, key=type_scores.get)
            max_score = type_scores[suggested_type]
            type_confidence = min(max_score / 5 * 100, 100)

        # Classifica categoria
        category_scores = {}
        for category, keywords in self.category_keywords.items():
            score = sum(1 for kw in keywords if kw in combined)
            if score > 0:
                category_scores[category] = score

        suggested_category = DocumentCategory.OUTRO
        category_confidence = 0.0
        if category_scores:
            suggested_category = max(category_scores, key=category_scores.get)
            max_score = category_scores[suggested_category]
            category_confidence = min(max_score / 5 * 100, 100)

        # Extrai palavras-chave
        keywords = self._extract_keywords(text)

        # Detecta datas
        dates = self._extract_dates(text)

        # Detecta valores monetários
        values = self._extract_monetary_values(text)

        # Detecta CPF/CNPJ
        documents = self._extract_documents(text)

        return {
            "suggested_type": suggested_type,
            "type_confidence": type_confidence,
            "suggested_category": suggested_category,
            "category_confidence": category_confidence,
            "keywords": keywords[:20],
            "dates_found": dates[:10],
            "values_found": values[:10],
            "documents_found": documents[:10],
            "entities": {
                "dates": len(dates),
                "values": len(values),
                "documents": len(documents),
            },
        }

    def _extract_keywords(self, text: str, min_length: int = 4) -> list[str]:
        """Extrai palavras-chave do texto."""
        if not text:
            return []

        # Remove pontuação e números
        words = re.findall(rf"\b[a-záàâãéèêíïóôõöúç]{{{min_length},}}\b", text.lower())

        # Conta frequência
        word_count = {}
        stopwords = {
            "para",
            "como",
            "com",
            "que",
            "por",
            "uma",
            "seu",
            "sua",
            "este",
            "esta",
            "esse",
            "essa",
            "aquele",
            "aquela",
            "mais",
            "menos",
            "sobre",
            "entre",
            "após",
            "antes",
        }

        for word in words:
            if word not in stopwords:
                word_count[word] = word_count.get(word, 0) + 1

        # Ordena por frequência
        sorted_words = sorted(word_count.items(), key=lambda x: x[1], reverse=True)
        return [word for word, _ in sorted_words]

    def _extract_dates(self, text: str) -> list[str]:
        """Extrai datas do texto."""
        if not text:
            return []

        patterns = [
            r"\d{2}/\d{2}/\d{4}",
            r"\d{2}-\d{2}-\d{4}",
            r"\d{2}\.\d{2}\.\d{4}",
            r"\d{4}-\d{2}-\d{2}",
        ]

        dates = []
        for pattern in patterns:
            matches = re.findall(pattern, text)
            dates.extend(matches)

        return list(set(dates))

    def _extract_monetary_values(self, text: str) -> list[str]:
        """Extrai valores monetários do texto."""
        if not text:
            return []

        patterns = [
            r"R\$\s*[\d.,]+",
            r"[\d.,]+\s*reais",
        ]

        values = []
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            values.extend(matches)

        return list(set(values))

    def _extract_documents(self, text: str) -> list[str]:
        """Extrai CPF/CNPJ do texto."""
        if not text:
            return []

        patterns = [
            r"\d{3}\.\d{3}\.\d{3}-\d{2}",  # CPF
            r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}",  # CNPJ
        ]

        docs = []
        for pattern in patterns:
            matches = re.findall(pattern, text)
            docs.extend(matches)

        return list(set(docs))

    async def analyze_ocr_result(self, document_id: str, ocr_text: str, confidence: float) -> dict:
        """Analisa resultado do OCR e atualiza documento."""
        document = await self.document_repository.get_by_id(document_id)
        if not document:
            return {"error": "Documento não encontrado"}

        # Classifica documento
        classification = await self.classify_document(ocr_text, document.file_name)

        # Extrai palavras-chave para indexação
        keywords = classification["keywords"]

        # Atualiza documento com resultado OCR
        await self.document_repository.set_ocr_result(document_id, ocr_text, confidence)
        await self.document_repository.mark_as_indexed(document_id, keywords)
        await self.session.commit()

        return {
            "document_id": document_id,
            "ocr_confidence": confidence,
            "classification": classification,
            "indexed_keywords": keywords,
            "status": "processed",
        }

    async def suggest_folder(self, document_type: DocumentType, condominium_id: str) -> str | None:
        """Sugere pasta para documento baseado no tipo."""
        # Mapeia tipo de documento para tipo de pasta
        default_folder = FolderType.DEPARTAMENTO
        proposta_folder = FolderType.COMERCIAL if hasattr(FolderType, "COMERCIAL") else default_folder
        type_folder_map = {
            DocumentType.CONTRATO: FolderType.CONTRATO,
            DocumentType.PROPOSTA: proposta_folder,
        }

        folder_type = type_folder_map.get(document_type, FolderType.DEPARTAMENTO)
        folders = await self.folder_repository.get_by_type(folder_type, condominium_id)

        if folders:
            return folders[0].id
        return None

    async def suggest_tags(self, text: str, condominium_id: str = None, limit: int = 5) -> list[dict]:
        """Sugere tags baseado no conteúdo."""
        keywords = self._extract_keywords(text)

        suggestions = []
        for keyword in keywords[:10]:
            tags = await self.tag_repository.search(keyword, condominium_id, 1)
            for tag in tags:
                suggestions.append(
                    {
                        "tag_id": tag.id,
                        "name": tag.name,
                        "match_keyword": keyword,
                        "confidence": 80,
                    }
                )

        return suggestions[:limit]

    async def find_duplicates(self, checksum: str = None, title: str = None, condominium_id: str = None) -> list[dict]:
        """Encontra documentos duplicados."""
        duplicates = []

        # Por checksum (exato)
        if checksum:
            doc = await self.document_repository.get_by_checksum(checksum)
            if doc:
                duplicates.append(
                    {
                        "document_id": doc.id,
                        "title": doc.title,
                        "match_type": "checksum_exact",
                        "confidence": 100,
                    }
                )

        # Por título similar
        if title:
            docs = await self.document_repository.search_fulltext(title, condominium_id, 5)
            for doc in docs:
                if doc.title.lower() != title.lower():
                    similarity = self._calculate_similarity(title, doc.title)
                    if similarity > 70:
                        duplicates.append(
                            {
                                "document_id": doc.id,
                                "title": doc.title,
                                "match_type": "title_similar",
                                "confidence": similarity,
                            }
                        )

        return duplicates

    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """Calcula similaridade entre strings."""
        s1_lower = str1.lower()
        s2_lower = str2.lower()

        words1 = set(s1_lower.split())
        words2 = set(s2_lower.split())

        intersection = words1 & words2
        union = words1 | words2

        if not union:
            return 0.0

        return round(len(intersection) / len(union) * 100, 2)

    async def get_insights(self, condominium_id: str = None) -> dict:
        """Retorna insights sobre documentos."""
        stats = await self.document_repository.get_stats(condominium_id)

        # Calcula tendências
        pending_approval = stats.get("pending_approval", 0)
        pending_signature = stats.get("pending_signature", 0)
        expired = stats.get("expired", 0)
        expiring_soon = stats.get("expiring_soon", 0)

        # Score de saúde documental
        total = stats.get("total_documents") or 1
        health_penalties = (
            (pending_approval / total * 20)
            + (pending_signature / total * 15)
            + (expired / total * 30)
            + (expiring_soon / total * 10)
        )
        health_score = max(0, min(100, 100 - health_penalties * 100))

        # Determina nível
        if health_score >= 90:
            health_level = "excellent"
        elif health_score >= 70:
            health_level = "good"
        elif health_score >= 50:
            health_level = "attention"
        else:
            health_level = "critical"

        # Recomendações
        recommendations = []
        if pending_approval > 5:
            recommendations.append(
                {
                    "type": "approval",
                    "priority": "high",
                    "message": f"{pending_approval} documentos aguardando aprovação",
                    "action": "Revise os documentos pendentes de aprovação",
                }
            )
        if pending_signature > 3:
            recommendations.append(
                {
                    "type": "signature",
                    "priority": "high",
                    "message": f"{pending_signature} documentos aguardando assinatura",
                    "action": "Envie lembretes aos signatários",
                }
            )
        if expired > 0:
            recommendations.append(
                {
                    "type": "expired",
                    "priority": "critical",
                    "message": f"{expired} documentos expirados",
                    "action": "Renove ou arquive documentos expirados",
                }
            )
        if expiring_soon > 0:
            recommendations.append(
                {
                    "type": "expiring",
                    "priority": "medium",
                    "message": f"{expiring_soon} documentos expirando em 30 dias",
                    "action": "Planeje renovação dos documentos",
                }
            )

        return {
            "health_score": health_score,
            "health_level": health_level,
            "stats": stats,
            "recommendations": recommendations,
            "alerts_count": len(recommendations),
        }

    async def get_trends(self, condominium_id: str = None, days: int = 30) -> dict:
        """Alias para analyze_document_trends."""
        return await self.analyze_document_trends(condominium_id, days)

    async def analyze_document_trends(  # pylint: disable=too-many-locals
        self, condominium_id: str = None, days: int = 30
    ) -> dict:
        """Analisa tendências de documentos."""
        # Busca documentos do período
        filters = None
        if condominium_id:
            filters = DocumentFilter(
                condominium_id=condominium_id,
                created_from=datetime.utcnow() - timedelta(days=days),
            )

        documents, total = await self.document_repository.list_with_filters(filters=filters, limit=1000)

        # Agrupa por dia
        by_day = {}
        by_type = {}
        by_category = {}

        for doc in documents:
            # Por dia
            day_key = doc.created_at.strftime("%Y-%m-%d")
            by_day[day_key] = by_day.get(day_key, 0) + 1

            # Por tipo
            type_key = doc.document_type.value
            by_type[type_key] = by_type.get(type_key, 0) + 1

            # Por categoria
            cat_key = doc.category.value
            by_category[cat_key] = by_category.get(cat_key, 0) + 1

        # Calcula média diária
        avg_daily = total / days if days > 0 else 0

        # Identifica pico
        peak_day = max(by_day.items(), key=lambda x: x[1]) if by_day else (None, 0)

        return {
            "period_days": days,
            "total_documents": total,
            "avg_daily": round(avg_daily, 2),
            "peak_day": peak_day[0],
            "peak_count": peak_day[1],
            "by_day": by_day,
            "by_type": by_type,
            "by_category": by_category,
            "most_common_type": (max(by_type.items(), key=lambda x: x[1])[0] if by_type else None),
            "most_common_category": (max(by_category.items(), key=lambda x: x[1])[0] if by_category else None),
        }

    async def get_dashboard(self, condominium_id: str = None) -> dict:
        """Retorna dashboard completo de documentos."""
        insights = await self.get_insights(condominium_id)
        trends = await self.analyze_document_trends(condominium_id, days=30)

        # Documentos recentes
        recent_docs, _ = await self.document_repository.list_with_filters(limit=10)

        # Documentos mais acessados
        top_docs = sorted(recent_docs, key=lambda d: d.view_count, reverse=True)[:5]

        return {
            "health": {
                "score": insights["health_score"],
                "level": insights["health_level"],
            },
            "stats": insights["stats"],
            "trends": {
                "avg_daily": trends["avg_daily"],
                "peak_day": trends["peak_day"],
                "most_common_type": trends["most_common_type"],
            },
            "alerts": insights["recommendations"],
            "top_documents": [
                {
                    "id": d.id,
                    "title": d.title,
                    "views": d.view_count,
                    "downloads": d.download_count,
                }
                for d in top_docs
            ],
        }

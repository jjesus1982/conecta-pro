"""
ASSESSOR Agent - Avaliacao Go/No-Go de licitacoes
===================================================
Avalia se a empresa deve participar de uma licitacao com base
na analise do edital e nas capacidades da empresa.
"""

import logging
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from modules.bidding.agents.base_agent import AgentConfig, AgentStatus, BaseAgent

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# DTOs
# ──────────────────────────────────────────────


class Recomendacao(StrEnum):
    """Recomendacao de participacao."""

    GO = "GO"
    NO_GO = "NO_GO"
    CONDICIONAL = "CONDICIONAL"


class CriterioAvaliacao(BaseModel):
    """Criterio individual de avaliacao."""

    nome: str
    descricao: str
    peso: float  # 0-1
    nota: float  # 0-100
    nota_ponderada: float = 0.0
    atende: bool = True
    observacao: str | None = None


class CompanyProfile(BaseModel):
    """Perfil da empresa para avaliacao de requisitos."""

    razao_social: str = "CONECTAMAIS ELETRONICA LTDA"
    cnpj: str = "35.710.481/0001-03"
    uf: str = "AM"
    municipio: str = "Manaus"

    # Regime tributario
    regime_tributario: str = "lucro_real"  # simples, lucro_real, lucro_presumido

    # Certificacoes e autorizacoes
    autorizacao_pf: bool = True  # Autorizacao da Policia Federal
    certificado_iso_9001: bool = False
    certificado_iso_14001: bool = False
    alvara_funcionamento: bool = True

    # Capacidade tecnica
    atestados_capacidade_tecnica: list[str] = Field(
        default_factory=lambda: [
            "vigilancia_patrimonial",
            "seguranca_eletronica",
            "portaria",
            "monitoramento_cftv",
        ]
    )
    # Numero de colaboradores ativos — deve vir de dado real (employees).
    # 0 = nao informado.
    quantidade_colaboradores: int = 0
    possui_base_operacional: bool = True
    cobertura_ufs: list[str] = Field(default_factory=lambda: ["AM"])

    # Capacidade economica — SEM fonte real no ERP para estes campos.
    # None = "nao informado". O scoring NAO deve penalizar valor desconhecido
    # nem fabricar numero. Preencher somente quando houver fonte confiavel
    # (balanco/contabilidade).
    capital_social: float | None = None
    patrimonio_liquido: float | None = None
    faturamento_anual: float | None = None
    indice_liquidez_corrente: float | None = None
    indice_liquidez_geral: float | None = None
    indice_endividamento: float | None = None

    # Documentos disponiveis — deve vir de dado real (bidding_certificates
    # com status valido). Vazio = nenhum documento valido conhecido.
    documentos_validos: list[str] = Field(default_factory=list)

    # Historico — SEM fonte real consolidada. None = nao informado.
    licitacoes_vencidas_12m: int | None = None
    licitacoes_participadas_12m: int | None = None
    taxa_sucesso: float | None = None


class AssessmentResponse(BaseModel):
    """Resultado da avaliacao Go/No-Go."""

    # Resultado principal
    score: float  # 0-100
    recomendacao: Recomendacao
    justificativa: str

    # Detalhamento por criterio
    criterios: list[CriterioAvaliacao] = Field(default_factory=list)

    # Requisitos nao atendidos
    requisitos_faltantes: list[str] = Field(default_factory=list)
    documentos_faltantes: list[str] = Field(default_factory=list)

    # Riscos
    riscos_identificados: list[str] = Field(default_factory=list)
    mitigacoes_sugeridas: list[str] = Field(default_factory=list)

    # Competitividade
    estimativa_concorrentes: int | None = None
    posicao_competitiva: str | None = None  # forte, media, fraca

    # Metadados
    avaliado_em: datetime | None = None


# ──────────────────────────────────────────────
# ASSESSOR Agent
# ──────────────────────────────────────────────


class AssessorAgent(BaseAgent):
    """
    Agente ASSESSOR - Avaliacao Go/No-Go para licitacoes.

    Responsabilidades:
    - Receber analise do ANALYST
    - Comparar requisitos do edital com capacidades da empresa
    - Avaliar criterios: tecnico, juridico, economico, operacional, risco
    - Calcular score (0-100) e recomendar GO, NO_GO ou CONDICIONAL
    """

    AGENT_NAME = "assessor"
    AGENT_DESCRIPTION = "Avaliacao Go/No-Go para participacao em licitacoes"
    AGENT_STATUS = AgentStatus.DEVELOPMENT

    # Limites de score para recomendacao
    THRESHOLD_GO = 70.0
    THRESHOLD_CONDICIONAL = 45.0

    def __init__(
        self,
        config: AgentConfig | None = None,
        company_profile: CompanyProfile | None = None,
    ):
        super().__init__(config)
        self.company = company_profile or CompanyProfile()

    async def execute(
        self,
        analysis: dict | None = None,
        company_profile: CompanyProfile | None = None,
        **kwargs,
    ) -> dict:
        """
        Avalia se a empresa deve participar da licitacao.

        Args:
            analysis: Resultado da analise do ANALYST (AnalysisResponse dict).
            company_profile: Perfil da empresa (override do default).

        Returns:
            AssessmentResponse como dict.
        """
        if not analysis:
            raise ValueError("analysis (resultado do ANALYST) e obrigatorio")

        company = company_profile or self.company

        # Avaliar cada criterio
        criterios = []
        criterios.append(self._avaliar_habilitacao_juridica(analysis, company))
        criterios.append(self._avaliar_regularidade_fiscal(analysis, company))
        criterios.append(self._avaliar_qualificacao_tecnica(analysis, company))
        criterios.append(self._avaliar_qualificacao_economica(analysis, company))
        criterios.append(self._avaliar_capacidade_operacional(analysis, company))
        criterios.append(self._avaliar_riscos(analysis, company))
        criterios.append(self._avaliar_competitividade(analysis, company))

        # Calcular score ponderado
        total_peso = sum(c.peso for c in criterios)
        score = sum(c.nota_ponderada for c in criterios) / total_peso if total_peso > 0 else 0.0
        score = round(score, 1)

        # Determinar recomendacao
        requisitos_faltantes = self._identificar_requisitos_faltantes(analysis, company)
        documentos_faltantes = self._identificar_documentos_faltantes(analysis, company)

        # Red flags criticas = NO_GO automatico
        red_flags_altas = [rf for rf in analysis.get("red_flags", []) if rf.get("severidade") == "alta"]

        if requisitos_faltantes and any("eliminatorio" in r.lower() for r in requisitos_faltantes):
            recomendacao = Recomendacao.NO_GO
            justificativa = (
                f"NAO PARTICIPAR. Requisito(s) eliminatorio(s) nao atendido(s): {'; '.join(requisitos_faltantes[:3])}"
            )
        elif score >= self.THRESHOLD_GO and not red_flags_altas:
            recomendacao = Recomendacao.GO
            justificativa = f"PARTICIPAR. Score {score}/100. Empresa atende aos requisitos principais."
        elif score >= self.THRESHOLD_CONDICIONAL:
            recomendacao = Recomendacao.CONDICIONAL
            pendencias = requisitos_faltantes + documentos_faltantes
            justificativa = (
                f"PARTICIPACAO CONDICIONAL. Score {score}/100. "
                f"Pendencia(s): {'; '.join(pendencias[:3]) if pendencias else 'red flags identificadas'}"
            )
        else:
            recomendacao = Recomendacao.NO_GO
            justificativa = f"NAO PARTICIPAR. Score {score}/100 abaixo do limiar ({self.THRESHOLD_CONDICIONAL})."

        riscos = [rf.get("descricao", "") for rf in red_flags_altas]
        mitigacoes = self._sugerir_mitigacoes(requisitos_faltantes, documentos_faltantes)

        assessment = AssessmentResponse(
            score=score,
            recomendacao=recomendacao,
            justificativa=justificativa,
            criterios=criterios,
            requisitos_faltantes=requisitos_faltantes,
            documentos_faltantes=documentos_faltantes,
            riscos_identificados=riscos,
            mitigacoes_sugeridas=mitigacoes,
            posicao_competitiva=self._classificar_posicao(score),
            avaliado_em=datetime.utcnow(),
        )

        self.logger.info(
            f"Avaliacao: {recomendacao.value} | Score: {score} | "
            f"Faltantes: {len(requisitos_faltantes)} req, {len(documentos_faltantes)} docs"
        )

        return assessment.model_dump(mode="json")

    # ──────────────────────────────────────────
    # Avaliacao por criterio
    # ──────────────────────────────────────────

    def _avaliar_habilitacao_juridica(self, analysis: dict, company: CompanyProfile) -> CriterioAvaliacao:
        """Avalia habilitacao juridica."""
        requisitos = [r for r in analysis.get("requisitos_habilitacao", []) if r.get("categoria") == "juridica"]

        nota = 100.0
        observacoes = []

        for req in requisitos:
            desc = req.get("descricao", "").lower()
            if "contrato social" in desc or "ato constitutivo" in desc:
                if "contrato_social" not in company.documentos_validos:
                    nota -= 50
                    observacoes.append("Contrato social nao disponivel")
            if "autorizacao" in desc and "policia federal" in desc:
                if not company.autorizacao_pf:
                    nota -= 50
                    observacoes.append("Sem autorizacao da PF")

        nota = max(0, nota)
        peso = 0.15
        return CriterioAvaliacao(
            nome="Habilitacao Juridica",
            descricao="Documentos juridicos e autorizacoes",
            peso=peso,
            nota=nota,
            nota_ponderada=nota * peso,
            atende=nota >= 60,
            observacao="; ".join(observacoes) if observacoes else "OK",
        )

    def _avaliar_regularidade_fiscal(self, analysis: dict, company: CompanyProfile) -> CriterioAvaliacao:
        """Avalia regularidade fiscal e trabalhista."""
        docs_fiscais = {
            "cnd_federal": ["cnd federal", "certidao negativa federal", "receita federal"],
            "cnd_estadual": ["cnd estadual", "certidao estadual", "fazenda estadual"],
            "cnd_municipal": ["cnd municipal", "certidao municipal", "iss"],
            "crf_fgts": ["fgts", "crf", "caixa economica"],
            "cndt_trabalhista": ["cndt", "trabalhista", "tst", "justica do trabalho"],
        }

        nota = 100.0
        observacoes = []

        requisitos = [r for r in analysis.get("requisitos_habilitacao", []) if r.get("categoria") == "fiscal"]

        for doc_key, keywords in docs_fiscais.items():
            # Verificar se o edital exige este documento
            exigido = False
            for req in requisitos:
                desc = req.get("descricao", "").lower()
                if any(kw in desc for kw in keywords):
                    exigido = True
                    break

            if exigido and doc_key not in company.documentos_validos:
                nota -= 20
                observacoes.append(f"{doc_key} nao disponivel/vencido")

        nota = max(0, nota)
        peso = 0.15
        return CriterioAvaliacao(
            nome="Regularidade Fiscal",
            descricao="CNDs, FGTS, CNDT",
            peso=peso,
            nota=nota,
            nota_ponderada=nota * peso,
            atende=nota >= 60,
            observacao="; ".join(observacoes) if observacoes else "Documentos em dia",
        )

    def _avaliar_qualificacao_tecnica(self, analysis: dict, company: CompanyProfile) -> CriterioAvaliacao:
        """Avalia qualificacao tecnica."""
        nota = 100.0
        observacoes = []

        requisitos_tecnicos = [r for r in analysis.get("requisitos_habilitacao", []) if r.get("categoria") == "tecnica"]

        segmento = (analysis.get("segmento") or "").lower()

        # Verificar se temos atestados para o segmento
        segmentos_atendidos = [a.lower() for a in company.atestados_capacidade_tecnica]

        if segmento and not any(segmento in s for s in segmentos_atendidos):
            nota -= 40
            observacoes.append(f"Sem atestado para segmento: {segmento}")

        # Verificar quantidade de postos vs capacidade
        qtd_postos = analysis.get("quantidade_postos")
        if qtd_postos and qtd_postos > 0:
            # Estimar necessidade de colaboradores (2.5 por posto em media para cobertura)
            colaboradores_necessarios = int(qtd_postos * 2.5)
            if colaboradores_necessarios > company.quantidade_colaboradores:
                nota -= 30
                observacoes.append(
                    f"Capacidade: {company.quantidade_colaboradores} postos, necessario ~{colaboradores_necessarios}"
                )

        # Armamento
        if analysis.get("armamento_necessario") and "vigilancia_armada" not in segmentos_atendidos:
            nota -= 20
            observacoes.append("Exige vigilancia armada - verificar autorizacao")

        # Cobertura geografica
        uf_edital = analysis.get("uf", "AM")
        if uf_edital and uf_edital not in company.cobertura_ufs:
            nota -= 25
            observacoes.append(f"Sem base operacional em {uf_edital}")

        # ISO exigida
        for req in requisitos_tecnicos:
            desc = req.get("descricao", "").lower()
            if "iso 9001" in desc and not company.certificado_iso_9001:
                nota -= 20
                observacoes.append("ISO 9001 exigida mas nao possui")
            if "iso 14001" in desc and not company.certificado_iso_14001:
                nota -= 15
                observacoes.append("ISO 14001 exigida mas nao possui")

        nota = max(0, nota)
        peso = 0.25
        return CriterioAvaliacao(
            nome="Qualificacao Tecnica",
            descricao="Atestados, capacidade operacional, certificacoes",
            peso=peso,
            nota=nota,
            nota_ponderada=nota * peso,
            atende=nota >= 50,
            observacao="; ".join(observacoes) if observacoes else "Qualificacao tecnica atendida",
        )

    def _avaliar_qualificacao_economica(self, analysis: dict, company: CompanyProfile) -> CriterioAvaliacao:
        """Avalia qualificacao economico-financeira."""
        nota = 100.0
        observacoes = []

        valor_estimado = analysis.get("valor_estimado")

        # Verificar capital social minimo (geralmente 10% do valor).
        # Se o capital social nao for informado (None), NAO penalizamos com
        # base em dado fabricado — apenas sinalizamos que falta informacao.
        if valor_estimado:
            capital_minimo_estimado = float(valor_estimado) * 0.10
            if company.capital_social is None:
                observacoes.append(
                    f"Capital social nao informado (minimo estimado: R${capital_minimo_estimado:,.2f}) - "
                    "verificar contabilidade"
                )
            elif company.capital_social < capital_minimo_estimado:
                nota -= 35
                observacoes.append(
                    f"Capital social R${company.capital_social:,.2f} pode ser insuficiente "
                    f"(estimado minimo: R${capital_minimo_estimado:,.2f})"
                )

        # Verificar indices contabeis (so penaliza se o indice for conhecido).
        requisitos_economicos = [
            r for r in analysis.get("requisitos_habilitacao", []) if r.get("categoria") == "economica"
        ]

        for req in requisitos_economicos:
            desc = req.get("descricao", "").lower()
            if "liquidez corrente" in desc:
                if company.indice_liquidez_corrente is None:
                    observacoes.append("Liquidez corrente exigida mas nao informada")
                elif company.indice_liquidez_corrente < 1.0:
                    nota -= 25
                    observacoes.append("Indice de liquidez corrente abaixo de 1.0")
            if "liquidez geral" in desc:
                if company.indice_liquidez_geral is None:
                    observacoes.append("Liquidez geral exigida mas nao informada")
                elif company.indice_liquidez_geral < 1.0:
                    nota -= 25
                    observacoes.append("Indice de liquidez geral abaixo de 1.0")
            if "endividamento" in desc:
                if company.indice_endividamento is not None and company.indice_endividamento > 0.6:
                    nota -= 20
                    observacoes.append("Endividamento elevado")

        if "balanco_patrimonial" not in company.documentos_validos:
            nota -= 30
            observacoes.append("Balanco patrimonial nao disponivel")

        nota = max(0, nota)
        peso = 0.15
        return CriterioAvaliacao(
            nome="Qualificacao Economica",
            descricao="Capital social, indices contabeis, balanco",
            peso=peso,
            nota=nota,
            nota_ponderada=nota * peso,
            atende=nota >= 50,
            observacao="; ".join(observacoes) if observacoes else "Qualificacao economica OK",
        )

    def _avaliar_capacidade_operacional(self, analysis: dict, company: CompanyProfile) -> CriterioAvaliacao:
        """Avalia capacidade de executar o contrato."""
        nota = 100.0
        observacoes = []

        # Base operacional
        if not company.possui_base_operacional:
            nota -= 30
            observacoes.append("Sem base operacional")

        # Prazo do contrato
        prazo_meses = analysis.get("prazo_contrato_meses")
        if prazo_meses and prazo_meses > 24:
            nota -= 10
            observacoes.append(f"Contrato longo ({prazo_meses} meses) - maior exposicao")

        # Verificar se ja tem muitos contratos ativos (estimativa simplificada).
        # So avalia se o historico for conhecido.
        if company.licitacoes_vencidas_12m is not None and company.licitacoes_vencidas_12m > 10:
            nota -= 15
            observacoes.append("Muitos contratos ativos - avaliar capacidade")

        nota = max(0, nota)
        peso = 0.10
        return CriterioAvaliacao(
            nome="Capacidade Operacional",
            descricao="Base, equipe, contratos ativos",
            peso=peso,
            nota=nota,
            nota_ponderada=nota * peso,
            atende=nota >= 50,
            observacao="; ".join(observacoes) if observacoes else "Capacidade operacional OK",
        )

    def _avaliar_riscos(self, analysis: dict, company: CompanyProfile) -> CriterioAvaliacao:
        """Avalia riscos gerais da licitacao."""
        nota = 100.0
        observacoes = []

        red_flags = analysis.get("red_flags", [])

        for rf in red_flags:
            severidade = rf.get("severidade", "baixa")
            desc = rf.get("descricao", "")

            if severidade == "alta":
                nota -= 30
                observacoes.append(f"[ALTO] {desc[:80]}")
            elif severidade == "media":
                nota -= 15
                observacoes.append(f"[MEDIO] {desc[:80]}")
            else:
                nota -= 5
                observacoes.append(f"[BAIXO] {desc[:80]}")

        nota = max(0, nota)
        peso = 0.10
        return CriterioAvaliacao(
            nome="Riscos",
            descricao="Red flags e riscos identificados no edital",
            peso=peso,
            nota=nota,
            nota_ponderada=nota * peso,
            atende=nota >= 40,
            observacao="; ".join(observacoes) if observacoes else "Sem riscos significativos",
        )

    def _avaliar_competitividade(self, analysis: dict, company: CompanyProfile) -> CriterioAvaliacao:
        """Avalia posicao competitiva da empresa."""
        nota = 70.0  # Base neutra
        observacoes = []

        # Taxa de sucesso historica (so pontua se conhecida; sem historico,
        # mantem a base neutra em vez de inventar desempenho).
        if company.taxa_sucesso is None:
            observacoes.append("Taxa de sucesso historica nao informada")
        elif company.taxa_sucesso > 50:
            nota += 20
            observacoes.append(f"Taxa sucesso alta: {company.taxa_sucesso:.1f}%")
        elif company.taxa_sucesso > 30:
            nota += 10
        elif company.taxa_sucesso < 20:
            nota -= 10
            observacoes.append(f"Taxa sucesso baixa: {company.taxa_sucesso:.1f}%")

        # Modalidade preferida
        modalidade = (analysis.get("modalidade") or "").lower()
        if "pregao" in modalidade:
            nota += 10
            observacoes.append("Pregao - modalidade conhecida")

        # Criterio - menor preco favorece quem tem estrutura lean
        criterio = (analysis.get("criterio_julgamento") or "").lower()
        if "menor_preco" in criterio:
            nota += 5
        elif "tecnica" in criterio:
            nota -= 5
            observacoes.append("Criterio tecnico - exige documentacao mais robusta")

        nota = min(100, max(0, nota))
        peso = 0.10
        return CriterioAvaliacao(
            nome="Competitividade",
            descricao="Posicao competitiva e historico",
            peso=peso,
            nota=nota,
            nota_ponderada=nota * peso,
            atende=nota >= 50,
            observacao="; ".join(observacoes) if observacoes else "Posicao competitiva neutra",
        )

    # ──────────────────────────────────────────
    # Auxiliares
    # ──────────────────────────────────────────

    def _identificar_requisitos_faltantes(self, analysis: dict, company: CompanyProfile) -> list[str]:
        """Identifica requisitos que a empresa nao atende."""
        faltantes = []

        for req in analysis.get("requisitos_habilitacao", []):
            desc = req.get("descricao", "").lower()
            categoria = req.get("categoria", "")

            if categoria == "tecnica":
                if "iso 9001" in desc and not company.certificado_iso_9001:
                    faltantes.append("Certificacao ISO 9001 (eliminatorio)")
                if "iso 14001" in desc and not company.certificado_iso_14001:
                    faltantes.append("Certificacao ISO 14001")

            if "capital social" in desc:
                # Tentar extrair valor minimo
                valor_estimado = analysis.get("valor_estimado")
                if valor_estimado and company.capital_social is not None:
                    minimo = float(valor_estimado) * 0.10
                    if company.capital_social < minimo:
                        faltantes.append(
                            f"Capital social minimo R${minimo:,.2f} (atual: R${company.capital_social:,.2f})"
                        )

        return faltantes

    def _identificar_documentos_faltantes(self, analysis: dict, company: CompanyProfile) -> list[str]:
        """Identifica documentos exigidos que nao estao disponiveis."""
        faltantes = []

        mapeamento = {
            "cnd federal": "cnd_federal",
            "cnd estadual": "cnd_estadual",
            "cnd municipal": "cnd_municipal",
            "fgts": "crf_fgts",
            "cndt": "cndt_trabalhista",
            "trabalhista": "cndt_trabalhista",
            "sicaf": "sicaf",
            "balanco": "balanco_patrimonial",
            "contrato social": "contrato_social",
        }

        for doc in analysis.get("documentos_necessarios", []):
            nome = doc.get("nome", "").lower()
            obrigatorio = doc.get("obrigatorio", True)

            if not obrigatorio:
                continue

            for keyword, doc_key in mapeamento.items():
                if keyword in nome and doc_key not in company.documentos_validos:
                    faltantes.append(doc.get("nome", keyword))
                    break

        return faltantes

    def _sugerir_mitigacoes(
        self,
        requisitos_faltantes: list[str],
        documentos_faltantes: list[str],
    ) -> list[str]:
        """Sugere acoes de mitigacao para pendencias."""
        mitigacoes = []

        for doc in documentos_faltantes:
            doc_lower = doc.lower()
            if "cnd" in doc_lower or "cndt" in doc_lower or "fgts" in doc_lower:
                mitigacoes.append(f"Emitir/renovar {doc} antes da data de abertura")
            elif "sicaf" in doc_lower:
                mitigacoes.append("Atualizar cadastro no SICAF")
            elif "balanco" in doc_lower:
                mitigacoes.append("Providenciar balanco patrimonial atualizado com contador")

        for req in requisitos_faltantes:
            req_lower = req.lower()
            if "iso" in req_lower:
                mitigacoes.append("Avaliar certificacao ISO - processo longo, considerar consorcio")
            if "capital social" in req_lower:
                mitigacoes.append("Considerar consorcio para atender requisito de capital social")

        return mitigacoes

    def _classificar_posicao(self, score: float) -> str:
        """Classifica posicao competitiva baseada no score."""
        if score >= 75:
            return "forte"
        elif score >= 50:
            return "media"
        else:
            return "fraca"

"""
ANALYST Agent - Analise de editais com IA
==========================================
Usa cascata LLM (OpenAI gpt-5 primario -> Anthropic fallback opcional) para
extrair informacoes estruturadas de editais, identificar red flags e
documentos necessarios.
"""

import json
import logging
import os
from datetime import datetime

from pydantic import BaseModel, Field

from modules.bidding.agents.base_agent import AgentConfig, AgentStatus, BaseAgent

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_MODEL = "gpt-5"  # analise de edital e pesada
CLAUDE_MODEL = "claude-sonnet-4-20250514"  # fallback opcional da cascata


# ──────────────────────────────────────────────
# DTOs de resposta
# ──────────────────────────────────────────────


class RedFlag(BaseModel):
    """Red flag identificada no edital."""

    tipo: str  # restritiva, prazo_curto, valor_incompativel, exigencia_excessiva, etc
    descricao: str
    severidade: str  # alta, media, baixa
    trecho_edital: str | None = None


class RequisitoHabilitacao(BaseModel):
    """Requisito de habilitacao extraido do edital."""

    categoria: str  # juridica, fiscal, tecnica, economica
    descricao: str
    obrigatorio: bool = True
    empresa_atende: bool | None = None  # Preenchido pelo ASSESSOR


class DocumentoNecessario(BaseModel):
    """Documento necessario para participacao."""

    nome: str
    descricao: str | None = None
    tipo: str  # habilitacao, proposta, declaracao, atestado
    obrigatorio: bool = True
    prazo_validade_dias: int | None = None


class AnalysisResponse(BaseModel):
    """Resultado completo da analise do edital."""

    # Identificacao
    numero_edital: str | None = None
    orgao: str | None = None
    uf: str | None = None

    # Objeto
    objeto_resumido: str
    objeto_detalhado: str | None = None
    segmento: str | None = None  # seguranca, limpeza, etc

    # Classificacao
    modalidade: str | None = None
    criterio_julgamento: str | None = None
    tipo_contratacao: str | None = None  # servicos_continuados, obra, compra
    regime_execucao: str | None = None

    # Valores
    valor_estimado: float | None = None
    valor_maximo_aceitavel: float | None = None

    # Prazos
    data_abertura: str | None = None
    data_encerramento_propostas: str | None = None
    prazo_contrato_meses: int | None = None
    prorrogavel: bool | None = None

    # Requisitos
    requisitos_habilitacao: list[RequisitoHabilitacao] = Field(default_factory=list)
    documentos_necessarios: list[DocumentoNecessario] = Field(default_factory=list)

    # Red flags
    red_flags: list[RedFlag] = Field(default_factory=list)

    # Postos/servicos (especifico para vigilancia)
    quantidade_postos: int | None = None
    tipos_posto: list[str] = Field(default_factory=list)  # 12x36, 24h, diurno, etc
    armamento_necessario: bool | None = None
    veiculo_necessario: bool | None = None

    # Metadados da analise
    confianca_analise: float = 0.0  # 0-100
    observacoes: list[str] = Field(default_factory=list)
    analisado_em: datetime | None = None


# ──────────────────────────────────────────────
# Prompt para Claude
# ──────────────────────────────────────────────

ANALYSIS_SYSTEM_PROMPT = """Voce e um especialista em licitacoes publicas brasileiras, \
especialmente na area de seguranca patrimonial, vigilancia e servicos terceirizados.

Sua tarefa e analisar o texto de um edital de licitacao e extrair informacoes estruturadas.

Voce DEVE retornar um JSON valido com a seguinte estrutura (sem markdown, sem ```json):
{
    "objeto_resumido": "string - resumo do objeto em ate 200 caracteres",
    "objeto_detalhado": "string - descricao detalhada do objeto",
    "segmento": "string - segmento: seguranca, limpeza, portaria, manutencao, etc",
    "modalidade": "string - modalidade: pregao_eletronico, concorrencia, etc",
    "criterio_julgamento": "string - menor_preco, tecnica_e_preco, etc",
    "tipo_contratacao": "string - servicos_continuados, obra, compra",
    "regime_execucao": "string ou null",
    "valor_estimado": "number ou null",
    "valor_maximo_aceitavel": "number ou null",
    "data_abertura": "string ISO ou null",
    "data_encerramento_propostas": "string ISO ou null",
    "prazo_contrato_meses": "number ou null",
    "prorrogavel": "boolean ou null",
    "requisitos_habilitacao": [
        {
            "categoria": "juridica|fiscal|tecnica|economica",
            "descricao": "string",
            "obrigatorio": true
        }
    ],
    "documentos_necessarios": [
        {
            "nome": "string",
            "descricao": "string ou null",
            "tipo": "habilitacao|proposta|declaracao|atestado",
            "obrigatorio": true,
            "prazo_validade_dias": "number ou null"
        }
    ],
    "red_flags": [
        {
            "tipo": "restritiva|prazo_curto|valor_incompativel|exigencia_excessiva|clausula_abusiva",
            "descricao": "string",
            "severidade": "alta|media|baixa",
            "trecho_edital": "string ou null"
        }
    ],
    "quantidade_postos": "number ou null",
    "tipos_posto": ["string"],
    "armamento_necessario": "boolean ou null",
    "veiculo_necessario": "boolean ou null",
    "confianca_analise": "number 0-100",
    "observacoes": ["string"]
}

Regras:
1. Seja preciso e objetivo.
2. Red flags importantes: exigencias que restringem competicao, prazos muito curtos, \
valores incompativeis com mercado, clausulas abusivas.
3. Para seguranca patrimonial, verifique se exige autorizacao PF/CFTV/curso de formacao.
4. Identifique TODOS os documentos de habilitacao exigidos.
5. Se nao conseguir extrair algum campo, use null.
6. O JSON DEVE ser valido e parseable."""


# ──────────────────────────────────────────────
# ANALYST Agent
# ──────────────────────────────────────────────


class AnalystAgent(BaseAgent):
    """
    Agente ANALYST - Analisa editais de licitacao com IA.

    Responsabilidades:
    - Receber texto do edital (ou URL para download)
    - Enviar para cascata LLM (OpenAI gpt-5 -> Anthropic fallback) para analise estruturada
    - Extrair: objeto, modalidade, requisitos, red flags, documentos
    - Retornar AnalysisResponse formatado
    """

    AGENT_NAME = "analyst"
    AGENT_DESCRIPTION = "Analisa editais de licitacao com IA (OpenAI -> Anthropic)"
    AGENT_STATUS = AgentStatus.DEVELOPMENT

    def __init__(self, config: AgentConfig | None = None, api_key: str | None = None):
        super().__init__(config or AgentConfig(timeout_seconds=180.0))
        # api_key: legado — chave Anthropic explicita (a cascata le as chaves do ambiente)
        self.api_key = api_key or ANTHROPIC_API_KEY

    async def execute(
        self,
        edital_text: str | None = None,
        numero_edital: str | None = None,
        orgao: str | None = None,
        uf: str | None = None,
        **kwargs,
    ) -> dict:
        """
        Analisa texto de edital usando Claude API.

        Args:
            edital_text: Texto completo ou parcial do edital.
            numero_edital: Numero do edital (para referencia).
            orgao: Nome do orgao licitante.
            uf: UF do orgao.

        Returns:
            AnalysisResponse como dict.
        """
        if not edital_text:
            raise ValueError("edital_text e obrigatorio para analise")

        if not (os.getenv("OPENAI_API_KEY", "").strip() or self.api_key):
            raise ValueError(
                "Nenhum provedor LLM configurado. Defina OPENAI_API_KEY (primario) "
                "e/ou ANTHROPIC_API_KEY (fallback)."
            )

        # Truncar texto se muito longo (limite de contexto do LLM)
        max_chars = 150_000
        if len(edital_text) > max_chars:
            self.logger.warning(f"Edital truncado de {len(edital_text)} para {max_chars} caracteres")
            edital_text = edital_text[:max_chars]

        # Chamar cascata LLM (OpenAI -> Anthropic)
        raw_analysis = await self._call_claude(edital_text)

        # Montar resposta
        analysis = AnalysisResponse(
            numero_edital=numero_edital,
            orgao=orgao,
            uf=uf,
            analisado_em=datetime.utcnow(),
            **raw_analysis,
        )

        self.logger.info(
            f"Analise concluida: {analysis.objeto_resumido[:80]}... "
            f"| {len(analysis.red_flags)} red flags "
            f"| {len(analysis.requisitos_habilitacao)} requisitos "
            f"| confianca: {analysis.confianca_analise}%"
        )

        return analysis.model_dump(mode="json")

    async def _call_claude(self, edital_text: str) -> dict:
        """
        Chama a cascata LLM (OpenAI gpt-5 -> Anthropic fallback) para analise do edital.

        Nome mantido por compatibilidade interna.

        Returns:
            Dict com campos da AnalysisResponse.
        """
        from core.llm_cascade import achat

        user_message = (
            f"Analise o seguinte edital de licitacao e retorne o JSON estruturado "
            f"conforme as instrucoes:\n\n"
            f"---INICIO DO EDITAL---\n{edital_text}\n---FIM DO EDITAL---"
        )

        text_content = await achat(
            messages=[
                {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            model_openai=OPENAI_MODEL,
            model_anthropic=CLAUDE_MODEL,
            max_tokens=8192,
            json_mode=True,
        )

        if not text_content or not text_content.strip():
            raise ValueError("Nenhum provedor LLM respondeu (OpenAI/Anthropic indisponiveis ou resposta vazia)")

        # Parse JSON da resposta
        try:
            parsed = json.loads(text_content.strip())
        except json.JSONDecodeError:
            # Tentar extrair JSON de dentro do texto
            parsed = self._extract_json_from_text(text_content)

        return parsed

    def _extract_json_from_text(self, text: str) -> dict:
        """
        Tenta extrair JSON de um texto que pode conter markdown ou outros wrappers.
        """
        import re

        # Tentar encontrar JSON entre ```json ... ```
        json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Tentar encontrar primeiro { ate ultimo }
        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace != -1 and last_brace != -1:
            try:
                return json.loads(text[first_brace : last_brace + 1])
            except json.JSONDecodeError:
                pass

        raise ValueError(f"Nao foi possivel extrair JSON da resposta do LLM: {text[:200]}")

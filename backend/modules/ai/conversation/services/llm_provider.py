"""Provider de LLM para integracao com OpenAI e Claude."""

import logging
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from core.config.settings import settings

logger = logging.getLogger(__name__)


class LLMModel(StrEnum):
    """Modelos de LLM disponiveis."""

    # OpenAI
    GPT_4 = "gpt-4"
    GPT_4_TURBO = "gpt-4-turbo-preview"
    GPT_4O_MINI = "gpt-4o-mini"
    GPT_35_TURBO = "gpt-3.5-turbo"

    # Anthropic
    CLAUDE_3_OPUS = "claude-3-opus-20240229"
    CLAUDE_3_SONNET = "claude-3-sonnet-20240229"
    CLAUDE_3_HAIKU = "claude-haiku-4-5-20251001"  # atualizado de claude-3-haiku-20240307 (deprecated)

    # Local/Fallback
    LOCAL = "local"


@dataclass
class LLMResponse:
    """Resposta do LLM."""

    content: str
    model: str
    tokens_used: int
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    finish_reason: str = "stop"
    metadata: dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class BaseLLMProvider(ABC):
    """Classe base para providers de LLM."""

    @abstractmethod
    async def generate(
        self,
        messages: list[dict[str, str]],
        system_prompt: str | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        **kwargs,
    ) -> LLMResponse:
        """Gera resposta do LLM."""
        pass

    @abstractmethod
    async def generate_stream(
        self,
        messages: list[dict[str, str]],
        system_prompt: str | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        """Gera resposta em streaming."""
        pass


class OpenAIProvider(BaseLLMProvider):
    """Provider para OpenAI GPT."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        """Inicializa provider OpenAI."""
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.model = model or settings.LLM_MODEL if settings.LLM_PROVIDER == "openai" else LLMModel.GPT_4.value
        self._client = None

        if not self.api_key:
            logger.warning("OpenAI API key nao configurada. Provider nao funcionara.")

    def _completion_params(self, max_tokens: int, temperature: float) -> dict[str, Any]:
        """Adapta os parametros ao contrato do modelo (provado por probe real 2026-07-25).

        Familia gpt-5 (modelos de raciocinio) NAO aceita `max_tokens` (exige
        `max_completion_tokens`) e SO aceita `temperature` no default 1 (qualquer outro
        valor -> 400). Logo, para gpt-5* enviamos `max_completion_tokens` e OMITIMOS
        `temperature` quando != 1 (cai no default do modelo). Modelos gpt-4.x/gpt-4o
        continuam com o contrato antigo (`max_tokens` + `temperature` livre).

        A assinatura publica de generate() nao muda: os chamadores continuam passando
        max_tokens/temperature; a adaptacao acontece aqui dentro.
        """
        model = (self.model or "").lower()
        if model.startswith("gpt-5"):
            params: dict[str, Any] = {"max_completion_tokens": max_tokens}
            if temperature == 1:
                params["temperature"] = temperature
            return params
        return {"max_tokens": max_tokens, "temperature": temperature}

    async def _get_client(self):
        """Obtem cliente OpenAI (lazy loading)."""
        if self._client is None:
            try:
                from openai import AsyncOpenAI

                self._client = AsyncOpenAI(api_key=self.api_key)
            except ImportError:
                logger.error("openai package not installed")
                raise
        return self._client

    async def generate(
        self,
        messages: list[dict[str, str]],
        system_prompt: str | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        **kwargs,
    ) -> LLMResponse:
        """Gera resposta usando OpenAI."""
        start_time = time.time()

        client = await self._get_client()

        # Prepara mensagens
        formatted_messages = []
        if system_prompt:
            formatted_messages.append({"role": "system", "content": system_prompt})
        formatted_messages.extend(messages)

        try:
            response = await client.chat.completions.create(
                model=self.model,
                messages=formatted_messages,
                **self._completion_params(max_tokens, temperature),
                **kwargs,
            )

            latency_ms = int((time.time() - start_time) * 1000)

            return LLMResponse(
                content=response.choices[0].message.content,
                model=self.model,
                tokens_used=response.usage.total_tokens,
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                latency_ms=latency_ms,
                finish_reason=response.choices[0].finish_reason,
            )
        except Exception as e:
            logger.error(f"Erro na chamada OpenAI: {e}")
            raise

    async def generate_stream(
        self,
        messages: list[dict[str, str]],
        system_prompt: str | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        """Gera resposta em streaming usando OpenAI."""
        client = await self._get_client()

        formatted_messages = []
        if system_prompt:
            formatted_messages.append({"role": "system", "content": system_prompt})
        formatted_messages.extend(messages)

        try:
            stream = await client.chat.completions.create(
                model=self.model,
                messages=formatted_messages,
                stream=True,
                **self._completion_params(max_tokens, temperature),
                **kwargs,
            )

            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.error(f"Erro no streaming OpenAI: {e}")
            raise


class ClaudeProvider(BaseLLMProvider):
    """Provider para Anthropic Claude."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        """Inicializa provider Claude."""
        self.api_key = api_key or settings.ANTHROPIC_API_KEY
        self.model = (
            model or settings.LLM_MODEL if settings.LLM_PROVIDER == "anthropic" else LLMModel.CLAUDE_3_SONNET.value
        )
        self._client = None

        if not self.api_key:
            logger.warning("Anthropic API key nao configurada. Provider nao funcionara.")

    async def _get_client(self):
        """Obtem cliente Anthropic (lazy loading)."""
        if self._client is None:
            try:
                from anthropic import AsyncAnthropic

                self._client = AsyncAnthropic(api_key=self.api_key)
            except ImportError:
                logger.error("anthropic package not installed")
                raise
        return self._client

    async def generate(
        self,
        messages: list[dict[str, str]],
        system_prompt: str | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        **kwargs,
    ) -> LLMResponse:
        """Gera resposta usando Claude."""
        start_time = time.time()

        client = await self._get_client()

        try:
            response = await client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system_prompt or "",
                messages=messages,
                temperature=temperature,
                **kwargs,
            )

            latency_ms = int((time.time() - start_time) * 1000)

            return LLMResponse(
                content=response.content[0].text,
                model=self.model,
                tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
                latency_ms=latency_ms,
                finish_reason=response.stop_reason,
            )
        except Exception as e:
            logger.error(f"Erro na chamada Claude: {e}")
            raise

    async def generate_stream(
        self,
        messages: list[dict[str, str]],
        system_prompt: str | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        """Gera resposta em streaming usando Claude."""
        client = await self._get_client()

        try:
            async with client.messages.stream(
                model=self.model,
                max_tokens=max_tokens,
                system=system_prompt or "",
                messages=messages,
                temperature=temperature,
                **kwargs,
            ) as stream:
                async for text in stream.text_stream:
                    yield text
        except Exception as e:
            logger.error(f"Erro no streaming Claude: {e}")
            raise


class LocalFallbackProvider(BaseLLMProvider):
    """Provider de fallback local (respostas pre-definidas)."""

    FALLBACK_RESPONSES = {
        # Saudacoes
        "greeting": "Ola! Sou seu assistente inteligente do Conecta PRO. Como posso ajudar?",
        "help": "Posso ajudar com navegacao, consultas de dados, criacao de registros e muito mais. O que voce precisa?",
        "error": "Desculpe, nao consegui processar sua solicitacao no momento. Tente novamente em alguns instantes.",
        "default": "Entendi sua mensagem. Para uma resposta mais precisa, poderia detalhar sua solicitacao?",
        # Modulo Operacional
        "operacional_escalas": "No modulo Operacional, voce pode gerenciar escalas de trabalho. Acesse Menu > Operacional > Escalas para criar, editar e visualizar escalas. Posso ajudar com templates de escalas, alocacoes de funcionarios e gestao de turnos.",
        "operacional_turnos": "Os turnos sao configurados em Operacional > Turnos. Voce pode criar turnos personalizados com horarios, intervalos e regras especificas. Cada turno pode ser vinculado a postos e escalas.",
        "operacional_postos": "Os postos de trabalho sao gerenciados em Operacional > Postos. Defina localizacao, requisitos, turnos e funcionarios alocados. Cada posto pode ter multiplos turnos e escalas.",
        "operacional_funcionarios": "No modulo Operacional > Funcionarios, voce gerencia colaboradores, documentos, treinamentos e historico profissional. Integrado com RH e Ponto Eletronico.",
        "operacional_ocorrencias": "As ocorrencias disciplinares sao registradas em Operacional > Ocorrencias. Registre advertencias, suspensoes e outras medidas administrativas com documentacao completa.",
        "operacional_banco_horas": "O banco de horas e gerenciado em Operacional > Banco de Horas. Acompanhe saldos, lancamentos, compensacoes e relatorios por funcionario.",
        "operacional_substituicoes": "As substituicoes sao gerenciadas em Operacional > Substituicoes. Registre trocas de turno, faltas cobertas e historico de substituicoes.",
        "operacional_rondas": "As rondas de inspecao sao configuradas em Operacional > Rondas. Crie roteiros, checkpoints, QR codes e acompanhe execucao em tempo real.",
        # Modulo CRM
        "crm_leads": "No modulo CRM > Leads, voce gerencia prospects e oportunidades de negocio. Registre contatos, interacoes, origem e status de cada lead.",
        "crm_propostas": "As propostas comerciais sao criadas em CRM > Propostas. Monte propostas com produtos/servicos, valores, prazos e envie para aprovacao do cliente.",
        "crm_contratos": "Os contratos sao gerenciados em CRM > Contratos. Vincule propostas aprovadas, configure faturamento, aditivos e renovacoes automaticas.",
        "crm_comissoes": "As comissoes de vendas sao calculadas em CRM > Comissoes. Configure regras por vendedor, produto e acompanhe pagamentos.",
        "crm_pipeline": "O pipeline de vendas e visualizado no Dashboard CRM. Acompanhe funil de vendas, taxas de conversao e metas por vendedor.",
        # Modulo Financeiro
        "financeiro_pagar": "As contas a pagar sao gerenciadas em Financeiro > Contas a Pagar. Registre fornecedores, vencimentos, categorias e realize pagamentos.",
        "financeiro_receber": "As contas a receber estao em Financeiro > Contas a Receber. Controle faturas, recebimentos, inadimplencia e cobrancas.",
        "financeiro_fluxo_caixa": "O fluxo de caixa e acompanhado em Financeiro > Fluxo de Caixa. Visualize entradas, saidas, saldo projetado e DRE.",
        "financeiro_bancos": "As contas bancarias sao gerenciadas em Financeiro > Bancos. Cadastre contas, lancamentos, conciliacoes e extratos OFX.",
        "financeiro_compras": "As compras sao gerenciadas em Financeiro > Compras. Crie pedidos, receba mercadorias e integre com contas a pagar.",
        "financeiro_estoque": "O estoque e controlado em Financeiro > Estoque. Gerencie produtos, entradas, saidas, inventarios e relatorios.",
        # Modulo RH
        "rh_admissao": "O processo de admissao e feito em RH > Admissoes. Colete documentos, gere ASO, registre funcionario e crie usuario no sistema.",
        "rh_folha": "A folha de pagamento e processada em RH > Folha. Calcule salarios, descontos, impostos e gere arquivos para banco.",
        "rh_ponto": "O ponto eletronico e gerenciado em RH > Ponto. Integrado com REPs, calcula horas extras, faltas e atrasos automaticamente.",
        "rh_ferias": "As ferias sao gerenciadas em RH > Ferias. Controle periodo aquisitivo, concessivo, calcule valores e gere documentos.",
        "rh_treinamentos": "Os treinamentos sao organizados em RH > Treinamentos. Agende cursos, registre presenca e emita certificados.",
        # Modulo GED
        "ged_documentos": "O GED gerencia documentos em GED > Documentos. Organize por pastas, tags, compartilhe, versione e assine digitalmente.",
        "ged_pastas": "As pastas do GED sao criadas em GED > Pastas. Defina hierarquia, permissoes e regras de retencao.",
        "ged_assinaturas": "As assinaturas digitais sao feitas em GED > Assinaturas. Assine documentos com certificado digital ICP-Brasil.",
        # Dashboard e KPIs
        "dashboard": "O Dashboard principal mostra indicadores em tempo real: receitas, despesas, contratos ativos, funcionarios, ocorrencias e muito mais.",
        "kpis": "Os KPIs sao metricas de performance. Cada modulo tem seus proprios indicadores: ocupacao de postos, inadimplencia, turnover, etc.",
        "relatorios": "Os relatorios estao disponiveis em cada modulo. Gere PDFs, Excel, graficos e agende envios automaticos por email.",
        # Ajuda Geral
        "navegacao": "Use o menu lateral para navegar entre modulos. A busca global (Ctrl+K) localiza registros em todo o sistema rapidamente.",
        "permissoes": "As permissoes sao gerenciadas em Configuracoes > Usuarios e Perfis. Defina acesso por modulo, tela e acao.",
        "notificacoes": "As notificacoes aparecem no sino superior direito. Configure alertas em Configuracoes > Notificacoes.",
        "suporte": "Para suporte tecnico, acesse Menu > Ajuda > Suporte ou envie email para suporte@conectapro.com.br.",
        # Sistema Geral
        "sistema": "O Conecta PRO e um sistema ERP completo para gestao de empresas de vigilancia e seguranca. Possui modulos: Operacional (escalas, turnos, postos), CRM (leads, propostas, contratos), Financeiro (pagar, receber, fluxo de caixa), RH (admissao, folha, ponto), e GED (documentos). O que gostaria de saber?",
        "cadastrar": "Para cadastros no sistema: Funcionarios em RH > Admissoes ou Operacional > Funcionarios. Clientes em CRM > Leads ou Clients > Condominios. Fornecedores em Financeiro > Fornecedores. Qual cadastro deseja fazer?",
    }

    def _analyze_intent(self, message: str) -> str:
        """Analisa a mensagem e determina a resposta mais adequada."""
        message_lower = message.lower()

        # Saudacoes
        if any(word in message_lower for word in ["oi", "ola", "hey", "bom dia", "boa tarde", "boa noite"]):
            return "greeting"

        # Ajuda geral
        if any(word in message_lower for word in ["ajuda", "help", "socorro", "como funciona"]):
            return "help"

        # Modulo Operacional
        if any(word in message_lower for word in ["escala", "escalas", "escalar"]):
            return "operacional_escalas"
        if any(word in message_lower for word in ["turno", "turnos", "horario"]):
            return "operacional_turnos"
        if any(word in message_lower for word in ["posto", "postos", "local", "locais"]):
            return "operacional_postos"
        if any(word in message_lower for word in ["funcionario", "funcionarios", "colaborador", "colaboradores"]):
            return "operacional_funcionarios"
        if any(word in message_lower for word in ["ocorrencia", "ocorrencias", "disciplinar", "advertencia"]):
            return "operacional_ocorrencias"
        if any(word in message_lower for word in ["banco de horas", "horas extras", "compensacao"]):
            return "operacional_banco_horas"
        if any(word in message_lower for word in ["substituicao", "substituicoes", "troca de turno"]):
            return "operacional_substituicoes"
        if any(word in message_lower for word in ["ronda", "rondas", "inspecao", "checkpoint"]):
            return "operacional_rondas"

        # Modulo CRM
        if any(word in message_lower for word in ["lead", "leads", "prospect"]):
            return "crm_leads"
        if any(word in message_lower for word in ["proposta", "propostas", "orcamento"]):
            return "crm_propostas"
        if any(word in message_lower for word in ["contrato", "contratos"]):
            return "crm_contratos"
        if any(word in message_lower for word in ["comissao", "comissoes", "vendas"]):
            return "crm_comissoes"
        if any(word in message_lower for word in ["pipeline", "funil", "vendas"]):
            return "crm_pipeline"

        # Modulo Financeiro
        if any(word in message_lower for word in ["pagar", "contas a pagar", "fornecedor", "pagamento"]):
            return "financeiro_pagar"
        if any(word in message_lower for word in ["receber", "contas a receber", "fatura", "cobranca"]):
            return "financeiro_receber"
        if any(word in message_lower for word in ["fluxo de caixa", "dre", "saldo"]):
            return "financeiro_fluxo_caixa"
        if any(word in message_lower for word in ["banco", "conta bancaria", "conciliacao"]):
            return "financeiro_bancos"
        if any(word in message_lower for word in ["compra", "compras", "pedido"]):
            return "financeiro_compras"
        if any(word in message_lower for word in ["estoque", "produto", "inventario"]):
            return "financeiro_estoque"

        # Modulo RH
        if any(word in message_lower for word in ["admissao", "admissoes", "contratar"]):
            return "rh_admissao"
        if any(word in message_lower for word in ["folha", "folha de pagamento", "salario"]):
            return "rh_folha"
        if any(word in message_lower for word in ["ponto", "ponto eletronico", "rep"]):
            return "rh_ponto"
        if any(word in message_lower for word in ["ferias", "periodo aquisitivo"]):
            return "rh_ferias"
        if any(word in message_lower for word in ["treinamento", "treinamentos", "curso"]):
            return "rh_treinamentos"

        # Modulo GED
        if any(word in message_lower for word in ["documento", "documentos", "arquivo", "ged"]):
            return "ged_documentos"
        if any(word in message_lower for word in ["pasta", "pastas", "diretorio"]):
            return "ged_pastas"
        if any(word in message_lower for word in ["assinar", "assinatura", "certificado"]):
            return "ged_assinaturas"

        # Dashboard e KPIs
        if any(word in message_lower for word in ["dashboard", "painel", "visao geral"]):
            return "dashboard"
        if any(word in message_lower for word in ["kpi", "indicador", "metrica"]):
            return "kpis"
        if any(word in message_lower for word in ["relatorio", "relatorios", "report"]):
            return "relatorios"

        # Navegacao e Sistema
        if any(word in message_lower for word in ["navegar", "navegacao", "menu", "onde fica"]):
            return "navegacao"
        if any(word in message_lower for word in ["permissao", "permissoes", "acesso", "perfil"]):
            return "permissoes"
        if any(word in message_lower for word in ["notificacao", "notificacoes", "alerta"]):
            return "notificacoes"
        if any(word in message_lower for word in ["suporte", "problema", "bug", "erro"]):
            return "suporte"

        # Sistema Geral
        if any(word in message_lower for word in ["sistema", "o que faz", "o que e", "conecta pro", "erp"]):
            return "sistema"
        if any(word in message_lower for word in ["cadastrar", "cadastro", "criar", "adicionar", "novo"]):
            return "cadastrar"

        return "default"

    async def generate(
        self,
        messages: list[dict[str, str]],
        system_prompt: str | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        **kwargs,
    ) -> LLMResponse:
        """Gera resposta de fallback."""
        start_time = time.time()

        # Analisa ultima mensagem para determinar resposta
        last_message = messages[-1]["content"] if messages else ""
        response_type = self._analyze_intent(last_message)

        content = self.FALLBACK_RESPONSES.get(response_type, self.FALLBACK_RESPONSES["default"])
        latency_ms = int((time.time() - start_time) * 1000)

        return LLMResponse(
            content=content,
            model="local-fallback",
            tokens_used=len(content.split()),
            prompt_tokens=sum(len(m["content"].split()) for m in messages),
            completion_tokens=len(content.split()),
            latency_ms=latency_ms,
            finish_reason="stop",
            metadata={"fallback": True, "intent": response_type},
        )

    async def generate_stream(
        self,
        messages: list[dict[str, str]],
        system_prompt: str | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        """Gera resposta de fallback em streaming (simula)."""
        response = await self.generate(messages, system_prompt, max_tokens, temperature)

        # Simula streaming palavra por palavra
        for word in response.content.split():
            yield word + " "


class LLMProvider:
    """
    Provider principal que gerencia multiplos backends de LLM.

    Implementa:
    - Selecao automatica de modelo
    - Fallback entre providers
    - Circuit breaker
    - Metricas
    """

    def __init__(
        self,
        primary_provider: str | None = None,
        primary_model: str | None = None,
        fallback_enabled: bool | None = None,
    ):
        """
        Inicializa o provider usando configuracoes do settings.

        Args:
            primary_provider: Provider principal (openai, claude, local). Default: usar settings.LLM_PROVIDER
            primary_model: Modelo especifico. Default: usar settings.LLM_MODEL
            fallback_enabled: Habilita fallback local. Default: usar settings.LLM_FALLBACK_ENABLED
        """
        # Use settings se nao especificado
        self.primary_provider_name = primary_provider or settings.LLM_PROVIDER
        self.fallback_enabled = fallback_enabled if fallback_enabled is not None else settings.LLM_FALLBACK_ENABLED

        # Inicializa providers
        self._providers: dict[str, BaseLLMProvider] = {}

        # Tenta inicializar provider configurado
        if self.primary_provider_name == "openai" and settings.OPENAI_API_KEY:
            model = primary_model or settings.LLM_MODEL
            self._providers["openai"] = OpenAIProvider(model=model)
            logger.info(f"OpenAI provider inicializado com modelo {model}")
        elif self.primary_provider_name == "anthropic" and settings.ANTHROPIC_API_KEY:
            model = primary_model or settings.LLM_MODEL
            self._providers["anthropic"] = ClaudeProvider(model=model)
            logger.info(f"Anthropic Claude provider inicializado com modelo {model}")
        elif self.primary_provider_name not in ["local", "fallback"]:
            logger.warning(
                f"Provider '{self.primary_provider_name}' configurado mas API key nao encontrada. "
                f"Usando fallback local."
            )
            self.primary_provider_name = "local"

        # Sempre adiciona fallback local
        self._providers["local"] = LocalFallbackProvider()

        # Define provider primario
        self._primary = self._providers.get(self.primary_provider_name, self._providers["local"])

        if self._primary == self._providers["local"]:
            logger.info("Usando LocalFallbackProvider (respostas pre-definidas)")

    async def generate(
        self,
        messages: list[dict[str, str]],
        system_prompt: str | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        use_fallback: bool = True,
        **kwargs,
    ) -> LLMResponse:
        """
        Gera resposta usando o provider configurado.

        Args:
            messages: Lista de mensagens
            system_prompt: Prompt de sistema
            max_tokens: Maximo de tokens
            temperature: Temperatura
            use_fallback: Usar fallback em caso de erro
            **kwargs: Argumentos adicionais

        Returns:
            LLMResponse com a resposta
        """
        try:
            return await self._primary.generate(
                messages=messages,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs,
            )
        except Exception as e:
            logger.error(f"Erro no provider primario: {e}")

            if use_fallback and self.fallback_enabled:
                logger.info("Usando fallback local")
                return await self._providers["local"].generate(
                    messages=messages,
                    system_prompt=system_prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
            raise

    async def generate_stream(
        self,
        messages: list[dict[str, str]],
        system_prompt: str | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        """Gera resposta em streaming."""
        try:
            async for chunk in self._primary.generate_stream(
                messages=messages,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs,
            ):
                yield chunk
        except Exception as e:
            logger.error(f"Erro no streaming: {e}")

            if self.fallback_enabled:
                async for chunk in self._providers["local"].generate_stream(
                    messages=messages,
                    system_prompt=system_prompt,
                ):
                    yield chunk

    def get_available_models(self) -> list[str]:
        """Retorna lista de modelos disponiveis."""
        return [model.value for model in LLMModel]

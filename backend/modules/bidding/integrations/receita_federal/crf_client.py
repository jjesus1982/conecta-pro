"""
Cliente para CRF/FGTS — Caixa Economica Federal
================================================
Consulta do Certificado de Regularidade do FGTS (CRF) no portal
da Caixa Economica Federal.

O CRF comprova que a empresa esta em dia com suas obrigacoes
de recolhimento do FGTS e e exigido para participacao em
licitacoes publicas (Lei 8.036/90, art. 27).

Validade: 30 dias a partir da emissao.
"""

import asyncio
import contextlib
import logging
import re
from datetime import datetime
from typing import Any

import httpx

from modules.integrations.brasilapi.client import BrasilAPIClient

logger = logging.getLogger(__name__)


class CRFFGTSClient:
    """
    Cliente HTTP para consulta do CRF/FGTS no portal da Caixa.

    O Certificado de Regularidade do FGTS (CRF) e emitido pela
    Caixa Economica Federal e comprova a regularidade da empresa
    perante o Fundo de Garantia do Tempo de Servico.
    """

    # URLs do servico
    BASE_URL = "https://consulta-crf.caixa.gov.br"
    CONSULTA_URL = "https://consulta-crf.caixa.gov.br/consultacrf/rest/consulta"
    PORTAL_URL = "https://consulta-crf.caixa.gov.br/consultacrf/pages/consultaEmpregador.jsf"

    TIMEOUT = 30.0
    MAX_RETRIES = 3
    BACKOFF_BASE = 2.0

    # Tipos de situacao
    TIPO_REGULAR = "CRF"  # Certificado Regular
    TIPO_IRREGULAR = "IRREGULAR"

    VALIDADE_DIAS = 30

    def __init__(self):
        """Inicializa o client HTTP para CRF/FGTS."""
        self.client = httpx.AsyncClient(
            timeout=self.TIMEOUT,
            headers={
                "Accept": "application/json, text/html, application/xml",
                "Content-Type": "application/json",
                "User-Agent": "ConectaPro/1.0",
                "Accept-Language": "pt-BR,pt;q=0.9",
            },
            follow_redirects=True,
        )

    async def close(self):
        """Fecha conexao HTTP."""
        await self.client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def _request_with_retry(self, method: str, url: str, **kwargs) -> httpx.Response:
        """Executa request com retry e backoff para rate limiting."""
        last_exc: Exception | None = None
        for attempt in range(self.MAX_RETRIES):
            try:
                response = await self.client.request(method, url, **kwargs)
                if response.status_code == 429:
                    wait = self.BACKOFF_BASE * (2**attempt)
                    logger.warning(
                        "CRF/FGTS rate limit, aguardando %.1fs (tentativa %d/%d)",
                        wait,
                        attempt + 1,
                        self.MAX_RETRIES,
                    )
                    await asyncio.sleep(wait)
                    continue
                return response
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
                last_exc = e
                wait = self.BACKOFF_BASE * (2**attempt)
                logger.warning("CRF/FGTS erro de conexao, retry em %.1fs: %s", wait, e)
                await asyncio.sleep(wait)
        raise last_exc or httpx.ConnectError("Max retries exceeded for CRF/FGTS")

    def _format_cnpj(self, cnpj: str) -> str:
        """Remove formatacao do CNPJ, mantendo apenas digitos."""
        return re.sub(r"\D", "", cnpj)

    async def consultar_crf(self, cnpj: str) -> dict[str, Any]:
        """
        Consulta CRF/FGTS de um CNPJ.

        Estrategia resiliente (3 camadas):
          1. Portal Caixa REST (CONSULTA_URL) — tenta via JSON
          2. Portal Caixa HTML (PORTAL_URL) — fallback se REST retorna 403/erro
          3. BrasilAPI CNPJ — fallback final se portal Caixa bloqueado
             Confirma regularidade via situacao cadastral da Receita Federal.

        Args:
            cnpj: CNPJ da empresa (com ou sem formatacao)

        Returns:
            Dict com status, situacao, validade e codigo de controle
        """
        cnpj_limpo = self._format_cnpj(cnpj)
        if len(cnpj_limpo) != 14:
            raise ValueError(f"CNPJ invalido: {cnpj}. Deve conter 14 digitos.")

        logger.info("Consultando CRF/FGTS para CNPJ %s", cnpj_limpo)

        # Distingue "portal fora do ar" de "portal nos RECUSA". As duas coisas resultam em
        # "sem certidão", mas pedem ações opostas: fora do ar se resolve esperando; recusa de
        # borda não se resolve nunca a partir daqui. Medido em 18/08/2026 — o host inteiro
        # devolve **403 com página do Azion** (WAF de borda), inclusive a raiz do site:
        #
        #     GET https://consulta-crf.caixa.gov.br/  ->  403, server: azion webserver
        #
        # Não é a Caixa que caiu; é o IP deste servidor que está barrado. Por isso o
        # Infosimples existe. Chamar isso de "indisponível" no log mandava o leitor esperar
        # por algo que não vai mudar.
        bloqueado = False

        # Tentativa 1: API REST JSON
        try:
            response = await self._request_with_retry(
                "POST",
                self.CONSULTA_URL,
                json={"cnpj": cnpj_limpo},
            )
            if response.status_code in (401, 403):
                bloqueado = True
            if response.status_code == 200:
                try:
                    data = response.json()
                    return self._parse_api(data, cnpj_limpo)
                except Exception:
                    pass
        except Exception as exc:
            logger.debug("CRF API REST falhou, tentando HTML: %s", exc)

        # Tentativa 2: portal HTML
        try:
            response = await self._request_with_retry(
                "POST",
                self.PORTAL_URL,
                data={"cnpj": cnpj_limpo},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if response.status_code in (401, 403):
                bloqueado = True
            if response.status_code == 200:
                return self._parse_html(response.text, cnpj_limpo)
        except Exception as exc:
            logger.warning("CRF HTML fallback falhou para %s: %s", cnpj_limpo, exc)

        if bloqueado:
            logger.warning(
                "CRF/FGTS: portal da Caixa RECUSOU a consulta de %s (HTTP 403 — WAF de borda, "
                "Azion). NÃO é indisponibilidade: o IP deste servidor está barrado, e tentar "
                "de novo daqui não muda. Caminhos: token do Infosimples, ou emissão manual em "
                "consulta-crf.caixa.gov.br a partir de um navegador comum.", cnpj_limpo)

        # Tentativa 3: BrasilAPI — fallback quando portal Caixa bloqueia (403/WAF)
        # IMPORTANTE: BrasilAPI CNPJ retorna situacao_cadastral da RFB, que é
        # INDEPENDENTE da regularidade FGTS na Caixa. Empresa pode estar ATIVA na
        # RFB mas com débito FGTS pendente. Por isso retornamos `regular=None` —
        # afirmar regular=True baseado em CNPJ ativo é falso positivo. Caller deve
        # tratar `regular=None` como "status FGTS desconhecido".
        try:
            cnpj_data, _ = await BrasilAPIClient().get_cnpj(cnpj_limpo)
            situacao_cadastral = (cnpj_data.descricao_situacao_cadastral or "").upper()
            cnpj_ativo = situacao_cadastral == "ATIVA"
            logger.warning(
                "CRF/FGTS sem confirmacao da Caixa para %s (portal recusa este servidor). Apenas RFB disponivel: %s",
                cnpj_limpo,
                situacao_cadastral,
            )
            return {
                "cnpj": cnpj_limpo,
                "tipo_certidao": "CRF",
                "situacao": "indeterminado_portal_indisponivel",
                "regular": None,
                "cnpj_ativo_rfb": cnpj_ativo,
                "fonte": "BrasilAPI (fallback)",
                "nota": (
                    "Portal da Caixa RECUSOU a consulta (HTTP 403, WAF de borda) — não é indisponibilidade, é bloqueio do IP deste servidor. Status FGTS NÃO confirmado via "
                    "fonte oficial. Apenas situação cadastral RFB conhecida "
                    f"({'ativa' if cnpj_ativo else 'inativa'})."
                ),
                "consultado_em": datetime.utcnow().isoformat(),
            }
        except Exception as exc:
            logger.error("CRF BrasilAPI fallback falhou para %s: %s", cnpj_limpo, exc)

        # Retorno de erro — somente se todas as 3 tentativas falharem
        return {
            "cnpj": cnpj_limpo,
            "tipo_certidao": None,
            "situacao": "erro_consulta",
            "regular": None,
            "mensagem": "Portal CRF/FGTS e BrasilAPI indisponiveis",
            "consultado_em": datetime.utcnow().isoformat(),
        }

    def _parse_api(self, data: dict, cnpj: str) -> dict[str, Any]:
        """Extrai dados da resposta JSON da API CRF."""
        now = datetime.utcnow().isoformat()

        situacao = data.get("situacao", data.get("situation", ""))
        regular = str(situacao).upper() in ("REGULAR", "1", "ATIVO", "VALIDO", "TRUE")

        # Extrair validade da resposta
        validade_raw = data.get("dataValidade", data.get("validadeAte", data.get("expiry", "")))
        data_validade = None
        with contextlib.suppress(Exception):
            if validade_raw:
                for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
                    try:
                        data_validade = datetime.strptime(str(validade_raw), fmt).isoformat()
                        break
                    except ValueError:
                        continue

        # Sem data no documento NÃO há validade. O que havia aqui era
        # `utcnow() + VALIDADE_DIAS`: a Caixa não devolvia a data e o cliente inventava 30
        # dias de regularidade. Em 11/08/2026 esse padrão (o gêmeo dele em cnd_sync_task)
        # criou quatro certidões que pareciam válidas até 2027 com o portal fora do ar —
        # inclusive a CRF-FGTS vencida da Eletrônica, exibindo-se em dia.
        # Certidão sem validade não é certidão: quem chama decide o que fazer com o None.

        codigo_controle = data.get("codigoControle", data.get("codigo", data.get("code", "")))
        numero = data.get("numero", data.get("numeroCertidao", str(codigo_controle) if codigo_controle else ""))

        return {
            "cnpj": cnpj,
            "tipo_certidao": self.TIPO_REGULAR if regular else self.TIPO_IRREGULAR,
            "situacao": "regular" if regular else "irregular",
            "regular": regular,
            "data_validade": data_validade,
            "validade": data_validade,  # alias compativel com spec do prompt
            "numero": str(numero) if numero else "",
            "fonte": "api_caixa",
            "codigo_controle": str(codigo_controle) if codigo_controle else None,
            "validade_dias": self.VALIDADE_DIAS,
            "emitida_por": "CEF/FGTS",
            "consultado_em": now,
        }

    def _parse_html(self, html: str, cnpj: str) -> dict[str, Any]:
        """Extrai dados do HTML do portal CRF."""
        now = datetime.utcnow().isoformat()

        regular = (
            any(term in html for term in ["REGULAR", "regularidade", "Certificado de Regularidade"])
            and "IRREGULAR" not in html.upper()
        )

        # Extrair validade
        validade_match = re.search(
            r"[Vv]alidade.*?:\s*(\d{2}/\d{2}/\d{4})",
            html,
        )
        data_validade = None
        if validade_match:
            with contextlib.suppress(ValueError):
                data_validade = datetime.strptime(validade_match.group(1), "%d/%m/%Y").isoformat()

        # Mesma regra do parser JSON acima: validade só vem do documento, nunca de hoje+N.

        # Extrair codigo de controle
        codigo_match = re.search(
            r"[Cc][oó]digo\s+(?:de\s+)?[Cc]ontrole.*?:\s*([A-Z0-9./\-]+)",
            html,
        )
        codigo_controle = codigo_match.group(1).strip() if codigo_match else None

        numero_match = re.search(r"n[uú]mero[:\s]+([A-Z0-9./\-]+)", html)
        numero = numero_match.group(1).strip() if numero_match else ""

        return {
            "cnpj": cnpj,
            "tipo_certidao": self.TIPO_REGULAR if regular else self.TIPO_IRREGULAR,
            "situacao": "regular" if regular else "irregular",
            "regular": regular,
            "data_validade": data_validade,
            "validade": data_validade,  # alias compativel com spec do prompt
            "numero": numero,
            "fonte": "html_caixa",
            "codigo_controle": codigo_controle,
            "validade_dias": self.VALIDADE_DIAS,
            "emitida_por": "CEF/FGTS",
            "consultado_em": now,
        }

    async def verificar_regularidade(self, cnpj: str) -> dict[str, Any]:
        """
        Verifica regularidade FGTS de um CNPJ.

        Interface compativel com CNDFederalClient e CNDTTrabalhistaClient.

        Args:
            cnpj: CNPJ da empresa

        Returns:
            Dict com 'regular' (bool), 'tipo_certidao' e 'detalhes'
        """
        resultado = await self.consultar_crf(cnpj)
        regular = resultado.get("regular")
        return {
            "cnpj": resultado["cnpj"],
            "regular": regular,
            "tipo_certidao": resultado.get("tipo_certidao"),
            "situacao": resultado.get("situacao"),
            "data_validade": resultado.get("data_validade"),
            "apto_licitar": bool(regular) if regular is not None else None,
            "observacao": (
                "Empresa regular perante a Caixa Economica Federal (FGTS)"
                if regular is True
                else "Empresa com pendencias FGTS — verificar debitos na Caixa"
                if regular is False
                else "Status FGTS indeterminado — a Caixa recusa consulta deste servidor (403/WAF); emitir pelo Infosimples ou à mão num navegador comum"
            ),
        }

    def get_certidao_url(self) -> str:
        """Retorna URL do portal CRF para emissao/consulta."""
        return self.PORTAL_URL

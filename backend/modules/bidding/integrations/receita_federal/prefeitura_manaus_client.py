"""
Cliente para CND Municipal — SEMEF Manaus (Prefeitura de Manaus)
================================================================
Consulta da Certidao Negativa de Debitos Municipais (ISS) no portal
da Secretaria Municipal de Financas e Tecnologia da Informacao (SEMEF)
da Prefeitura de Manaus.

Portais:
  https://semef.manaus.am.gov.br/certidao
  https://semef.manaus.am.gov.br/cnd
  https://sistemas.semef.manaus.am.gov.br/cnd

Validade: 180 dias a partir da emissao.
Quando o portal estiver inacessivel, retorna requer_manual=True
com instrucao para emissao manual — nunca quebra o pipeline.
"""

import asyncio
import logging
import re
from datetime import datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class PrefeituraManausClient:
    """
    Cliente HTTP para CND Municipal de Manaus (SEMEF).

    A Certidao Negativa de Debitos Municipais comprova regularidade
    perante o municipio de Manaus, incluindo ISS e demais tributos.
    Validade: 180 dias.

    Compativel com o pipeline de certidoes do cnd_sync_task.py:
    usa async context manager identico ao CNDFederalClient.
    """

    SEMEF_URLS = [
        "https://semef.manaus.am.gov.br/certidao",
        "https://semef.manaus.am.gov.br/cnd",
        "https://sistemas.semef.manaus.am.gov.br/cnd",
        "https://www.manaus.am.gov.br/servico/certidao-negativa-de-debitos-municipais",
    ]

    TIMEOUT = 30.0
    MAX_RETRIES = 3
    BACKOFF_BASE = 2.0
    VALIDADE_DIAS = 180
    VALIDADE_PADRAO_DIAS = 180  # alias conforme especificação

    TIPO_CND = "CND"
    TIPO_CPDEN = "CPDEN"
    TIPO_CPD = "CPD"

    def __init__(self) -> None:
        self.client = httpx.AsyncClient(
            timeout=self.TIMEOUT,
            headers={
                "Accept": "application/json, text/html",
                "User-Agent": "ConectaPRO/1.0",
                "Accept-Language": "pt-BR,pt;q=0.9",
            },
            follow_redirects=True,
            verify=False,  # noqa: S501  # nosec B501 — portais SEMEF/Manaus usam cert auto-assinado
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def __aenter__(self) -> "PrefeituraManausClient":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    def _format_cnpj(self, cnpj: str) -> str:
        return re.sub(r"\D", "", cnpj)

    async def _request_with_retry(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(self.MAX_RETRIES):
            try:
                response = await self.client.request(method, url, **kwargs)
                if response.status_code == 429:
                    wait = self.BACKOFF_BASE * (2**attempt)
                    logger.warning(
                        "SEMEF Manaus rate limit, aguardando %.1fs (tentativa %d/%d)",
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
                logger.debug(
                    "SEMEF Manaus erro de conexao (tentativa %d/%d), retry em %.1fs: %s",
                    attempt + 1,
                    self.MAX_RETRIES,
                    wait,
                    e,
                )
                await asyncio.sleep(wait)
        raise last_exc or httpx.ConnectError("Max retries exceeded for SEMEF Manaus")

    def _parse_resultado_cnd(self, html: str, cnpj: str, url: str) -> dict[str, Any]:
        """Extrai dados da certidao do HTML de resposta do portal SEMEF."""
        html_lower = html.lower()
        now = datetime.utcnow().isoformat()

        # ── O veredito só vale se a resposta for SOBRE ESTE CNPJ ──────────────────
        # Medido em 11/08/2026: este parser recebia a PÁGINA DE SERVIÇO do órgão (que
        # explica o que é uma certidão) e casava as palavras dela. Resultado: veredito
        # idêntico para qualquer CNPJ — o de Manaus dizia `irregular` até para o Banco do
        # Brasil; o da Sefaz dizia `regular` até para o CNPJ inexistente 11111111111111,
        # sempre com a mesma validade (que era o fallback hoje+180d, não documento).
        # Página que não cita o CNPJ perguntado não é resposta: é folheto.
        _digitos = re.sub(r"\D", "", cnpj or "")
        _html_digitos = re.sub(r"\D", "", html_lower)
        _cita_cnpj = bool(_digitos) and _digitos in _html_digitos
        # A citação do CNPJ sozinha NÃO basta: o portal ecoa a query string (`?cnpj=...`)
        # de volta no HTML, então até um CNPJ inexistente "aparece" na página. Certidão de
        # verdade sempre traz DATA DE VALIDADE — sem data no documento, não há veredito.
        _tem_data = bool(re.search(r"\d{2}/\d{2}/\d{4}", html_lower))
        if not _cita_cnpj or not _tem_data:
            return {
                "cnpj": cnpj,
                "tipo_certidao": None,
                "situacao": "requer_manual",
                "regular": None,
                "data_validade": None,
                "requer_manual": True,
                "nota": ("Resposta do portal não menciona o CNPJ consultado — é página "
                         "informativa, não resultado. Emitir manualmente no portal."),
                "url": url,
                "consultado_em": now,
            }

        # Detectar tipo de certidao
        tipo_certidao: str | None = None
        if any(
            x in html_lower
            for x in [
                "certidão negativa",
                "certidao negativa",
                "nada consta",
                "isento",
                "sem débito",
                "sem debito",
            ]
        ):
            tipo_certidao = self.TIPO_CND
        elif any(x in html_lower for x in ["positiva com efeito", "efeito de negativa"]):
            tipo_certidao = self.TIPO_CPDEN
        elif any(
            x in html_lower
            for x in [
                "débito",
                "debito",
                "pendência",
                "pendencia",
                "irregular",
                "bloqueado",
            ]
        ):
            tipo_certidao = self.TIPO_CPD

        regular = tipo_certidao in (self.TIPO_CND, self.TIPO_CPDEN)

        # Extrair validade
        data_match = re.search(r"v[aá]lid[ao][^\d]*(\d{2}/\d{2}/\d{4})", html_lower)
        data_validade: str | None = None
        if data_match:
            try:
                data_validade = datetime.strptime(data_match.group(1), "%d/%m/%Y").isoformat()
            except ValueError:
                pass

        # Sem data no documento não há validade. O fallback que existia aqui
        # (hoje + VALIDADE_DIAS) foi metade da fabricação de 11/08/2026.

        # Extrair numero da certidao
        num_match = re.search(r"n[uú]mero[^\d]*([\d][\d\.\/\-]+)", html_lower)
        codigo_controle = num_match.group(1).strip() if num_match else None

        return {
            "cnpj": cnpj,
            "tipo_certidao": tipo_certidao or "CND_MUNICIPAL",
            "situacao": "regular" if regular else "irregular",
            "regular": regular,
            "data_validade": data_validade,
            "codigo_controle": codigo_controle,
            "validade_dias": self.VALIDADE_DIAS,
            "emitida_por": "SEMEF/Manaus",
            "url": url,
            "consultado_em": now,
        }

    async def consultar_cnd(self, cnpj: str) -> dict[str, Any]:
        """
        Consulta CND Municipal (SEMEF Manaus) para um CNPJ.

        Tenta os endpoints conhecidos do portal SEMEF.
        Quando o portal estiver inacessivel, retorna requer_manual=True.

        Args:
            cnpj: CNPJ da empresa (com ou sem formatacao)

        Returns:
            Dict com situacao, regular, data_validade, requer_manual
        """
        cnpj_limpo = self._format_cnpj(cnpj)
        if len(cnpj_limpo) != 14:
            raise ValueError(f"CNPJ invalido: {cnpj}. Deve conter 14 digitos.")

        logger.info("Consultando CND Municipal (SEMEF Manaus) para CNPJ %s", cnpj_limpo)

        for url_base in self.SEMEF_URLS:
            try:
                # Tentar GET com CNPJ como query param
                resp = await self._request_with_retry("GET", f"{url_base}?cnpj={cnpj_limpo}")
                if resp.status_code == 200 and len(resp.text) > 200:
                    return self._parse_resultado_cnd(resp.text, cnpj_limpo, url_base)

                # Tentar POST com form-data
                resp2 = await self._request_with_retry(
                    "POST",
                    url_base,
                    data={"cnpj": cnpj_limpo, "tipo": "CNPJ"},
                )
                if resp2.status_code == 200 and len(resp2.text) > 200:
                    return self._parse_resultado_cnd(resp2.text, cnpj_limpo, url_base)

            except Exception as e:
                logger.debug("SEMEF Manaus URL %s falhou: %s", url_base, e)
                continue

        # Portal inacessivel — retornar instrucao manual sem quebrar o pipeline
        logger.warning(
            "SEMEF Manaus: portal inacessivel para CNPJ %s — marcando como requer_manual",
            cnpj_limpo,
        )
        return {
            "cnpj": cnpj_limpo,
            "tipo_certidao": "CND_MUNICIPAL",
            "situacao": "requer_manual",
            "regular": None,
            "data_validade": None,
            "codigo_controle": None,
            "validade_dias": self.VALIDADE_DIAS,
            "emitida_por": "SEMEF/Manaus",
            "requer_manual": True,
            "instrucao": ("Emitir manualmente em: https://semef.manaus.am.gov.br"),
            "consultado_em": datetime.utcnow().isoformat(),
        }

    async def verificar_regularidade(self, cnpj: str) -> dict[str, Any]:
        """
        Verifica regularidade fiscal municipal de um CNPJ.

        Interface compativel com CNDFederalClient.verificar_regularidade().
        """
        resultado = await self.consultar_cnd(cnpj)
        return {
            "cnpj": resultado.get("cnpj", cnpj),
            "regular": resultado.get("regular", False),
            "tipo_certidao": resultado.get("tipo_certidao"),
            "situacao": resultado.get("situacao"),
            "data_validade": resultado.get("data_validade"),
            "apto_licitar": resultado.get("regular", False),
            "requer_manual": resultado.get("requer_manual", False),
            "instrucao": resultado.get("instrucao", ""),
            "observacao": (
                "Empresa regular perante a Prefeitura de Manaus (SEMEF)"
                if resultado.get("regular")
                else (
                    "Emissao manual necessaria — portal SEMEF inacessivel"
                    if resultado.get("requer_manual")
                    else "Empresa com pendencias fiscais municipais — verificar debitos SEMEF Manaus"
                )
            ),
        }

    # Alias conforme especificação do prompt
    async def consultar_cnd_municipal(self, cnpj: str) -> dict[str, Any]:
        """Alias de consultar_cnd() conforme especificação."""
        return await self.consultar_cnd(cnpj)

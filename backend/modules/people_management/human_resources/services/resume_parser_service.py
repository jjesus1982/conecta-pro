"""
Serviço de Parsing de Currículos — PDF/DOCX + IA.

Extrai texto de currículos em PDF e DOCX, analisa com cascata LLM
(OpenAI gpt-5 primário → Anthropic fallback opcional) para extrair
dados estruturados (dados pessoais, experiência, formação, etc).

Fallback final: regex parsing quando nenhum provedor LLM está disponível.
"""

import io
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Tentar importar PyMuPDF (fitz) como alternativa ao PyPDF2
try:
    import fitz as pymupdf  # PyMuPDF

    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

try:
    from docx import Document as DocxDocument

    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

class ResumeParserService:
    """Parser de currículos com extração por IA (cascata OpenAI→Anthropic) e fallback regex."""

    OPENAI_MODEL = "gpt-5"
    CLAUDE_MODEL = "claude-sonnet-4-20250514"  # fallback opcional da cascata
    LLM_MAX_TOKENS = 2048
    CLAUDE_MAX_TOKENS = 2048  # legado (mantido por compatibilidade)

    # === EXTRAÇÃO DE TEXTO ===

    @staticmethod
    def extract_text_pdf(file_bytes: bytes) -> str:
        """Extrai texto de arquivo PDF.

        Usa PyMuPDF (fitz) para melhor extração.

        Args:
            file_bytes: Bytes do arquivo PDF.

        Returns:
            Texto extraído do PDF.

        Raises:
            ImportError: Se PyMuPDF não estiver instalado.
        """
        if not HAS_PYMUPDF:
            raise ImportError("PyMuPDF (fitz) não instalado. Instale com: pip install PyMuPDF")

        doc = pymupdf.open(stream=file_bytes, filetype="pdf")
        text_parts = []
        for page in doc:
            text_parts.append(page.get_text())
        doc.close()
        return "\n".join(text_parts)

    @staticmethod
    def extract_text_docx(file_bytes: bytes) -> str:
        """Extrai texto de arquivo DOCX.

        Args:
            file_bytes: Bytes do arquivo DOCX.

        Returns:
            Texto extraído do DOCX.

        Raises:
            ImportError: Se python-docx não estiver instalado.
        """
        if not HAS_DOCX:
            raise ImportError("python-docx não instalado. Instale com: pip install python-docx")

        doc = DocxDocument(io.BytesIO(file_bytes))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n".join(paragraphs)

    @staticmethod
    def extract_text(file_bytes: bytes, filename: str) -> str:
        """Extrai texto baseado na extensão do arquivo.

        Args:
            file_bytes: Bytes do arquivo.
            filename: Nome do arquivo (para detectar extensão).

        Returns:
            Texto extraído.

        Raises:
            ValueError: Se formato não suportado.
        """
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext == "pdf":
            return ResumeParserService.extract_text_pdf(file_bytes)
        elif ext in ("docx", "doc"):
            return ResumeParserService.extract_text_docx(file_bytes)
        elif ext == "txt":
            return file_bytes.decode("utf-8", errors="replace")
        else:
            raise ValueError(f"Formato não suportado: .{ext}. Use PDF, DOCX ou TXT.")

    # === ANÁLISE COM IA (cascata OpenAI → Anthropic) ===

    @staticmethod
    def analyze_with_claude(text: str) -> dict[str, Any]:
        """Analisa texto do currículo usando cascata LLM (OpenAI → Anthropic).

        Extrai dados estruturados: dados pessoais, experiência profissional,
        formação acadêmica, habilidades e idiomas.

        Nome mantido por compatibilidade (contrato público chamado pelos controllers).

        Args:
            text: Texto do currículo.

        Returns:
            Dicionário com dados estruturados extraídos.
        """
        try:
            from core.llm_cascade import chat_ex

            prompt = f"""Analise o currículo abaixo e extraia dados estruturados em JSON.

Retorne EXATAMENTE este formato JSON (sem markdown, sem backticks):
{{
  "dados_pessoais": {{
    "nome": "",
    "email": "",
    "telefone": "",
    "cidade": "",
    "estado": "",
    "linkedin": ""
  }},
  "objetivo": "",
  "experiencia": [
    {{
      "empresa": "",
      "cargo": "",
      "periodo": "",
      "descricao": ""
    }}
  ],
  "formacao": [
    {{
      "instituicao": "",
      "curso": "",
      "nivel": "",
      "periodo": ""
    }}
  ],
  "habilidades": [],
  "idiomas": [
    {{
      "idioma": "",
      "nivel": ""
    }}
  ],
  "certificacoes": [],
  "resumo_profissional": "",
  "anos_experiencia_total": 0,
  "area_principal": "",
  "nivel_senioridade": ""
}}

CURRÍCULO:
{text[:6000]}"""

            result = chat_ex(
                messages=[{"role": "user", "content": prompt}],
                model_openai=ResumeParserService.OPENAI_MODEL,
                model_anthropic=ResumeParserService.CLAUDE_MODEL,
                max_tokens=ResumeParserService.LLM_MAX_TOKENS,
                json_mode=True,
            )

            if result is None:
                logger.warning("Nenhum provedor LLM disponível, usando fallback regex")
                return ResumeParserService._fallback_regex_parse(text)

            result_text, provider, model = result
            result_text = result_text.strip()

            # Tentar extrair JSON da resposta
            import json

            # Remove possíveis backticks
            if result_text.startswith("```"):
                result_text = result_text.split("```")[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]

            parsed = json.loads(result_text)
            parsed["_source"] = f"{provider}_api"
            parsed["_model"] = model
            logger.info(
                "Currículo analisado via %s (%s): %s",
                provider,
                model,
                parsed.get("dados_pessoais", {}).get("nome", "?"),
            )
            return parsed

        except Exception as e:
            logger.error("Erro na análise via LLM: %s. Usando fallback.", e)
            return ResumeParserService._fallback_regex_parse(text)

    # === FALLBACK REGEX ===

    @staticmethod
    def _fallback_regex_parse(text: str) -> dict[str, Any]:
        """Parsing de currículo via regex quando API não disponível.

        Extração básica de email, telefone, e seções por palavras-chave.

        Args:
            text: Texto do currículo.

        Returns:
            Dicionário com dados extraídos por regex.
        """
        result: dict[str, Any] = {
            "dados_pessoais": {},
            "objetivo": "",
            "experiencia": [],
            "formacao": [],
            "habilidades": [],
            "idiomas": [],
            "certificacoes": [],
            "_source": "regex_fallback",
        }

        # Email
        email_match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
        if email_match:
            result["dados_pessoais"]["email"] = email_match.group()

        # Telefone
        phone_match = re.search(r"\(?\d{2}\)?\s*\d{4,5}[-.\s]?\d{4}", text)
        if phone_match:
            result["dados_pessoais"]["telefone"] = phone_match.group()

        # Nome (primeira linha não vazia)
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        if lines:
            candidate_name = lines[0]
            if len(candidate_name) < 60 and not re.search(r"@|http|curricul|resumo", candidate_name, re.I):
                result["dados_pessoais"]["nome"] = candidate_name

        # LinkedIn
        linkedin_match = re.search(r"linkedin\.com/in/[\w-]+", text, re.I)
        if linkedin_match:
            result["dados_pessoais"]["linkedin"] = linkedin_match.group()

        # Habilidades
        skills_section = _extract_section(text, ["habilidades", "competências", "skills", "conhecimentos"])
        if skills_section:
            items = re.split(r"[,;•\n]", skills_section)
            result["habilidades"] = [s.strip() for s in items if s.strip() and len(s.strip()) < 50][:20]

        # Idiomas
        idiomas_section = _extract_section(text, ["idiomas", "languages"])
        if idiomas_section:
            items = re.split(r"[;\n]", idiomas_section)
            for item in items:
                item = item.strip()
                if item and len(item) < 80:
                    result["idiomas"].append({"idioma": item, "nivel": ""})

        logger.info("Currículo analisado via regex fallback")
        return result

    # === MÉTODO PRINCIPAL ===

    @staticmethod
    def parse_resume(file_bytes: bytes, filename: str) -> dict[str, Any]:
        """Método principal: extrai texto e analisa currículo.

        Pipeline completo:
        1. Detecta formato (PDF/DOCX/TXT)
        2. Extrai texto
        3. Analisa com cascata LLM OpenAI→Anthropic (ou fallback regex)

        Args:
            file_bytes: Bytes do arquivo.
            filename: Nome do arquivo.

        Returns:
            Dicionário com dados estruturados do currículo.
        """
        text = ResumeParserService.extract_text(file_bytes, filename)
        analysis = ResumeParserService.analyze_with_claude(text)
        analysis["_filename"] = filename
        analysis["_text_length"] = len(text)
        return analysis


def _extract_section(text: str, keywords: list[str]) -> str:
    """Extrai seção do currículo por palavras-chave.

    Args:
        text: Texto completo.
        keywords: Lista de palavras-chave para encontrar o início da seção.

    Returns:
        Texto da seção encontrada, ou string vazia.
    """
    pattern = "|".join(re.escape(k) for k in keywords)
    match = re.search(rf"(?:^|\n)\s*(?:{pattern})\s*:?\s*\n(.*?)(?:\n\s*\n|\Z)", text, re.I | re.S)
    return match.group(1).strip() if match else ""

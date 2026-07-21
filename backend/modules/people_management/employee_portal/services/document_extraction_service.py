"""Extração de dados de documentos do candidato (Fase 6.1).

Recebe um documento (imagem ou PDF), identifica o tipo e extrai os campos para
PRÉ-PREENCHER o autocadastro — o candidato revisa antes de enviar. NUNCA fabrica:
campo ausente = null. Usa o llm_cascade (gpt-5) com visão (bloco image_url) para
imagens/PDF escaneado e texto (PyMuPDF) para PDF nativo.
"""

import base64
import json
from typing import Any

from core.llm_cascade import chat_ex

# Campos que cada tipo de documento pode preencher (chaves do form do candidato).
_CAMPOS_POR_TIPO: dict[str, list[str]] = {
    "rg": ["nome", "rg", "rg_orgao", "rg_uf", "data_nascimento", "nome_mae", "nome_pai", "naturalidade"],
    "cpf": ["cpf", "nome", "data_nascimento"],
    "comprovante_endereco": ["cep", "logradouro", "numero", "bairro", "cidade", "uf"],
    "curriculo": ["nome", "email", "telefone", "cidade", "uf"],
    "ctps": ["pis", "ctps_numero", "ctps_serie", "ctps_uf", "nome", "data_nascimento", "nome_mae"],
    "certidao_nascimento": ["dependente_nome", "dependente_nascimento", "nome_mae", "nome_pai"],
    "outro": ["nome", "cpf", "rg", "data_nascimento", "cep", "logradouro", "bairro", "cidade", "uf", "nome_mae"],
}

_DESC_TIPO: dict[str, str] = {
    "rg": "uma carteira de identidade (RG)",
    "cpf": "um comprovante de CPF",
    "comprovante_endereco": "um comprovante de endereço (conta de luz/água/etc.)",
    "curriculo": "um currículo",
    "ctps": "uma Carteira de Trabalho (CTPS)",
    "certidao_nascimento": "uma certidão de nascimento de filho (para salário-família)",
    "outro": "um documento pessoal",
}

_TIPOS = set(_CAMPOS_POR_TIPO.keys())


def _prompt(tipo: str) -> str:
    campos = _CAMPOS_POR_TIPO.get(tipo, _CAMPOS_POR_TIPO["outro"])
    return (
        "Você extrai dados de documentos brasileiros para um cadastro de RH. "
        f"O documento é {_DESC_TIPO.get(tipo, 'um documento pessoal')}. "
        f"Responda SOMENTE um objeto JSON com exatamente estas chaves: {', '.join(campos)}. "
        "Regras: datas no formato YYYY-MM-DD; CEP/CPF/RG conforme aparecem no documento; "
        "nomes em CAIXA conforme o documento. "
        "NÃO INVENTE nada: se um campo não estiver claramente no documento, use null. "
        "Se houver vários valores, use o principal/titular do documento."
    )


def _pdf_texto(data: bytes) -> str:
    import fitz  # PyMuPDF

    doc = fitz.open(stream=data, filetype="pdf")
    try:
        return "\n".join(p.get_text() for p in doc)
    finally:
        doc.close()


def _pdf_primeira_pagina_png(data: bytes) -> bytes:
    import fitz

    doc = fitz.open(stream=data, filetype="pdf")
    try:
        pix = doc[0].get_pixmap(dpi=150)
        return pix.tobytes("png")
    finally:
        doc.close()


def _msgs_imagem(prompt: str, mime: str, data: bytes) -> list[dict]:
    b64 = base64.b64encode(data).decode()
    return [
        {"role": "system", "content": prompt},
        {"role": "user", "content": [
            {"type": "text", "text": "Extraia os dados deste documento:"},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        ]},
    ]


def extrair(file_bytes: bytes, mime: str, tipo: str) -> dict[str, Any]:
    """Extrai campos do documento. Retorna {status, campos:{...}, modelo?}.
    status='ok' com campos, ou 'vazio'/'erro'. campos só traz o que EXISTE no doc."""
    tipo = tipo if tipo in _TIPOS else "outro"
    prompt = _prompt(tipo)
    try:
        mime = (mime or "").lower()
        if "pdf" in mime:
            texto = (_pdf_texto(file_bytes) or "").strip()
            if len(texto) >= 40:  # PDF com camada de texto
                msgs = [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": "Conteúdo do documento:\n\n" + texto[:7000]},
                ]
            else:  # PDF escaneado → renderiza e usa visão
                msgs = _msgs_imagem(prompt, "image/png", _pdf_primeira_pagina_png(file_bytes))
        else:  # imagem (jpeg/png/…)
            msgs = _msgs_imagem(prompt, mime or "image/jpeg", file_bytes)

        r = chat_ex(msgs, model_openai="gpt-5-mini", model_anthropic=None, json_mode=True, max_tokens=700)
        if not r:
            return {"status": "erro", "erro": "IA indisponível", "campos": {}}
        dados = json.loads(r[0]) if r[0] else {}
        campos = {
            k: (v.strip() if isinstance(v, str) else v)
            for k, v in dados.items()
            if v not in (None, "", "null", "N/A", "-") and k in _CAMPOS_POR_TIPO.get(tipo, [])
        }
        return {"status": "ok" if campos else "vazio", "campos": campos, "modelo": r[2]}
    except Exception as e:  # noqa: BLE001 — extração é best-effort, nunca quebra o cadastro
        return {"status": "erro", "erro": str(e)[:150], "campos": {}}

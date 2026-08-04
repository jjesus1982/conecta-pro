"""Anexos do chat escopado: extrai texto de PDF/DOCX/TXT e prepara fotos como data URL
para o modelo enxergar (vision). Reusa a MESMA extração do consultor jurídico
(fitz/python-docx), num único lugar. O texto é truncado p/ não estourar o contexto."""
from __future__ import annotations

import base64

_IMG_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif")
_MAX_TEXTO = 200000  # ~50k tokens; cabe uma folha de 13+ páginas inteira. gpt-5.1 tem 400k
# de contexto — 24k cortava a folha da Portte na pág. 7/13 e perdia o quadro-resumo final.


def eh_imagem(nome: str) -> bool:
    return (nome or "").lower().endswith(_IMG_EXT)


def extrair_texto_arquivo(nome: str, data: bytes) -> str:
    """Extrai texto de PDF (PyMuPDF), DOCX (python-docx) ou TXT. Trunca em _MAX_TEXTO."""
    n = (nome or "").lower()
    try:
        if n.endswith(".pdf"):
            import fitz  # noqa: PLC0415
            doc = fitz.open(stream=data, filetype="pdf")
            txt = "\n".join(p.get_text() for p in doc)
            doc.close()
        elif n.endswith(".docx"):
            import io  # noqa: PLC0415
            from docx import Document  # noqa: PLC0415
            d = Document(io.BytesIO(data))
            txt = "\n".join(p.text for p in d.paragraphs)
        else:
            txt = data.decode("utf-8", "ignore")
    except Exception:  # noqa: BLE001 — anexo ruim nunca derruba o chat
        txt = data.decode("utf-8", "ignore")
    return txt.strip()[:_MAX_TEXTO]


def imagem_data_url(nome: str, data: bytes) -> str:
    """Foto -> data URL base64 p/ o content-part image_url (vision do gpt-5.1)."""
    n = (nome or "").lower()
    if n.endswith((".jpg", ".jpeg")):
        mime = "image/jpeg"
    elif n.endswith(".webp"):
        mime = "image/webp"
    elif n.endswith(".gif"):
        mime = "image/gif"
    else:
        mime = "image/png"
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


def _demo() -> None:
    assert eh_imagem("foto.JPG") and not eh_imagem("contrato.pdf")
    assert extrair_texto_arquivo("nota.txt", b"  ola mundo  ") == "ola mundo"
    assert extrair_texto_arquivo("x.txt", b"a" * (_MAX_TEXTO + 5000)) == "a" * _MAX_TEXTO  # trunca
    u = imagem_data_url("f.jpeg", b"\x00\x01")
    assert u.startswith("data:image/jpeg;base64,")
    print("anexos ok")


if __name__ == "__main__":
    _demo()

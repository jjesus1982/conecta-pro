"""Decodificador de BR Code PIX (copia-e-cola / QR Code) — padrão EMV MPM (BCB).

Extrai chave PIX, valor, nome do recebedor e txid de um "copia e cola". Suporta o
caso ESTÁTICO (chave embutida) — o mais comum para pagar fornecedor recorrente. O
caso DINÂMICO (payload traz uma URL do PSP, sem chave embutida) é sinalizado
(`dinamico=True`) para o chamador tratar (hoje: pagar pelo app e conciliar).

Não faz efeito externo — recebe string, devolve dict. Nunca fabrica dado: se não
achar chave, devolve chave=None e o motivo.
"""

from __future__ import annotations

from typing import Any


def _parse_tlv(payload: str) -> dict[str, str]:
    """Quebra um payload EMV em {id: valor}. Cada campo = ID(2) + LEN(2) + VALOR(LEN)."""
    out: dict[str, str] = {}
    i = 0
    n = len(payload)
    while i + 4 <= n:
        tag = payload[i:i + 2]
        try:
            length = int(payload[i + 2:i + 4])
        except ValueError:
            break
        start = i + 4
        end = start + length
        if end > n:
            break
        out[tag] = payload[start:end]
        i = end
    return out


def _crc16(data: str) -> str:
    """CRC-16/CCITT-FALSE (polinômio 0x1021, init 0xFFFF) — valida integridade do BR Code."""
    crc = 0xFFFF
    for ch in data.encode("utf-8"):
        crc ^= ch << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if (crc & 0x8000) else (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def _detectar_tipo_chave(chave: str) -> str:
    c = (chave or "").strip()
    digitos = "".join(ch for ch in c if ch.isdigit())
    if "@" in c:
        return "EMAIL"
    if c.startswith("+") or (digitos == c and len(digitos) in (10, 11) and not len(digitos) == 11):
        pass
    if len(digitos) == 11 and c == digitos:
        return "CPF"
    if len(digitos) == 14 and c == digitos:
        return "CNPJ"
    if c.startswith("+55") or (len(digitos) in (12, 13) and c.startswith("+")):
        return "TELEFONE"
    # EVP (aleatória) = UUID 36 chars com hífens
    if len(c) == 36 and c.count("-") == 4:
        return "EVP"
    return "EVP"


def decodificar_brcode(brcode: str) -> dict[str, Any]:
    """Decodifica um copia-e-cola PIX. Retorna:
    {valido, dinamico, chave, tipo_chave, valor, nome, cidade, txid, motivo}.
    """
    raw = (brcode or "").strip()
    if len(raw) < 20 or "br.gov.bcb.pix" not in raw.lower() and "BR.GOV.BCB.PIX" not in raw:
        # ainda tenta parsear — alguns leitores devolvem sem o GUI em maiúsculo
        pass
    res: dict[str, Any] = {"valido": False, "dinamico": False, "chave": None, "tipo_chave": None,
                           "valor": None, "nome": None, "cidade": None, "txid": None, "motivo": None}
    try:
        top = _parse_tlv(raw)
    except Exception:
        res["motivo"] = "Payload ilegível."
        return res

    # valida CRC (campo 63, sempre os últimos 4 chars após "6304")
    if "6304" in raw:
        idx = raw.rfind("6304")
        base = raw[:idx + 4]
        crc_informado = raw[idx + 4:idx + 8].upper()
        if crc_informado and _crc16(base) != crc_informado:
            res["motivo"] = "CRC inválido — o código pode ter sido copiado errado/incompleto."
            return res

    # Merchant Account Information PIX = qualquer tag 26..51 que contenha o GUI br.gov.bcb.pix
    mai = None
    for tag in (f"{n:02d}" for n in range(26, 52)):
        val = top.get(tag)
        if val and "br.gov.bcb.pix" in val.lower():
            mai = _parse_tlv(val)
            break
    if mai is None:
        res["motivo"] = "Não é um PIX copia-e-cola válido (sem dados PIX)."
        return res

    chave = (mai.get("01") or "").strip()      # chave estática
    url = (mai.get("25") or "").strip()         # payload dinâmico (URL do PSP)
    res["nome"] = (top.get("59") or "").strip() or None
    res["cidade"] = (top.get("60") or "").strip() or None
    valor_str = (top.get("54") or "").strip()
    if valor_str:
        try:
            res["valor"] = float(valor_str)
        except ValueError:
            res["valor"] = None
    dados_extra = _parse_tlv(top.get("62") or "")
    res["txid"] = (dados_extra.get("05") or "").strip() or None

    if chave:
        res["valido"] = True
        res["dinamico"] = False
        res["chave"] = chave
        res["tipo_chave"] = _detectar_tipo_chave(chave)
        return res
    if url:
        # dinâmico: precisa resolver a URL no PSP (não suportado no fluxo direto ainda)
        res["valido"] = True
        res["dinamico"] = True
        res["motivo"] = ("QR dinâmico (valor/link no PSP). Pague pelo app do Inter e marque como "
                         "'pago pelo app Inter', ou use a chave PIX direta.")
        return res
    res["motivo"] = "Sem chave PIX no código."
    return res

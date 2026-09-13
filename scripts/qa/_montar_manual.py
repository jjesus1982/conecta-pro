#!/usr/bin/env python3
"""Converte o PPTX da marca (gerado pelo conector) em PDF — 13/09/2026.

⚠️ O PPTX é SEMPRE gerado por `gerar_apresentacao` do conector: é ela que aplica o timbrado
padrão-ouro (logo, cores, rodapé com CNPJ/0800). Aqui só se muda o CONTAINER do arquivo, nunca
o conteúdo. Montar slide fora do conector é proibido pela regra da casa.

O caminho `formato="pdf"` da própria ferramenta está quebrado em produção: falta LibreOffice no
container (`RuntimeError: LibreOffice (soffice) não encontrado`). Enquanto não entrar na imagem,
a conversão acontece no host.
"""
from __future__ import annotations

import base64
import json
import subprocess
import sys
from pathlib import Path

SAIDA = Path("/opt/conecta-pro/uploads/manuais")


def main() -> int:
    if len(sys.argv) < 3:
        print("uso: _montar_manual.py <json-do-tool-result> <Nome_Do_Arquivo>"); return 2
    dados = json.load(open(sys.argv[1]))
    if not dados.get("ok"):
        print("tool devolveu erro:", {k: v for k, v in dados.items() if k != "pptx_base64"}); return 1
    SAIDA.mkdir(parents=True, exist_ok=True)
    pptx = SAIDA / f"{sys.argv[2]}.pptx"
    pptx.write_bytes(base64.b64decode(dados["pptx_base64"]))
    r = subprocess.run(  # noqa: S603 — comando fixo
        ["/usr/bin/soffice", "--headless", "--convert-to", "pdf", "--outdir", str(SAIDA), str(pptx)],
        capture_output=True, text=True, timeout=600)
    pdf = SAIDA / f"{sys.argv[2]}.pdf"
    if not pdf.exists():
        print("conversão falhou:", r.stdout[-300:], r.stderr[-300:]); return 1
    print(f"OK {pdf.name}  {pdf.stat().st_size // 1024} KB  (pptx {pptx.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

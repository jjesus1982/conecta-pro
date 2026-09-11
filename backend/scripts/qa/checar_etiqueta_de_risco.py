#!/usr/bin/env python3
"""As travas do conector MCP passam a RODAR — elas existiam e ninguém as chamava.

`mcp-server/` tem quatro arquivos `test_*.py` escritos em 23/08/2026 contra defeitos reais
(etiqueta de risco que mente, exceção virando gaveta, identidade, segundo plano). Medido em
11/09: **nenhum é executado por nada** — não estão no `checar_regressao`, não estão na
varredura da meia-noite, não estão em CI. Teste que ninguém roda é documentação com sintaxe
de teste.

E o preço apareceu no mesmo dia. `test_read_nao_escreve` existe exatamente para impedir que
uma ferramenta que ESCREVE se declare `read` — a classe que o `gate_propose` deixa passar sem
humano. Ele estava verde com **13 ferramentas mentindo**, porque a regex dele só conhecia
`erp.post(...)` e as 13 chamam pela outra porta, `erp.request("PUT", ...)`. Entre elas
`revisar_justificativa_ponto` (decide a falta de alguém, e a folha lê isso),
`definir_parametros_precificacao` (o parâmetro de onde sai todo preço cotado) e
`excluir_campanha` (`DELETE FROM`, sem soft).

Este caçador não reimplementa nada: ele EXECUTA os testes do `mcp-server/` e devolve o
resultado. A régua e a lista de exceções continuam num lugar só, junto do código que elas
vigiam — duas cópias da mesma regra divergem, e a que diverge cala.

    python3 backend/scripts/qa/checar_etiqueta_de_risco.py

Linha canônica: `TOTAL travas do MCP falhando: N` (binária: N = 0).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

MCP = Path("/opt/conecta-pro/mcp-server")
# DESCOBERTA, não lista fixa: a lista fixa conhecia três, e o quarto arquivo
# (`test_segundo_plano.py`, 11/09/2026) rodava no build da imagem e ficava invisível aqui.
# Trava que depende de alguém lembrar de acrescentar o nome não é trava — é convenção.
# Exclui `test_aceites_cowork.py`: ele exige o ERP de pé e mede a superfície, não a etiqueta.
_FORA = {"test_aceites_cowork.py"}


def _travas(raiz) -> list[str]:
    return sorted(f.name for f in raiz.glob("test_*.py") if f.name not in _FORA)


def main() -> int:
    falhando: list[str] = []
    travas = _travas(MCP)
    if len(travas) < 3:
        # some trava = alguém apagou arquivo. Descoberta sem piso vira "zero travas, tudo ok".
        print(f"  SÓ {len(travas)} trava(s) em {MCP} — havia pelo menos 3. Alguém apagou?")
        return 1
    for arquivo in travas:
        alvo = MCP / arquivo
        if not alvo.exists():
            print(f"  SUMIU: {arquivo} — a trava não existe mais no repositório")
            falhando.append(arquivo)
            continue
        r = subprocess.run(  # noqa: S603 — caminho fixo, sem entrada do usuário
            [sys.executable, str(alvo)], capture_output=True, text=True, timeout=180, cwd=str(MCP),
        )
        saida = (r.stdout or "") + (r.stderr or "")
        if "No module named 'fastmcp'" in saida:
            # A trava do middleware precisa do fastmcp, que só existe DENTRO do conector. Lá
            # ela vale mais: afirma a parede na cópia que está no ar, não na do disco. O
            # `checar_mcp_tools` é quem cobra git == imagem; aqui a pergunta é "a parede que
            # está rodando ainda barra?".
            r = subprocess.run(  # noqa: S603 — nomes fixos
                ["/usr/bin/docker", "exec", "conecta-pro-mcp", "python3", f"/app/{arquivo}"],
                capture_output=True, text=True, timeout=180,
            )
            saida = ((r.stdout or "") + (r.stderr or "")) + "\n      (rodou DENTRO de conecta-pro-mcp)"
        if r.returncode != 0:
            falhando.append(arquivo)
            print(f"  FALHOU: {arquivo}")
            for linha in saida.strip().splitlines()[:14]:
                print(f"      {linha}")
        else:
            print(f"  ok: {arquivo} ({sum(1 for l in saida.splitlines() if l.startswith('PASS'))} travas)")

    print(f"TOTAL travas do MCP falhando: {len(falhando)}")
    return 1 if falhando else 0


if __name__ == "__main__":
    sys.exit(main())

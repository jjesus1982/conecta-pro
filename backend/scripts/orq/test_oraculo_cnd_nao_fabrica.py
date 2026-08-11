"""Oráculo: o sync de certidões NUNCA grava certidão que o órgão não confirmou.

Em 11/08/2026 este caminho fabricou compliance fiscal. A guarda só rejeitava
`erro_consulta`; `indeterminado_portal_indisponivel` (portal fora do ar) e `irregular`
(empresa COM pendência) passavam direto. E quando o portal não devolvia validade, um
"fallback: validade padrao pelo tipo" inventava hoje+180 dias.

Quatro linhas nasceram/renovaram parecendo válidas até 2027 sem uma única consulta
respondida — inclusive a CRF-FGTS vencida da Eletrônica, que passou a exibir-se em dia.

Certidão falsa é PIOR que certidão ausente: sem ela a tela mostra "FALTA" e alguém
providencia; com ela o painel fica verde e a empresa descobre na hora de faturar ou licitar.

Este oráculo não chama portal nenhum — injeta a resposta e prova a decisão. Determinístico,
sem rede, sem custo.

Roda:
    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_oraculo_cnd_nao_fabrica.py
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.people_management.ged.tasks import cnd_sync_task as cst  # noqa: E402


class _DBFalso:
    """Session mínima: registra se alguém tentou ESCREVER. Escrita = fabricação."""

    def __init__(self):
        self.sqls: list[str] = []

    async def execute(self, stmt, params=None):  # noqa: ARG002
        self.sqls.append(str(stmt))
        return _Vazio()

    async def commit(self):
        self.sqls.append("COMMIT")


class _Vazio:
    def mappings(self):
        return self

    def first(self):
        return None

    def scalar(self):
        return None

    def scalar_one_or_none(self):
        return None


def _escreveu(db: _DBFalso) -> bool:
    return any(("insert" in s.lower() or "update" in s.lower()) for s in db.sqls)


async def _tentar(resposta: dict) -> tuple[dict, bool]:
    """Roda o fluxo com a resposta injetada; devolve (retorno, gravou?)."""
    db = _DBFalso()

    class _ClienteFalso:
        async def consultar_cnd(self, cnpj):  # noqa: ARG002
            return resposta

        async def consultar_cndt(self, cnpj):  # noqa: ARG002
            return resposta

        async def consultar_crf(self, cnpj):  # noqa: ARG002
            return resposta

    # O cliente é importado DENTRO da função (`from ...cnd_client import CNDFederalClient`),
    # então trocar atributo no módulo do sync não adianta — a substituição tem que ser no
    # módulo de ORIGEM, antes do import local acontecer.
    import modules.bidding.integrations.receita_federal.cnd_client as origem

    class _Ctx(_ClienteFalso):
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    original = origem.CNDFederalClient
    origem.CNDFederalClient = _Ctx
    try:
        out = await cst._buscar_e_salvar_certidao(db, "66014833000110", "cnd_federal")
    finally:
        origem.CNDFederalClient = original
    return out, _escreveu(db)


async def main() -> None:
    # 1. Portal fora do ar — foi o caso REAL de 11/08. Nada pode ser gravado.
    out, gravou = await _tentar({"situacao": "indeterminado_portal_indisponivel"})
    assert not gravou, f"portal indisponível GRAVOU certidão — fabricação de volta: {out}"
    assert out.get("status") == "indisponivel", f"status esperado 'indisponivel', veio {out}"
    print(f"OK portal fora do ar: nada gravado ({out['status']})")

    # 2. Empresa IRREGULAR no órgão — houve resposta, e a resposta é que há pendência.
    out, gravou = await _tentar({"situacao": "irregular", "data_validade": "2027-02-07"})
    assert not gravou, f"situação irregular GRAVOU certidão válida: {out}"
    assert out.get("status") == "irregular", f"status esperado 'irregular', veio {out}"
    print(f"OK empresa irregular: nada gravado ({out['status']})")

    # 3. Regular mas SEM data do órgão — validade não se estima.
    out, gravou = await _tentar({"situacao": "regular"})
    assert not gravou, f"sem data de validade GRAVOU certidão — o fallback de 180 dias voltou: {out}"
    assert out.get("status") == "sem_validade", f"status esperado 'sem_validade', veio {out}"
    print(f"OK regular sem data: nada gravado ({out['status']})")

    # 4. Caminho legítimo: órgão confirmou E deu a data. Aqui TEM que gravar — senão o
    #    conserto viraria um bloqueio geral, e o sync deixaria de servir para o que existe.
    out, gravou = await _tentar({"situacao": "regular", "data_validade": "2027-02-07"})
    assert gravou, f"resposta legítima NÃO gravou — o gate ficou apertado demais: {out}"
    print("OK regular com data: gravou (o caminho bom continua funcionando)")

    print("TEST oraculo_cnd_nao_fabrica PASS")


if __name__ == "__main__":
    asyncio.run(main())

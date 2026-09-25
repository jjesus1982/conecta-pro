#!/usr/bin/env python3
"""Endereço de cliente vindo da RECEITA FEDERAL (BrasilAPI), pelo CNPJ.

Complementa `preencher_endereco_cliente_das_notas.py`, que lê das notas que o fisco já emitiu.
Aqui a fonte é o **cadastro do próprio CNPJ na Receita** — melhor ainda, porque existe para
todo cliente com CNPJ válido, não só para quem já recebeu nota.

NF-e de mercadoria EXIGE logradouro, número, bairro, CEP e código IBGE do destinatário. E o
**município do tomador** decide onde o ISS da NFS-e é devido: sem ele, `nfse_emissao.py` assume
«Manaus/AM», o que acerta por acaso enquanto todos os clientes forem daqui.

## As regras, e elas são as mesmas do outro script

1. **Só preenche campo VAZIO.** Nunca sobrescreve. Se o cadastro diz uma coisa e a Receita diz
   outra, isso é DIVERGÊNCIA e vira relatório: pode ser o condomínio que mudou de endereço de
   correspondência sem alterar o cadastro federal, e quem decide é o dono.
2. **CNPJ inválido ou inativo é pulado**, com o motivo dito.
3. **`--aplicar` para gravar.** Sem a bandeira, só mostra.

Conferido em 25/09/2026: o endereço que a Receita devolve para a HawkEye
(Ramos Ferreira 2159, Praça 14, CEP 69020-080) bate **exatamente** com o orçamento em papel
que o fornecedor mandou. Duas fontes independentes, mesma resposta.

Linha canônica: `TOTAL: <n> cliente(s) com endereço preenchido da Receita`.
"""

from __future__ import annotations

import asyncio
import re
import sys

sys.path.insert(0, "/app")

#: Código IBGE de Manaus. Só é preenchido quando a Receita diz que o município É Manaus —
#: para os outros fica vazio e o validador da NF-e cobra, que é o certo: chutar código de
#: município é emitir nota no município errado.
IBGE_MANAUS = "1302603"


async def main() -> int:
    aplicar = "--aplicar" in sys.argv
    try:
        from sqlalchemy import text  # noqa: PLC0415

        from core.database import async_session_factory  # noqa: PLC0415

        from modules.integrations.brasilapi.client import BrasilAPIClient  # noqa: PLC0415
    except ModuleNotFoundError as e:
        print(f"RECUSO: roda DENTRO do container ({e})")
        return 2

    cli = BrasilAPIClient()
    preenchidos: list[str] = []
    divergentes: list[str] = []
    pulados: list[str] = []

    async with async_session_factory() as db:
        rows = (
            await db.execute(
                text(
                    "SELECT id::text, name, regexp_replace(coalesce(document_number,''),'\\D','','g') doc,"
                    " coalesce(address_street,'') logr, coalesce(address_number,'') num,"
                    " coalesce(address_neighborhood,'') bairro, coalesce(address_city,'') cidade,"
                    " coalesce(address_state,'') uf,"
                    " regexp_replace(coalesce(address_zipcode,''),'\\D','','g') cep"
                    "  FROM clients ORDER BY name"
                )
            )
        ).mappings().all()

        for c in rows:
            falta = not (c["logr"] and c["bairro"] and c["cidade"] and len(c["cep"]) == 8)
            if not falta:
                continue
            if len(c["doc"]) != 14 or c["doc"] == "00000000000000":
                pulados.append(f"{c['name']}: CNPJ inválido ou ausente ({c['doc'] or '—'})")
                continue
            try:
                r, _ = await cli.get_cnpj(c["doc"])
                d = r.model_dump() if hasattr(r, "model_dump") else dict(r)
            except Exception as e:  # noqa: BLE001 — um CNPJ ruim não para o lote
                pulados.append(f"{c['name']}: Receita não respondeu ({type(e).__name__})")
                continue
            sit = str(d.get("descricao_situacao_cadastral") or "").upper()
            if sit and sit != "ATIVA":
                pulados.append(f"{c['name']}: CNPJ na Receita está «{sit}» — não preencho sem o dono ver")
                continue

            campos = {
                "logr": (d.get("logradouro") or "").strip(),
                "num": (d.get("numero") or "").strip() or "S/N",
                "bairro": (d.get("bairro") or "").strip(),
                "cidade": (d.get("municipio") or "").strip(),
                "uf": (d.get("uf") or "").strip().upper(),
                "cep": re.sub(r"\D", "", str(d.get("cep") or "")),
            }
            novo = {}
            for k in campos:
                atual = c[k]
                vindo = campos[k]
                # «Manaus/AM» no campo CIDADE é a UF colada na cidade — defeito de
                # cadastro, não divergência de fato. Medido em 25/09/2026: 5 clientes
                # assim, e sairiam com `<xMun>Manaus/AM</xMun>` na nota, que é errado.
                # Tirando o sufixo, é a MESMA cidade — então a forma limpa da Receita
                # substitui, e isso não é sobrescrever fato, é normalizar.
                if k == "cidade" and atual and vindo:
                    limpo = re.sub(r"\s*[/-]\s*[A-Za-z]{2}\s*$", "", atual).strip()
                    if limpo.upper() == vindo.upper():
                        novo[k] = vindo
                        continue
                if atual and vindo and atual.strip().upper() != vindo.upper():
                    divergentes.append(f"{c['name']} · {k}: cadastro «{atual}» × Receita «{vindo}»")
                novo[k] = atual or vindo
            ibge = IBGE_MANAUS if novo["cidade"].upper().startswith("MANAUS") else ""
            preenchidos.append(
                f"{c['name']} → {novo['logr']}, {novo['num']} — {novo['bairro']}, "
                f"{novo['cidade']}/{novo['uf']} CEP {novo['cep']}" + (f" · IBGE {ibge}" if ibge else " · IBGE a informar")
            )
            if aplicar:
                await db.execute(
                    text(
                        "UPDATE clients SET address_street = :l, address_number = :n,"
                        " address_neighborhood = :b, address_city = :c, address_state = :u,"
                        " address_zipcode = :z WHERE id::text = :i"
                    ),
                    {"l": novo["logr"], "n": novo["num"], "b": novo["bairro"], "c": novo["cidade"],
                     "u": novo["uf"], "z": novo["cep"], "i": c["id"]},
                )
        if aplicar:
            await db.commit()

    if preenchidos:
        print("PREENCHIDO da Receita:" if aplicar else "PREENCHERIA (rode com --aplicar):")
        for p in preenchidos:
            print(f"   {p}")
    if divergentes:
        print("\nDIVERGÊNCIA — cadastro tem valor diferente do da Receita. NÃO sobrescrevi:")
        for d in divergentes:
            print(f"   {d}")
    if pulados:
        print("\nPULADOS:")
        for p in pulados:
            print(f"   {p}")
    print(f"\nTOTAL: {len(preenchidos)} cliente(s) com endereço preenchido da Receita")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

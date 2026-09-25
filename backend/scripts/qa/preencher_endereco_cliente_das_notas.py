#!/usr/bin/env python3
"""Endereço de cliente vindo das NOTAS QUE O FISCO JÁ EMITIU — não de digitação.

25/09/2026. Medido minutos antes da primeira NF-e de produção: **14 dos 29 clientes** não
tinham endereço completo no cadastro (`clients`). NF-e de mercadoria EXIGE logradouro, número,
bairro, CEP e código IBGE do destinatário — sem isso o emissor recusa, e com razão.

A saída óbvia seria pedir ao dono que digitasse 14 endereços. A saída certa é que eles **já
estão escritos**, em documento fiscal, nos PDFs que ele mesmo subiu: cada NFS-e do Padrão
Nacional traz o bloco TOMADOR/ADQUIRENTE com CNPJ, CEP, município e endereço, e o DANFE traz o
bloco DESTINATÁRIO. Endereço tirado de nota autorizada é o endereço que o fisco aceitou —
melhor fonte que qualquer digitação.

REGRAS, e elas são o que separa isto de um `UPDATE` perigoso:

1. **Casa por CNPJ, nunca por nome.** «Condomínio Park Village» e «Condomínio Parque Village»
   são a mesma coisa para um humano e coisas diferentes para o fisco. CNPJ é a chave.
2. **Só preenche campo VAZIO.** Nunca sobrescreve o que está no cadastro. Se o cadastro diz uma
   coisa e a nota diz outra, isso é DIVERGÊNCIA e vira relatório, não `UPDATE`: pode ser o
   condomínio que mudou de síndico e de endereço de correspondência, e quem decide é o dono.
3. **`--aplicar` para gravar.** Sem a bandeira, só mostra o que faria. Escrita em cadastro que
   vai dentro de documento fiscal não acontece por acidente de execução.

Linha canônica: `TOTAL: <n> cliente(s) com endereço preenchido das notas`.
"""

from __future__ import annotations

import asyncio
import glob
import re
import sys

#: O bloco do tomador na NFS-e Nacional e o do destinatário no DANFE. Dois leiautes, um
#: extrator: os dois dizem CNPJ, CEP e endereço, e é só isso que interessa aqui.
_RE_CNPJ = re.compile(r"(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})")

#: O CEP sai SÓ da linha «Código IBGE / CEP», que na NFS-e Nacional vem como
#: «13.02603 / 69.040-110». Ancorado assim de propósito, e isto foi medido:
#:
#: a primeira versão procurava «8 dígitos com cara de CEP» em qualquer lugar do bloco, e
#: casou com o **Indicador Municipal (Inscrição)** — que também tem 8 dígitos e aparece
#: ANTES do endereço. O resultado foi um relatório acusando 5 «divergências de CEP» que não
#: existiam: o Michelangelo com «CEP 45177801», que é a inscrição municipal da Eletrônica.
#:
#: Cinco falsos positivos numa varredura de sete. Se eu tivesse rodado com `--aplicar`, teria
#: gravado inscrição municipal no campo de CEP de cinco condomínios — e a próxima NF-e sairia
#: com CEP inválido para o fisco. Número com a forma certa no lugar errado é pior que número
#: ausente: ausência avisa, forma certa convence.
_RE_IBGE_CEP = re.compile(r"C[óo]digo\s+IBGE\s*/\s*CEP\s*\n\s*[\d.]+\s*/\s*(\d{2}\.?\d{3}-?\d{3})")
#: No DANFE o CEP vem sob o rótulo «CEP», em linha própria.
_RE_CEP_DANFE = re.compile(r"\bCEP\b\s*\n\s*(\d{5}-?\d{3})")


def _so_digitos(v: str) -> str:
    return re.sub(r"\D", "", v or "")


def _partir_endereco(bruto: str) -> tuple[str, str, str]:
    """«TORQUATO TAPAJOS, 11265, RODOVIA AM-10, TARUMA» → (logradouro, número, bairro).

    O bairro é a ÚLTIMA parte e o número é a SEGUNDA — o que sobra no meio é complemento, que
    a NF-e não exige. Função pura: o teste bate nela sem PDF.
    """
    partes = [p.strip() for p in (bruto or "").split(",") if p.strip()]
    if len(partes) < 2:
        return ((partes[0] if partes else ""), "", "")
    return (partes[0], partes[1], partes[-1] if len(partes) > 2 else "")


def _dos_pdfs(pasta: str) -> dict[str, dict]:
    """CNPJ → endereço, lido dos PDFs de nota. O último arquivo lido para um CNPJ vence."""
    import fitz  # noqa: PLC0415

    achados: dict[str, dict] = {}
    for caminho in sorted(glob.glob(f"{pasta}/*.pdf")):
        try:
            doc = fitz.open(caminho)
            texto = doc[0].get_text()
            doc.close()
        except Exception as e:  # noqa: BLE001 — PDF ruim não derruba a varredura
            print(f"   (pulei {caminho.split('/')[-1]}: {e})")
            continue
        bloco = re.search(
            r"(TOMADOR\s*/\s*ADQUIRENTE.{0,700}|DESTINAT[ÁA]RIO\s*/\s*REMETENTE.{0,700})", texto, re.S | re.I
        )
        if not bloco:
            continue
        b = bloco.group(0)
        cnpj = _RE_CNPJ.search(b)
        end = re.search(r"Endere[çc]o\s*\n(.+)", b)
        cep = _RE_IBGE_CEP.search(b) or _RE_CEP_DANFE.search(b)
        if not (cnpj and end):
            continue
        logr, num, bairro = _partir_endereco(end.group(1))
        achados[_so_digitos(cnpj.group(1))] = {
            "logradouro": logr,
            "numero": num,
            "bairro": bairro,
            "cep": _so_digitos(cep.group(1)) if cep else "",
            "fonte": caminho.split("/")[-1],
        }
    return achados


async def main() -> int:
    aplicar = "--aplicar" in sys.argv
    try:
        from sqlalchemy import text  # noqa: PLC0415

        from core.database import async_session_factory  # noqa: PLC0415
    except ModuleNotFoundError:
        print("RECUSO: roda DENTRO do container (precisa do banco)")
        return 2

    dos_pdfs = _dos_pdfs("/app/uploads/_entrada/NFs")
    print(f"notas lidas: {len(dos_pdfs)} CNPJ(s) com endereço no documento fiscal\n")

    preenchidos: list[str] = []
    divergentes: list[str] = []
    sem_fonte: list[str] = []

    async with async_session_factory() as db:
        linhas = (
            (
                await db.execute(
                    text(
                        "SELECT id::text, name, regexp_replace(coalesce(document_number,''),'\\D','','g') AS doc,"
                        "       coalesce(address_street,'') AS logr, coalesce(address_number,'') AS num,"
                        "       coalesce(address_neighborhood,'') AS bairro,"
                        "       regexp_replace(coalesce(address_zipcode,''),'\\D','','g') AS cep"
                        "  FROM clients ORDER BY name"
                    )
                )
            )
            .mappings()
            .all()
        )
        for c in linhas:
            falta = not (c["logr"] and c["bairro"] and len(c["cep"]) == 8)
            nota = dos_pdfs.get(c["doc"])
            if not falta:
                # cadastro completo: confere contra a nota e RELATA divergência, sem tocar
                if nota and nota["cep"] and nota["cep"] != c["cep"]:
                    divergentes.append(
                        f"{c['name']} · cep: cadastro «{c['cep']}» × nota «{nota['cep']}» ({nota['fonte']})"
                    )
                continue
            if not nota:
                sem_fonte.append(f"{c['name']} (CNPJ {c['doc'] or '—'})")
                continue
            # Campo a campo, e NUNCA em silêncio: se o cadastro tem um valor e a nota tem
            # outro, o cadastro fica e a diferença vira linha de relatório. Misturar metade de
            # cada fonte produz um endereço que não existe em lugar nenhum — «Rua Parque dos
            # Franceses» (nome do cadastro) com o bairro e o CEP da nota, sendo que o fisco
            # conhece aquela rua como «A-1». Endereço meio-a-meio não é mais completo: é novo.
            novo = {}
            for chave, no_cadastro, na_nota in (
                ("logr", c["logr"], nota["logradouro"]),
                ("num", c["num"], nota["numero"]),
                ("bairro", c["bairro"], nota["bairro"]),
                ("cep", c["cep"] if len(c["cep"]) == 8 else "", nota["cep"]),
            ):
                novo[chave] = no_cadastro or na_nota
                if no_cadastro and na_nota and no_cadastro.strip().upper() != na_nota.strip().upper():
                    divergentes.append(
                        f"{c['name']} · {chave}: cadastro «{no_cadastro}» × nota «{na_nota}» ({nota['fonte']})"
                    )
            novo["num"] = novo["num"] or "S/N"
            preenchidos.append(
                f"{c['name']} → {novo['logr']}, {novo['num']} — {novo['bairro']}, CEP {novo['cep']}  [{nota['fonte']}]"
            )
            if aplicar:
                await db.execute(
                    text(
                        "UPDATE clients SET address_street = :l, address_number = :n,"
                        "       address_neighborhood = :b, address_zipcode = :c,"
                        "       address_city = coalesce(nullif(address_city,''),'Manaus'),"
                        "       address_state = coalesce(nullif(address_state,''),'AM')"
                        " WHERE id::text = :i"
                    ),
                    {"l": novo["logr"], "n": novo["num"], "b": novo["bairro"], "c": novo["cep"], "i": c["id"]},
                )
        if aplicar:
            await db.commit()

    if preenchidos:
        print("PREENCHIDO das notas:" if aplicar else "PREENCHERIA (rode com --aplicar):")
        for p in preenchidos:
            print(f"   {p}")
    if divergentes:
        print("\nDIVERGÊNCIA — cadastro completo mas diferente da nota. NÃO toquei; é decisão do dono:")
        for d in divergentes:
            print(f"   {d}")
    if sem_fonte:
        print("\nSEM endereço e SEM nota que o diga — só digitando:")
        for s in sem_fonte:
            print(f"   {s}")
    print(f"\nTOTAL: {len(preenchidos)} cliente(s) com endereço preenchido das notas")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, "/app")
    raise SystemExit(asyncio.run(main()))

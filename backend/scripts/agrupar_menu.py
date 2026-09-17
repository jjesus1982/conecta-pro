#!/usr/bin/env python3
"""Agrupa o EXTRA_MENU de um builder do redesign por assunto.

Origem: 17/09/2026. O Jordan: «a side bar tá gigante, me perco diante de tanta coisa» e
«parece que tudo faz a mesma coisa». Medido: 289 itens de menu; o RH sozinho tinha 44, dos
quais 18 eram «CCT — alguma coisa» — incluindo TRÊS entradas só para feriados.

O que faz: marca `"grupo": "Nome"` nos itens cujo id casa com um prefixo, e os REORDENA para
ficarem em sequência. A ordem importa: a sidebar (`agrupar()` no ModuleView) só junta itens
consecutivos do mesmo grupo — item do mesmo assunto espalhado vira dois blocos com o mesmo
nome, que é pior que não agrupar.

Item sem grupo continua solto e na ordem original. Nada some: agrupar é dobrar, não podar.

    python3 backend/scripts/agrupar_menu.py rh --aplicar
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
BUILDERS = RAIZ / "backend/modules/operacional/controllers/redesign_builders"

#: builder -> (rótulo do grupo, prefixos de id). Primeira regra que casa vence, então o mais
#: específico vem antes. Ver `GRUPOS["rh"]`: 'cct-' antes de qualquer coisa mais frouxa.
GRUPOS: dict[str, list[tuple[str, tuple[str, ...]]]] = {
    "crm": [
        (
            "Contratos",
            ("contrato", "contratos-", "novo-contrato", "aditivo", "aditivos", "modelo-contrato", "modelos-contrato"),
        ),
        ("Propostas & orçamento", ("proposta-", "doc-orcamento", "apresentacao-", "simular-fechamento")),
        ("Follow-up & relacionamento", ("followup-", "nps-", "reativar-lead", "timeline-nota", "whatsapp-")),
        ("Reuniões & visitas", ("reuniao-", "visita-")),
        ("Clientes & contatos", ("cliente-", "contato-", "condominio", "condominios", "consultar-cnpj")),
        ("Catálogo", ("produto", "produtos")),
        ("Consultor comercial", ("consultor-",)),
    ],
    "documentos": [
        ("GEDEON", ("gedeon-",)),
        ("Kits documentais", ("kit-", "kits-")),
        ("GED — coleta e config", ("ged-",)),
        ("Certidões", ("certidoes-", "cnd-")),
        ("Assinaturas", ("assinatura-", "assinaturas-")),
        ("Acervo (SOPHIA)", ("sophia-", "ingestao-")),
    ],
    "fiscal": [
        ("Cálculos", ("calc-",)),
        ("Notas fiscais", ("nfse-", "nfe-")),
        ("Certidões & sincronismo", ("certidoes-", "sync-")),
        ("Consultor fiscal", ("consultor-",)),
    ],
    "integracoes": [
        ("Onvio", ("onvio-",)),
        ("Banco Inter", ("inter-",)),
        ("Google Drive", ("gdrive-", "drive-")),
        ("Sólides", ("solides-",)),
    ],
    "juridico": [
        ("DET — comunicações", ("det-",)),
        ("Processos & prazos", ("processo-", "prazos", "analise-", "parecer-")),
        ("Base de conhecimento", ("conhecimento-", "playbook-")),
        ("Consultor jurídico", ("consultor-",)),
    ],
    "rh": [
        ("CCT — convenção coletiva", ("cct-",)),
        ("Medidas disciplinares", ("disc-",)),
        ("Treinamento & carreira", ("curso-", "treinamento-", "carreira-", "e360-", "ciclo-avaliacao", "performance-")),
        ("Recrutamento", ("curriculo-",)),
        ("eSocial", ("esocial-",)),
        ("Ativação do ponto", ("ativacao-ponto",)),
        ("Consultor de RH", ("consultor-",)),
    ],
}

_ITEM = re.compile(r'^(\s*)\{"id":\s*"([^"]+)",\s*"label":\s*"([^"]+)"(.*)\},\s*$')


def _grupo_de(ident: str, regras: list[tuple[str, tuple[str, ...]]]) -> str | None:
    for rotulo, prefixos in regras:
        if any(ident.startswith(p) for p in prefixos):
            return rotulo
    return None


def agrupar(slug: str, aplicar: bool) -> int:
    regras = GRUPOS.get(slug)
    if not regras:
        print(f"sem regras para '{slug}' — declare em GRUPOS", file=sys.stderr)
        return 2
    arq = BUILDERS / f"{slug}.py"
    if not arq.exists():
        print(f"{arq} não existe", file=sys.stderr)
        return 2

    linhas = arq.read_text(encoding="utf8").splitlines(keepends=True)
    ini = fim = None
    for n, linha in enumerate(linhas):
        if linha.startswith("EXTRA_MENU"):
            ini = n
        elif ini is not None and linha.rstrip() == "]":
            fim = n
            break
    if ini is None or fim is None:
        print("EXTRA_MENU não encontrado", file=sys.stderr)
        return 2

    #: dedup por id no caminho: menu com id repetido é lixo puro na sidebar.
    vistos: set[str] = set()
    soltos: list[str] = []
    por_grupo: dict[str, list[str]] = {}
    ordem_grupos: list[str] = []
    fora = 0

    for linha in linhas[ini + 1 : fim]:
        m = _ITEM.match(linha)
        if not m:
            if linha.strip():
                soltos.append(linha)  # comentário ou formato diferente: preserva onde está
            continue
        indent, ident, label, resto = m.groups()
        if ident in vistos:
            fora += 1
            continue
        vistos.add(ident)
        g = _grupo_de(ident, regras)
        # `grupo` já presente? tira para não duplicar a chave.
        resto = re.sub(r',\s*"grupo":\s*"[^"]*"', "", resto)
        nova = f'{indent}{{"id": "{ident}", "label": "{label}"{resto}' + (f', "grupo": "{g}"}},\n' if g else "},\n")
        if g:
            if g not in por_grupo:
                por_grupo[g] = []
                ordem_grupos.append(g)
            por_grupo[g].append(nova)
        else:
            soltos.append(nova)

    novas = soltos + [l for g in ordem_grupos for l in por_grupo[g]]
    antes = len(vistos) + fora
    visiveis = len([l for l in soltos if l.strip().startswith('{"id"')]) + len(ordem_grupos)

    print(
        f"  {slug}: {antes} itens -> {visiveis} linhas visíveis na sidebar "
        f"({len(ordem_grupos)} grupos, {fora} duplicados removidos)"
    )
    for g in ordem_grupos:
        print(f"      {g}: {len(por_grupo[g])}")

    if aplicar:
        arq.write_text("".join(linhas[: ini + 1] + novas + linhas[fim:]), encoding="utf8")
        print(f"  gravado em {arq.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--aplicar", action="store_true", help="sem isto, só mostra")
    a = ap.parse_args()
    sys.exit(agrupar(a.slug, a.aplicar))

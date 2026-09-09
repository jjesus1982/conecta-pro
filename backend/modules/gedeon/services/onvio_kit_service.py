"""
GEDEON — Arquiva os documentos do Onvio (Portte) no kit, formato flat.

Onvio (categoria) → nome do arquivo no kit (igual ao que a equipe entrega):
  folha_pagamento → "Folha de Pagamento.pdf"
  recibo_folha    → "Contracheques.pdf"

Cada doc do Onvio traz o condomínio no nome ("Folha 05.2026_Ideal Flores.pdf");
mapeamos pro nome do condomínio no workspace e arquivamos em [Condomínio]/[Mês]/.
Lê o binário do disco (caminho_local) e, se faltar, re-busca do Onvio.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile

from sqlalchemy import text

from modules.gdrive.services.gdrive_service import gdrive_service
from modules.gedeon.services.kit_layout import _arquivo_ja_existe, pasta_kit_arquivo

logger = logging.getLogger(__name__)

NOME_KIT: dict[str, str] = {
    "folha_pagamento": "Folha de Pagamento.pdf",
    "recibo_folha": "Contracheques.pdf",
}

# Guias da EMPRESA (Conecta Mais) — entram iguais em TODOS os kits (replicadas).
# Valor None = preserva o nome original do Onvio (já é descritivo e padrão do kit).
CATEGORIAS_EMPRESA: dict[str, str | None] = {
    "fgts_guia": None,
    "fgts_relatorio": None,
    "inss_guia": None,
    "dctfweb_declaracao": None,
    "dctfweb_recibo": None,
    "dctfweb_resumo_debitos": None,
}

#: Trecho que identifica o condomínio DENTRO do nome do arquivo que vem do Onvio. O contador
#: nomeia como "Folha 07.2026_Ideal Flores.pdf" — o nome do arquivo nunca traz a razão social
#: inteira, então a chave é o apelido. O VALOR, porém, tem de ser o nome do CONTRATO.
#:
#: 🔴 ESTE MAPA CRIAVA PASTA DUPLICADA NO DRIVE DO CLIENTE. Ele devolvia o nome curto
#: ("IDEAL FLORES") e os outros blocos — certidões, guias, boletos — usam o nome que vem dos
#: contratos ("CONDOMINIO IDEAL FLORES DA CIDADE"). Resultado medido em 17/08/2026: 18 pastas
#: no Drive para 11 clientes, e cada um dos 7 postos com o kit partido em duas — 63 dos 66
#: arquivos na pasta longa e os 3 contracheques de julho na curta. A completude do mês caiu
#: para 6% porque as 7 pastas quase vazias entravam no denominador.
#:
#: Decisão do Jordan em 17/08: fica o nome LONGO, o do contrato.
_APELIDO_ONVIO: dict[str, str] = {
    "ideal flores": "IDEAL FLORES",
    "michelangelo": "MICHELANGELO",
    "mirante": "MIRANTE",
    "villa dei fiori": "VILLA DEI FIORI",
    "villa dos passaros": "VILLA PÁSSAROS",
    "villa dos pássaros": "VILLA PÁSSAROS",
    "laranjeiras": "LARANJEIRAS",
    "prime arena": "PRIME ARENA",
}


def _nome_de_contrato(apelido: str) -> str:
    """Apelido do arquivo → nome do cliente no CONTRATO, que é o nome da pasta no Drive.

    Consulta os contratos em vez de uma segunda lista fixa: quando o GREEN HILLS entrar em
    setembro, basta o contrato existir. Com o mapa antigo, o contracheque dele não casaria
    com nada e o arquivo simplesmente não seria arquivado — sem erro, sem aviso.

    Se não achar contrato, devolve o apelido: o arquivo vai para algum lugar em vez de sumir.
    """
    from sqlalchemy import text as _t

    from core.database.session import get_sync_db

    try:
        with get_sync_db() as db:
            r = db.execute(
                _t(
                    "SELECT cl.name FROM clients cl "
                    "JOIN contracts c ON c.client_id = cl.id "
                    "WHERE lower(coalesce(c.status::text,'')) = 'active' "
                    "  AND upper(cl.name) LIKE '%' || upper(:ap) || '%' "
                    "ORDER BY length(cl.name) DESC LIMIT 1"
                ),
                {"ap": apelido},
            ).scalar()
            return r or apelido
    except Exception:  # noqa: BLE001 — nunca derrubar a montagem por causa da resolução
        return apelido


def _clientes_de_contrato() -> list[str]:
    """Nomes dos clientes com contrato ATIVO. É a lista que manda — não uma cópia em código.

    🔴 SEM ISTO, CLIENTE NOVO SOME EM SILÊNCIO. O mapa de apelidos tem sete entradas fixas;
    o GREEN HILLS entra em setembro com 4 agentes e o contracheque dele não casaria com
    nada — sem erro, sem aviso, o arquivo simplesmente não seria arquivado. É o mesmo
    "nunca fixe a lista em código" que a F0.2 estabeleceu para a lista de kits.
    """
    from sqlalchemy import text as _t

    from core.database.session import get_sync_db

    try:
        with get_sync_db() as db:
            return [
                r[0]
                for r in db.execute(
                    _t(
                        "SELECT DISTINCT cl.name FROM clients cl "
                        "JOIN contracts c ON c.client_id = cl.id "
                        "WHERE lower(coalesce(c.status::text,'')) = 'active' AND cl.name IS NOT NULL"
                    )
                ).fetchall()
            ]
    except Exception:  # noqa: BLE001
        return []


#: Palavras que não distinguem um condomínio de outro — sozinhas casariam com meio mundo.
_GENERICAS = {
    "condominio",
    "condomínio",
    "residencial",
    "edificio",
    "edifício",
    "do",
    "da",
    "de",
    "dos",
    "das",
    "e",
    "village",
    "ltda",
    "conecta",
    "mais",
}


def _condominio_do_nome(nome_arquivo: str) -> str | None:
    """Nome da PASTA no Drive para este arquivo do Onvio — o do CONTRATO, não o apelido.

    Duas passadas, nesta ordem:
      1. apelido declarado (o contador escreve "Ideal Flores", o contrato diz
         "CONDOMINIO IDEAL FLORES DA CIDADE" — só um humano liga as duas coisas);
      2. os próprios clientes com contrato ativo, casando pelas palavras que DISTINGUEM.

    A segunda passada é o que faz cliente novo funcionar sem alguém lembrar de editar o mapa.
    """
    import unicodedata

    def _norm(x: str) -> str:
        return unicodedata.normalize("NFKD", x or "").encode("ascii", "ignore").decode().lower()

    n = _norm(nome_arquivo)
    clientes = _clientes_de_contrato()

    # 1 · apelido declarado → acha o contrato pelo trecho SEM ACENTO. O contrato do Villa dos
    # Pássaros está escrito "VILLA DOS PASSAROS"; comparar com acento não casava e o arquivo
    # voltava para a pasta curta.
    for chave, apelido in _APELIDO_ONVIO.items():
        if _norm(chave) in n:
            alvo = _norm(chave)
            achou = [c for c in clientes if alvo in _norm(c)]
            if achou:
                return max(achou, key=len)
            return _nome_de_contrato(apelido)

    # 2 · sem apelido: casa pelas palavras distintivas do próprio contrato
    for c in clientes:
        toks = [t for t in _norm(c).split() if t not in _GENERICAS and len(t) > 2]
        if toks and all(t in n for t in toks):
            return c
    return None


#: Compat: alguém pode importar o nome antigo. Mantido como ALIAS do apelido, não como fonte.
CONDOMINIO_MAP = _APELIDO_ONVIO


def _garantir_binario(onvio_client, caminho_local, onvio_folder_id, onvio_id) -> str | None:
    """Devolve um caminho local válido do PDF (disco ou re-baixado do Onvio)."""
    if caminho_local and os.path.exists(caminho_local):
        return caminho_local
    if onvio_client and onvio_folder_id and onvio_id:
        try:
            b = onvio_client.baixar_pdf(onvio_folder_id, onvio_id)
            tmp = os.path.join(tempfile.gettempdir(), f"onvio_{onvio_id}.pdf")
            with open(tmp, "wb") as fh:
                fh.write(b)
            return tmp
        except Exception as exc:
            logger.warning("re-fetch Onvio %s falhou: %s", onvio_id, exc)
    return None


def arquivar_onvio_flat(competencia: str, db, onvio_client=None, dry_run: bool = False) -> dict:
    """Arquiva folha + contracheque do Onvio (competência) no kit de cada condomínio."""
    cats = tuple(NOME_KIT.keys())
    rows = db.execute(
        text("""
        SELECT o.categoria, o.nome_arquivo, o.caminho_local, o.onvio_folder_id, o.onvio_id,
               o.referente_a_employee_id::text,
               (SELECT cl.name FROM allocations a JOIN posts p ON p.id = a.post_id JOIN clients cl ON cl.id = p.client_id
                 WHERE a.employee_id = o.referente_a_employee_id AND a.is_active
                 ORDER BY a.start_date DESC NULLS LAST LIMIT 1) AS cliente_do_posto,
               (SELECT e.nome FROM employees e WHERE e.id = o.referente_a_employee_id) AS colaborador
        FROM onvio_documents o
        WHERE o.mes_ref = :m AND o.categoria IN :cats
        ORDER BY o.nome_arquivo
    """).bindparams(__import__("sqlalchemy").bindparam("cats", expanding=True)),
        {"m": competencia, "cats": list(cats)},
    ).all()
    rel = {"competencia": competencia, "arquivados": 0, "pulados": [], "por_condominio": {}, "sem_condominio": 0}
    feitos: set = set()  # (condominio, categoria[, colaborador]) — 1 por condomínio/tipo (evita dupes "(1)")
    for categoria, nome, caminho, folder_id, oid, emp_id, cliente_do_posto, colaborador in rows:
        cond = _condominio_do_nome(nome)
        por_pessoa = False
        if not cond and emp_id and cliente_do_posto:
            # 08/09/2026: o Onvio entrega o recibo de folha POR COLABORADOR ("Recibo de Pagamento-08-2026-N-NOME.pdf");
            # o nome do arquivo não tem condomínio e 47/47 caíam no `continue` em silêncio — a subpasta
            # "1. Folha e Pessoal" ficava vazia mesmo com os recibos no banco. O Hermes do GEDEON já liga o recibo ao
            # colaborador (referente_a_employee_id); daqui vai para o condomínio do posto onde ele está alocado.
            cond = cliente_do_posto
            por_pessoa = True
        if not cond:
            rel["sem_condominio"] += 1
            continue  # Laranjeiras/Prime Arena (Innovare) ou Geral — fora
        chave = (cond, categoria, colaborador) if por_pessoa else (cond, categoria)
        if chave in feitos:
            continue
        fn = f"Contracheque — {colaborador}.pdf" if por_pessoa else NOME_KIT[categoria]
        if dry_run:
            feitos.add(chave)
            rel["arquivados"] += 1
            rel["por_condominio"].setdefault(cond, []).append(fn)
            continue
        path = _garantir_binario(onvio_client, caminho, folder_id, oid)
        if not path:
            rel["pulados"].append(f"{cond}/{fn} (sem binário)")
            continue
        folder = pasta_kit_arquivo(cond, competencia, fn)
        if folder and not _arquivo_ja_existe(folder, fn):
            if gdrive_service.fazer_upload_arquivo(path, folder, fn):
                feitos.add(chave)
                rel["arquivados"] += 1
                rel["por_condominio"].setdefault(cond, []).append(fn)
        elif folder:
            feitos.add(chave)
    return rel


_SQL_CNPJ_EMPREGADORA = text(
    """
    SELECT em.cnpj
      FROM allocations a
      JOIN employees e ON e.id = a.employee_id
      JOIN empresas em ON em.id = e.empresa_id
     WHERE a.is_active AND lower(coalesce(e.status,'')) = 'ativo'
     GROUP BY em.cnpj
     ORDER BY count(*) DESC
     LIMIT 1
    """
)


def _empresa_empregadora_id(db):
    """UUID da empresa que EMPREGA a gente alocada nos postos.

    Desde que o Onvio passou a trazer os dois CNPJs (18/08/2026), filtrar por nome de
    arquivo não basta: a GFD FGTS não carrega CNPJ no nome, e existem duas — "_Conecta
    Mais" (Eletrônica) e "_Conecta Patrimonial". Ordenadas por nome, a errada vem antes.
    """
    try:
        return db.execute(
            text(
                "SELECT em.id FROM allocations a "
                "  JOIN employees e ON e.id = a.employee_id "
                "  JOIN empresas em ON em.id = e.empresa_id "
                " WHERE a.is_active AND lower(coalesce(e.status,'')) = 'ativo' "
                " GROUP BY em.id ORDER BY count(*) DESC LIMIT 1"
            )
        ).scalar()
    except Exception as exc:  # noqa: BLE001
        logger.warning("nao consegui ler a empresa empregadora: %s", exc)
        return None


def _cnpj_empregadora(db) -> str | None:
    """CNPJ de quem EMPREGA a gente alocada nos postos — só dígitos.

    Lido do banco, não chumbado: é a empresa que responde pelos 52 alocados hoje
    (Patrimonial, 66.014.833). Se um dia a mão de obra migrar de CNPJ, a trava migra junto.
    """
    try:
        v = db.execute(_SQL_CNPJ_EMPREGADORA).scalar()
        return re.sub(r"\D", "", v) if v else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("nao consegui ler o CNPJ da empregadora: %s", exc)
        return None


def _e_de_outra_empresa(nome_arquivo: str, cnpj_ok: str | None) -> bool:
    """True quando o nome do arquivo carrega um CNPJ que NÃO é o da empregadora.

    O kit do condomínio serve para provar que quem emprega os porteiros daquele posto
    recolheu os tributos DELE — é isso que protege o condomínio da responsabilidade
    subsidiária. Um DCTFWeb da Eletrônica não prova nada disso, e chegaram a ficar 21
    arquivos assim nos kits (3 documentos × 7 condomínios, competência 07/2026).

    Arquivo sem CNPJ no nome PASSA: não dá para afirmar que é da empresa errada, e barrar
    por suspeita tiraria do kit guia legítima (a GFD FGTS não traz CNPJ no nome).
    """
    if not cnpj_ok:
        return False
    achados = re.findall(r"\d{14}", nome_arquivo or "")
    return bool(achados) and cnpj_ok not in achados


def arquivar_guias_empresa_flat(
    competencia: str, condominios: list[str], db, onvio_client=None, dry_run: bool = False
) -> dict:
    """Arquiva as guias da empresa (FGTS, INSS, DCTFWeb) replicadas em cada kit."""
    cats = tuple(CATEGORIAS_EMPRESA.keys())
    emp_id = _empresa_empregadora_id(db)
    # empresa_id IS NULL passa: documento anterior a 18/08/2026 não tem dono declarado e
    # barrar por omissão esvaziaria o kit. A trava por CNPJ no nome cobre esses.
    rows = db.execute(
        text("""
        SELECT categoria, nome_arquivo, caminho_local, onvio_folder_id, onvio_id
        FROM onvio_documents
        WHERE mes_ref = :m AND categoria IN :cats
          AND (:emp IS NULL OR empresa_id IS NULL OR empresa_id = :emp)
        ORDER BY categoria, (empresa_id = :emp) DESC NULLS LAST, nome_arquivo
    """).bindparams(__import__("sqlalchemy").bindparam("cats", expanding=True)),
        {"m": competencia, "cats": list(cats), "emp": emp_id},
    ).all()

    rel = {"competencia": competencia, "guias": 0, "replicas": 0, "lista": [], "de_outra_empresa": []}
    cnpj_ok = _cnpj_empregadora(db)
    vistos: set = set()
    for categoria, nome, caminho, folder_id, oid in rows:
        if _e_de_outra_empresa(nome, cnpj_ok):
            rel["de_outra_empresa"].append(nome)
            continue
        if categoria in vistos:  # 1 por tipo (evita duplicatas "(1)")
            continue
        vistos.add(categoria)
        fn = CATEGORIAS_EMPRESA[categoria] or nome
        rel["guias"] += 1
        rel["lista"].append(fn)
        if dry_run:
            continue
        path = _garantir_binario(onvio_client, caminho, folder_id, oid)
        if not path:
            continue
        for cond in condominios:
            folder = pasta_kit_arquivo(cond, competencia, fn)
            if folder and not _arquivo_ja_existe(folder, fn):
                if gdrive_service.fazer_upload_arquivo(path, folder, fn):
                    rel["replicas"] += 1
    return rel

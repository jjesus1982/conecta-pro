"""Emissor de NF-e modelo 55 — numeração, persistência e guarda legal do XML.

É a camada que faltava em volta do `NFeProvider` (que só conversa com a SEFAZ):

  · numeração por (CNPJ + série + ambiente) sem buraco e sem repetir, com índice
    único no banco e contador atômico — o emissor antigo usava um TIMESTAMP como
    número de nota, o que garante buraco permanente na numeração fiscal;
  · identidade do emitente vinda da tabela `empresas` (nunca chumbada) e
    certificado A1 da empresa certa, pelo registro único de `qualified_signer`;
  · guarda do XML assinado + protocolo em disco por 5 anos (art. 195 CTN /
    cláusula décima do Ajuste SINIEF 07/05), com o caminho referenciado na linha;
  · cancelamento (evento 110111, prazo 24h) e inutilização de faixa.

Endpoints (prefixo /fiscal, montado em main_production):
  GET  /fiscal/nfe/sefaz-status         status do serviço da SEFAZ por empresa
  GET  /fiscal/nfe/listar               notas emitidas
  POST /fiscal/nfe/emitir               emite (homologação por padrão)
  POST /fiscal/nfe/cancelar             evento 110111
  POST /fiscal/nfe/inutilizar           inutiliza faixa de numeração

Ambiente: `NFE_AMBIENTE` (default "2" = homologação). Produção exige, além disso,
`NFE_PRODUCAO_LIBERADA` com o valor-senha — ver `nfe_provider._exigir_ambiente`.
"""

import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text as sqltext
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database.session import get_db
from modules.empresas.services.empresa_lookup import get_empresa
from modules.financial.integrations.nfe_provider import (
    NFeError,
    _exigir_ambiente,
    create_nfe_provider,
    producao_liberada,
)
from modules.fiscal.services import icms_entrada
from modules.fiscal.services.tributacao_nfe import calcular_puro

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/nfe", tags=["NF-e Produto"])

#: Onde o XML fica guardado por 5 anos. /app/uploads é bind do host (durável).
DIR_XML = Path(os.getenv("NFE_XML_DIR", "/app/uploads/nfe"))

#: CRT por regime da tabela `empresas` (1=Simples, 2=Simples excesso, 3=Regime normal).
_CRT_POR_REGIME = {"simples_nacional": "1", "simples_excesso": "2", "lucro_real": "3", "lucro_presumido": "3"}


def ambiente_atual() -> str:
    """Ambiente de emissão. Default homologação — produção é decisão explícita."""
    amb = (os.getenv("NFE_AMBIENTE") or "2").strip()
    return amb if amb in ("1", "2") else "2"


# ---------------------------------------------------------------------------
# DDL idempotente
# ---------------------------------------------------------------------------

_DDL = (
    # Ambiente e vínculo com a empresa: sem eles, homologação e produção se
    # misturam na mesma tabela e a numeração de uma contamina a da outra.
    "ALTER TABLE nfes ADD COLUMN IF NOT EXISTS tp_amb VARCHAR(1) NOT NULL DEFAULT '2'",
    "ALTER TABLE nfes ADD COLUMN IF NOT EXISTS empresa_id UUID",
    "ALTER TABLE nfes ADD COLUMN IF NOT EXISTS codigo_status VARCHAR(4)",
    "ALTER TABLE nfes ADD COLUMN IF NOT EXISTS xml_path TEXT",
    "ALTER TABLE nfes ADD COLUMN IF NOT EXISTS data_cancelamento TIMESTAMP",
    "ALTER TABLE nfes ADD COLUMN IF NOT EXISTS motivo_cancelamento TEXT",
    "ALTER TABLE nfes ADD COLUMN IF NOT EXISTS protocolo_cancelamento VARCHAR(20)",
    # A trava que impede duas notas com o mesmo número no mesmo CNPJ/série/ambiente.
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_nfes_emitente_serie_numero "
    "ON nfes (emitente_cnpj, serie, numero, tp_amb) WHERE numero IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS ix_nfes_chave ON nfes (chave_acesso)",
    # Contador por (CNPJ, série, ambiente). Linha única, incrementada atomicamente.
    "CREATE TABLE IF NOT EXISTS nfe_numeracao ("
    " emitente_cnpj VARCHAR(14) NOT NULL,"
    " serie INTEGER NOT NULL,"
    " tp_amb VARCHAR(1) NOT NULL,"
    " ultimo INTEGER NOT NULL DEFAULT 0,"
    " updated_at TIMESTAMP NOT NULL DEFAULT now(),"
    " PRIMARY KEY (emitente_cnpj, serie, tp_amb))",
    # Eventos: cancelamento e inutilização, com o XML da SEFAZ inteiro.
    "CREATE TABLE IF NOT EXISTS nfe_eventos ("
    " id UUID PRIMARY KEY,"
    " nfe_id UUID,"
    " emitente_cnpj VARCHAR(14) NOT NULL,"
    " tp_amb VARCHAR(1) NOT NULL,"
    " tipo VARCHAR(20) NOT NULL,"
    " chave_acesso VARCHAR(44),"
    " serie INTEGER,"
    " numero_inicial INTEGER,"
    " numero_final INTEGER,"
    " justificativa TEXT,"
    " codigo_status VARCHAR(4),"
    " mensagem TEXT,"
    " protocolo VARCHAR(20),"
    " xml_path TEXT,"
    " created_at TIMESTAMP NOT NULL DEFAULT now())",
    "CREATE INDEX IF NOT EXISTS ix_nfe_eventos_chave ON nfe_eventos (chave_acesso)",
    "CREATE INDEX IF NOT EXISTS ix_nfe_eventos_faixa ON nfe_eventos (emitente_cnpj, serie, tp_amb, tipo)",
    # Endereço legal do emitente: a NF-e exige xLgr/nro/xBairro/CEP e `empresas`
    # não tinha onde guardar — ficava chumbado no Python, em duas versões que
    # divergiam entre si.
    "ALTER TABLE empresas ADD COLUMN IF NOT EXISTS endereco_logradouro VARCHAR(60)",
    "ALTER TABLE empresas ADD COLUMN IF NOT EXISTS endereco_numero VARCHAR(60)",
    "ALTER TABLE empresas ADD COLUMN IF NOT EXISTS endereco_bairro VARCHAR(60)",
    "ALTER TABLE empresas ADD COLUMN IF NOT EXISTS endereco_cep VARCHAR(8)",
    "ALTER TABLE empresas ADD COLUMN IF NOT EXISTS endereco_municipio VARCHAR(60)",
    "ALTER TABLE empresas ADD COLUMN IF NOT EXISTS endereco_uf VARCHAR(2)",
    "ALTER TABLE empresas ADD COLUMN IF NOT EXISTS telefone VARCHAR(14)",
)

#: Semente do endereço legal, por SLUG (nunca por CNPJ literal — guard multi-CNPJ).
#: Eletrônica: endereço com que a SEFAZ-AM AUTORIZOU a nota em 24/09/2026.
#: Patrimonial: rua/nº/bairro vêm de `crm/services/pdf_branding.py` (fonte da casa);
#: o CEP NÃO é semeado porque não há fonte — sem ele o emissor recusa e diz qual
#: campo falta, em vez de chutar um CEP numa nota fiscal.
_SEED_ENDERECO = {
    "conecta_eletronica": {
        "endereco_logradouro": "Avenida Constantino Nery",
        "endereco_numero": "3343",
        "endereco_bairro": "Chapada",
        "endereco_cep": "69050001",
        "endereco_municipio": "Manaus",
        "endereco_uf": "AM",
        "telefone": "9232212100",
    },
    "conecta_patrimonial": {
        "endereco_logradouro": "Rua Victor Hughes",
        "endereco_numero": "19",
        "endereco_bairro": "Parque 10 de Novembro",
        "endereco_cep": None,
        "endereco_municipio": "Manaus",
        "endereco_uf": "AM",
        "telefone": "9232212100",
    },
}

_ensure_feito = False


async def _ensure(db: AsyncSession) -> None:
    """DDL idempotente + semente do endereço legal. Chamada por toda ação."""
    global _ensure_feito
    if _ensure_feito:
        return
    for ddl in _DDL:
        await db.execute(sqltext(ddl))
    for slug, campos in _SEED_ENDERECO.items():
        sets = ", ".join(f"{c} = COALESCE({c}, :{c})" for c in campos)
        await db.execute(sqltext(f"UPDATE empresas SET {sets} WHERE slug = :slug"), {**campos, "slug": slug})
    await db.commit()
    DIR_XML.mkdir(parents=True, exist_ok=True)
    _ensure_feito = True


# ---------------------------------------------------------------------------
# Emitente e numeração
# ---------------------------------------------------------------------------


async def carregar_emitente(db: AsyncSession, *, slug: str | None = None, cnpj: str | None = None) -> dict[str, Any]:
    """Identidade fiscal do emitente, da tabela `empresas`. Nada chumbado aqui."""
    emp = await get_empresa(db, slug=slug, cnpj=cnpj)
    linha = (
        await db.execute(
            sqltext(
                "SELECT endereco_logradouro, endereco_numero, endereco_bairro, endereco_cep,"
                " endereco_municipio, endereco_uf, telefone FROM empresas WHERE id = :id"
            ),
            {"id": str(emp["id"])},
        )
    ).mappings().first() or {}
    return {
        **emp,
        **dict(linha),
        "cnpj": re.sub(r"\D", "", str(emp.get("cnpj") or "")),
        "endereco_cod_municipio": emp.get("codigo_municipio_ibge") or "1302603",
        "crt": _CRT_POR_REGIME.get(str(emp.get("regime_tributario") or ""), "3"),
    }


async def proximo_numero(db: AsyncSession, cnpj: str, serie: int, tp_amb: str) -> int:
    """Reserva o próximo número de (CNPJ, série, ambiente). Atômico.

    `ON CONFLICT DO UPDATE` trava a linha do contador: duas emissões concorrentes
    serializam e recebem números diferentes. `GREATEST` com o que já existe em
    `nfes` conserta um contador que nasceu depois das notas (migração).
    """
    linha = (
        await db.execute(
            sqltext(
                # Casts explícitos: sem eles o asyncpg deduz text para o INSERT e
                # varchar para as comparações do mesmo $1 e recusa (AmbiguousParameter).
                "INSERT INTO nfe_numeracao (emitente_cnpj, serie, tp_amb, ultimo)"
                " VALUES (CAST(:cnpj AS VARCHAR), CAST(:serie AS INTEGER), CAST(:amb AS VARCHAR),"
                "   COALESCE((SELECT MAX(numero) FROM nfes"
                "             WHERE emitente_cnpj = CAST(:cnpj AS VARCHAR)"
                "               AND serie = CAST(:serie AS INTEGER)"
                "               AND tp_amb = CAST(:amb AS VARCHAR)), 0) + 1)"
                " ON CONFLICT (emitente_cnpj, serie, tp_amb) DO UPDATE"
                " SET ultimo = GREATEST("
                "       nfe_numeracao.ultimo,"
                "       COALESCE((SELECT MAX(numero) FROM nfes"
                "                 WHERE emitente_cnpj = CAST(:cnpj AS VARCHAR)"
                "                   AND serie = CAST(:serie AS INTEGER)"
                "                   AND tp_amb = CAST(:amb AS VARCHAR)), 0),"
                # Só faixa inutilizada que ENCOSTA no contador o empurra. Inutilizar
                # 9500-9502 estando no nº 8 é legítimo, mas não pode pular para 9503 —
                # isso abriria 9491 números sem nota e sem inutilização declarada.
                "       COALESCE((SELECT MAX(numero_final) FROM nfe_eventos"
                "                 WHERE emitente_cnpj = CAST(:cnpj AS VARCHAR)"
                "                   AND serie = CAST(:serie AS INTEGER)"
                "                   AND tp_amb = CAST(:amb AS VARCHAR)"
                "                   AND tipo = 'inutilizacao' AND codigo_status = '102'"
                "                   AND numero_inicial <= nfe_numeracao.ultimo + 1), 0)"
                "     ) + 1,"
                "     updated_at = now()"
                " RETURNING ultimo"
            ),
            {"cnpj": cnpj, "serie": serie, "amb": tp_amb},
        )
    ).scalar_one()
    return int(linha)


def _caminho_xml(cnpj: str, chave: str, sufixo: str) -> Path:
    """<DIR_XML>/<cnpj>/<AAAAMM>/<chave>-<sufixo>.xml — guarda de 5 anos."""
    pasta = DIR_XML / cnpj / (chave[2:6] if len(chave) == 44 else datetime.now().strftime("%y%m"))
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta / f"{chave}-{sufixo}.xml"


def _guardar_xml(cnpj: str, chave: str, sufixo: str, conteudo: str | None) -> str | None:
    """Grava o XML em disco. NUNCA levanta.

    Medido em PRODUÇÃO, 24/09/2026: a pasta `/app/uploads/nfe/<cnpj>/<AAMM>` tinha sido criada
    por fora com dono `root`, e o processo roda como uid 999. O `write_text` levantou
    `PermissionError`, a exceção subiu por `emitir()` até virar HTTP 500, **a transação foi
    desfeita e a linha da nota sumiu** — mas o número já tinha sido consumido pelo contador. Duas
    tentativas assim abriram os números **3 e 4** como buraco na numeração fiscal: o contador
    dizia 4 e só existiam as notas 1 e 2.

    O veredito da SEFAZ é o fato irreversível; o arquivo em disco é conveniência — o mesmo XML
    também vai para `nfes.xml_autorizado`/`nfes.xml_enviado`, que é a cópia que sobrevive. Perder
    o arquivo é dívida a resolver; perder a LINHA da nota é buraco fiscal invisível. Então aqui o
    erro de disco vira log e `None`, e a nota é gravada do mesmo jeito.
    """
    if not conteudo:
        return None
    try:
        caminho = _caminho_xml(cnpj, chave, sufixo)
        caminho.write_text(conteudo, encoding="utf-8")
        return str(caminho)
    except OSError as e:
        logger.error(
            "NF-e %s: XML (%s) NÃO foi para o disco (%s). A nota é gravada assim mesmo; "
            "o XML continua em `nfes.xml_*`. Conferir dono/permissão de %s.",
            chave,
            sufixo,
            e,
            DIR_XML,
        )
        return None


def _provider_para(emitente: dict[str, Any], tp_amb: str | None = None):
    """Provider com o certificado A1 DESTA empresa (registro de qualified_signer)."""
    from modules.signatures.services.qualified_signer import _cert_password, _cert_path

    slug = str(emitente.get("slug") or "")
    senha = _cert_password(slug)
    return create_nfe_provider(
        certificado_path=_cert_path(slug),
        certificado_senha=senha.decode("utf-8") if isinstance(senha, bytes) else str(senha),
        ambiente=tp_amb or ambiente_atual(),
        uf=str(emitente.get("endereco_uf") or "AM"),
    )


# ---------------------------------------------------------------------------
# Emissão
# ---------------------------------------------------------------------------


def _tributar(emitente: dict[str, Any], dados: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """Resolve CFOP e tributo de cada item pela régua da casa (DGX Z4).

    O emissor NÃO escolhe alíquota. `tributacao_nfe.calcular_puro` devolve CFOP, CST/CSOSN,
    base, alíquota e as mensagens fiscais obrigatórias — com norma e origem de cada número.
    `bloqueios` não vazio é recusa: melhor não emitir do que emitir com tributo chutado.
    """
    dest = dados.get("destinatario") or {}
    end = dest.get("endereco") or {}
    alvo = {
        "uf": end.get("uf") or emitente.get("endereco_uf") or "AM",
        "contribuinte": bool(dest.get("contribuinte")),
        "suframa": dest.get("inscricao_suframa") or dest.get("suframa") or "",
        "consumidor_final": dest.get("consumidor_final", True),
    }
    saida: list[dict[str, Any]] = []
    mensagens: list[str] = []
    for i, item in enumerate(dados.get("items") or [], start=1):
        calc = calcular_puro(
            emitente,
            {
                "codigo": item.get("codigo"),
                "ncm": item.get("ncm"),
                "valor": item.get("valor_unitario"),
                "quantidade": item.get("quantidade") or 1,
                "origem": item.get("icms_origem") or "0",
                # AA5 — como a mercadoria ENTROU decide o CFOP/CST da saída. Vem do CATÁLOGO
                # (`enriquecer_itens`, chamado em `emitir`), nunca do payload: se viesse do
                # payload, qualquer chamada declararia «entrou com ST» e ganharia ICMS zero.
                "icms_entrada_cst": item.get("icms_entrada_cst"),
                "icms_entrada_fonte": item.get("icms_entrada_fonte"),
            },
            alvo,
            operacao=str(dados.get("operacao") or "revenda"),
        )
        if calc.get("bloqueios"):
            raise NFeError(
                f"Item {i}: a régua fiscal recusou — " + " | ".join(calc["bloqueios"]),
                code="TRIBUTACAO_BLOQUEADA",
                details={"bloqueios": calc["bloqueios"], "item": i},
            )
        if not calc.get("cfop") or not calc.get("cst_ou_csosn"):
            raise NFeError(
                f"Item {i}: sem CFOP ou CST/CSOSN — {calc.get('origem_regra')}",
                code="TRIBUTACAO_INCOMPLETA",
            )
        simples = calc.get("crt") == "1"
        deson = calc.get("deson") or {}
        pis_cofins_zerado = bool(deson)
        saida.append(
            {
                **item,
                "cfop": calc["cfop"],
                "icms_csosn": calc["cst_ou_csosn"] if simples else "",
                "icms_cst": "" if simples else calc["cst_ou_csosn"],
                "icms_aliquota": calc.get("aliquota") or 0,
                "icms_base_calculo": calc.get("base"),
                "icms_valor": calc.get("valor") or 0,
                "icms_desonerado": deson.get("vICMSDeson") or 0,
                "icms_motivo_desoneracao": 7 if deson else None,
                # Simples: PIS/COFINS dentro do DAS (CST 49). ZFM: alíquota zero (CST 06).
                "pis_cst": "49" if simples else ("06" if pis_cofins_zerado else "01"),
                "cofins_cst": "49" if simples else ("06" if pis_cofins_zerado else "01"),
                "pis_aliquota": 0 if (simples or pis_cofins_zerado) else 1.65,
                "cofins_aliquota": 0 if (simples or pis_cofins_zerado) else 7.60,
            }
        )
        if calc.get("mensagem_fiscal") and calc["mensagem_fiscal"] not in mensagens:
            mensagens.append(calc["mensagem_fiscal"])
    return saida, mensagens


async def _registrar_falha(
    db: AsyncSession,
    emitente: dict[str, Any],
    serie: int,
    numero: int,
    tp_amb: str,
    nfe_id: UUID,
    motivo: str,
) -> None:
    """Grava o número reservado que não virou nota. Sem isso o buraco fica invisível."""
    await db.rollback()
    await db.execute(
        sqltext(
            "INSERT INTO nfes (id, condominio_id, empresa_id, tipo, finalidade, status, serie, numero,"
            " natureza_operacao, data_emissao, emitente_cnpj, emitente_razao_social, emitente_uf,"
            " emitente_crt, destinatario_cpf_cnpj, destinatario_razao_social, destinatario_uf,"
            " destinatario_logradouro, destinatario_numero, destinatario_bairro, destinatario_municipio,"
            " destinatario_cep, modalidade_frete, forma_pagamento, meio_pagamento, tp_amb,"
            " motivo_rejeicao, active)"
            " VALUES (:id, :cond, :emp, '1', '1', 'rejeitada', :serie, :numero, 'EMISSAO FALHOU', now(),"
            " :cnpj, :razao, :uf, :crt, '00000000000', 'NAO EMITIDA', :uf, '-', '-', '-', '-', '00000000',"
            " '9', '01', '01', :amb, :motivo, TRUE)"
            " ON CONFLICT DO NOTHING"
        ),
        {
            "id": str(nfe_id),
            "cond": str(emitente["id"]),
            "emp": str(emitente["id"]),
            "serie": serie,
            "numero": numero,
            "cnpj": emitente["cnpj"],
            "razao": str(emitente["razao_social"])[:60],
            "uf": str(emitente.get("endereco_uf") or "AM"),
            "crt": str(emitente.get("crt") or "3"),
            "amb": tp_amb,
            "motivo": motivo[:2000],
        },
    )
    await db.commit()


async def _exigir_documento_nfe55(db: AsyncSession, *, slug: str | None, cnpj: str | None) -> None:
    """Traduz a política de documentos da empresa para o `NFeError` desta casa.

    Sem isto, a Patrimonial era recusada por `EMITENTE_INCOMPLETO / falta: inscrição
    estadual, CEP` — o que manda a pessoa correr atrás de uma IE que o dono não pediu.
    A recusa certa diz o motivo (ela vende serviço) e aponta a tela de NFS-e.
    """
    from modules.fiscal.services.documentos_da_empresa import DocumentoNaoPermitido, exigir_nfe_produto

    try:
        await exigir_nfe_produto(db, slug=slug, cnpj=None if slug else cnpj)
    except DocumentoNaoPermitido as e:
        raise NFeError(str(e), code=e.code, details={"empresa": e.empresa, "tela": e.tela}) from e


async def emitir(
    db: AsyncSession,
    *,
    slug: str | None = None,
    cnpj: str | None = None,
    serie: int = 1,
    dados: dict[str, Any],
    tp_amb: str | None = None,
) -> dict[str, Any]:
    """Emite UMA NF-e: reserva número, monta, assina, transmite, guarda e persiste."""
    await _ensure(db)
    tp_amb = tp_amb or ambiente_atual()
    # A trava de produção vem ANTES de reservar número: recusar depois queimaria um
    # número da série de produção (e deixaria linha com tp_amb='1') sem nota nenhuma.
    _exigir_ambiente(tp_amb, "Emissão de NF-e")
    emitente = await carregar_emitente(db, slug=slug, cnpj=cnpj)
    cnpj_emit = emitente["cnpj"]
    # Antes de reservar número: esta empresa emite NF-e de PRODUTO? A CONECTAMAIS
    # PATRIMONIAL não emite — decisão do dono em 24/09/2026, não cadastro incompleto.
    # A regra mora em `empresas` (frente Z7); aqui só se obedece e se explica.
    await _exigir_documento_nfe55(db, slug=slug, cnpj=cnpj_emit)
    numero = await proximo_numero(db, cnpj_emit, serie, tp_amb)
    await db.commit()  # o número é reservado ANTES de ir à SEFAZ: não se reusa.

    # AA5: o fato «como a mercadoria entrou» é colado nos itens a partir de `fin_produtos`
    # ANTES da régua. Sem ele a régua recusa — melhor não emitir do que emitir com o CFOP errado.
    await icms_entrada.enriquecer_itens(db, dados.get("items") or [])
    itens, mensagens = _tributar(emitente, dados)

    nfe_id = uuid4()
    provider = _provider_para(emitente, tp_amb)
    complemento = " ".join(x for x in ([dados.get("informacoes_complementares") or ""] + mensagens) if x).strip()
    try:
        resultado = await provider.emitir_nfe(
            {**dados, "serie": serie, "items": itens, "informacoes_complementares": complemento},
            nfe_id,
            numero,
            emitente,
        )
    except Exception as exc:
        # O número JÁ foi reservado. Se a transmissão explode e nada é gravado, esse número
        # some da tabela e vira buraco na numeração fiscal — que só se fecha com inutilização.
        # Então a falha também vira linha: o número fica rastreável e inutilizável.
        await _registrar_falha(db, emitente, serie, numero, tp_amb, nfe_id, str(exc))
        raise

    chave = resultado["chave_acesso"]
    xml_path = _guardar_xml(
        cnpj_emit,
        chave,
        "proc" if resultado["status"] == "autorizada" else "rejeitada",
        resultado.get("xml_autorizado") or resultado.get("xml_enviado"),
    )

    dest = dados.get("destinatario") or {}
    end = dest.get("endereco") or {}
    total = sum(float(i.get("quantidade", 1)) * float(i.get("valor_unitario", 0)) for i in (dados.get("items") or []))
    await db.execute(
        sqltext(
            "INSERT INTO nfes (id, condominio_id, empresa_id, tipo, finalidade, status, serie, numero,"
            " chave_acesso, natureza_operacao, data_emissao, emitente_cnpj, emitente_razao_social,"
            " emitente_ie, emitente_uf, emitente_crt, destinatario_cpf_cnpj, destinatario_razao_social,"
            " destinatario_uf, destinatario_logradouro, destinatario_numero, destinatario_bairro,"
            " destinatario_municipio, destinatario_cep, modalidade_frete, forma_pagamento, meio_pagamento,"
            " valor_total_produtos, valor_total_nota, informacoes_complementares, tp_amb, codigo_status, motivo_rejeicao,"
            " protocolo_autorizacao, data_autorizacao, xml_enviado, xml_autorizado, xml_path, active)"
            " VALUES (:id, :cond, :emp, '1', :fin, CAST(:status AS VARCHAR), :serie, :numero, :chave, :natop, now(),"
            " :cnpj, :razao, :ie, :uf, :crt, :dcnpj, :drazao, :duf, :dlgr, :dnro, :dbai, :dmun, :dcep,"
            " '9', '01', '01', :vprod, :vnf, :infcpl, :amb, :cstat, :motivo, :prot,"
            " CASE WHEN CAST(:status AS VARCHAR) = 'autorizada' THEN now() ELSE NULL END, :xenv, :xaut, :xpath, TRUE)"
        ),
        {
            "id": str(nfe_id),
            "cond": str(emitente["id"]),
            "emp": str(emitente["id"]),
            "fin": str(dados.get("finalidade") or "1"),
            "status": resultado["status"],
            "serie": serie,
            "numero": numero,
            "chave": chave,
            "natop": str(dados.get("natureza_operacao") or "VENDA DE MERCADORIA")[:60],
            "cnpj": cnpj_emit,
            "razao": str(emitente["razao_social"])[:60],
            "ie": str(emitente.get("inscricao_estadual") or "")[:14],
            "uf": str(emitente.get("endereco_uf") or "AM"),
            "crt": str(emitente.get("crt") or "3"),
            "dcnpj": re.sub(r"\D", "", str(dest.get("cnpj") or dest.get("cpf") or ""))[:14] or "00000000000",
            "drazao": str(dest.get("razao_social") or dest.get("nome") or "CONSUMIDOR")[:60],
            "duf": str(end.get("uf") or "AM")[:2],
            "dlgr": str(end.get("logradouro") or "NAO INFORMADO")[:60],
            "dnro": str(end.get("numero") or "S/N")[:60],
            "dbai": str(end.get("bairro") or "NAO INFORMADO")[:60],
            "dmun": str(end.get("municipio") or "Manaus")[:60],
            "dcep": re.sub(r"\D", "", str(end.get("cep") or "69000000"))[:8],
            "infcpl": str(dados.get("informacoes_complementares") or "")[:2000] or None,
            "vprod": total,
            "vnf": total,
            "amb": tp_amb,
            "cstat": resultado.get("codigo_status") or "",
            "motivo": resultado.get("motivo") or "",
            "prot": (resultado.get("protocolo") or "")[:15] or None,
            "xenv": resultado.get("xml_enviado"),
            "xaut": resultado.get("xml_autorizado"),
            "xpath": xml_path,
        },
    )
    await db.commit()
    return {
        "nfe_id": str(nfe_id),
        "numero": numero,
        "serie": serie,
        "chave_acesso": chave,
        "tp_amb": tp_amb,
        "ambiente": "homologação" if tp_amb == "2" else "PRODUÇÃO",
        "status": resultado["status"],
        "cStat": resultado.get("codigo_status"),
        "xMotivo": resultado.get("motivo"),
        "protocolo": resultado.get("protocolo"),
        "xml_path": xml_path,
    }


async def cancelar(db: AsyncSession, *, chave: str, justificativa: str, tp_amb: str | None = None) -> dict[str, Any]:
    """Cancela NF-e autorizada (evento 110111). Guarda o evento e marca a nota."""
    await _ensure(db)
    tp_amb = tp_amb or ambiente_atual()
    _exigir_ambiente(tp_amb, "Cancelamento de NF-e")
    nota = (
        (
            await db.execute(
                sqltext(
                    "SELECT id, emitente_cnpj, protocolo_autorizacao, status, data_autorizacao, tp_amb"
                    " FROM nfes WHERE chave_acesso = :chave AND tp_amb = :amb"
                ),
                {"chave": chave, "amb": tp_amb},
            )
        )
        .mappings()
        .first()
    )
    if not nota:
        raise NFeError(f"NF-e {chave} não encontrada no ambiente {tp_amb}.", code="NAO_ENCONTRADA")
    if nota["status"] != "autorizada":
        raise NFeError(f"Só se cancela nota AUTORIZADA (esta está '{nota['status']}').", code="STATUS_INVALIDO")

    emitente = await carregar_emitente(db, cnpj=nota["emitente_cnpj"])
    provider = _provider_para(emitente, tp_amb)
    resultado = await provider.cancelar_nfe(
        chave, justificativa, UUID(str(nota["id"])), str(nota["protocolo_autorizacao"] or ""), nota["emitente_cnpj"]
    )
    xml_path = _guardar_xml(nota["emitente_cnpj"], chave, "cancelamento", resultado.get("xml_evento"))

    await db.execute(
        sqltext(
            "INSERT INTO nfe_eventos (id, nfe_id, emitente_cnpj, tp_amb, tipo, chave_acesso,"
            " justificativa, codigo_status, mensagem, protocolo, xml_path)"
            " VALUES (:id, :nfe, :cnpj, :amb, 'cancelamento', :chave, :just, :cstat, :msg, :prot, :xpath)"
        ),
        {
            "id": str(uuid4()),
            "nfe": str(nota["id"]),
            "cnpj": nota["emitente_cnpj"],
            "amb": tp_amb,
            "chave": chave,
            "just": justificativa,
            "cstat": resultado.get("codigo_status"),
            "msg": resultado.get("mensagem"),
            "prot": (resultado.get("protocolo") or "")[:20] or None,
            "xpath": xml_path,
        },
    )
    if resultado["status"] == "cancelada":
        await db.execute(
            sqltext(
                "UPDATE nfes SET status = 'cancelada', data_cancelamento = now(),"
                " motivo_cancelamento = :just, protocolo_cancelamento = :prot WHERE id = :id"
            ),
            {"id": str(nota["id"]), "just": justificativa, "prot": (resultado.get("protocolo") or "")[:20] or None},
        )
    await db.commit()
    return {**resultado, "xml_path": xml_path}


async def inutilizar(
    db: AsyncSession,
    *,
    slug: str | None = None,
    cnpj: str | None = None,
    serie: int,
    numero_inicial: int,
    numero_final: int,
    justificativa: str,
    tp_amb: str | None = None,
) -> dict[str, Any]:
    """Inutiliza faixa de numeração — declara o buraco em vez de escondê-lo."""
    await _ensure(db)
    tp_amb = tp_amb or ambiente_atual()
    _exigir_ambiente(tp_amb, "Inutilização de faixa")
    emitente = await carregar_emitente(db, slug=slug, cnpj=cnpj)
    usados = (
        await db.execute(
            sqltext(
                # Nota REJEITADA nunca existiu no fisco — o número volta para a fila e
                # pode ser inutilizado. Só autorizada/cancelada/denegada ocupam de verdade.
                "SELECT COUNT(*) FROM nfes WHERE emitente_cnpj = :cnpj AND serie = :serie"
                " AND tp_amb = :amb AND numero BETWEEN :ini AND :fim"
                " AND status IN ('autorizada', 'cancelada', 'denegada')"
            ),
            {"cnpj": emitente["cnpj"], "serie": serie, "amb": tp_amb, "ini": numero_inicial, "fim": numero_final},
        )
    ).scalar_one()
    if usados:
        raise NFeError(
            f"{usados} nota(s) já ocupam a faixa {numero_inicial}-{numero_final} da série {serie}. "
            "Inutilização é só para número que NUNCA virou nota.",
            code="FAIXA_OCUPADA",
        )

    provider = _provider_para(emitente, tp_amb)
    resultado = await provider.inutilizar_faixa(emitente["cnpj"], serie, numero_inicial, numero_final, justificativa)
    chave_falsa = f"{emitente['cnpj']}-{serie}-{numero_inicial}-{numero_final}"
    xml_path = _guardar_xml(emitente["cnpj"], chave_falsa, "inutilizacao", resultado.get("xml_evento"))
    await db.execute(
        sqltext(
            "INSERT INTO nfe_eventos (id, emitente_cnpj, tp_amb, tipo, serie, numero_inicial, numero_final,"
            " justificativa, codigo_status, mensagem, protocolo, xml_path)"
            " VALUES (:id, :cnpj, :amb, 'inutilizacao', :serie, :ini, :fim, :just, :cstat, :msg, :prot, :xpath)"
        ),
        {
            "id": str(uuid4()),
            "cnpj": emitente["cnpj"],
            "amb": tp_amb,
            "serie": serie,
            "ini": numero_inicial,
            "fim": numero_final,
            "just": justificativa,
            "cstat": resultado.get("codigo_status"),
            "msg": resultado.get("mensagem"),
            "prot": (resultado.get("protocolo") or "")[:20] or None,
            "xpath": xml_path,
        },
    )
    if resultado["status"] == "inutilizada":
        await db.execute(
            sqltext(
                "UPDATE nfes SET status = 'inutilizada' WHERE emitente_cnpj = :cnpj AND serie = :serie"
                " AND tp_amb = :amb AND numero BETWEEN :ini AND :fim AND status = 'rejeitada'"
            ),
            {"cnpj": emitente["cnpj"], "serie": serie, "amb": tp_amb, "ini": numero_inicial, "fim": numero_final},
        )
        # O contador só avança se a faixa inutilizada encostar nele. Uma faixa lá em cima
        # fica declarada em `nfe_eventos` e o contador segue de onde estava.
        await db.execute(
            sqltext(
                "INSERT INTO nfe_numeracao (emitente_cnpj, serie, tp_amb, ultimo)"
                " VALUES (CAST(:cnpj AS VARCHAR), CAST(:serie AS INTEGER), CAST(:amb AS VARCHAR), 0)"
                " ON CONFLICT (emitente_cnpj, serie, tp_amb) DO UPDATE"
                " SET ultimo = CASE WHEN CAST(:ini AS INTEGER) <= nfe_numeracao.ultimo + 1"
                "                   THEN GREATEST(nfe_numeracao.ultimo, CAST(:fim AS INTEGER))"
                "                   ELSE nfe_numeracao.ultimo END,"
                "     updated_at = now()"
            ),
            {
                "cnpj": emitente["cnpj"],
                "serie": serie,
                "amb": tp_amb,
                "ini": numero_inicial,
                "fim": numero_final,
            },
        )
    await db.commit()
    return {**resultado, "xml_path": xml_path}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


class ItemNFe(BaseModel):
    codigo: str = Field(..., max_length=60)
    descricao: str = Field(..., max_length=120)
    ncm: str = Field(..., description="NCM de 8 dígitos")
    cfop: str = Field(default="5102")
    unidade: str = Field(default="UN", max_length=6)
    quantidade: float = Field(..., gt=0)
    valor_unitario: float = Field(..., gt=0)


class EmitirRequest(BaseModel):
    empresa_slug: str = Field(default="conecta_eletronica", description="slug em `empresas`")
    serie: int = Field(default=1, ge=1)
    natureza_operacao: str = Field(default="VENDA DE MERCADORIA", max_length=60)
    destinatario: dict[str, Any] = Field(default_factory=dict)
    items: list[ItemNFe] = Field(..., min_length=1)
    informacoes_complementares: str | None = None


class CancelarRequest(BaseModel):
    chave_acesso: str = Field(..., min_length=44, max_length=44)
    justificativa: str = Field(..., min_length=15, max_length=255)


class InutilizarRequest(BaseModel):
    empresa_slug: str = Field(default="conecta_eletronica")
    serie: int = Field(default=1, ge=1)
    numero_inicial: int = Field(..., ge=1)
    numero_final: int = Field(..., ge=1)
    justificativa: str = Field(..., min_length=15, max_length=255)


def _erro(e: NFeError) -> HTTPException:
    return HTTPException(status_code=400, detail={"code": e.code, "message": e.message, **e.details})


@router.get("/sefaz-status", summary="Status do serviço da SEFAZ para a empresa")
async def sefaz_status(
    empresa_slug: str = "conecta_eletronica",
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    await _ensure(db)
    emitente = await carregar_emitente(db, slug=empresa_slug)
    try:
        status = await _provider_para(emitente).test_connection()
    except NFeError as e:
        raise _erro(e) from e
    return {
        **status,
        "empresa": emitente["razao_social"],
        "tp_amb": ambiente_atual(),
        "producao_liberada": producao_liberada(),
    }


@router.get("/listar", summary="NF-e emitidas")
async def listar(
    empresa_slug: str | None = None,
    limite: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    await _ensure(db)
    filtro, params = "", {"lim": min(limite, 500)}
    if empresa_slug:
        emitente = await carregar_emitente(db, slug=empresa_slug)
        filtro = " WHERE emitente_cnpj = :cnpj"
        params["cnpj"] = emitente["cnpj"]
    linhas = (
        (
            await db.execute(
                sqltext(
                    "SELECT numero, serie, tp_amb, status, codigo_status, chave_acesso, emitente_razao_social,"
                    " destinatario_razao_social, valor_total_nota, protocolo_autorizacao, motivo_rejeicao,"
                    " xml_path, data_emissao FROM nfes" + filtro + " ORDER BY data_emissao DESC LIMIT :lim"
                ),
                params,
            )
        )
        .mappings()
        .all()
    )
    return {"total": len(linhas), "ambiente_atual": ambiente_atual(), "notas": [dict(x) for x in linhas]}


@router.post("/emitir", summary="Emite NF-e modelo 55 (homologação por padrão)")
async def emitir_endpoint(
    req: EmitirRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        return await emitir(
            db,
            slug=req.empresa_slug,
            serie=req.serie,
            dados={
                "natureza_operacao": req.natureza_operacao,
                "destinatario": req.destinatario,
                "items": [i.model_dump() for i in req.items],
                "informacoes_complementares": req.informacoes_complementares,
            },
        )
    except NFeError as e:
        raise _erro(e) from e


@router.post("/cancelar", summary="Cancela NF-e autorizada (evento 110111, prazo 24h)")
async def cancelar_endpoint(
    req: CancelarRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        return await cancelar(db, chave=req.chave_acesso, justificativa=req.justificativa)
    except NFeError as e:
        raise _erro(e) from e


@router.post("/inutilizar", summary="Inutiliza faixa de numeração")
async def inutilizar_endpoint(
    req: InutilizarRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        return await inutilizar(
            db,
            slug=req.empresa_slug,
            serie=req.serie,
            numero_inicial=req.numero_inicial,
            numero_final=req.numero_final,
            justificativa=req.justificativa,
        )
    except NFeError as e:
        raise _erro(e) from e

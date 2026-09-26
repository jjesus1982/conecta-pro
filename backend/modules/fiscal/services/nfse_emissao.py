"""DGX Z7 — emissor de NFS-e (Padrão Nacional): numeração, persistência e guarda do XML.

É a camada que faltava em volta de `government_integrations/core/nfse_nacional.py`, que
sabe montar a DPS, assinar e transmitir — e **não guarda nada**. O resultado medido em
24/09/2026, no sandbox e em produção, era o mesmo:

    select count(*), count(*) filter (where coalesce(protocolo,'')<>''),
           count(*) filter (where coalesce(xml_retorno,'')<>'') from nfses;
    -->  27 | 0 | 0

Vinte e sete linhas dizendo `status='autorizada'` sem uma única prova do órgão. O status
era uma palavra escrita localmente — exatamente o que a frente Z2 encontrou na NF-e.

O que esta camada acrescenta
----------------------------
  · **numeração atômica** por (CNPJ + série + ambiente), no mesmo desenho da Z2
    (`INSERT … ON CONFLICT DO UPDATE … GREATEST(…)+1 RETURNING`): uma ida ao banco, linha
    travada. O número é reservado ANTES de ir ao fisco e nunca volta atrás; transmissão que
    falha também vira linha, com o motivo — senão o número some e vira buraco invisível.
    O que havia antes era `numero_dps = int(time.time())`: buraco garantido e permanente.
  · **persistência do que o órgão devolveu**: chave de acesso, `cStat`, `nNFSe`, `nDFSe`,
    `dhProc` e o XML `<NFSe>` assinado pelo próprio fisco.
  · **guarda do XML nos DOIS lugares** — disco (`/app/uploads/nfse`, bind do host) e banco.
    A Z2 aprendeu do jeito duro: gravou só num volume de container efêmero e perdeu o XML
    das notas autorizadas quando o container morreu.
  · **a trava de produção** mora uma camada abaixo, em `nfse_nacional`, onde TODO chamador
    passa (`_exigir_ambiente_nfse` + `_conferir_tp_amb`). Aqui ela é só reafirmada antes de
    gastar numeração.

O que NÃO faz
-------------
  · não escolhe alíquota de ISS: manda o que veio e **grava o que o órgão devolveu**. Para
    a Patrimonial (Simples Nacional) o fisco não devolve ISS nenhum — o ISSQN dela é apurado
    dentro do DAS —, então a coluna fica nula em vez de receber um número inventado;
  · não cancela NFS-e (evento de cancelamento não foi implementado — §5 do relatório);
  · não toca nas 27 linhas antigas. Elas não são minhas para reescrever: ficam como estão e
    a tela mostra o estado real («sem comprovação — nunca transmitida»).

Ambiente: vem de `empresas.nfse_ambiente` (hoje 'homologacao' nas duas empresas).
Produção exige, além disso, `NFSE_PRODUCAO_LIBERADA` com a frase-senha.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import text as sqltext
from sqlalchemy.ext.asyncio import AsyncSession

from modules.government_integrations.core.nfse_nacional import (
    ENV_GATE_PRODUCAO_NFSE,
    NFSeAmbienteError,
    _exigir_ambiente_nfse,
    producao_nfse_liberada,
    url_para,
)

logger = logging.getLogger(__name__)

#: Onde o XML fica guardado. `/app/uploads` é bind do host (durável) — ver docstring.
DIR_XML = Path(os.getenv("NFSE_XML_DIR", "/app/uploads/nfse"))

#: Série PADRÃO do ERP, usada só quando a empresa não declarou a dela em
#: `empresas.nfse_serie_rps`. As notas que a empresa já emite pelo portal do fisco usam
#: outra numeração (115 notas em `nfse_emitidas_nacional`, nº 1–123) — série separada é
#: o que impede o ERP de colidir com elas.
#:
#: POR QUE VIROU DADO E NÃO É MAIS CONSTANTE (24/09/2026, medido):
#: a homologação do Padrão Nacional é UMA SÓ para todo mundo. O sandbox e a produção deste
#: mesmo sistema batem nela com o MESMO CNPJ. Emitindo de produção com a série 900 — que o
#: sandbox já tinha queimado nos testes da frente Z7 — o fisco devolveu:
#:
#:     E0014 · Conjunto de Série, Número, Código do Município Emissor e CNPJ/CPF informado
#:             nesta DPS já existe em uma NFS-e gerada a partir de uma DPS enviada anteriormente
#:
#: É o mesmo defeito que a NF-e teve hoje (lá resolvido com série 2 para produção). A série
#: identifica o PONTO DE EMISSÃO; sandbox e produção são dois pontos e precisam de séries
#: diferentes. E há um terceiro ponto: o portal que a contabilidade usa, na série 70000.
#: Com a série em `empresas`, cada ponto declara a sua sem tocar em código.
SERIE_PADRAO = "900"


def serie_da(emp: dict) -> str:
    """Série da DPS de quem emite DAQUI. `empresas.nfse_serie_rps` manda; sem ela, a padrão.

    Não confundir com `nfse_parametros.serie_de`, que devolve a série do PORTAL da
    contabilidade (70000) e serve para ler, não para emitir.
    """
    return str(emp.get("nfse_serie_rps") or SERIE_PADRAO).strip() or SERIE_PADRAO


#: Condomínio "empresa da casa": `nfses.condominio_id` é NOT NULL e não tem FK. Mesmo id
#: que a frente Z3 usa em `nfes`.
_COND = "00000000-0000-0000-0000-000000000001"


class NFSeErro(Exception):  # noqa: N818 — «Erro» é o sufixo da casa (ver HEClassificacaoErro)
    """Recusa com motivo legível. `code` é o que a tela usa para decidir o texto."""

    def __init__(self, msg: str, code: str = "NFSE_ERRO", details: dict | None = None) -> None:
        super().__init__(msg)
        self.code = code
        self.details = details or {}


# ---------------------------------------------------------------------------
# DDL idempotente
# ---------------------------------------------------------------------------

_DDL = (
    # Sem ambiente na linha, homologação e produção se misturam na mesma tabela e a
    # numeração de uma contamina a da outra. As 27 linhas antigas ficam com NULL — não
    # dá para adivinhar em qual ambiente elas foram, e adivinhar seria mentir.
    "ALTER TABLE nfses ADD COLUMN IF NOT EXISTS ambiente varchar(16)",
    "ALTER TABLE nfses ADD COLUMN IF NOT EXISTS empresa_slug varchar(40)",
    "ALTER TABLE nfses ADD COLUMN IF NOT EXISTS chave_acesso varchar(60)",
    "ALTER TABLE nfses ADD COLUMN IF NOT EXISTS numero_dfe varchar(20)",
    "ALTER TABLE nfses ADD COLUMN IF NOT EXISTS c_stat varchar(8)",
    "ALTER TABLE nfses ADD COLUMN IF NOT EXISTS xml_path text",
    "ALTER TABLE nfses ADD COLUMN IF NOT EXISTS criado_por varchar(120)",
    "CREATE INDEX IF NOT EXISTS ix_nfses_chave ON nfses (chave_acesso)",
    # A trava que impede duas notas com o mesmo número no mesmo CNPJ/série/ambiente.
    # `WHERE ambiente IS NOT NULL` deixa as 27 linhas antigas de fora: elas não têm
    # ambiente e não podem ser julgadas por uma regra que nasceu depois delas.
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_nfses_prestador_serie_numero "
    "ON nfses (prestador_cnpj, serie_rps, numero_rps, ambiente) "
    "WHERE ambiente IS NOT NULL AND numero_rps IS NOT NULL",
    # Contador por (CNPJ, série, ambiente). Linha única, incrementada atomicamente.
    "CREATE TABLE IF NOT EXISTS nfse_numeracao ("
    " prestador_cnpj varchar(14) NOT NULL,"
    " serie varchar(5) NOT NULL,"
    " ambiente varchar(16) NOT NULL,"
    " ultimo integer NOT NULL DEFAULT 0,"
    " updated_at timestamp NOT NULL DEFAULT now(),"
    " PRIMARY KEY (prestador_cnpj, serie, ambiente))",
)


async def _ensure(db: AsyncSession) -> None:
    for sql in _DDL:
        await db.execute(sqltext(sql))
    await db.commit()


# ---------------------------------------------------------------------------
# Identidade e ambiente
# ---------------------------------------------------------------------------


async def carregar_empresa(db: AsyncSession, empresa: str) -> dict[str, Any]:
    """Identidade fiscal da empresa emitente, da tabela `empresas`. Nada chumbado aqui."""
    from modules.government_integrations.services.nfse_nacional_service import resolver_empresa_slug

    slug = resolver_empresa_slug(empresa)
    linha = (
        (
            await db.execute(
                sqltext(
                    "SELECT id::text, slug, cnpj, razao_social, inscricao_municipal,"
                    " coalesce(nfse_ambiente,'homologacao') AS nfse_ambiente,"
                    " coalesce(codigo_municipio_ibge,'1302603') AS cod_mun,"
                    # Série da DPS DESTA empresa. Sem ela cai na SERIE_PADRAO — e aí sandbox
                    # e produção colidem no fisco (E0014, medido em 24/09). Ver `serie_da`.
                    " nullif(trim(coalesce(nfse_serie_rps,'')),'') AS nfse_serie_rps,"
                    " regime_tributario::text AS regime"
                    " FROM empresas WHERE slug = :s AND status = 'ativa'"
                ),
                {"s": slug},
            )
        )
        .mappings()
        .first()
    )
    if not linha:
        raise NFSeErro(
            f"Empresa emitente '{empresa}' não encontrada (ou inativa) na tabela `empresas`.",
            code="EMPRESA_DESCONHECIDA",
        )
    d = dict(linha)
    d["cnpj"] = re.sub(r"\D", "", str(d.get("cnpj") or ""))
    if not d["cnpj"]:
        raise NFSeErro(f"A empresa '{slug}' está sem CNPJ em `empresas`.", code="EMITENTE_INCOMPLETO")
    return d


def tp_amb_de(ambiente: str) -> str:
    """'producao' → '1'; qualquer outra coisa → '2'. Homologação é o padrão seguro."""
    return "1" if str(ambiente).strip().lower() == "producao" else "2"


def estado_da_trava() -> dict[str, Any]:
    """O que a tela mostra sobre a trava. Nunca expõe a frase-senha."""
    return {
        "variavel": ENV_GATE_PRODUCAO_NFSE,
        "producao_liberada": producao_nfse_liberada(),
        "host_homologacao": url_para("homologacao"),
        "host_producao": url_para("producao"),
    }


# ---------------------------------------------------------------------------
# Numeração
# ---------------------------------------------------------------------------


async def proximo_numero(db: AsyncSession, cnpj: str, serie: str, ambiente: str) -> int:
    """Reserva o próximo número de (CNPJ, série, ambiente). Atômico.

    `ON CONFLICT DO UPDATE` trava a linha do contador: duas emissões concorrentes
    serializam e recebem números diferentes e consecutivos. O `GREATEST` com o
    `MAX(numero_rps)` de `nfses` conserta um contador que nasce depois das notas.
    """
    p = {"cnpj": cnpj, "serie": serie, "amb": ambiente}
    linha = (
        await db.execute(
            sqltext(
                # Casts explícitos: sem eles o asyncpg deduz text no INSERT e varchar na
                # comparação do MESMO parâmetro e recusa (AmbiguousParameterError) — foi
                # o que derrubou a primeira emissão da Z2.
                "INSERT INTO nfse_numeracao (prestador_cnpj, serie, ambiente, ultimo)"
                " VALUES (CAST(:cnpj AS VARCHAR), CAST(:serie AS VARCHAR), CAST(:amb AS VARCHAR),"
                "   COALESCE((SELECT MAX(numero_rps) FROM nfses"
                "             WHERE prestador_cnpj = CAST(:cnpj AS VARCHAR)"
                "               AND serie_rps = CAST(:serie AS VARCHAR)"
                "               AND ambiente = CAST(:amb AS VARCHAR)), 0) + 1)"
                " ON CONFLICT (prestador_cnpj, serie, ambiente) DO UPDATE"
                " SET ultimo = GREATEST("
                "       nfse_numeracao.ultimo,"
                "       COALESCE((SELECT MAX(numero_rps) FROM nfses"
                "                 WHERE prestador_cnpj = CAST(:cnpj AS VARCHAR)"
                "                   AND serie_rps = CAST(:serie AS VARCHAR)"
                "                   AND ambiente = CAST(:amb AS VARCHAR)), 0)) + 1,"
                "     updated_at = now()"
                " RETURNING ultimo"
            ),
            p,
        )
    ).first()
    return int(linha[0])


async def espiar_numero(db: AsyncSession, cnpj: str, serie: str, ambiente: str) -> int:
    """Qual número SERIA reservado agora, sem reservar. Só para a prévia."""
    linha = (
        await db.execute(
            sqltext(
                "SELECT GREATEST("
                "  COALESCE((SELECT ultimo FROM nfse_numeracao"
                "            WHERE prestador_cnpj = :cnpj AND serie = :serie AND ambiente = :amb), 0),"
                "  COALESCE((SELECT MAX(numero_rps) FROM nfses"
                "            WHERE prestador_cnpj = :cnpj AND serie_rps = :serie"
                "              AND ambiente = :amb), 0)) + 1"
            ),
            {"cnpj": cnpj, "serie": serie, "amb": ambiente},
        )
    ).first()
    return int(linha[0])


# ---------------------------------------------------------------------------
# Guarda do XML
# ---------------------------------------------------------------------------


def guardar_xml(cnpj: str, nome: str, conteudo: str | None) -> str | None:
    """Grava o XML em disco e devolve o caminho. Falha de disco NÃO derruba a emissão.

    A nota já existe no fisco; perder o arquivo local é ruim, fingir que a nota não
    saiu é pior. Por isso o banco também guarda o XML inteiro (`xml_retorno`).
    """
    if not conteudo:
        return None
    try:
        pasta = DIR_XML / cnpj / datetime.now().strftime("%y%m")
        pasta.mkdir(parents=True, exist_ok=True)
        destino = pasta / f"{re.sub(r'[^A-Za-z0-9._-]', '_', nome)}.xml"
        destino.write_text(conteudo, encoding="utf-8")
        return str(destino)
    except Exception as e:  # noqa: BLE001
        logger.error(f"NFS-e: não consegui gravar o XML em disco ({e}); o banco segue com o conteúdo")
        return None


# ---------------------------------------------------------------------------
# Emissão
# ---------------------------------------------------------------------------


def _ts(v: Any) -> datetime | None:
    """`dhProc` do fisco ('2026-09-24T16:23:57-03:00') → datetime. Ilegível vira None."""
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v)[:19])
    except Exception:  # noqa: BLE001
        return None


def _num(v: Any) -> float | None:
    try:
        return float(str(v).replace(",", "."))
    except Exception:  # noqa: BLE001
        return None


async def _gravar(
    db: AsyncSession,
    *,
    emp: dict[str, Any],
    ambiente: str,
    numero: int,
    tomador: dict[str, Any],
    servico: dict[str, Any],
    competencia: str,
    resultado: dict[str, Any],
    status: str,
    quem: str,
) -> str:
    """UMA linha em `nfses` — autorizada ou rejeitada. O número nunca fica sem linha."""
    chave = resultado.get("chave_acesso")
    xml_dps = resultado.get("xml_dps_assinado")
    xml_nfse = resultado.get("xml_nfse")
    base = chave or f"rejeitada-{ambiente}-{serie_da(emp)}-{numero}"
    xml_path = guardar_xml(emp["cnpj"], f"{base}-nfse", xml_nfse) or guardar_xml(emp["cnpj"], f"{base}-dps", xml_dps)

    nfse_id = str(uuid4())
    comp = competencia if re.fullmatch(r"\d{4}-\d{2}", str(competencia or "")) else datetime.now().strftime("%Y-%m")
    motivo = resultado.get("response") or resultado.get("erro") or ""
    if resultado.get("c_stat"):
        motivo = f"cStat {resultado['c_stat']} · nNFSe {resultado.get('numero_nfse', '?')} · nDFSe {resultado.get('numero_dfe', '?')}"
    await db.execute(
        sqltext(
            "INSERT INTO nfses (id, condominio_id, empresa_id, empresa_slug, ambiente, status,"
            " serie_rps, numero_rps, tipo_rps, numero_nfse, chave_acesso, numero_dfe, c_stat,"
            " data_emissao, data_competencia, data_processamento, natureza_operacao,"
            " prestador_cnpj, prestador_inscricao_municipal, prestador_razao_social,"
            " tomador_cpf_cnpj, tomador_razao_social, tomador_email, tomador_logradouro,"
            " tomador_numero, tomador_bairro, tomador_municipio, tomador_uf, tomador_cep,"
            " codigo_servico, descricao_servico, discriminacao, valor_servicos, iss_aliquota,"
            " iss_valor, protocolo, mensagem_retorno, xml_enviado, xml_retorno, xml_path,"
            " criado_por, created_at, active)"
            " VALUES (CAST(:id AS UUID), CAST(:cond AS UUID), CAST(:emp AS UUID), :slug, :amb, :st,"
            " :serie, :num, '1', :nnfse, :chave, :ndfe, :cstat,"
            " now(), :comp, :dhproc, '1',"
            " :cnpj, :im, :razao,"
            " :tdoc, :tnome, :tmail, :tlgr,"
            " :tnum, :tbai, :tmun, :tuf, :tcep,"
            " :cserv, :desc, :desc, :valor, :aliq,"
            " :vitiss, :prot, :msg, :xenv, :xret, :xpath,"
            " :quem, now(), TRUE)"
        ),
        {
            "id": nfse_id,
            "cond": _COND,
            "emp": emp["id"],
            "slug": emp["slug"],
            "amb": ambiente,
            "st": status,
            "serie": serie_da(emp),
            "num": numero,
            "nnfse": str(resultado.get("numero_nfse") or "")[:20] or None,
            "chave": chave,
            "ndfe": str(resultado.get("numero_dfe") or "")[:20] or None,
            "cstat": str(resultado.get("c_stat") or "")[:8] or None,
            # asyncpg confere o TIPO do parâmetro antes do CAST do SQL: string em coluna
            # date/timestamp estoura `'str' object has no attribute 'toordinal'`. Converte aqui.
            "comp": date.fromisoformat(f"{comp}-01"),
            "dhproc": _ts(resultado.get("data_processamento")),
            "cnpj": emp["cnpj"],
            "im": (emp.get("inscricao_municipal") or "")[:15] or None,
            "razao": (emp.get("razao_social") or "")[:150],
            "tdoc": re.sub(r"\D", "", str(tomador.get("cpf_cnpj") or ""))[:14],
            "tnome": str(tomador.get("razao_social") or "")[:150],
            "tmail": (str(tomador.get("email") or "") or None),
            "tlgr": str(tomador.get("logradouro") or "")[:125],
            "tnum": str(tomador.get("numero") or "S/N")[:10],
            "tbai": str(tomador.get("bairro") or "")[:60],
            "tmun": str(tomador.get("municipio") or "Manaus")[:60],
            "tuf": str(tomador.get("uf") or "AM")[:2],
            "tcep": re.sub(r"\D", "", str(tomador.get("cep") or ""))[:8],
            "cserv": str(servico.get("codigo_tributacao_nacional") or "")[:20],
            "desc": str(servico.get("descricao") or ""),
            "valor": _num(servico.get("valor_servico")) or 0,
            # A alíquota e o ISS são os que o FISCO devolveu — não os que mandamos. Para
            # o Simples Nacional o fisco não devolve nenhum (o ISSQN sai no DAS): fica
            # nulo, nunca um número inventado para preencher coluna.
            # `iss_aliquota` é NOT NULL na tabela. Quando o fisco NÃO devolve alíquota
            # — o caso do Simples Nacional, em que o ISSQN é apurado dentro do DAS — vai
            # 0 e o motivo fica escrito em `mensagem_retorno`; a tela mostra «—», não 0%.
            "aliq": (_num(resultado.get("aliquota_iss_fisco")) or 0) / 100,
            "vitiss": _num(resultado.get("valor_iss_fisco")),
            # O Padrão Nacional não devolve "protocolo" como a NF-e: o que prova a nota é
            # a chave + o nDFSe (sequencial nacional) + o XML assinado pelo fisco.
            "prot": str(resultado.get("numero_dfe") or "")[:50] or None,
            "msg": motivo[:4000],
            "xenv": xml_dps,
            "xret": xml_nfse or (resultado.get("response") or None),
            "xpath": xml_path,
            "quem": quem[:120],
        },
    )
    await db.commit()
    return nfse_id


async def emitir(
    db: AsyncSession,
    *,
    empresa: str,
    tomador: dict[str, Any],
    servico: dict[str, Any],
    competencia: str | None = None,
    tipo_tributacao: str = "1",
    dry_run: bool = False,
    quem: str = "sistema",
) -> dict[str, Any]:
    """Emite UMA NFS-e: reserva número, transmite, guarda o XML e persiste a linha."""
    await _ensure(db)
    emp = await carregar_empresa(db, empresa)
    ambiente = str(emp["nfse_ambiente"]).strip().lower()
    tp_amb = tp_amb_de(ambiente)

    # A trava vem ANTES de reservar número: recusar depois queimaria um número da série
    # de produção sem nota nenhuma. (A mesma trava roda de novo lá embaixo, no manager,
    # para pegar também quem chamar o transmissor por fora daqui.)
    try:
        _exigir_ambiente_nfse(tp_amb, "Emissão de NFS-e")
    except NFSeAmbienteError as e:
        raise NFSeErro(str(e), code=e.code, details={"empresa": emp["slug"], "ambiente": ambiente}) from e

    if not re.sub(r"\D", "", str(tomador.get("cpf_cnpj") or "")):
        raise NFSeErro(
            "Tomador sem CPF/CNPJ — a DPS exige o documento de quem recebe o serviço.", code="TOMADOR_SEM_DOC"
        )
    if not str(servico.get("descricao") or "").strip():
        raise NFSeErro("Serviço sem descrição — é o `xDescServ` da nota.", code="SERVICO_SEM_DESCRICAO")
    if not (_num(servico.get("valor_servico")) or 0) > 0:
        raise NFSeErro("Valor do serviço tem de ser maior que zero.", code="VALOR_INVALIDO")

    from modules.government_integrations.services.nfse_nacional_service import get_nfse_nacional_service

    if dry_run:
        # Simulação não gasta número: ela não chega ao fisco e não vira documento. Mas
        # ESPIA a série e o próximo número e os mostra, porque sem isso a simulação
        # exibia `serie 900` e um nDPS de timestamp — os dois campos que mais erram
        # saíam certos no fisco e errados na prévia. Prévia que não mostra o que vai
        # ser enviado não é prévia.
        svc = get_nfse_nacional_service(emp["slug"])
        return {
            **svc.emitir_dps(
                tomador_data=tomador,
                servico_data=servico,
                competencia=competencia,
                tipo_tributacao=tipo_tributacao,
                dry_run=True,
                numero=str(await espiar_numero(db, emp["cnpj"], serie_da(emp), ambiente)),
                serie=serie_da(emp),
            ),
            "ambiente": ambiente,
            "empresa": emp["slug"],
            "gravou": False,
        }

    numero = await proximo_numero(db, emp["cnpj"], serie_da(emp), ambiente)
    await db.commit()  # o número é reservado ANTES de ir ao fisco: não se reusa.

    try:
        svc = get_nfse_nacional_service(emp["slug"])
        resultado = svc.emitir_dps(
            tomador_data=tomador,
            servico_data=servico,
            competencia=competencia,
            tipo_tributacao=tipo_tributacao,
            dry_run=False,
            numero=str(numero),
            serie=serie_da(emp),
        )
    except Exception as exc:
        # O número JÁ foi reservado. Sem esta linha ele some e vira buraco invisível na
        # numeração fiscal — foi o que a Z2 mediu na NF-e nº 3.
        await _gravar(
            db,
            emp=emp,
            ambiente=ambiente,
            numero=numero,
            tomador=tomador,
            servico=servico,
            competencia=competencia or "",
            resultado={"erro": f"{type(exc).__name__}: {exc}"},
            status="erro",
            quem=quem,
        )
        if isinstance(exc, NFSeAmbienteError):
            raise NFSeErro(str(exc), code=exc.code) from exc
        raise

    aceita = resultado.get("status") == "aceita" and bool(resultado.get("chave_acesso"))
    # «autorizada» só com prova: chave do órgão E o XML `<NFSe>` que ele assinou.
    # Sem isso é `sem_comprovacao` — que é o que as 27 linhas de 2026 sempre foram.
    status = "autorizada" if aceita and resultado.get("xml_nfse") else ("sem_comprovacao" if aceita else "rejeitada")
    nfse_id = await _gravar(
        db,
        emp=emp,
        ambiente=ambiente,
        numero=numero,
        tomador=tomador,
        servico=servico,
        competencia=competencia or "",
        resultado=resultado,
        status=status,
        quem=quem,
    )
    return {
        "id": nfse_id,
        "status": status,
        "empresa": emp["slug"],
        "cnpj": emp["cnpj"],
        "ambiente": ambiente,
        "serie": serie_da(emp),
        "numero": numero,
        "chave_acesso": resultado.get("chave_acesso"),
        "numero_nfse": resultado.get("numero_nfse"),
        "numero_dfe": resultado.get("numero_dfe"),
        "c_stat": resultado.get("c_stat"),
        "data_processamento": resultado.get("data_processamento"),
        "http_status": resultado.get("http_status"),
        "im_omitida_por_E0120": resultado.get("im_omitida_por_E0120", False),
        "mensagem": resultado.get("response") or resultado.get("erro"),
        # E0141 = «essa série+número já existe numa NFS-e anterior». Acontece quando o fisco
        # tem número que este contador não conhece — o caso de quem emitiu por fora antes de
        # existir persistência aqui. O número fica queimado (com linha e motivo) e o contador
        # já avançou, então a próxima tentativa pega o seguinte.
        # ponytail: uma tentativa por clique. Se houver muitos números queimados em sequência,
        # o remédio é semear `nfse_numeracao.ultimo` com o último número real — não um laço
        # que dispara N pedidos ao fisco.
        "dica": (
            f"O nº {numero} da série {serie_da(emp)} já existe no fisco (E0141). Ele fica registrado "
            f"como queimado e a próxima emissão usa o {numero + 1}."
            if "E0141" in str(resultado.get("response") or "")
            else None
        ),
        "gravou": True,
    }

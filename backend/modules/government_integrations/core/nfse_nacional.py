"""
Module: NFSeNacional
Description: Integração com o Sistema Nacional NFS-e (Padrão Nacional)
             Obrigatório para todos municípios a partir de 01/01/2026
             Lei Complementar 214/2025
Author: Conecta PRO
Date: 2026-01-17

Portal: https://www.nfse.gov.br
Documentação: https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica
Swagger: https://www.nfse.gov.br/swagger/contribuintesissqn/

Características:
- API REST (não mais SOAP)
- Autenticação mTLS com certificado ICP-Brasil
- XML assinado, compactado (GZip) e codificado (Base64)
- Respostas em JSON
- Número único nacional da NFS-e
"""

import base64
import gzip
import logging
import re
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


# O endereço do fisco. NÃO existe "host de homologação" com esse nome: o ambiente de teste do
# Padrão Nacional chama-se PRODUÇÃO RESTRITA e tem host PRÓPRIO — medido em 24/09/2026:
#   sefin.producaorestrita.nfse.gov.br → 189.9.67.145 · HTTPS válido · HTTP 403 sem certificado
#   sefin.nfse.gov.br                  → 189.9.84.43  · HTTPS válido · HTTP 403 sem certificado
# (403 sem certificado é o esperado: a autenticação é mTLS com A1 ICP-Brasil.)
# O `tpAmb` do XML e o HOST têm de concordar — um DPS com tpAmb=2 enviado ao host de produção
# é recusado, e o contrário seria nota real emitida sem querer. Quem escolhe é `url_para()`.
URL_PRODUCAO = "https://sefin.nfse.gov.br/sefinnacional"
URL_PRODUCAO_RESTRITA = "https://sefin.producaorestrita.nfse.gov.br/sefinnacional"


def url_para(ambiente: "AmbienteNacional | str") -> str:
    """Host do fisco para o ambiente pedido. Homologação = produção restrita, host próprio."""
    return URL_PRODUCAO if str(ambiente) == "producao" else URL_PRODUCAO_RESTRITA


class AmbienteNacional(StrEnum):
    """Ambientes do Padrão Nacional."""

    PRODUCAO = "producao"
    HOMOLOGACAO = "homologacao"


class TipoTributacao(StrEnum):
    """Tipos de tributação no Padrão Nacional."""

    TRIBUTACAO_MUNICIPIO = "1"
    TRIBUTACAO_FORA_MUNICIPIO = "2"
    ISENCAO = "3"
    IMUNE = "4"
    EXIGIBILIDADE_SUSPENSA_JUDICIAL = "5"
    EXIGIBILIDADE_SUSPENSA_ADM = "6"
    EXPORTACAO_SERVICO = "7"


class RegimeEspecial(StrEnum):
    """Regimes especiais de tributação."""

    SEM_REGIME = "0"
    MICROEMPRESA = "1"
    ESTIMATIVA = "2"
    SOCIEDADE_PROFISSIONAIS = "3"
    COOPERATIVA = "4"
    MEI = "5"
    ME_EPP_SIMPLES = "6"


@dataclass
class PrestadorNacional:
    """Dados do prestador no Padrão Nacional."""

    cnpj: str
    inscricao_municipal: str
    codigo_municipio: str  # Código IBGE
    razao_social: str
    nome_fantasia: str | None = None
    regime_especial: RegimeEspecial = RegimeEspecial.ME_EPP_SIMPLES
    optante_simples: bool = True


@dataclass
class TomadorNacional:
    """Dados do tomador no Padrão Nacional."""

    cpf_cnpj: str
    razao_social: str
    endereco: dict[str, str] = field(default_factory=dict)
    email: str | None = None
    telefone: str | None = None
    inscricao_municipal: str | None = None
    tipo_documento: str = "CNPJ"  # CPF ou CNPJ


@dataclass
class ServicoNacional:
    """Dados do serviço no Padrão Nacional."""

    codigo_tributacao_nacional: str  # Código do item da NBS ou LC 116
    descricao: str
    valor_servico: Decimal
    valor_deducao: Decimal = Decimal("0")
    valor_desconto_incondicionado: Decimal = Decimal("0")
    valor_desconto_condicionado: Decimal = Decimal("0")
    codigo_cnae: str | None = None
    #: cNBS — Nomenclatura Brasileira de Serviços. OPCIONAL no leiaute e sem fonte
    #: oficial neste repositório: o valor que estava CHUMBADO aqui ("120032900" =
    #: «instalação de maquinários») ia em TODA nota, inclusive nas de vigilância da
    #: Patrimonial — o fisco devolvia o xNBS errado, medido em 24/09/2026. Sem tabela
    #: NBS, a tag não vai. Número fiscal sem fonte não se inventa.
    codigo_nbs: str | None = None
    aliquota_iss: Decimal = Decimal("0.05")
    iss_retido: bool = False


@dataclass
class DPSNacional:
    """
    Declaração de Prestação de Serviços (DPS).

    No Padrão Nacional, o RPS foi substituído pela DPS.
    """

    # Identificação
    id_dps: str | None = None
    numero: str | None = None
    #: Série da DPS. Ficava CHUMBADA em dois lugares do montador («00900» no Id e
    #: <serie>900</serie> no XML) — e por isso trocar a série em `empresas` não mudava nada:
    #: o fisco continuava recebendo 900 e devolvendo E0014 (série+número já usados). Medido
    #: em 24/09/2026, quando produção tentou emitir com a série 901 e o `idDPS` da resposta
    #: ainda dizia `...00900...`. Quem emite escolhe a série; aqui ela só viaja.
    serie: str = "900"

    # Prestador
    prestador: PrestadorNacional | None = None

    # Tomador
    tomador: TomadorNacional | None = None

    # Serviço
    servico: ServicoNacional | None = None

    # Datas
    data_competencia: datetime = field(default_factory=datetime.now)

    # Tributação
    tipo_tributacao: TipoTributacao = TipoTributacao.TRIBUTACAO_MUNICIPIO

    # Valores calculados
    valor_liquido: Decimal | None = None
    valor_iss: Decimal | None = None

    def calcular_valores(self):
        """Calcula valores derivados."""
        if self.servico:
            base_calculo = (
                self.servico.valor_servico - self.servico.valor_deducao - self.servico.valor_desconto_incondicionado
            )
            self.valor_iss = base_calculo * self.servico.aliquota_iss

            self.valor_liquido = (
                self.servico.valor_servico
                - self.servico.valor_deducao
                - self.servico.valor_desconto_incondicionado
                - (self.valor_iss if self.servico.iss_retido else Decimal("0"))
            )


# ---------------------------------------------------------------------------
# A trava de produção — duas camadas + gate humano
#
# NFS-e autorizada em produção é documento fiscal IRREVERSÍVEL, com ISS devido ao
# município e obrigação acessória. O padrão é o mesmo que a frente Z2 usa na NF-e
# (`financial/integrations/nfe_provider._exigir_ambiente`), com gate PRÓPRIO: soltar
# a NF-e de mercadoria não pode soltar junto a nota de serviço.
#
#   camada 1 — `_exigir_ambiente_nfse()` no COMEÇO de toda emissão, antes de gastar
#              numeração ou tocar o certificado;
#   camada 2 — `_conferir_tp_amb()` relê o <tpAmb> do XML JÁ ASSINADO, imediatamente
#              antes do POST, e confere contra o host de destino.
#
# Env setada como "1"/"true" NÃO abre: só a frase-senha exata.
# ---------------------------------------------------------------------------

ENV_GATE_PRODUCAO_NFSE = "NFSE_PRODUCAO_LIBERADA"
_SENHA_GATE_NFSE = "sim-emitir-nfse-em-producao-com-iss-devido"


class NFSeAmbienteError(RuntimeError):
    """Pedido de transmissão recusado pela trava de ambiente. Nada foi transmitido."""

    def __init__(self, msg: str, code: str = "PRODUCAO_TRAVADA") -> None:
        super().__init__(msg)
        self.code = code


def producao_nfse_liberada() -> bool:
    """True só quando o dono destravou produção na env, com a frase exata."""
    import os as _os

    return _os.getenv(ENV_GATE_PRODUCAO_NFSE, "") == _SENHA_GATE_NFSE


def _exigir_ambiente_nfse(tp_amb: str, operacao: str = "Emissão de NFS-e") -> None:
    """Camada 1. Toda ida ao fisco passa por aqui."""
    if tp_amb == "2":
        return
    if tp_amb != "1":
        raise NFSeAmbienteError(
            f"Ambiente de NFS-e inválido: {tp_amb!r} (1=produção, 2=homologação/produção restrita)",
            code="AMBIENTE_INVALIDO",
        )
    if not producao_nfse_liberada():
        raise NFSeAmbienteError(
            f"{operacao} em PRODUÇÃO bloqueada. NFS-e autorizada em produção é documento "
            f"fiscal irreversível, com ISS devido ao município. Para liberar, defina a "
            f"variável de ambiente {ENV_GATE_PRODUCAO_NFSE} com o valor-senha combinado — "
            f"decisão humana, nunca automática."
        )


#: ⭐ CAMADA 3 (30/09/2026) — DISCRIMINAÇÃO DE TESTE NÃO VAI PARA PRODUÇÃO, NUNCA.
#: As camadas 1 e 2 perguntam «o ambiente está liberado?». Esta pergunta outra coisa:
#: «este DOCUMENTO é de teste?». São perguntas diferentes e a segunda faltava.
#:
#: Em 24/09/2026 saíram 7 notas com «FIXTURE DGX Z7 - PRODUCAO RESTRITA - SEM VALOR
#: FISCAL», «PROVA DE PRODUCAO EM HOMOLOGACAO» e «PROVA PELO ENDPOINT DE PRODUCAO».
#: Foram para a produção RESTRITA e ali não valem nada — mas bastava a frase-senha do
#: gate estar no ambiente para as MESMAS chamadas irem para a produção de verdade,
#: com ISS devido ao município e sem desfazer.
#:
#: Escrever «SEM VALOR FISCAL» no corpo da nota não retira o valor fiscal dela. Quem
#: escreve isso está dizendo que é ensaio — e ensaio não vai a produção.
_MARCAS_DE_TESTE = re.compile(
    r"(fixture|sem\s+valor\s+fiscal|produ[cç][aã]o\s+restrita|homologa[cç][aã]o"
    r"|teste|testes|prova|dgx|lixo|n[aã]o\s+usar)",
    re.IGNORECASE,
)


def _recusar_teste_em_producao(descricao: str | None, tp_amb: str, operacao: str) -> None:
    """Camada 3. Só olha o DOCUMENTO, e só morde em produção."""
    if tp_amb != "1":
        return
    achado = _MARCAS_DE_TESTE.search(str(descricao or ""))
    if not achado:
        return
    raise NFSeAmbienteError(
        f"{operacao} recusada: a discriminação contém {achado.group(0)!r}, que marca "
        f"documento de ENSAIO — e ensaio não vai para produção, onde a nota é "
        f"irreversível e o ISS é devido ao município. Escrever «sem valor fiscal» no "
        f"corpo não retira o valor fiscal da nota. Use tpAmb=2 (produção restrita) ou "
        f"escreva a discriminação real do serviço.",
        code="DISCRIMINACAO_DE_TESTE",
    )


def tp_amb_do_xml(xml: str | bytes) -> list[str]:
    """Os <tpAmb> do que REALMENTE vai no fio (com ou sem prefixo de namespace)."""
    bruto = xml.encode("utf-8") if isinstance(xml, str) else bytes(xml)
    return [m.decode() for m in re.findall(rb"<(?:\w+:)?tpAmb>(\d)</(?:\w+:)?tpAmb>", bruto)]


def _conferir_tp_amb(xml: str | bytes, tp_amb: str, url: str, operacao: str = "Emissão de NFS-e") -> None:
    """Camada 2. O ambiente é o que está no XML assinado e no HOST — não o que o config diz."""
    achados = set(tp_amb_do_xml(xml))
    if not achados:
        raise NFSeAmbienteError(f"{operacao}: XML sem <tpAmb> — recuso transmitir às cegas.", code="TPAMB_AUSENTE")
    if achados != {tp_amb}:
        raise NFSeAmbienteError(
            f"{operacao}: tpAmb do XML {sorted(achados)} difere do ambiente pedido ({tp_amb}). Nada foi transmitido.",
            code="TPAMB_DIVERGENTE",
        )
    # A URL de destino tem CAMINHO — `/nfse`, `/nfse/{chave}/eventos` — e comparar a URL
    # inteira com a base nunca dá igual. Medido em 26/09/2026: com `==`, TODA operação de
    # produção era recusada aqui com «o host não corresponde ao tpAmb=1», mesmo com o gate
    # humano aberto e o XML correto. Ninguém tinha notado porque nenhuma NFS-e havia sido
    # emitida em produção — os contadores de produção estão em 0 desde que nasceram.
    #
    # O teste certo é o HOST, e `startswith` sobre a base resolve sem falso positivo: a
    # produção restrita mora em `sefin.producaorestrita.nfse.gov.br`, que não começa por
    # `sefin.nfse.gov.br`.
    em_producao = url.startswith(URL_PRODUCAO)
    if em_producao != (tp_amb == "1"):
        raise NFSeAmbienteError(
            f"{operacao}: o host ({url}) não corresponde ao tpAmb={tp_amb} do XML. Nada foi transmitido.",
            code="HOST_DIVERGENTE",
        )
    if achados == {"1"} and not producao_nfse_liberada():
        raise NFSeAmbienteError(f"{operacao}: XML em PRODUÇÃO sem o gate humano. Nada foi transmitido.")


def _erro_do_fisco(resp: Any) -> dict[str, Any] | None:
    """O bloco `erro` que o Padrão Nacional devolve em JSON, ou `None`.

    `None` significa «não foi o fisco que respondeu isso» — página de erro do servidor
    web, proxy, qualquer coisa. Distinguir os dois é o que impede a conciliação de fechar
    um número fiscal com base num 404 de rota errada. Ver `_get`.
    """
    import json as _json

    if "json" not in str(resp.headers.get("content-type", "")).lower():
        return None
    try:
        dado = _json.loads(resp.text)
    except Exception:  # noqa: BLE001
        return None
    erro = dado.get("erro") if isinstance(dado, dict) else None
    if isinstance(erro, dict) and erro.get("codigo"):
        return erro
    # alguns retornos trazem uma lista de erros
    if isinstance(erro, list) and erro and isinstance(erro[0], dict) and erro[0].get("codigo"):
        return erro[0]
    return None


def _ler_retorno_nfse(corpo: str) -> dict[str, Any]:
    """Lê o que o fisco devolveu no 201: chave, NFS-e assinada e os números DELE.

    O Padrão Nacional não tem "protocolo de autorização" como a NF-e. O que prova a
    nota é o conjunto `chaveAcesso` + o XML `<NFSe>` assinado pelo próprio fisco, que
    traz `cStat`, `nNFSe` (número da nota no município) e `nDFSe` (sequencial nacional
    do documento). Medido em 24/09/2026 contra a produção restrita: HTTP 201 devolve
    `{tipoAmbiente, versaoAplicativo, dataHoraProcessamento, chaveAcesso, nfseXmlGZipB64}`.

    Devolve só o que ACHOU. Campo ausente não vira zero nem string vazia — some.
    """
    import json as _json

    fora: dict[str, Any] = {}
    try:
        dado = _json.loads(corpo)
    except Exception:  # noqa: BLE001 — corpo que não é JSON não derruba a emissão
        return fora
    if not isinstance(dado, dict):
        return fora
    if dado.get("chaveAcesso"):
        fora["chave_acesso"] = str(dado["chaveAcesso"])
    if dado.get("dataHoraProcessamento"):
        fora["data_hora_processamento"] = str(dado["dataHoraProcessamento"])
    if dado.get("tipoAmbiente") is not None:
        fora["tp_amb_retorno"] = str(dado["tipoAmbiente"])
    b64 = dado.get("nfseXmlGZipB64")
    if not b64:
        return fora
    try:
        xml = gzip.decompress(base64.b64decode(b64)).decode("utf-8")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"NFS-e: retorno com nfseXmlGZipB64 ilegível ({e})")
        return fora
    fora["xml_nfse"] = xml
    for tag, chave in (
        ("cStat", "c_stat"),
        ("nNFSe", "numero_nfse"),
        ("nDFSe", "numero_dfe"),
        ("dhProc", "data_processamento"),
        ("ambGer", "amb_ger"),
        ("vISSQN", "valor_iss_fisco"),
        ("pAliqAplic", "aliquota_iss_fisco"),
        ("vBC", "base_calculo_fisco"),
        ("vLiq", "valor_liquido_fisco"),
        # vServ é o valor BRUTO do serviço. Faltava aqui, e a conciliação acabava gravando
        # `vLiq` no campo do bruto: em nota com retenção da Lei 9.711 (11%) os dois diferem,
        # e é o bruto que é receita. Medido em 27/09/2026: 28 de 34 notas da Patrimonial
        # ficaram com valor_servicos == valor_liquido. Receita menor vira RBT12 menor, que
        # vira faixa menor do Simples, que vira DAS menor — o erro anda até o imposto.
        ("vServ", "valor_bruto_fisco"),
    ):
        m = re.search(rf"<(?:\w+:)?{tag}>([^<]+)</(?:\w+:)?{tag}>", xml)
        if m:
            fora[chave] = m.group(1)
    return fora


def chave_dps(cnpj: str, serie: str, numero: int | str, cod_municipio: str = "1302603") -> str:
    """Chave da DPS: cMun(7) + tpInsc(1) + nrInsc(14) + serie(5) + nDPS(15) = 42 dígitos.

    É a ÚNICA chave que se pode construir. A chave da NFS-e (50 dígitos) carrega um
    código numérico de 8 dígitos sorteado pelo fisco — medido em 24/09/2026 nos DANFSe
    das duas empresas: `…260896878833` (nota 29) e `…260894006421 00` (nota 116), sem
    relação com o número da nota. Por isso a conciliação varre DPS, não NFS-e.

    tpInsc: 1 = CPF, 2 = CNPJ. Prestador é CNPJ → 2.
    """
    doc = re.sub(r"\D", "", str(cnpj))
    return f"{str(cod_municipio)[:7]}2{doc:0>14}{re.sub(r'\D', '', str(serie)):0>5}{int(numero):015d}"


@contextmanager
def _certificado_pem(caminho: str | None, senha: str | None):
    """Exporta o .pfx para o par PEM que o mTLS exige e apaga os arquivos ao sair.

    `emitir_dps` tem a sua própria cópia desta dança e continua com ela: deduplicar o
    único caminho de emissão fiscal provado não valia o risco nesta frente.
    NUNCA loga a senha — nem em erro.
    """
    from .certificate_manager import CertificateManager

    cert_mgr = CertificateManager(pfx_path=caminho, password=senha)
    cert_mgr.load()
    tmp_cert = tempfile.NamedTemporaryFile(delete=False, suffix=".pem", mode="wb")  # noqa: SIM115
    tmp_key = tempfile.NamedTemporaryFile(delete=False, suffix=".pem", mode="wb")  # noqa: SIM115
    try:
        tmp_cert.write(cert_mgr.get_certificate_pem())
        tmp_cert.close()
        tmp_key.write(cert_mgr.get_private_key_pem())
        tmp_key.close()
        yield (tmp_cert.name, tmp_key.name)
    finally:
        import os as _os

        for _p in (tmp_cert.name, tmp_key.name):
            try:
                _os.unlink(_p)
            except Exception:  # noqa: BLE001
                pass


class NFSeNacionalManager:
    """
    Gerenciador de NFS-e Padrão Nacional (Preparação).

    IMPORTANTE: Esta classe está em preparação para a migração.
    O Padrão Nacional ainda não está disponível em Manaus.

    Quando a migração for realizada, este manager substituirá
    o NFSeManausManager para novas emissões.

    Hosts em `url_para()` — produção e produção restrita são endereços DIFERENTES.
    """

    URL_API = URL_PRODUCAO  # compatibilidade com quem já lia a constante da classe

    ENDPOINTS = {
        "emitir_dps": "/nfse",
        "consultar_nfse": "/nfse/{chave}",
        # MEDIDO em 24/09/2026 contra a produção restrita — o valor anterior aqui era
        # "/nfse/DPS/{chave}" e devolve 404 **com página HTML do IIS**, porque a rota não
        # existe. Ninguém tinha notado: o dicionário estava declarado e nenhum método o
        # usava. O caminho certo é `/dps/{id}`, minúsculo e sem o prefixo `/nfse`.
        "consultar_dps": "/dps/{chave}",
        # `/nfse/DANFSe/{chave}` estava declarado aqui e NÃO é rota: medido em 25/09/2026
        # contra a produção, devolve 404 `text/html` com a página do IIS (o «404 que mente»
        # descrito em `_get`). O fisco não serve o PDF do DANFSe por API — serve o XML por
        # `/nfse/{chave}`, e o PDF é desenhado em `gedeon/services/nfse_danfse_generator.py`.
        # Nenhum método usava a entrada; ficou só a lição.
        "eventos": "/nfse/{chave}/eventos",
    }

    def __init__(
        self,
        ambiente: AmbienteNacional = AmbienteNacional.HOMOLOGACAO,
        cnpj: str = "",
        certificado_path: str | None = None,
        certificado_senha: str | None = None,
    ):
        """
        Inicializa o manager.

        Args:
            ambiente: Ambiente (produção ou homologação)
            cnpj: CNPJ do prestador
            certificado_path: Caminho para certificado A1
            certificado_senha: Senha do certificado
        """
        self.ambiente = ambiente
        self.cnpj = cnpj
        self.certificado_path = certificado_path
        self.certificado_senha = certificado_senha

        # Homologação nacional = "produção restrita", host PRÓPRIO (ver `url_para`).
        self.url_base = url_para(ambiente)
        self.tp_amb = "1" if ambiente == AmbienteNacional.PRODUCAO else "2"

        logger.info(f"NFSe Nacional Manager inicializado - Ambiente: {ambiente.value}, URL: {self.url_base}")

    def _build_dps_xml(self, dps: DPSNacional) -> str:
        """Constrói XML DPS conforme schema nacional."""
        import re as _re
        from datetime import datetime as _dt

        dps.calcular_valores()
        tp_amb = "1" if getattr(self, "ambiente", None) == AmbienteNacional.PRODUCAO else "2"
        cnpj_clean = _re.sub(r"\D", "", self.cnpj)
        tomador_doc = _re.sub(r"\D", "", dps.tomador.cpf_cnpj) if dps.tomador else ""
        # IM do prestador. SEM fallback: o valor fixo que estava aqui era a inscrição
        # municipal da Eletrônica — qualquer outra empresa sem IM emitia com a IM dela.
        # Vazio => a tag <IM> não vai no XML (o CNC do município pode não ter cadastro
        # complementar; nesse caso o fisco devolve E0120 exigindo a ausência da tag).
        im = (dps.prestador.inscricao_municipal or "").strip() if dps.prestador else ""
        tag_im = f"\n      <IM>{im}</IM>" if im else ""
        # cTribNac: 6 dígitos (2 Item + 2 Subitem + 2 Desdobro LC 116/2003)
        raw_trib = _re.sub(r"\D", "", dps.servico.codigo_tributacao_nacional) if dps.servico else "140601"
        cod_trib = raw_trib[:6] if len(raw_trib) >= 6 else raw_trib.ljust(6, "0")
        valor = f"{dps.servico.valor_servico:.2f}" if dps.servico else "0.00"
        _aliquota = f"{dps.servico.aliquota_iss * 100:.2f}" if dps.servico else "5.00"  # noqa: F841
        _valor_iss = f"{dps.valor_iss:.2f}" if dps.valor_iss else "0.00"  # noqa: F841
        descricao = dps.servico.descricao if dps.servico else "Prestação de serviços"
        nbs = _re.sub(r"\D", "", (dps.servico.codigo_nbs or "")) if dps.servico else ""
        tag_nbs = f"\n        <cNBS>{nbs}</cNBS>" if nbs else ""
        competencia = (
            dps.data_competencia.strftime("%Y-%m-%d") if dps.data_competencia else _dt.now().strftime("%Y-%m-%d")
        )

        # Id do infDPS: cMun(7) + tpInsc(1) + nrInsc(14) + serie(5) + nDPS(15) = 42 chars
        # tpInsc: 1=CPF, 2=CNPJ (prestador é CNPJ → 2)
        serie_pad = _re.sub(r"\D", "", str(dps.serie or "900"))[:5].zfill(5)  # 5 dígitos, da DPS
        ndps_pad = f"{int(dps.numero or '1'):015d}"  # nDPS com 15 dígitos
        dps_id = f"DPS13026032{cnpj_clean}{serie_pad}{ndps_pad}"

        # opSimpNac: 1=Não optante (Lucro Real/Presumido), 2=MEI, 3=ME/EPP Simples
        _optante = bool(dps.prestador and dps.prestador.optante_simples)
        op_simp = "3" if _optante else "1"
        # regApTribSN é OBRIGATÓRIO para ME/EPP do Simples (E0166) e PROIBIDO fora dele.
        # 1 = tributos federais E o ISSQN apurados pelo próprio Simples — que é o caso da
        # Patrimonial. (2 = ISS fixo por fora; 3 = ISS por fora pela LC 116.)
        tag_reg_ap = "\n        <regApTribSN>1</regApTribSN>" if op_simp == "3" else ""
        # totTrib: optante usa pTotTribSN (% Simples); não optante usa vTotTrib (valores R$,
        # Lei 12.741 transparência fiscal) — indTotTrib/pTotTribSN proibidos p/ não optante (E0713)
        tot_trib = (
            "<pTotTribSN>0.00</pTotTribSN>"
            if _optante
            else "<vTotTrib><vTotTribFed>0.00</vTotTribFed>"
            "<vTotTribEst>0.00</vTotTribEst><vTotTribMun>0.00</vTotTribMun></vTotTrib>"
        )

        # Ordem EXATA do XSD TCInfDPS (tiposComplexos_v1.00.xsd):
        # tpAmb → dhEmi → verAplic → serie → nDPS → dCompet → tpEmit → cLocEmi →
        # [subst] → prest → [toma] → [interm] → serv → valores
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<DPS xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.00">
  <infDPS Id="{dps_id}">
    <tpAmb>{tp_amb}</tpAmb>
    <dhEmi>{(_dt.now() - __import__("datetime").timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%S")}-03:00</dhEmi>
    <verAplic>ConectaPRO-2.0</verAplic>
    <serie>{_re.sub(r"[^0-9]", "", str(dps.serie or "900")) or "900"}</serie>
    <nDPS>{dps.numero or "1"}</nDPS>
    <dCompet>{competencia}</dCompet>
    <tpEmit>1</tpEmit>
    <cLocEmi>1302603</cLocEmi>
    <prest>
      <CNPJ>{cnpj_clean}</CNPJ>{tag_im}
      <regTrib>
        <opSimpNac>{op_simp}</opSimpNac>{tag_reg_ap}
        <regEspTrib>0</regEspTrib>
      </regTrib>
    </prest>
    <toma>
      <CNPJ>{tomador_doc}</CNPJ>
      <xNome>{dps.tomador.razao_social if dps.tomador else "TOMADOR"}</xNome>
    </toma>
    <serv>
      <locPrest>
        <cLocPrestacao>1302603</cLocPrestacao>
      </locPrest>
      <cServ>
        <cTribNac>{cod_trib}</cTribNac>
        <cTribMun>100</cTribMun>
        <xDescServ>{descricao}</xDescServ>{tag_nbs}
      </cServ>
    </serv>
    <valores>
      <vServPrest>
        <vServ>{valor}</vServ>
      </vServPrest>
      <trib>
        <tribMun>
          <tribISSQN>1</tribISSQN>
          <tpRetISSQN>1</tpRetISSQN>
        </tribMun>
        <totTrib>
          {tot_trib}
        </totTrib>
      </trib>
    </valores>
  </infDPS>
</DPS>"""
        return xml

    def emitir_dps(self, dps: DPSNacional, dry_run: bool = False, _sem_im: bool = False) -> dict[str, Any]:
        """
        Emite DPS (Declaração de Prestação de Serviços) via API Nacional.

        Fluxo: XML DPS → Assinar XMLDSig → GZip → Base64 → POST mTLS

        Args:
            dps: Dados da DPS
            dry_run: Se True, gera XML sem transmitir

        Returns:
            Dict com resultado da emissão
        """
        import base64
        import gzip

        import requests

        # Camada 1 da trava: ANTES de montar, assinar ou reservar qualquer coisa.
        # Vale para TODO chamador deste manager — não só para o emissor da Z7.
        _exigir_ambiente_nfse(self.tp_amb, "Emissão de NFS-e")
        # Camada 3: o gate libera o AMBIENTE; esta linha olha o DOCUMENTO. Com a
        # frase-senha no ambiente, as 7 notas de ensaio de 24/09 teriam ido para a
        # produção de verdade — as camadas 1 e 2 não fazem esta pergunta.
        _recusar_teste_em_producao(
            getattr(getattr(dps, "servico", None), "descricao", None), self.tp_amb, "Emissão de NFS-e"
        )

        # 1. Construir XML
        if _sem_im and dps.prestador:
            dps.prestador.inscricao_municipal = ""
        xml_dps = self._build_dps_xml(dps)

        result = {
            "xml_gerado": True,
            "xml_tamanho": len(xml_dps),
            "ambiente": self.ambiente.value,
        }

        if dry_run:
            result["xml_preview"] = xml_dps[:800]
            result["status"] = "dry_run"
            result["fonte"] = "xml_gerado_localmente"
            return result

        # 2. Assinar XML com certificado A1
        try:
            from .certificate_manager import CertificateManager
            from .xml_signer import NFSeNacionalXMLSigner

            cert_mgr = CertificateManager(
                pfx_path=self.certificado_path,
                password=self.certificado_senha,
            )
            cert_mgr.load()
            # NFSeNacionalXMLSigner gera <Signature> sem prefixo ds: (resolve E6155)
            signer = NFSeNacionalXMLSigner(cert_mgr)
            xml_assinado = signer.sign_nfse(xml_dps)
            result["xml_assinado"] = True
            # O XML que REALMENTE vai no fio. Sem ele, quem persiste a nota guarda o
            # rascunho sem assinatura — e o que vale legalmente é o assinado.
            result["xml_dps_assinado"] = xml_assinado
        except Exception as e:
            logger.error(f"Erro assinando DPS: {e}")
            result["status"] = "erro_assinatura"
            result["erro"] = str(e)
            return result

        # 3. GZip + Base64
        xml_gzipped = gzip.compress(xml_assinado.encode("utf-8"))
        xml_b64 = base64.b64encode(xml_gzipped).decode("ascii")

        # 4. POST para API Nacional com mTLS
        url = f"{self.url_base}/nfse"

        # Exportar certificado .pfx para PEM temporários (mTLS)
        from .certificate_manager import CertificateManager

        tmp_cert_path = None
        tmp_key_path = None
        try:
            cert_mgr = CertificateManager(pfx_path=self.certificado_path, password=self.certificado_senha)
            cert_mgr.load()

            with tempfile.NamedTemporaryFile(delete=False, suffix=".pem", mode="wb") as tmp_cert:
                tmp_cert.write(cert_mgr.get_certificate_pem())
                tmp_cert_path = tmp_cert.name

            with tempfile.NamedTemporaryFile(delete=False, suffix=".pem", mode="wb") as tmp_key:
                tmp_key.write(cert_mgr.get_private_key_pem())
                tmp_key_path = tmp_key.name

            # Camada 2 da trava: o ambiente é o que está no XML ASSINADO e no host de
            # destino, não o que o config disse lá atrás.
            _conferir_tp_amb(xml_assinado, self.tp_amb, url, "Emissão de NFS-e")

            resp = requests.post(
                url,
                json={"dpsXmlGZipB64": xml_b64},
                cert=(tmp_cert_path, tmp_key_path),
                timeout=30,
                verify=True,
            )

            result["http_status"] = resp.status_code
            result["response"] = resp.text[:1000]
            result["url"] = url

            if resp.status_code in (200, 201):
                result["status"] = "aceita"
                result.update(_ler_retorno_nfse(resp.text))
            elif resp.status_code == 400:
                result["status"] = "rejeitada"
            else:
                result["status"] = f"http_{resp.status_code}"

            logger.info(f"NFS-e Nacional: HTTP {resp.status_code} — {resp.text[:200]}")

        except NFSeAmbienteError:
            # A trava recusou. Não vira "erro_transmissao" genérico: sobe como recusa,
            # senão a tela diz «erro» onde deveria dizer «bloqueado de propósito».
            raise
        except Exception as e:
            logger.error(f"Erro transmitindo DPS: {e}")
            result["status"] = "erro_transmissao"
            result["erro"] = str(e)
        finally:
            import os as _os

            for _p in (tmp_cert_path, tmp_key_path):
                if _p:
                    try:
                        _os.unlink(_p)
                    except Exception:
                        pass

        # E0120: "IM do prestador não deve ser informado, pois não existem informações
        # complementares registradas no CNC NFS-e do município emissor". É o caso da
        # Patrimonial em Manaus hoje — a Eletrônica está no CNC e a Patrimonial não.
        # Nada foi emitido (HTTP 400), então repetir é seguro; repete UMA vez sem a <IM>.
        # No dia em que a prefeitura cadastrar a empresa no CNC, a 1ª tentativa passa e
        # esta não roda mais — por isso é retentativa e não uma flag para alguém manter.
        if (
            not _sem_im
            and result.get("status") == "rejeitada"
            and "E0120" in str(result.get("response", ""))
            and dps.prestador
            and (dps.prestador.inscricao_municipal or "").strip()
        ):
            logger.info("NFS-e Nacional: E0120 — reenviando sem a IM do prestador (ordem do fisco)")
            segunda = self.emitir_dps(dps, dry_run=False, _sem_im=True)
            segunda["im_omitida_por_E0120"] = True
            return segunda

        return result

    def cancelar_nfse(
        self,
        chave: str,
        motivo: str,
        cod_motivo: str = "1",
        n_pedido: int = 1,
        dry_run: bool = False,
        tipo_evento: str = "101101",
        descricao: str = "Cancelamento de NFS-e",
    ) -> dict[str, Any]:
        """Pede o CANCELAMENTO de uma NFS-e ao Ambiente Nacional (evento e101101).

        Nasceu em 26/09/2026. O endpoint `/nfse/{chave}/eventos` estava DECLARADO em
        `ENDPOINTS` desde sempre e **nenhum método o usava** — o sistema registrava o pedido
        em `nfse_emitidas_nacional.cancelamento_solicitado_em` e ficava esperando que alguém
        cancelasse no portal; o sync depois descobria o evento e marcava a nota. Não havia
        caminho para cancelar.

        `cod_motivo` — MEDIDO contra a produção em 26/09/2026, sondando o esquema com uma
        chave estruturalmente válida e inexistente. O tipo `TSCodJustCanc` aceita **1, 2 e
        9, e só**:

            1 = erro na emissão   ·   2 = serviço não prestado   ·   9 = outros

        A tabela que estava escrita aqui («3=erro de assinatura, 4=duplicidade, para
        duplicata use 4») veio de analogia com outro leiaute e o fisco recusa com E1235,
        «The Enumeration constraint failed». Para nota em duplicidade, **1** é o código:
        emitir duas vezes é erro na emissão. O `xMotivo` tem comprimento MÍNIMO — texto
        curto também é recusado por esquema.

        MESMO FLUXO DA EMISSÃO, e de propósito: XML → assina XMLDSig → GZip → Base64 →
        POST mTLS. Passa pelas DUAS camadas da trava de ambiente — cancelar é tão
        irreversível quanto emitir, e em produção precisa do mesmo destravamento humano.

        O fisco é o juiz do PRAZO. Se a competência já fechou, ele recusa — e a recusa não
        estraga nada, é informação. Nada aqui tenta adivinhar o prazo do município.
        """
        import base64
        import gzip
        import tempfile

        import requests

        _exigir_ambiente_nfse(self.tp_amb, "Cancelamento de NFS-e")

        chave_limpa = re.sub(r"\D", "", chave or "")
        if len(chave_limpa) != 50:
            return {
                "status": "erro_chave",
                "erro": f"Chave de acesso deve ter 50 dígitos; recebi {len(chave_limpa)}.",
            }
        cnpj_limpo = re.sub(r"\D", "", self.cnpj or "")
        xml_evento = self._build_evento_cancelamento_xml(
            chave_limpa,
            cnpj_limpo,
            motivo,
            cod_motivo,
            n_pedido,
            tipo_evento=tipo_evento,
            descricao=descricao,
        )

        result: dict[str, Any] = {
            "chave": chave_limpa,
            "tipo_evento": tipo_evento,
            "cod_motivo": cod_motivo,
            "motivo": motivo,
            "ambiente": self.ambiente.value,
            "xml_tamanho": len(xml_evento),
        }
        if dry_run:
            result["status"] = "dry_run"
            result["xml_preview"] = xml_evento
            return result

        try:
            from .certificate_manager import CertificateManager
            from .xml_signer import NFSeNacionalXMLSigner

            cert_mgr = CertificateManager(pfx_path=self.certificado_path, password=self.certificado_senha)
            cert_mgr.load()
            xml_assinado = NFSeNacionalXMLSigner(cert_mgr).sign_nfse(xml_evento)
            result["xml_assinado"] = True
            result["xml_evento_assinado"] = xml_assinado
        except Exception as e:  # noqa: BLE001
            logger.error("Erro assinando evento de cancelamento: %s", e)
            return {**result, "status": "erro_assinatura", "erro": str(e)}

        xml_b64 = base64.b64encode(gzip.compress(xml_assinado.encode("utf-8"))).decode("ascii")
        url = f"{self.url_base}/nfse/{chave_limpa}/eventos"

        tmp_cert_path = tmp_key_path = None
        try:
            cert_mgr = CertificateManager(pfx_path=self.certificado_path, password=self.certificado_senha)
            cert_mgr.load()
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pem", mode="wb") as f:
                f.write(cert_mgr.get_certificate_pem())
                tmp_cert_path = f.name
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pem", mode="wb") as f:
                f.write(cert_mgr.get_private_key_pem())
                tmp_key_path = f.name

            _conferir_tp_amb(xml_assinado, self.tp_amb, url, "Cancelamento de NFS-e")

            resp = requests.post(
                url,
                json={"pedidoRegistroEventoXmlGZipB64": xml_b64},
                cert=(tmp_cert_path, tmp_key_path),
                timeout=30,
                verify=True,
            )
            result["http_status"] = resp.status_code
            result["response"] = resp.text[:1200]
            result["url"] = url
            if resp.status_code in (200, 201):
                result["status"] = "cancelada"
            elif resp.status_code == 400:
                result["status"] = "rejeitada"
            else:
                result["status"] = f"http_{resp.status_code}"
            logger.info("Cancelamento NFS-e %s: HTTP %s — %s", chave_limpa, resp.status_code, resp.text[:200])
        except NFSeAmbienteError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.error("Erro transmitindo cancelamento: %s", e)
            result["status"] = "erro_transmissao"
            result["erro"] = str(e)
        finally:
            import os as _os

            for _p in (tmp_cert_path, tmp_key_path):
                if _p:
                    try:
                        _os.unlink(_p)
                    except Exception:  # noqa: BLE001
                        pass
        return result

    def solicitar_analise_fiscal_cancelamento(
        self, chave: str, motivo: str, cod_motivo: str = "1", dry_run: bool = False
    ) -> dict[str, Any]:
        """RECUSA: o esquema do e105102 não está conhecido, e sondar o fisco não é método.

        Passado o prazo do município, o cancelamento deixa de ser ato do contribuinte e
        vira **Solicitação de Análise Fiscal (evento e105102)**. Foi o fisco que disse
        isso, em 26/09/2026, nas três duplicatas provadas:

            GELAIN 115 (07/2026) e PRIME ARENA 100 (06/2026)
                E0822 — «O prazo para o cancelamento da NFS-e expirou, conforme
                parametrização do município emissor da NFS-e.»
            LARANJEIRAS 3 (06/2026)
                E0840 — «o evento de Solicitação de Análise Fiscal para Cancelamento já
                está vinculado à NFS-e» — ou seja, o pedido dela JÁ FOI ABERTO.

        Tentei montar o e105102 reaproveitando o corpo do e101101
        (`xDesc` + `cMotivo` + `xMotivo`) e o fisco recusou com E1235: o `xDesc` tem
        ENUMERAÇÃO própria, e nenhum dos cinco textos plausíveis passou — inclusive
        «Cancelamento de NFS-e», que é o valor aceito dentro do e101101. Ou seja: o corpo
        do e105102 não é o mesmo, e descobrir a diferença por tentativa contra um
        endpoint de governo não é método. **Falta o XSD do evento.**

        Enquanto ele não estiver aqui, o caminho é o portal do município — e este método
        levanta com o texto acima em vez de deixar alguém repetir a sondagem.
        """
        raise NotImplementedError(
            "Solicitação de Análise Fiscal (e105102) não implementada: o esquema do "
            "evento não é o do cancelamento e o XSD não está no repositório. Medido em "
            "26/09/2026 — cinco variações de `xDesc` recusadas com E1235. Fora do prazo "
            "(E0822) o cancelamento é pedido ao município, hoje pelo portal."
        )

    def _build_evento_cancelamento_xml(
        self,
        chave: str,
        cnpj_autor: str,
        motivo: str,
        cod_motivo: str,
        n_pedido: int = 1,
        tipo_evento: str = "101101",
        descricao: str = "Cancelamento de NFS-e",
    ) -> str:
        """XML do pedido de registro de evento (e101101 cancelamento, e105102 análise fiscal).

        O schema deste evento **não tem `nPedRegEvento`**. Ele existe no leiaute de outros
        eventos e eu o coloquei aqui por analogia — o fisco devolveu «has invalid child
        element 'nPedRegEvento'». `n_pedido` fica na assinatura só para quem chamava antes
        não quebrar; não entra no XML.

        A ordem das tags segue o leiaute, e XML de evento fora de ordem é rejeitado do
        mesmo jeito que DPS fora de ordem. Provado por transmissão real em homologação:
        HTTP 201 com este formato, HTTP 400 com os quatro anteriores.
        """
        from datetime import datetime as _dt

        tp_amb = "1" if self.ambiente == AmbienteNacional.PRODUCAO else "2"
        # Id do evento: "PRE" + chave(50) + tipo(6) = 59 caracteres. SEM sufixo de
        # sequência — MEDIDO contra a produção restrita em 26/09/2026, deixando o fisco
        # dizer o formato: com 3 dígitos de sequência (62), com 2 (61), com 1 (60) e com
        # o "e" do nome do evento (63), todos devolvem E1235 «The Pattern constraint
        # failed» no datatype TSIdPedRegEvt. Com 59, passa.
        id_evento = f"PRE{chave}{tipo_evento}"
        agora = _dt.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")
        dh = f"{agora[:-2]}:{agora[-2:]}" if len(agora) > 5 else agora
        texto = (motivo or "Cancelamento de NFS-e").strip()[:255]
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<pedRegEvento xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.00">
  <infPedReg Id="{id_evento}">
    <tpAmb>{tp_amb}</tpAmb>
    <verAplic>ConectaPRO-2.0</verAplic>
    <dhEvento>{dh}</dhEvento>
    <CNPJAutor>{cnpj_autor}</CNPJAutor>
    <chNFSe>{chave}</chNFSe>
    <e{tipo_evento}>
      <xDesc>{descricao}</xDesc>
      <cMotivo>{cod_motivo}</cMotivo>
      <xMotivo>{texto}</xMotivo>
    </e{tipo_evento}>
  </infPedReg>
</pedRegEvento>"""

    def _get(self, caminho: str, operacao: str) -> dict[str, Any]:
        """GET mTLS no host do ambiente. Leitura pura: não cria, não altera, não numera.

        A trava de produção NÃO roda aqui de propósito: ela existe para impedir que saia
        documento fiscal irreversível, e consultar não emite nada. Conciliar a produção
        exige justamente ler a produção. O que a trava garante continua garantido —
        `emitir_dps` é o único caminho que grava no fisco.
        """
        import requests

        url = f"{self.url_base}{caminho}"
        fora: dict[str, Any] = {"url": url, "ambiente": self.ambiente.value, "operacao": operacao}
        if not self.certificado_path:
            fora["status"] = "sem_certificado"
            fora["erro"] = "Consulta ao fisco exige certificado A1 (mTLS) — nenhum configurado para este CNPJ."
            return fora
        try:
            with _certificado_pem(self.certificado_path, self.certificado_senha) as pem:
                resp = requests.get(url, cert=pem, timeout=30, verify=True)
        except Exception as e:  # noqa: BLE001 — senha NUNCA entra na mensagem
            fora["status"] = "erro_rede"
            fora["erro"] = f"{type(e).__name__}: {e}"
            return fora
        fora["http_status"] = resp.status_code
        fora["response"] = resp.text[:1000]
        if resp.status_code == 200:
            fora["status"] = "encontrada"
            fora.update(_ler_retorno_nfse(resp.text))
            return fora

        # ── O 404 que MENTE ──────────────────────────────────────────────────────────
        # Medido em 24/09/2026: o fisco devolve 404 em DOIS casos muito diferentes.
        #
        #   caminho errado   → 404 text/html, página do IIS «The resource cannot be found»
        #   não existe mesmo → 404 application/json, {"erro": {"codigo": "E2404",
        #                      "descricao": "Não foi gerada uma NFS-e com o identificador
        #                      de DPS informado"}}
        #
        # Ler o primeiro como «o fisco disse que não existe» é o pior erro possível nesta
        # rotina: ela fecharia as 37 notas ausentes como inexistentes, com a tela verde, e
        # o dinheiro ficaria perdido com aparência de conferido. Foi o que aconteceu na
        # primeira medição desta frente, com `/nfse/DPS/{chave}` — que não é rota.
        #
        # Então: **só o código de erro do próprio fisco fecha um número.**
        erro = _erro_do_fisco(resp)
        if resp.status_code == 404 and erro:
            fora["status"] = "inexistente"
            fora["codigo_erro"] = erro.get("codigo")
            fora["descricao_erro"] = erro.get("descricao")
        elif resp.status_code == 404:
            fora["status"] = "caminho_invalido"
            fora["erro"] = (
                f"HTTP 404 sem corpo de erro do fisco em {url} — isto é rota inexistente, "
                "NÃO «documento não existe». Nada foi concluído sobre este número."
            )
        else:
            fora["status"] = f"http_{resp.status_code}"
            if erro:
                fora["codigo_erro"] = erro.get("codigo")
                fora["descricao_erro"] = erro.get("descricao")
        return fora

    def consultar_nfse(self, chave_acesso: str) -> dict[str, Any]:
        """`GET /nfse/{chave}` — a NFS-e que o fisco tem, pela chave de 50 dígitos."""
        chave = re.sub(r"\D", "", str(chave_acesso or ""))
        if len(chave) != 50:
            return {"status": "chave_invalida", "erro": f"Chave da NFS-e tem 50 dígitos; recebi {len(chave)}."}
        return self._get(self.ENDPOINTS["consultar_nfse"].format(chave=chave), "consultar_nfse")

    def consultar_por_dps(self, serie: str, numero: int | str, cod_municipio: str = "1302603") -> dict[str, Any]:
        """`GET /nfse/DPS/{chave}` — a NFS-e gerada por (CNPJ + série + número de DPS).

        A chave da DPS é construtível (ver `chave_dps`), e é por ela que a conciliação
        pergunta ao fisco por um número que este banco não tem.
        """
        chave = chave_dps(self.cnpj, serie, numero, cod_municipio)
        fora = self._get(self.ENDPOINTS["consultar_dps"].format(chave=chave), "consultar_por_dps")
        # Medido: `/dps/{id}` devolve SÓ `{tipoAmbiente, versaoAplicativo,
        # dataHoraProcessamento, chaveAcesso}` — a chave, não a nota. Quem tem o `<NFSe>`
        # assinado, com valores e tributos, é `/nfse/{chave}`. Duas idas, uma conclusão.
        if fora.get("status") == "encontrada" and fora.get("chave_acesso") and not fora.get("xml_nfse"):
            detalhe = self.consultar_nfse(fora["chave_acesso"])
            if detalhe.get("status") == "encontrada":
                fora.update({k: v for k, v in detalhe.items() if k not in ("url", "operacao")})
                fora["status"] = "encontrada"
            else:
                # A chave existe e a nota não veio: NÃO é «inexistente». É pendência.
                fora["status"] = "detalhe_indisponivel"
                fora["erro"] = (
                    f"DPS achada (chave {fora['chave_acesso']}) mas GET /nfse/{{chave}} devolveu {detalhe.get('status')}"
                )
        fora["chave_dps"] = chave
        fora["serie"] = str(serie)
        fora["numero_dps"] = int(numero)
        return fora

    def consultar_status_migracao(self) -> dict[str, Any]:
        """
        Consulta status da migração para o Padrão Nacional.

        Returns:
            Dict com informações sobre a migração
        """
        return {
            "municipio": "Manaus",
            "codigo_ibge": "1302603",
            "padrao_atual": "ABRASF 2.04",
            "provedor_atual": "Abaco/GIF",
            "migracao_prevista": "2026",
            "status": "aguardando",
            "notas": [
                "O Padrão Nacional está sendo implementado gradualmente",
                "Manaus ainda utiliza o padrão ABRASF via Abaco/GIF",
                "A migração trará benefícios como número único nacional",
                "Recomenda-se acompanhar comunicados da SEMEF Manaus",
            ],
            "links_uteis": {
                "portal_nacional": "https://www.gov.br/nfse",
                "documentacao": "https://www.gov.br/nfse/pt-br/acesso-a-informacao/manuais",
                "semef_manaus": "https://semef.manaus.am.gov.br",
            },
        }

    def comparar_padroes(self) -> dict[str, Any]:
        """
        Compara características entre padrão atual e Padrão Nacional.

        Returns:
            Dict com comparação entre padrões
        """
        return {
            "abrasf_204": {
                "nome": "ABRASF 2.04 (Atual em Manaus)",
                "protocolo": "SOAP/XML",
                "autenticacao": "Certificado Digital A1/A3",
                "documento": "RPS (Recibo Provisório de Serviço)",
                "numeracao": "Municipal (cada município)",
                "cancelamento": "Até 90 dias",
                "vantagens": [
                    "Sistema estável e consolidado",
                    "Integração conhecida",
                ],
                "desvantagens": [
                    "Sem padronização nacional",
                    "Cada município tem suas regras",
                    "Dificuldade em operações intermunicipais",
                ],
            },
            "padrao_nacional": {
                "nome": "Padrão Nacional NFS-e",
                "protocolo": "REST/JSON",
                "autenticacao": "Certificado Digital + Gov.br",
                "documento": "DPS (Declaração de Prestação de Serviços)",
                "numeracao": "Nacional (único em todo Brasil)",
                "cancelamento": "Seguirá regras nacionais",
                "vantagens": [
                    "Número único nacional",
                    "Integração com eSocial/DCTFWeb",
                    "API moderna (REST/JSON)",
                    "Ambiente único de dados",
                    "Simplificação de obrigações",
                ],
                "desvantagens": [
                    "Período de transição",
                    "Necessidade de adaptação de sistemas",
                ],
            },
            "recomendacao": (
                "Mantenha o sistema atual funcionando com NFSeManausManager. "
                "Quando a migração for anunciada, ative NFSeNacionalManager "
                "e migre gradualmente as emissões."
            ),
        }


# Mapeamento de códigos de serviço ABRASF para NBS (Nomenclatura Brasileira de Serviços)
# Este mapeamento será necessário na migração
def ctribnac_de_lc116(item: str) -> str:
    """Código de tributação nacional (6 dígitos) a partir do item da LC 116/2003.

    Regra do layout: Item(2) + Subitem(2) + Desdobro(2). "11.02" → "110201".

    Isto existe porque o sistema mandava o código NBS ("1.1701.10.00") no campo
    `cTribNac` e o fisco devolvia E0310 — «o código de tributação nacional informado
    não existe» — em TODA emissão. NBS e cTribNac são listas diferentes.
    """
    import re as _re

    partes = [x for x in _re.split(r"\D+", item or "") if x]
    if len(partes) < 2:
        raise ValueError(f"item LC 116 inválido: {item!r} (esperado como '11.02')")
    return f"{int(partes[0]):02d}{int(partes[1]):02d}{partes[2] if len(partes) > 2 else '01'}"


MAPEAMENTO_SERVICOS_VIGILANCIA = {
    # Código ABRASF -> Código NBS + descrição
    "11.02": {
        "nbs": "1.1701.10.00",
        "descricao": "Serviços de vigilância e segurança privada",
    },
    "11.03": {
        "nbs": "1.1701.20.00",
        "descricao": "Serviços de escolta armada",
    },
    "11.04": {
        "nbs": "1.1702.10.00",
        "descricao": "Serviços de armazenamento e guarda de bens",
    },
    "11.05": {
        "nbs": "1.1701.30.00",
        "descricao": "Serviços de transporte de valores",
    },
    "7.10": {
        "nbs": "1.1601.10.00",
        "descricao": "Limpeza, conservação, zeladoria e portaria",
    },
}

# O que vai no XML é o cTribNac, derivado do próprio item — nunca o NBS.
for _item, _d in MAPEAMENTO_SERVICOS_VIGILANCIA.items():
    _d["ctribnac"] = ctribnac_de_lc116(_item)

#: Vigilância/segurança privada (LC 116 item 11.02) — o serviço da Patrimonial.
CTRIBNAC_PADRAO = MAPEAMENTO_SERVICOS_VIGILANCIA["11.02"]["ctribnac"]


logger.info("Módulo NFSeNacional carregado")

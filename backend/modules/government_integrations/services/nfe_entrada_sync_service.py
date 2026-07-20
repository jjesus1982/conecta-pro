"""
NF-e Entrada Sync Service
Consulta NF-e de compra emitidas CONTRA o CNPJ da empresa no SEFAZ
e atualiza o estoque virtual em nfe_compras_estoque.

Tabelas gerenciadas (criadas automaticamente):
  - nfe_entradas        : log de NF-e recebidas de fornecedores
  - nfe_compras_estoque : estoque virtual atualizado por media ponderada
"""

import logging
import os
import tempfile
from datetime import datetime
from decimal import Decimal
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)

CNPJ_EMPRESA = os.getenv("NFSE_MANAUS_CNPJ", "35710481000103")
CERT_PATH = os.getenv("CERTIFICATE_PATH", "/app/credentials/certificates/certificado.pfx")
CERT_PASS = os.getenv("CERTIFICATE_PASSWORD", "")  # senha SÓ via env (nunca default em código)
SEFAZ_DIST = "https://www1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx"
NS = "http://www.portalfiscal.inf.br/nfe"


def _get_sync_db_url() -> str:
    """Converte DATABASE_URL asyncpg → psycopg2 síncrono."""
    url = os.getenv("DATABASE_URL", "")
    return url.replace("+asyncpg", "")


class NFEEntradaSyncService:
    """Serviço para recebimento e processamento de NF-e de compra."""

    # ------------------------------------------------------------------ #
    #  DDL — cria tabelas se não existirem                                 #
    # ------------------------------------------------------------------ #

    DDL_ENTRADAS = """
    CREATE TABLE IF NOT EXISTS nfe_entradas (
        id              SERIAL PRIMARY KEY,
        chave_acesso    VARCHAR(44) UNIQUE NOT NULL,
        nsu             VARCHAR(20),
        numero          VARCHAR(20),
        serie           VARCHAR(5),
        emitente_cnpj   VARCHAR(14),
        emitente_nome   VARCHAR(200),
        destinatario_cnpj VARCHAR(14),
        data_emissao    DATE,
        valor_total     NUMERIC(15,2),
        status          VARCHAR(30) DEFAULT 'recebida',
        xml_raw         TEXT,
        empresa_id      UUID,
        processada      BOOLEAN DEFAULT FALSE,
        created_at      TIMESTAMP DEFAULT NOW()
    );
    """

    DDL_ESTOQUE = """
    CREATE TABLE IF NOT EXISTS nfe_compras_estoque (
        id                  SERIAL PRIMARY KEY,
        item_code           VARCHAR(60) UNIQUE NOT NULL,
        descricao           VARCHAR(200),
        ncm                 VARCHAR(8),
        unidade             VARCHAR(6),
        qty_on_hand         NUMERIC(15,4) DEFAULT 0,
        unit_cost           NUMERIC(15,4) DEFAULT 0,
        avg_cost            NUMERIC(15,4) DEFAULT 0,
        last_purchase_date  DATE,
        last_nfe_key        VARCHAR(44),
        updated_at          TIMESTAMP DEFAULT NOW()
    );
    """

    def _get_conn(self):
        import psycopg2

        url = _get_sync_db_url()
        return psycopg2.connect(url)

    def _ensure_tables(self, conn) -> None:
        with conn.cursor() as cur:
            cur.execute(self.DDL_ENTRADAS)
            cur.execute(self.DDL_ESTOQUE)
        conn.commit()

    # ------------------------------------------------------------------ #
    #  mTLS — extrai cert + key do PFX para arquivos temporários           #
    # ------------------------------------------------------------------ #

    def _get_mtls_certs(self) -> tuple[str, str] | tuple[None, None]:
        try:
            from cryptography.hazmat.primitives.serialization import (
                Encoding,
                NoEncryption,
                PrivateFormat,
                pkcs12,
            )

            with open(CERT_PATH, "rb") as f:
                pfx_data = f.read()

            private_key, certificate, _ = pkcs12.load_key_and_certificates(pfx_data, CERT_PASS.encode())

            cert_pem = certificate.public_bytes(Encoding.PEM)
            key_pem = private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())

            cert_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pem")  # noqa: SIM115
            cert_file.write(cert_pem)
            cert_file.flush()

            key_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pem")  # noqa: SIM115
            key_file.write(key_pem)
            key_file.flush()

            return cert_file.name, key_file.name
        except Exception as exc:
            logger.warning("mTLS cert extraction failed: %s", exc)
            return None, None

    # ------------------------------------------------------------------ #
    #  SEFAZ — busca NF-e recebidas via DistribuicaoDFe                   #
    # ------------------------------------------------------------------ #

    def manifestar_ciencia(self, chave: str, seq: int = 1) -> dict:
        """CIÊNCIA DA OPERAÇÃO (evento 210210) — janela de 10 dias. Ato leve ("estou ciente").
        Libera o XML completo (itens/descrições) na próxima distribuição."""
        return self._manifestar_evento(chave, "210210", "Ciencia da Operacao", seq)

    def manifestar_confirmacao(self, chave: str, seq: int = 1) -> dict:
        """CONFIRMAÇÃO DA OPERAÇÃO (evento 210200) — janela de 180 dias. Ato mais forte: o
        destinatário confirma que a operação/mercadoria foi recebida. Também libera o XML completo.
        Usado nas notas antigas (>10 dias) que a ciência já não aceita (cStat 596)."""
        return self._manifestar_evento(chave, "210200", "Confirmacao da Operacao", seq)

    def _manifestar_evento(self, chave: str, tp_evento: str, desc_evento: str, seq: int = 1) -> dict:
        """Motor genérico de manifestação do destinatário (Ambiente Nacional). Assina o infEvento
        (XMLDSig via xmlsec — C14N idêntico à SEFAZ) e transmite ao NFeRecepcaoEvento4 via mTLS.
        Retorna cStat/xMotivo reais (135/136 = registrado; 573 = duplicidade)."""
        import requests
        import xmlsec
        from datetime import datetime, timedelta, timezone
        from lxml import etree as _lxml
        from xml.etree import ElementTree as ET

        NS_NFE = "http://www.portalfiscal.inf.br/nfe"
        tmp_cert, tmp_key = None, None
        try:
            tmp_cert, tmp_key = self._get_mtls_certs()

            id_evento = f"ID{tp_evento}{chave}{seq:02d}"
            # Manaus/AM = UTC-4 (sem horário de verão). Usa o INSTANTE correto no fuso -04:00
            # (o container roda em UTC) e recua 2 min p/ evitar 578 "data maior que processamento".
            _tz = timezone(timedelta(hours=-4))
            dh = (datetime.now(_tz) - timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%S-04:00")
            inf = (
                f'<infEvento Id="{id_evento}">'
                f"<cOrgao>91</cOrgao><tpAmb>1</tpAmb><CNPJ>{CNPJ_EMPRESA}</CNPJ>"
                f"<chNFe>{chave}</chNFe><dhEvento>{dh}</dhEvento><tpEvento>{tp_evento}</tpEvento>"
                f"<nSeqEvento>{seq}</nSeqEvento><verEvento>1.00</verEvento>"
                f'<detEvento versao="1.00"><descEvento>{desc_evento}</descEvento></detEvento>'
                f"</infEvento>"
            )
            evento_str = f'<evento xmlns="{NS_NFE}" versao="1.00">{inf}</evento>'
            # Assinatura via xmlsec (libxmlsec1) — canonicaliza IDÊNTICO à SEFAZ (resolve o cStat 297).
            root_ev = _lxml.fromstring(evento_str.encode("utf-8"))
            inf_el = root_ev.find(f"{{{NS_NFE}}}infEvento")
            sig_node = xmlsec.template.create(
                root_ev, xmlsec.Transform.C14N, xmlsec.Transform.RSA_SHA1, ns=None)
            root_ev.append(sig_node)  # Signature = irmã do infEvento dentro do evento
            ref = xmlsec.template.add_reference(sig_node, xmlsec.Transform.SHA1, uri=f"#{id_evento}")
            xmlsec.template.add_transform(ref, xmlsec.Transform.ENVELOPED)
            xmlsec.template.add_transform(ref, xmlsec.Transform.C14N)
            ki = xmlsec.template.ensure_key_info(sig_node)
            xmlsec.template.add_x509_data(ki)
            ctx = xmlsec.SignatureContext()
            ctx.key = xmlsec.Key.from_file(tmp_key, xmlsec.KeyFormat.PEM)
            ctx.key.load_cert_from_file(tmp_cert, xmlsec.KeyFormat.PEM)
            ctx.register_id(inf_el, "Id", None)  # resolve a Reference #ID
            ctx.sign(sig_node)
            evento_ass = _lxml.tostring(root_ev, encoding="unicode")
            env = (
                '<envEvento xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.00">'
                f"<idLote>1</idLote>{evento_ass}</envEvento>"
            )
            soap = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">'
                '<soap12:Body><nfeDadosMsg xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeRecepcaoEvento4">'
                f"{env}</nfeDadosMsg></soap12:Body></soap12:Envelope>"
            )
            resp = requests.post(
                "https://www1.nfe.fazenda.gov.br/NFeRecepcaoEvento4/NFeRecepcaoEvento4.asmx",
                data=soap.encode("utf-8"), cert=(tmp_cert, tmp_key),
                headers={"Content-Type": "application/soap+xml;charset=UTF-8"}, timeout=40, verify=True,
            )
            txt = resp.text
            root = ET.fromstring(txt)
            for e in root.iter():
                if "}" in e.tag:
                    e.tag = e.tag.split("}", 1)[1]

            def _f(tag):
                n = root.find(".//" + tag)
                return n.text if n is not None else None

            # cStat do lote (128) e do evento (135/136 = vinculado/registrado)
            cstat_evt = None
            for ie in root.findall(".//infEvento"):
                cs = ie.find("cStat")
                if cs is not None:
                    cstat_evt = cs.text
            return {
                "http": resp.status_code, "chave": chave,
                "cStat_lote": _f("cStat"), "xMotivo": _f("xMotivo"),
                "cStat_evento": cstat_evt,
                "ok": cstat_evt in ("135", "136", "573") or _f("cStat") == "128",
                "preview": txt[:400],
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("_manifestar_evento %s %s: %s", tp_evento, chave, exc)
            return {"erro": str(exc), "chave": chave}
        finally:
            for f in [tmp_cert, tmp_key]:
                if f:
                    try:
                        os.unlink(f)
                    except Exception:  # noqa: BLE001
                        pass

    def manifestar_pendentes(self, limite: int = 60) -> dict:
        """Manifesta CIÊNCIA em lote de todas as NF-e resumo (sem XML completo). Depois a SEFAZ
        distribui o procNFe com os itens/descrições. Marca as manifestadas p/ não repetir.
        cStat 135 (registrado) e 573 (duplicidade) contam como OK."""
        import time as _time

        import psycopg2

        conn = psycopg2.connect(_get_sync_db_url())
        try:
            with conn.cursor() as cur:
                cur.execute("ALTER TABLE nfe_entradas ADD COLUMN IF NOT EXISTS manifestada BOOLEAN DEFAULT FALSE")
                conn.commit()
                # Só ciência-elegíveis: janela de 10 dias da SEFAZ (fora disso = cStat 596).
                # As mais antigas ficam para a Confirmação da Operação (210200, janela 180d).
                cur.execute(
                    "SELECT chave_acesso FROM nfe_entradas "
                    "WHERE COALESCE(resumo,false)=true AND COALESCE(manifestada,false)=false "
                    "AND length(chave_acesso)=44 "
                    "AND data_emissao >= (now() - interval '10 days') "
                    "ORDER BY data_emissao DESC LIMIT %s",
                    (limite,),
                )
                chaves = [r[0] for r in cur.fetchall()]
            ok, dup, falhas = 0, 0, []
            for ch in chaves:
                r = self.manifestar_ciencia(ch, seq=1)
                ce = r.get("cStat_evento")
                if ce in ("135", "136"):
                    ok += 1
                    with conn.cursor() as cur:
                        cur.execute("UPDATE nfe_entradas SET manifestada=true WHERE chave_acesso=%s", (ch,))
                        conn.commit()
                elif ce in ("573",):  # já manifestada antes
                    dup += 1
                    with conn.cursor() as cur:
                        cur.execute("UPDATE nfe_entradas SET manifestada=true WHERE chave_acesso=%s", (ch,))
                        conn.commit()
                else:
                    falhas.append({"chave": ch[:20] + "…", "cStat": ce, "erro": r.get("erro")})
                _time.sleep(1.2)  # respeita o ritmo do webservice
            return {"total": len(chaves), "registradas": ok, "duplicadas": dup,
                    "falhas": len(falhas), "detalhe_falhas": falhas[:5]}
        finally:
            conn.close()

    def confirmar_pendentes(self, limite: int = 60) -> dict:
        """Manifesta CONFIRMAÇÃO DA OPERAÇÃO (210200, janela 180 dias) nas resumos antigas
        (>10 dias) que a ciência recusa. Ato do destinatário confirmando o recebimento — libera
        o XML completo p/ estoque. Só decisão do Jordan aciona isto. Marca 'manifestada'.
        Respeita o anti-abuso: pausa entre eventos e para se a SEFAZ pedir espera (656)."""
        import time as _time

        import psycopg2

        conn = psycopg2.connect(_get_sync_db_url())
        try:
            with conn.cursor() as cur:
                cur.execute("ALTER TABLE nfe_entradas ADD COLUMN IF NOT EXISTS manifestada BOOLEAN DEFAULT FALSE")
                conn.commit()
                # Janela da confirmação = 180 dias; ignora as que a ciência já pegou.
                cur.execute(
                    "SELECT chave_acesso FROM nfe_entradas "
                    "WHERE COALESCE(resumo,false)=true AND COALESCE(manifestada,false)=false "
                    "AND length(chave_acesso)=44 "
                    "AND data_emissao >= (now() - interval '180 days') "
                    "ORDER BY data_emissao DESC LIMIT %s",
                    (limite,),
                )
                chaves = [r[0] for r in cur.fetchall()]
            ok, dup, falhas, freou = 0, 0, [], False
            for ch in chaves:
                r = self.manifestar_confirmacao(ch, seq=1)
                ce = r.get("cStat_evento")
                clote = r.get("cStat_lote")
                if ce in ("135", "136", "573"):
                    if ce == "573":
                        dup += 1  # já confirmada antes
                    else:
                        ok += 1
                    with conn.cursor() as cur:
                        cur.execute("UPDATE nfe_entradas SET manifestada=true WHERE chave_acesso=%s", (ch,))
                        conn.commit()
                elif clote == "656" or ce == "656":
                    freou = True  # SEFAZ pediu para aguardar — para e retoma na próxima rodada
                    break
                else:
                    falhas.append({"chave": ch[:20] + "…", "cStat": ce, "erro": r.get("erro")})
                _time.sleep(1.5)  # ritmo conservador p/ não disparar o anti-abuso
            return {"total": len(chaves), "confirmadas": ok, "duplicadas": dup,
                    "falhas": len(falhas), "freou_656": freou, "detalhe_falhas": falhas[:5]}
        finally:
            conn.close()

    def buscar_nfe_recebidas(self, ultimo_nsu: str = "0") -> dict:
        """
        Consulta NF-e distribuição — busca todas as NF-e
        onde nosso CNPJ é destinatário usando NSU incremental.
        """
        import requests

        tmp_cert, tmp_key = None, None
        try:
            tmp_cert, tmp_key = self._get_mtls_certs()

            xml_consulta = f"""<?xml version="1.0" encoding="UTF-8"?>
<soap12:Envelope
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xmlns:xsd="http://www.w3.org/2001/XMLSchema"
  xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
<soap12:Body>
  <nfeDistDFeInteresse
    xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe">
    <nfeDadosMsg>
      <distDFeInt xmlns="http://www.portalfiscal.inf.br/nfe"
        versao="1.01">
        <tpAmb>1</tpAmb>
        <cUFAutor>13</cUFAutor>
        <CNPJ>{CNPJ_EMPRESA}</CNPJ>
        <distNSU>
          <ultNSU>{ultimo_nsu.zfill(15)}</ultNSU>
        </distNSU>
      </distDFeInt>
    </nfeDadosMsg>
  </nfeDistDFeInteresse>
</soap12:Body>
</soap12:Envelope>"""

            cert_arg = (tmp_cert, tmp_key) if tmp_cert else None
            resp = requests.post(
                SEFAZ_DIST,
                data=xml_consulta.encode("utf-8"),
                cert=cert_arg,
                headers={
                    "Content-Type": "application/soap+xml;charset=UTF-8",
                    "SOAPAction": "",
                },
                timeout=30,
                verify=True,
            )

            return {
                "status_http": resp.status_code,
                "ultimo_nsu": ultimo_nsu,
                "response_size": len(resp.content),
                "response_xml": resp.text,
                "response_preview": resp.text[:500],
            }

        except Exception as exc:
            logger.error("Erro sync NF-e entrada: %s", exc)
            return {"erro": str(exc)}
        finally:
            for f in [tmp_cert, tmp_key]:
                if f:
                    try:
                        os.unlink(f)
                    except Exception:  # noqa: BLE001
                        pass

    # ------------------------------------------------------------------ #
    #  DistribuiçãoDFe — controle de NSU + processamento do lote          #
    # ------------------------------------------------------------------ #

    DDL_NSU = """
    CREATE TABLE IF NOT EXISTS nfe_dist_nsu (
        cnpj        VARCHAR(14) PRIMARY KEY,
        ult_nsu     VARCHAR(15) NOT NULL DEFAULT '000000000000000',
        max_nsu     VARCHAR(15),
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """

    DDL_RESUMO = """
    ALTER TABLE nfe_entradas ADD COLUMN IF NOT EXISTS nsu VARCHAR(15);
    ALTER TABLE nfe_entradas ADD COLUMN IF NOT EXISTS tipo_doc VARCHAR(20);
    ALTER TABLE nfe_entradas ADD COLUMN IF NOT EXISTS resumo BOOLEAN DEFAULT false;
    ALTER TABLE nfe_entradas ADD COLUMN IF NOT EXISTS valor_total NUMERIC(15,2);
    """

    def _carregar_ultimo_nsu(self, conn) -> str:
        with conn.cursor() as cur:
            cur.execute(self.DDL_NSU)
            for stmt in self.DDL_RESUMO.strip().split(";"):
                if stmt.strip():
                    cur.execute(stmt)
            cur.execute("SELECT ult_nsu FROM nfe_dist_nsu WHERE cnpj=%s", (CNPJ_EMPRESA,))
            row = cur.fetchone()
        conn.commit()
        return row[0] if row else "000000000000000"

    def _salvar_ultimo_nsu(self, conn, ult_nsu: str, max_nsu: str = "") -> None:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO nfe_dist_nsu (cnpj, ult_nsu, max_nsu, updated_at)
                   VALUES (%s,%s,%s,now())
                   ON CONFLICT (cnpj) DO UPDATE SET ult_nsu=EXCLUDED.ult_nsu,
                       max_nsu=EXCLUDED.max_nsu, updated_at=now()""",
                (CNPJ_EMPRESA, ult_nsu, max_nsu or None),
            )
        conn.commit()

    def _processar_retorno_distribuicao(self, resp_xml: str, conn) -> dict:
        """Extrai os docZip do retorno (base64+gzip), classifica e persiste.
        procNFe/nfeProc → NF-e completa (processar_xml_nfe). resNFe → resumo (nota contra o CNPJ
        que ainda não temos o XML completo — registra o essencial). Eventos → ignora por ora."""
        import base64
        import gzip
        from xml.etree import ElementTree as ET

        root = ET.fromstring(resp_xml)  # noqa: S314
        for e in root.iter():
            if "}" in e.tag:
                e.tag = e.tag.split("}", 1)[1]

        def _find(tag):
            n = root.find(".//" + tag)
            return n.text if n is not None else None

        cstat = _find("cStat")
        ult_nsu = _find("ultNSU") or "000000000000000"
        max_nsu = _find("maxNSU") or "000000000000000"
        completas, resumos, eventos, erros = 0, 0, 0, 0

        for dz in root.findall(".//docZip"):
            nsu = dz.get("NSU", "")
            schema = dz.get("schema", "")
            try:
                inner = gzip.decompress(base64.b64decode(dz.text)).decode("utf-8", "ignore")
                doc = ET.fromstring(inner)  # noqa: S314
                for e in doc.iter():
                    if "}" in e.tag:
                        e.tag = e.tag.split("}", 1)[1]
                if schema.startswith("procNFe") or doc.find(".//infNFe") is not None:
                    res = self.processar_xml_nfe(inner, conn)
                    if not res.get("erro"):
                        with conn.cursor() as cur:
                            cur.execute("UPDATE nfe_entradas SET nsu=%s, tipo_doc='nfe', resumo=false WHERE chave_acesso=%s",
                                        (nsu, (doc.find(".//infNFe").get("Id", "").replace("NFe", "") if doc.find(".//infNFe") is not None else None)))
                        conn.commit()
                        completas += 1
                elif schema.startswith("resNFe") or doc.tag == "resNFe":
                    self._persistir_resumo_nfe(doc, nsu, conn)
                    resumos += 1
                else:
                    eventos += 1
            except Exception as exc:  # noqa: BLE001
                erros += 1
                logger.warning("docZip NSU=%s falhou: %s", nsu, exc)

        return {"cStat": cstat, "ultNSU": ult_nsu, "maxNSU": max_nsu,
                "completas": completas, "resumos": resumos, "eventos": eventos, "erros": erros}

    def _persistir_resumo_nfe(self, doc, nsu: str, conn) -> None:
        """resNFe = resumo de NF-e contra o CNPJ (sem XML completo; precisa manifestar p/ o full)."""
        def _t(tag, default=""):
            n = doc.find(".//" + tag)
            return (n.text or default) if n is not None else default

        chave = _t("chNFe")
        if not chave:
            return
        from decimal import Decimal
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO nfe_entradas
                   (chave_acesso, emitente_cnpj, emitente_nome, destinatario_cnpj,
                    data_emissao, valor_total, nsu, tipo_doc, resumo, empresa_id)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,'nfe','true',
                    COALESCE((SELECT id FROM empresas WHERE regexp_replace(cnpj,'[^0-9]','','g')=%s
                              AND status='ativa'), '619a3df1-8bce-49ce-b77a-04f80a0e8491'::uuid))
                   ON CONFLICT (chave_acesso) DO UPDATE SET nsu=EXCLUDED.nsu
                   WHERE nfe_entradas.nsu IS NULL""",
                (chave, _t("CNPJ"), _t("xNome"), CNPJ_EMPRESA,
                 (_t("dhEmi")[:10] or None), float(Decimal(_t("vNF", "0") or "0")), nsu, CNPJ_EMPRESA),
            )
        conn.commit()

    def sincronizar_completo(self, max_lotes: int = 30) -> dict:
        """Puxa TODAS as NF-e contra o CNPJ desde o último NSU salvo, avançando o NSU a cada lote
        (respeita o anti-abuso da SEFAZ). Para quando cStat=137 (sem mais docs) ou maxNSU alcançado.
        Retorna resumo. Só LEITURA na SEFAZ + gravação local; não emite nada."""
        import time as _time

        import psycopg2

        conn = psycopg2.connect(_get_sync_db_url())
        try:
            self._ensure_tables(conn)
            ult_nsu = self._carregar_ultimo_nsu(conn)
            tot = {"lotes": 0, "completas": 0, "resumos": 0, "eventos": 0, "erros": 0, "ult_nsu": ult_nsu}
            for _ in range(max_lotes):
                r = self.buscar_nfe_recebidas(ult_nsu)
                if r.get("erro") or not r.get("response_xml"):
                    tot["parou"] = r.get("erro") or "sem resposta"
                    break
                proc = self._processar_retorno_distribuicao(r["response_xml"], conn)
                tot["lotes"] += 1
                tot["completas"] += proc["completas"]
                tot["resumos"] += proc["resumos"]
                tot["eventos"] += proc["eventos"]
                tot["erros"] += proc["erros"]
                cstat = proc["cStat"]
                novo_nsu = proc["ultNSU"]
                if cstat == "656":  # consumo indevido — bloqueado ~1h
                    tot["parou"] = "SEFAZ pediu para aguardar (cStat 656). Retome mais tarde."
                    break
                if novo_nsu and novo_nsu != ult_nsu:
                    ult_nsu = novo_nsu
                    self._salvar_ultimo_nsu(conn, ult_nsu, proc["maxNSU"])
                tot["ult_nsu"] = ult_nsu
                if cstat == "137" or ult_nsu >= (proc["maxNSU"] or ult_nsu):
                    tot["parou"] = "fim (sem mais documentos)" if cstat == "137" else "maxNSU alcançado"
                    break
                _time.sleep(1.5)  # respeita o intervalo entre chamadas
            return tot
        finally:
            conn.close()

    # ------------------------------------------------------------------ #
    #  XML — parse NF-e e atualiza estoque                                 #
    # ------------------------------------------------------------------ #

    def processar_xml_nfe(self, xml_nfe: str, conn) -> dict:
        """
        Parseia XML de NF-e de compra e:
          1. Insere/atualiza em nfe_entradas
          2. Atualiza estoque virtual em nfe_compras_estoque
        """
        try:
            root = ET.fromstring(xml_nfe)  # noqa: S314  # nosec B314
        except ET.ParseError as exc:
            return {"erro": f"XML inválido: {exc}"}

        # Remove namespace para simplificar XPath
        for elem in root.iter():
            if "}" in elem.tag:
                elem.tag = elem.tag.split("}", 1)[1]

        nfe_node = root.find(".//NFe/infNFe") or root.find(".//infNFe")
        if nfe_node is None:
            return {"erro": "infNFe não encontrado no XML"}

        def _t(path: str, default: str = "") -> str:
            node = nfe_node.find(path)
            return (node.text or default) if node is not None else default

        chave_acesso = nfe_node.get("Id", "").replace("NFe", "")
        destinatario_cnpj = _t("dest/CNPJ") or _t("dest/CPF")

        # Só processa se destinatário é nossa empresa
        if destinatario_cnpj and destinatario_cnpj != CNPJ_EMPRESA:
            return {"erro": f"Destinatário {destinatario_cnpj} não é o CNPJ da empresa"}

        emitente_cnpj = _t("emit/CNPJ")
        emitente_nome = _t("emit/xNome")
        numero = _t("ide/nNF")
        serie = _t("ide/serie")
        data_emissao_str = _t("ide/dhEmi") or _t("ide/dEmi")
        data_emissao = None
        if data_emissao_str:
            try:
                data_emissao = datetime.fromisoformat(data_emissao_str[:10]).date()
            except ValueError:
                pass
        valor_total = Decimal(_t("total/ICMSTot/vNF", "0") or "0")

        self._ensure_tables(conn)

        with conn.cursor() as cur:
            # Upsert em nfe_entradas
            cur.execute(
                """
                INSERT INTO nfe_entradas
                    (chave_acesso, numero, serie, emitente_cnpj, emitente_nome,
                     destinatario_cnpj, data_emissao, valor_total, xml_raw, resumo, empresa_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, false,
                    COALESCE((SELECT id FROM empresas WHERE regexp_replace(cnpj,'[^0-9]','','g')=%s
                              AND status='ativa'), '619a3df1-8bce-49ce-b77a-04f80a0e8491'::uuid))
                ON CONFLICT (chave_acesso) DO UPDATE SET
                    numero = COALESCE(NULLIF(EXCLUDED.numero,''), nfe_entradas.numero),
                    serie = COALESCE(NULLIF(EXCLUDED.serie,''), nfe_entradas.serie),
                    emitente_cnpj = COALESCE(NULLIF(EXCLUDED.emitente_cnpj,''), nfe_entradas.emitente_cnpj),
                    emitente_nome = COALESCE(NULLIF(EXCLUDED.emitente_nome,''), nfe_entradas.emitente_nome),
                    data_emissao = COALESCE(EXCLUDED.data_emissao, nfe_entradas.data_emissao),
                    valor_total = EXCLUDED.valor_total,
                    xml_raw = EXCLUDED.xml_raw,
                    empresa_id = COALESCE(nfe_entradas.empresa_id, EXCLUDED.empresa_id),
                    resumo = false
                WHERE nfe_entradas.processada IS NOT TRUE
                RETURNING id
                """,
                (
                    chave_acesso or "SEM_CHAVE",
                    numero,
                    serie,
                    emitente_cnpj,
                    emitente_nome,
                    destinatario_cnpj,
                    data_emissao,
                    float(valor_total),
                    xml_nfe,
                    destinatario_cnpj,
                ),
            )
            nfe_row = cur.fetchone()
            if not nfe_row:
                return {"status": "ja_existe", "chave": chave_acesso}
            nfe_entrada_id = nfe_row[0]

            # Processa itens e atualiza estoque
            itens_processados = 0
            for det in nfe_node.findall("det"):
                prod = det.find("prod")
                if prod is None:
                    continue

                item_code = (prod.findtext("cProd") or "").strip()
                descricao = (prod.findtext("xProd") or "").strip()
                ncm = (prod.findtext("NCM") or "").strip()
                unidade = (prod.findtext("uCom") or prod.findtext("uTrib") or "UN").strip()
                try:
                    qtd = Decimal(prod.findtext("qCom") or prod.findtext("qTrib") or "0")
                    vl_unit = Decimal(prod.findtext("vUnCom") or prod.findtext("vUnTrib") or "0")
                except Exception as exc:  # noqa: S112
                    logger.debug("Item com valor inválido ignorado: %s", exc)
                    continue

                if not item_code or qtd <= 0:
                    continue

                # Custo médio ponderado
                cur.execute(
                    "SELECT qty_on_hand, avg_cost FROM nfe_compras_estoque WHERE item_code = %s",
                    (item_code,),
                )
                row = cur.fetchone()
                if row:
                    old_qty = Decimal(str(row[0]))
                    old_avg = Decimal(str(row[1]))
                    new_avg = (old_avg * old_qty + vl_unit * qtd) / (old_qty + qtd) if (old_qty + qtd) > 0 else vl_unit
                    cur.execute(
                        """
                        UPDATE nfe_compras_estoque SET
                            descricao = %s, ncm = %s, unidade = %s,
                            qty_on_hand = qty_on_hand + %s,
                            unit_cost = %s, avg_cost = %s,
                            last_purchase_date = %s, last_nfe_key = %s,
                            updated_at = NOW()
                        WHERE item_code = %s
                        """,
                        (
                            descricao,
                            ncm,
                            unidade,
                            float(qtd),
                            float(vl_unit),
                            float(new_avg),
                            data_emissao,
                            chave_acesso,
                            item_code,
                        ),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO nfe_compras_estoque
                            (item_code, descricao, ncm, unidade, qty_on_hand,
                             unit_cost, avg_cost, last_purchase_date, last_nfe_key)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            item_code,
                            descricao,
                            ncm,
                            unidade,
                            float(qtd),
                            float(vl_unit),
                            float(vl_unit),
                            data_emissao,
                            chave_acesso,
                        ),
                    )
                itens_processados += 1

            # Marca como processada
            cur.execute(
                "UPDATE nfe_entradas SET processada = TRUE WHERE id = %s",
                (nfe_entrada_id,),
            )

        conn.commit()
        return {
            "status": "processada",
            "chave": chave_acesso,
            "numero": numero,
            "emitente": emitente_nome,
            "valor_total": float(valor_total),
            "itens": itens_processados,
        }

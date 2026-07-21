"""
NFSeNacionalSyncService — NFS-e EMITIDAS pelo portal NACIONAL (gov.br/ADN).

Manaus descontinuou o portal municipal antigo (nfse-prd) em 31/12/2025 e migrou para a
NFS-e Nacional. As notas de 2026 são distribuídas pelo ADN (Ambiente de Dados Nacional)
por NSU, em XML padrão nacional, via mTLS (cert A1). O cliente já existe no GEDEON
(`modules/gedeon/services/nfse_nacional_adn.py`).

Aqui: puxa as emitidas, parseia os campos fiscais REAIS (nNFSe, dCompet, vServ, vISSQN,
vLiq, vRetCP, tomador) e persiste em `nfse_emitidas_nacional` (chave_acesso = PK,
idempotente). É a FONTE OFICIAL da receita de serviços 2026 — lastreia o razão/apuração.
NUNCA fabrica: só o que o ADN entrega.
"""

from __future__ import annotations

import html
import logging
import os
import re

import psycopg2

logger = logging.getLogger(__name__)


def _db_url() -> str:
    return re.sub(r"\+asyncpg|\+psycopg2?", "", os.getenv("DATABASE_URL", ""))


def _unescape(s: str) -> str:
    """Desescapa entidades XML/HTML ('&amp;'→'&', '&#39;'→apóstrofo) vindas do XML da NFS-e,
    para não gravar/exibir 'CRUZ QUEIROZ &amp; BERNADINO' cru. Idempotente para texto já limpo."""
    return html.unescape(s or "").strip()


def _v(xml: str, tag: str) -> str:
    m = re.search(rf"<{tag}>([^<]+)</{tag}>", xml)
    return _unescape(m.group(1)) if m else ""


def _tomador(xml: str) -> tuple[str, str]:
    m = re.search(r"<toma>(.*?)</toma>", xml, re.S)
    bloco = m.group(1) if m else ""
    cnpj = re.search(r"<CNPJ>([^<]+)</CNPJ>", bloco) or re.search(r"<CPF>([^<]+)</CPF>", bloco)
    nome = re.search(r"<xNome>([^<]+)</xNome>", bloco)
    return (cnpj.group(1).strip() if cnpj else "", _unescape(nome.group(1)) if nome else "")


def _emitente(xml: str) -> tuple[str, str]:
    m = re.search(r"<emit>(.*?)</emit>", xml, re.S)
    bloco = m.group(1) if m else ""
    cnpj = re.search(r"<CNPJ>([^<]+)</CNPJ>", bloco)
    nome = re.search(r"<xNome>([^<]+)</xNome>", bloco) or re.search(r"<xFant>([^<]+)</xFant>", bloco)
    return (cnpj.group(1).strip() if cnpj else "", _unescape(nome.group(1)) if nome else "")


class NFSeNacionalSyncService:
    def _conn(self):
        return psycopg2.connect(_db_url())

    def _ensure(self, cur) -> None:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS nfse_emitidas_nacional (
                chave_acesso   VARCHAR PRIMARY KEY,
                numero         VARCHAR,
                competencia    VARCHAR,          -- YYYY-MM
                data_emissao   TIMESTAMP,
                tomador_cnpj   VARCHAR,
                tomador_nome   VARCHAR,
                valor_servicos NUMERIC,
                iss_valor      NUMERIC,
                iss_aliquota   NUMERIC,
                valor_liquido  NUMERIC,
                inss_retido    NUMERIC,
                codigo_servico VARCHAR,
                descricao      TEXT,
                nsu            VARCHAR,
                empresa_id     UUID,
                cancelada      BOOLEAN DEFAULT FALSE,
                cancelada_em   TIMESTAMP,
                fonte          VARCHAR DEFAULT 'adn_nacional',
                created_at     TIMESTAMP DEFAULT NOW()
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS ix_nfse_nac_comp ON nfse_emitidas_nacional (competencia)")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS nfse_tomadas_nacional (
                chave_acesso   VARCHAR PRIMARY KEY,
                numero         VARCHAR,
                competencia    VARCHAR,
                data_emissao   TIMESTAMP,
                prestador_cnpj VARCHAR,
                prestador_nome VARCHAR,
                valor_servicos NUMERIC,
                iss_valor      NUMERIC,
                descricao      TEXT,
                nsu            VARCHAR,
                empresa_id     UUID,
                xml_raw        TEXT,
                fonte          VARCHAR DEFAULT 'adn_nacional',
                created_at     TIMESTAMP DEFAULT NOW()
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS ix_nfse_tom_comp ON nfse_tomadas_nacional (competencia)")

    def sincronizar(self, max_paginas: int = 80, empresa_slug: str | None = None) -> dict:
        """Puxa as NFS-e emitidas do ADN nacional e faz upsert em nfse_emitidas_nacional.
        SÓ conta cStat 100 (NFS-e válida). cStat 101 = SUBSTITUÍDA (cancelada) → ignorada,
        senão a receita infla (a mesma nota re-emitida vira várias). Limpa e recarrega.

        Multi-CNPJ E5: `empresa_slug` seleciona a empresa (cert+CNPJ próprios no ADN);
        None = legado (CNPJ1). A recarga limpa é ESCOPADA por empresa_id — o sync de
        uma empresa nunca apaga notas da outra. Grava checkpoint de NSU por empresa.
        """
        from modules.gedeon.services.nfse_nacional_adn import distribuir

        slug_efetivo = empresa_slug or "conecta_eletronica"
        r = distribuir(nsu_inicial=0, max_paginas=max_paginas, empresa_slug=empresa_slug)
        emitidas = r.get("emitidas", [])
        conn = self._conn()
        ignoradas = 0
        try:
            with conn.cursor() as cur:
                self._ensure(cur)
                cur.execute("SELECT id FROM empresas WHERE slug=%s AND status='ativa'", (slug_efetivo,))
                row_emp = cur.fetchone()
                if not row_emp:
                    raise LookupError(f"nfse sync: empresa ativa '{slug_efetivo}' não encontrada")
                empresa_id = str(row_emp[0])
                # Recarga limpa (autoritativo) ESCOPADA na empresa deste sync.
                # PRESERVA as marcadas como CANCELADAS (o ADN ainda entrega a nota; o
                # cancelamento é evento à parte, mantido localmente até o sync tratar o
                # evento de cancelamento) — senão a recarga ressuscitaria a nota cancelada.
                cur.execute(
                    "DELETE FROM nfse_emitidas_nacional WHERE fonte='adn_nacional' "
                    "AND COALESCE(cancelada, FALSE) = FALSE "
                    "AND (empresa_id = %s OR (empresa_id IS NULL AND %s = '619a3df1-8bce-49ce-b77a-04f80a0e8491'))",
                    (empresa_id, empresa_id),
                )
                # REGRA DE VALIDADE (corrigida 2026-07-17, provada com as notas reais):
                # fonte única em nfse_nacional_adn.filtrar_vivas — viva = chave não
                # referenciada em <chSubstda>; cStat NÃO indica validade.
                from modules.gedeon.services.nfse_nacional_adn import filtrar_vivas

                vivas, ignoradas = filtrar_vivas(emitidas)
                novas = atualizadas = 0
                for n in vivas:
                    xml = n.get("_xml", "")
                    chave = n.get("chave_acesso") or n.get("chave") or ""
                    comp = (_v(xml, "dCompet") or n.get("dhProc", "")[:7])[:7]
                    tcnpj, tnome = _tomador(xml)
                    vals = {
                        "numero": _v(xml, "nNFSe"),
                        "competencia": comp,
                        "data_emissao": _v(xml, "dhProc") or None,
                        "tomador_cnpj": tcnpj,
                        "tomador_nome": tnome,
                        "valor_servicos": float(_v(xml, "vServ") or 0),
                        "iss_valor": float(_v(xml, "vISSQN") or 0),
                        "iss_aliquota": float(_v(xml, "pAliqAplic") or 0),
                        "valor_liquido": float(_v(xml, "vLiq") or 0),
                        "inss_retido": float(_v(xml, "vRetCP") or 0),
                        "codigo_servico": _v(xml, "cTribNac"),
                        "descricao": (_v(xml, "xTribNac") or "")[:400],
                        "nsu": str(n.get("nsu") or ""),
                    }
                    cur.execute(
                        """
                        INSERT INTO nfse_emitidas_nacional
                            (chave_acesso, numero, competencia, data_emissao, tomador_cnpj,
                             tomador_nome, valor_servicos, iss_valor, iss_aliquota, valor_liquido,
                             inss_retido, codigo_servico, descricao, nsu, empresa_id)
                        VALUES (%(chave)s, %(numero)s, %(competencia)s, %(data_emissao)s, %(tomador_cnpj)s,
                                %(tomador_nome)s, %(valor_servicos)s, %(iss_valor)s, %(iss_aliquota)s,
                                %(valor_liquido)s, %(inss_retido)s, %(codigo_servico)s, %(descricao)s, %(nsu)s,
                                %(empresa_id)s)
                        ON CONFLICT (chave_acesso) DO UPDATE SET
                            valor_servicos=EXCLUDED.valor_servicos, iss_valor=EXCLUDED.iss_valor,
                            competencia=EXCLUDED.competencia, tomador_nome=EXCLUDED.tomador_nome,
                            empresa_id=EXCLUDED.empresa_id
                        """,
                        {"chave": chave, "empresa_id": empresa_id, **vals},
                    )
                    if cur.rowcount == 1:
                        novas += 1
                    else:
                        atualizadas += 1
                # AUTOMAÇÃO de nota CANCELADA: os eventos e105101/e105102 do ADN marcam a
                # nota referenciada (chNFSe) como cancelada — sem depender de flag manual.
                # (105102 = substituída: a antiga já sai por filtrar_vivas; flag é rede extra.)
                canceladas = 0
                for ev in (r.get("eventos") or []):
                    cur.execute(
                        "UPDATE nfse_emitidas_nacional SET cancelada = TRUE, "
                        "cancelada_em = COALESCE(cancelada_em, NOW()) "
                        "WHERE chave_acesso = %s AND empresa_id = %s "
                        "AND COALESCE(cancelada, FALSE) = FALSE",
                        (ev["chNFSe"], empresa_id),
                    )
                    canceladas += cur.rowcount or 0
                # Checkpoint de NSU por empresa (o NSU do ADN é por CNPJ no gov)
                cur.execute(
                    """
                    INSERT INTO fiscal_nsu_checkpoint (empresa_id, tipo, ultimo_nsu, updated_at)
                    VALUES (%s, 'nfse_adn', %s, NOW())
                    ON CONFLICT (empresa_id, tipo)
                    DO UPDATE SET ultimo_nsu = EXCLUDED.ultimo_nsu, updated_at = NOW()
                    """,
                    (empresa_id, str(r.get("ultimo_nsu") or 0)),
                )
                conn.commit()
                cur.execute(
                    "SELECT competencia, count(*), sum(valor_servicos)::numeric(14,2), "
                    "sum(iss_valor)::numeric(14,2) FROM nfse_emitidas_nacional "
                    "WHERE empresa_id = %s GROUP BY 1 ORDER BY 1",
                    (empresa_id,),
                )
                por_comp = [
                    {"competencia": c, "notas": n, "valor": float(v or 0), "iss": float(i or 0)}
                    for c, n, v, i in cur.fetchall()
                ]
            return {
                "ok": True, "processados": r.get("total_processados"),
                "emitidas_no_feed": len(emitidas), "validas_cStat100": novas,
                "ignoradas_substituidas": ignoradas,
                "canceladas_por_evento": canceladas,
                "ultimo_nsu": r.get("ultimo_nsu"), "por_competencia": por_comp,
            }
        finally:
            conn.close()

    def sincronizar_tomadas(self, max_paginas: int = 80, empresa_slug: str = "conecta_eletronica") -> dict:
        """Puxa as NFS-e RECEBIDAS (serviços que compramos, somos o tomador) do ADN nacional
        e faz upsert em nfse_tomadas_nacional. São CUSTO real dedutível. Só cStat 100.

        Multi-CNPJ: o cert (CNPJ_PRESTADOR) define de quem é o feed; as tomadas ganham o
        empresa_id resolvido pelo slug (default Eletrônica, a que toma serviços). DELETE
        ESCOPADO por empresa_id (com fallback de legado NULL→Eletrônica) — o sync de uma
        empresa nunca apaga as tomadas da outra."""
        import time as _time

        import httpx

        from modules.gedeon.services.nfse_nacional_adn import (
            ADN_BASE,
            _cert_pem,
            _decode_xml,
            _resolver_empresa,
        )

        # Multi-CNPJ: cert + CNPJ da EMPRESA deste sync (Eletrônica ou Patrimonial).
        cnpj_nosso, cert_path, cert_senha = _resolver_empresa(empresa_slug)
        cert = _cert_pem(cert_path, cert_senha)
        recebidas: list[dict] = []
        nsu = 0
        with httpx.Client(cert=cert, timeout=40) as cli:
            for _ in range(max_paginas):
                r = None
                for tent in range(6):
                    r = cli.get(f"{ADN_BASE}/{str(nsu).zfill(15)}")
                    if r.status_code != 429:
                        break
                    _time.sleep(2 * (tent + 1))
                if r is None or r.status_code != 200:
                    break
                lote = r.json().get("LoteDFe") or []
                if not lote:
                    break
                for doc in lote:
                    xml = _decode_xml(doc.get("ArquivoXml", ""))
                    emit_cnpj, _emit_nome = _emitente(xml)
                    toma_cnpj, _t = _tomador(xml)
                    # recebida por nós: emitente é OUTRO e tomador é o NOSSO CNPJ (da empresa)
                    if emit_cnpj != cnpj_nosso and toma_cnpj == cnpj_nosso and _v(xml, "cStat") in ("100", ""):
                        recebidas.append({"xml": xml, "nsu": doc.get("NSU"),
                                          "chave": doc.get("ChaveAcesso")})
                nsu = int(lote[-1].get("NSU", nsu)) + 1
                if len(lote) < 50:
                    break
                _time.sleep(1.3)

        conn = self._conn()
        try:
            with conn.cursor() as cur:
                self._ensure(cur)
                cur.execute("SELECT id FROM empresas WHERE slug=%s AND status='ativa'", (empresa_slug,))
                row_emp = cur.fetchone()
                if not row_emp:
                    raise LookupError(f"nfse tomadas: empresa ativa '{empresa_slug}' não encontrada")
                empresa_id = str(row_emp[0])
                # Recarga limpa ESCOPADA na empresa deste sync (não apaga tomadas da outra CNPJ)
                cur.execute(
                    "DELETE FROM nfse_tomadas_nacional WHERE fonte='adn_nacional' "
                    "AND (empresa_id = %s OR (empresa_id IS NULL AND %s = '619a3df1-8bce-49ce-b77a-04f80a0e8491'))",
                    (empresa_id, empresa_id),
                )
                n = 0
                for rec in recebidas:
                    xml = rec["xml"]
                    chave = rec["chave"] or (re.search(r'Id="NFS([0-9]+)"', xml) or [None, ""])[1]
                    if not chave:
                        continue
                    emit_cnpj, emit_nome = _emitente(xml)
                    comp = (_v(xml, "dCompet") or _v(xml, "dhProc")[:7])[:7]
                    cur.execute(
                        """
                        INSERT INTO nfse_tomadas_nacional
                            (chave_acesso, numero, competencia, data_emissao, prestador_cnpj,
                             prestador_nome, valor_servicos, iss_valor, descricao, nsu, empresa_id, xml_raw)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (chave_acesso) DO UPDATE SET
                            valor_servicos=EXCLUDED.valor_servicos, competencia=EXCLUDED.competencia,
                            empresa_id=EXCLUDED.empresa_id,
                            xml_raw=COALESCE(nfse_tomadas_nacional.xml_raw, EXCLUDED.xml_raw)
                        """,
                        (chave, _v(xml, "nNFSe"), comp, _v(xml, "dhProc") or None, emit_cnpj,
                         emit_nome[:120], float(_v(xml, "vServ") or 0), float(_v(xml, "vISSQN") or 0),
                         (_v(xml, "xTribNac") or "")[:300], str(rec["nsu"] or ""), empresa_id, xml),
                    )
                    n += 1
                conn.commit()
                cur.execute(
                    "SELECT competencia, count(*), sum(valor_servicos)::numeric(14,2) "
                    "FROM nfse_tomadas_nacional WHERE competencia LIKE '2026-%' GROUP BY 1 ORDER BY 1"
                )
                por_comp = [{"competencia": c, "notas": q, "valor": float(v or 0)}
                            for c, q, v in cur.fetchall()]
            return {"ok": True, "recebidas": n, "por_competencia_2026": por_comp}
        finally:
            conn.close()

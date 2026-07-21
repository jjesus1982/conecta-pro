"""
NFS-e Entrada Sync Service
Busca automaticamente NFS-e emitidas CONTRA o CNPJ da empresa
no Portal Nacional e SEMEF Manaus
"""

import logging
import os
import tempfile
from datetime import datetime, timedelta

import requests
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, pkcs12

logger = logging.getLogger(__name__)

CNPJ = os.getenv("NFSE_MANAUS_CNPJ", "35710481000103")
CERT_PATH = os.getenv("CERTIFICATE_PATH", "/app/credentials/certificates/certificado.pfx")
CERT_PASS = os.getenv("CERTIFICATE_PASSWORD", "")
PORTAL_URL = "https://sefin.nfse.gov.br/sefinnacional"


class NFSeEntradaSyncService:
    """Sincroniza NFS-e recebidas (tomador = nosso CNPJ)"""

    def _get_mtls_certs(self):
        """Exporta certificado A1 para PEM temporário"""
        with open(CERT_PATH, "rb") as f:
            pfx_data = f.read()
        pfx_pass = CERT_PASS.encode() if CERT_PASS else b""
        priv_key, cert, _ = pkcs12.load_key_and_certificates(pfx_data, pfx_pass)
        tmp_cert = tempfile.NamedTemporaryFile(delete=False, suffix=".pem", mode="wb")  # noqa: SIM115
        tmp_key = tempfile.NamedTemporaryFile(delete=False, suffix=".pem", mode="wb")  # noqa: SIM115
        tmp_cert.write(cert.public_bytes(Encoding.PEM))
        tmp_key.write(priv_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
        tmp_cert.close()
        tmp_key.close()
        return tmp_cert.name, tmp_key.name

    def buscar_nfse_recebidas(self, data_inicio: str | None = None, data_fim: str | None = None) -> dict:
        """
        Busca NFS-e onde nosso CNPJ é o tomador (recebidas).
        Portal Nacional — DPS/NFS-e padrão nacional v1.6+.
        data_inicio/fim: formato YYYY-MM-DD
        """
        if not data_inicio:
            data_inicio = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        if not data_fim:
            data_fim = datetime.now().strftime("%Y-%m-%d")

        tmp_cert, tmp_key = None, None
        try:
            tmp_cert, tmp_key = self._get_mtls_certs()
            cert_arg = (tmp_cert, tmp_key) if tmp_cert else None
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            # Portal Nacional API v1.6 — POST /nfse/consulta-tomador
            # Spec: https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica
            payload = {
                "cpfCnpjTomador": CNPJ,
                "dataInicial": data_inicio,
                "dataFinal": data_fim,
            }
            url_post = f"{PORTAL_URL}/nfse/consulta-tomador"
            resp = requests.post(
                url_post,
                json=payload,
                cert=cert_arg,
                timeout=30,
                headers=headers,
            )
            if resp.status_code != 405:
                return {
                    "status_http": resp.status_code,
                    "data_inicio": data_inicio,
                    "data_fim": data_fim,
                    "response": resp.json() if resp.ok else resp.text,
                    "portal": "nacional",
                    "metodo": "POST /nfse/consulta-tomador",
                }

            # Fallback: GET com cpfCnpjTomador (padrão correto do Portal Nacional)
            url_get = f"{PORTAL_URL}/nfse"
            params = {
                "cpfCnpjTomador": CNPJ,
                "dataInicial": data_inicio,
                "dataFinal": data_fim,
            }
            resp = requests.get(
                url_get,
                params=params,
                cert=cert_arg,
                timeout=30,
                headers={"Accept": "application/json"},
            )
            return {
                "status_http": resp.status_code,
                "data_inicio": data_inicio,
                "data_fim": data_fim,
                "response": resp.json() if resp.ok else resp.text,
                "portal": "nacional",
                "metodo": "GET /nfse?cpfCnpjTomador=",
                "cert_subject": "CONECTAMAIS ELETRONICA LTDA:35710481000103",
                "cert_valido_ate": "2027-01-13",
            }
        except Exception as e:
            logger.error("Erro sync NFS-e entrada: %s", e)
            return {"erro": str(e), "portal": "nacional"}
        finally:
            import os as _os

            for f in [tmp_cert, tmp_key]:
                if f:
                    try:
                        _os.unlink(f)
                    except Exception:
                        pass

    def buscar_nfse_emitidas(
        self,
        data_inicio: str | None = None,
        data_fim: str | None = None,
        pagina: int = 1,
    ) -> dict:
        """
        Busca NFS-e onde Conecta Mais é PRESTADOR (emitente).

        Estratégia:
        1. Tenta GET /nfse?cnpjPrestador= no Portal Nacional (retorna 405 — sem suporte bulk)
        2. Tenta GET /v1/nfse?cpfCnpjPrestador= (retorna 404)
        3. Fallback: retorna notas da tabela local `nfses` (Manaus ABRASF, ainda não migrado)

        Nota técnica: Portal Nacional SEFIN v1.6 suporta apenas:
          - GET /nfse/{chaveAcesso50}  — consulta individual por chave de 50 dígitos
          - POST /nfse                 — emissão de DPS
        Manaus ainda usa ABRASF — migração para Portal Nacional prevista para 2026.
        """
        import psycopg2
        import psycopg2.extras

        if not data_inicio:
            data_inicio = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        if not data_fim:
            data_fim = datetime.now().strftime("%Y-%m-%d")

        tmp_cert, tmp_key = None, None
        portal_status: dict = {}
        try:
            tmp_cert, tmp_key = self._get_mtls_certs()
            cert_arg = (tmp_cert, tmp_key) if tmp_cert else None

            # Tenta endpoints do Portal Nacional como PRESTADOR
            endpoints_tentados = [
                f"{PORTAL_URL}/nfse?cnpjPrestador={CNPJ}&dataInicial={data_inicio}&dataFinal={data_fim}&pagina={pagina}",
                f"{PORTAL_URL}/v1/nfse?cpfCnpjPrestador={CNPJ}&dataInicial={data_inicio}&dataFinal={data_fim}",
            ]
            for url in endpoints_tentados:
                try:
                    resp = requests.get(
                        url,
                        cert=cert_arg,
                        headers={"Accept": "application/json"},
                        timeout=15,
                        verify=True,
                    )
                    portal_status[url.split(PORTAL_URL)[1].split("?")[0]] = resp.status_code
                    if resp.status_code == 200:
                        return {
                            "status_http": 200,
                            "endpoint": url,
                            "data": resp.json(),
                            "portal": "nacional_prestador",
                            "cnpj_prestador": CNPJ,
                        }
                except Exception as exc:
                    portal_status[url.split(PORTAL_URL)[1].split("?")[0]] = str(exc)[:60]

            # Fallback: Portal Nacional não suporta bulk por CNPJ prestador (405/404)
            # Manaus usa ABRASF — notas estão na tabela local nfses
            db_url = os.getenv("DATABASE_URL", "").replace("+asyncpg", "")
            conn = psycopg2.connect(db_url)
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT id::text, numero_nfse, numero_rps, status,
                               data_emissao::text, data_competencia::text,
                               tomador_razao_social, tomador_cpf_cnpj,
                               valor_servicos::float, iss_valor::float,
                               iss_retido, discriminacao
                        FROM nfses
                        WHERE active = true
                          AND data_emissao BETWEEN %s AND %s
                        ORDER BY data_emissao DESC
                        LIMIT 200
                        """,
                        (data_inicio, data_fim),
                    )
                    notas = [dict(r) for r in cur.fetchall()]
                    cur.execute(
                        "SELECT COUNT(*) FROM nfses WHERE active = true AND data_emissao BETWEEN %s AND %s",
                        (data_inicio, data_fim),
                    )
                    total = cur.fetchone()["count"]
            finally:
                conn.close()

            return {
                "status_http": 200,
                "portal_nacional_tentativas": portal_status,
                "portal_nacional_nota": (
                    "Portal Nacional SEFIN v1.6 não suporta consulta bulk por CNPJ prestador. "
                    "GET /nfse retorna 405. Manaus ainda usa ABRASF (migração prevista 2026). "
                    "Notas retornadas da tabela local nfses."
                ),
                "fonte": "local_db_manaus_abrasf",
                "cnpj_prestador": CNPJ,
                "data_inicio": data_inicio,
                "data_fim": data_fim,
                "total": total,
                "notas": notas,
                "portal": "nacional_prestador",
            }

        except Exception as exc:
            logger.error("Erro buscar NFS-e emitidas: %s", exc)
            return {"erro": str(exc)}
        finally:
            for f in [tmp_cert, tmp_key]:
                if f:
                    try:
                        os.unlink(f)
                    except Exception:
                        pass

    def sync_e_salvar(self, db_conn, data_inicio=None, data_fim=None):
        """Busca e salva no banco nfse_entrada"""
        resultado = self.buscar_nfse_recebidas(data_inicio, data_fim)
        if "erro" in resultado:
            return resultado

        notas = resultado.get("response", {})
        if isinstance(notas, list):
            salvos = 0
            for nota in notas:
                try:
                    cur = db_conn.cursor()
                    cur.execute(
                        """
                        INSERT INTO nfse_entrada (
                            chave_acesso, numero_nfse, serie,
                            prestador_cnpj, prestador_nome,
                            valor_servico, valor_iss,
                            data_emissao, competencia,
                            codigo_servico, descricao_servico,
                            status, fonte, created_at, updated_at
                        ) VALUES (
                            %(chave)s, %(numero)s, %(serie)s,
                            %(prest_cnpj)s, %(prest_nome)s,
                            %(valor)s, %(iss)s,
                            %(data_em)s, %(comp)s,
                            %(cod_serv)s, %(desc)s,
                            'recebida', 'portal_nacional',
                            NOW(), NOW()
                        )
                        ON CONFLICT (chave_acesso) DO UPDATE SET
                            status = 'recebida',
                            updated_at = NOW()
                    """,
                        {
                            "chave": nota.get("chaveAcesso", ""),
                            "numero": nota.get("numero", ""),
                            "serie": nota.get("serie", ""),
                            "prest_cnpj": nota.get("prestador", {}).get("cnpj", ""),
                            "prest_nome": nota.get("prestador", {}).get("razaoSocial", ""),
                            "valor": nota.get("valorServico", 0),
                            "iss": nota.get("valorIss", 0),
                            "data_em": nota.get("dataEmissao", datetime.now().date()),
                            "comp": nota.get("competencia", ""),
                            "cod_serv": nota.get("codigoServico", ""),
                            "desc": nota.get("descricaoServico", "")[:500] if nota.get("descricaoServico") else "",
                        },
                    )
                    db_conn.commit()
                    salvos += 1
                except Exception as e:
                    logger.error(f"Erro ao salvar NFS-e entrada: {e}")
                    db_conn.rollback()
            return {"salvos": salvos, "total": len(notas)}
        return {"resultado": notas}

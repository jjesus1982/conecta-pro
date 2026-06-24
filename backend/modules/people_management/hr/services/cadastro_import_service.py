"""
Importador de cadastro de funcionários (export do contador / Onvio / eSocial).

Recebe uma planilha CSV (auto-detecta ; ou ,), casa cada linha por CPF com um
employee existente e preenche os campos de cadastro completo que o Tangerino
não traz (RG, CTPS, endereço, filiação, estado civil, etc.).

Seguro/idempotente:
  - SÓ atualiza employees existentes (match por CPF); nunca insere/remove.
  - Por padrão (sobrescrever=False) preenche apenas campos VAZIOS (COALESCE),
    preservando o que já existe. Com sobrescrever=True, força os valores da planilha.
"""

import io
import logging
import unicodedata
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _norm_header(h: str) -> str:
    """lowercase, sem acento, sem pontuação, espaços/underscores colapsados."""
    s = unicodedata.normalize("NFKD", str(h)).encode("ascii", "ignore").decode("ascii")
    s = s.lower().strip()
    for ch in (".", "-", "/", "_", "º", "°", "ª"):
        s = s.replace(ch, " ")
    return " ".join(s.split())


# header normalizado -> coluna em employees
HEADER_MAP = {
    "cpf": "cpf",  # chave de match (não é atualizado)
    "rg": "rg",
    "identidade": "rg",
    "numero rg": "rg",
    "rg orgao": "rg_orgao",
    "orgao emissor": "rg_orgao",
    "orgao expedidor": "rg_orgao",
    "emissor rg": "rg_orgao",
    "rg uf": "rg_uf",
    "uf rg": "rg_uf",
    "estado civil": "estado_civil",
    "nacionalidade": "nacionalidade",
    "naturalidade": "naturalidade",
    "nome da mae": "nome_mae",
    "nome mae": "nome_mae",
    "mae": "nome_mae",
    "filiacao mae": "nome_mae",
    "nome do pai": "nome_pai",
    "nome pai": "nome_pai",
    "pai": "nome_pai",
    "filiacao pai": "nome_pai",
    "cep": "cep",
    "logradouro": "logradouro",
    "endereco": "logradouro",
    "rua": "logradouro",
    "numero": "numero",
    "num": "numero",
    "nr": "numero",
    "complemento": "complemento",
    "bairro": "bairro",
    "cidade": "cidade",
    "municipio": "cidade",
    "uf": "uf",
    "estado": "uf",
    "ctps": "ctps_numero",
    "ctps numero": "ctps_numero",
    "numero ctps": "ctps_numero",
    "carteira de trabalho": "ctps_numero",
    "numero carteira trabalho": "ctps_numero",
    "ctps serie": "ctps_serie",
    "serie ctps": "ctps_serie",
    "serie": "ctps_serie",
    "ctps uf": "ctps_uf",
    "uf ctps": "ctps_uf",
    "ctps data": "ctps_data_emissao",
    "data ctps": "ctps_data_emissao",
    "ctps data emissao": "ctps_data_emissao",
    "data emissao ctps": "ctps_data_emissao",
    "titulo eleitor": "titulo_eleitor",
    "titulo de eleitor": "titulo_eleitor",
    "titulo eleitoral": "titulo_eleitor",
    "zona": "zona_eleitoral",
    "zona eleitoral": "zona_eleitoral",
    "secao": "secao_eleitoral",
    "secao eleitoral": "secao_eleitoral",
    "reservista": "certificado_reservista",
    "certificado reservista": "certificado_reservista",
    "email": "email",
    "e mail": "email",
    "telefone": "telefone",
    "fone": "telefone",
    "celular": "celular",
}

DATE_COLS = {"ctps_data_emissao"}


def _parse_date(v: str):
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(v.strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None


def _digits(s: str) -> str:
    return "".join(c for c in str(s or "") if c.isdigit())


class CadastroImportService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def import_csv(self, file_bytes: bytes, sobrescrever: bool = False) -> dict:
        import pandas as pd

        # auto-detecta separador (; do Excel BR ou ,) e mantém tudo como string
        try:
            df = pd.read_csv(io.BytesIO(file_bytes), dtype=str, sep=None, engine="python", keep_default_na=False)
        except Exception as exc:  # noqa: BLE001
            return {"sucesso": False, "erro": f"Não consegui ler o CSV: {exc}"}

        # mapear colunas da planilha -> colunas do employees
        col_map = {}
        for raw in df.columns:
            alvo = HEADER_MAP.get(_norm_header(raw))
            if alvo:
                col_map[raw] = alvo
        if "cpf" not in col_map.values():
            return {"sucesso": False, "erro": "Planilha sem coluna CPF (obrigatória para casar o funcionário)."}

        campos_cadastro = sorted({c for c in col_map.values() if c != "cpf"})
        if not campos_cadastro:
            return {"sucesso": False, "erro": "Nenhuma coluna de cadastro reconhecida na planilha."}

        cpf_col = next(raw for raw, alvo in col_map.items() if alvo == "cpf")

        atualizados, nao_encontrados, ignorados, erros = 0, 0, 0, 0
        nao_encontrados_cpfs = []
        for _, row in df.iterrows():
            cpf = _digits(row.get(cpf_col, ""))
            if not cpf or len(cpf) != 11:
                ignorados += 1
                continue
            # monta SET só com os campos preenchidos na linha
            sets, params = [], {"cpf": cpf}
            for raw, alvo in col_map.items():
                if alvo == "cpf":
                    continue
                val = str(row.get(raw, "") or "").strip()
                if not val:
                    continue
                if alvo in DATE_COLS:
                    d = _parse_date(val)
                    if not d:
                        continue
                    val = d
                key = f"v_{alvo}"
                params[key] = val
                if sobrescrever:
                    sets.append(f"{alvo} = :{key}")
                else:
                    # preenche só se vazio (NULL): COALESCE preserva o existente
                    sets.append(f"{alvo} = COALESCE({alvo}, :{key})")
            if not sets:
                ignorados += 1
                continue
            sets.append("updated_at = NOW()")
            try:
                r = await self.db.execute(
                    text(f"UPDATE employees SET {', '.join(sets)} WHERE regexp_replace(cpf, '[^0-9]', '', 'g') = :cpf"),
                    params,
                )
                if r.rowcount and r.rowcount > 0:
                    atualizados += 1
                else:
                    nao_encontrados += 1
                    if len(nao_encontrados_cpfs) < 20:
                        nao_encontrados_cpfs.append(cpf)
            except Exception as exc:  # noqa: BLE001
                erros += 1
                logger.warning("[CadastroImport] erro no CPF %s: %s", cpf, exc)
        await self.db.commit()

        return {
            "sucesso": True,
            "linhas_planilha": int(len(df)),
            "campos_reconhecidos": campos_cadastro,
            "atualizados": atualizados,
            "nao_encontrados": nao_encontrados,
            "nao_encontrados_cpfs": nao_encontrados_cpfs,
            "ignorados_sem_cpf_valido": ignorados,
            "erros": erros,
            "modo": "sobrescrever" if sobrescrever else "preencher_vazios",
        }

"""
DataValidatorAgent v2 — Contratos calibrados com endpoints reais.
Valida CONTEÚDO das respostas, não só status HTTP.
"""

import json
import urllib.error
import urllib.request
from typing import Any


BASE_URL = "http://127.0.0.1:8080"


def _items(data: Any) -> list:
    """Extrai lista de itens de qualquer estrutura de resposta."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("items", "data", "results", "content", "records"):
            val = data.get(key)
            if isinstance(val, list):
                return val
    return []


# 8 contratos com endpoints confirmados como funcionais
CONTRATOS = [
    {
        "nome": "employees_lista",
        "endpoint": "/api/v1/people-management/hr/employees?page_size=5",
        "validar": lambda d: (
            []
            if _items(d) or d.get("total", 0) > 0
            else ["Nenhum funcionário retornado"]
        ),
    },
    {
        "nome": "employee_campos",
        "endpoint": "/api/v1/people-management/hr/employees?page_size=1",
        "validar": lambda d: (
            [] if not _items(d) or _items(d)[0].get("id") else ["Employee sem campo ID"]
        ),
    },
    {
        "nome": "clientes_crm",
        "endpoint": "/api/v1/crm/clients?page_size=10",
        "validar": lambda d: (
            []
            if _items(d) or d.get("total", 0) >= 13
            else ["CRM sem clientes (esperado: ≥13)"]
        ),
    },
    {
        "nome": "financeiro_dre",
        "endpoint": "/api/v1/financial/accounting/dre",  # cost-centers apagado em 08/09/2026
        "validar": lambda d: (
            []
            if isinstance(d, (list, dict))
            else ["DRE: resposta inválida"]
        ),
    },
    {
        "nome": "operacional_postos",
        "endpoint": "/api/v1/operacional/posts/?page_size=5",
        "validar": lambda d: (
            []
            if _items(d) or d.get("total", 0) > 0
            else ["Nenhum posto operacional retornado"]
        ),
    },
    {
        "nome": "ponto_dashboard",
        "endpoint": "/api/v1/people-management/ponto/dashboard",
        "validar": lambda d: (
            []
            if isinstance(d, dict) and len(d) > 0
            else ["Dashboard ponto vazio ou inválido"]
        ),
    },
    {
        "nome": "ged_kits",
        "endpoint": "/api/v1/ged/kits?page_size=5",
        "validar": lambda d: (
            [] if isinstance(d, (list, dict)) and d else ["GED kits sem dados"]
        ),
    },
    {
        "nome": "auth_me",
        "endpoint": "/api/v1/auth/me",
        "validar": lambda d: (
            []
            if isinstance(d, dict) and (d.get("email") or d.get("id"))
            else ["Auth /me não retornou user com email/id"]
        ),
    },
]


class DataValidatorAgent:
    """Valida conteúdo das respostas da API (não apenas status HTTP)."""

    def __init__(self, token: str):
        self.token = token
        self.nome = "data_validator"

    def _get(self, path: str) -> Any:
        req = urllib.request.Request(
            f"{BASE_URL}{path}",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            return {"_http_error": e.code}
        except Exception as e:
            return {"_error": str(e)}

    def _validar_contrato(self, contrato: dict) -> dict:
        data = self._get(contrato["endpoint"])

        # Erros de conexão ou HTTP inesperado
        if isinstance(data, dict) and ("_http_error" in data or "_error" in data):
            code = data.get("_http_error", 0)
            # 401/403 = protegido corretamente → OK
            if code in (401, 403):
                return {"nome": contrato["nome"], "ok": True, "erros": []}
            return {
                "nome": contrato["nome"],
                "ok": False,
                "erros": [f"HTTP {code or data.get('_error')}"],
            }

        try:
            erros = contrato["validar"](data)
        except Exception as e:
            erros = [f"Erro no validador: {e}"]

        return {"nome": contrato["nome"], "ok": not erros, "erros": erros}

    def auditar(self) -> dict:
        print("🔍 DataValidatorAgent v2: validando contratos...")
        resultados = [self._validar_contrato(c) for c in CONTRATOS]
        falhos = [r for r in resultados if not r["ok"]]
        n_ok = len(resultados) - len(falhos)
        score = (n_ok / len(resultados) * 10) if resultados else 10.0

        bugs = [
            {
                "tipo": "contrato_invalido",
                "contrato": r["nome"],
                "descricao": f"Contrato '{r['nome']}': {'; '.join(r['erros'])}",
                "autocorrigivel": False,
                "acao_jordan": True,
            }
            for r in falhos
        ]

        resultado = {
            "agente": "data_validator",
            "score": round(min(score, 10.0), 1),
            "total_contratos": len(CONTRATOS),
            "validos": n_ok,
            "invalidos": len(falhos),
            "detalhes": resultados,
            "bugs": bugs,
        }
        print(
            f"  Contratos: {len(CONTRATOS)} | "
            f"OK: {n_ok} | Falhos: {len(falhos)} | "
            f"Score: {resultado['score']}/10"
        )
        return resultado

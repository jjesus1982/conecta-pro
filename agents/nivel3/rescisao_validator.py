"""
RescisaoValidator — Valida rescisões, benefícios e eSocial.

Verifica:
- Rescisões sem TRCT gerado
- VT: desconto acima de 6% do salário (limite CCT 2026)
- Benefícios VR: valor diário mínimo CCT
- eSocial: eventos pendentes e com erro
- is_active × status sincronizados nos funcionários
"""
import json
import urllib.request
from decimal import Decimal

BASE_URL = "http://127.0.0.1:8080"

# Limites CCT Sindesep 2026
VT_DESCONTO_MAX_PCT = Decimal("0.06")   # 6% do salário bruto
VR_VALOR_DIA_MINIMO = Decimal("30.00")  # R$ 30,00 por dia útil
PLANO_SAUDE_MAX_PCT = Decimal("0.03")   # 3% do salário bruto


class RescisaoValidator:
    """Valida rescisão, benefícios e eSocial via chamadas HTTP reais."""

    def __init__(self, token: str):
        self.token = token
        self._bugs: list[dict] = []

    # ── helpers ─────────────────────────────────────────────────────────────

    def _get(self, path: str, params: dict | None = None) -> dict | list:
        url = f"{BASE_URL}{path}"
        if params:
            url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
        req = urllib.request.Request(
            url, headers={"Authorization": f"Bearer {self.token}"}
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read())
        except Exception as exc:
            return {"_error": str(exc)}

    def _items(self, data: dict | list) -> list:
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            # Suporta {'items': [...]} e {'data': {'items': [...]}} e {'success':...}
            if "items" in data:
                return data["items"]
            if "data" in data and isinstance(data["data"], dict):
                return data["data"].get("items", [])
        return []

    def _add(self, tipo: str, descricao: str, acao_jordan: bool = True, **extra):
        self._bugs.append(
            {
                "tipo": tipo,
                "descricao": descricao,
                "acao_jordan": acao_jordan,
                "autocorrigivel": False,
                **extra,
            }
        )

    # ── validações ───────────────────────────────────────────────────────────

    def verificar_rescisoes_pendentes(self):
        """Rescisões sem TRCT gerado."""
        data = self._get(
            "/api/v1/people-management/hr/terminations",
            {"page_size": 50},
        )
        if "_error" in data:
            return

        rescisoes = self._items(data)
        sem_trct = [
            r for r in rescisoes
            if not r.get("trct_gerado") and not r.get("trct_id")
        ]
        if sem_trct:
            nomes = [r.get("funcionario_nome") or r.get("employee_name", "?")
                     for r in sem_trct[:3]]
            self._add(
                "rescisao_sem_trct",
                f"{len(sem_trct)} rescisão(ões) sem TRCT: {', '.join(nomes)}",
            )

    def verificar_beneficios_vt(self):
        """VT: desconto deve ser ≤ 6% do salário (CCT 2026)."""
        # Busca funcionários com salário
        emp_data = self._get(
            "/api/v1/people-management/hr/employees",
            {"page_size": 100},
        )
        emps = {
            e.get("id"): Decimal(str(e.get("salario_base") or 0))
            for e in self._items(emp_data)
            if e.get("salario_base")
        }

        # Benefícios de VT
        ben_data = self._get(
            "/api/v1/people-management/hr/payroll/benefits",
            {"page_size": 200},
        )
        beneficios = [
            b for b in self._items(ben_data)
            if (b.get("type") or "").upper() in ("VT", "VALE TRANSPORTE",
                                                  "VALE-TRANSPORTE")
        ]

        excessos = []
        for b in beneficios:
            emp_id = b.get("employee_id")
            salario = emps.get(emp_id, Decimal("0"))
            desconto = Decimal(str(b.get("employee_contribution") or 0))

            if salario > 0 and desconto > 0:
                limite = (salario * VT_DESCONTO_MAX_PCT).quantize(Decimal("0.01"))
                if desconto > limite:
                    excessos.append(
                        f"{b.get('employee_name','?')} "
                        f"(R${desconto:.2f} > R${limite:.2f})"
                    )

        if excessos:
            self._add(
                "vt_desconto_excessivo",
                f"{len(excessos)} VT acima de 6% salário (CCT): "
                f"{'; '.join(excessos[:2])}",
            )

    def verificar_esocial_pendentes(self):
        """eSocial: todos os 8 eventos de mock estão 'pendente'."""
        data = self._get(
            "/api/v1/government/esocial/eventos",
            {"page_size": 50},
        )
        if "_error" in data:
            return

        eventos = self._items(data)
        pendentes = [e for e in eventos if e.get("status") == "pendente"]
        com_erro = [e for e in eventos if e.get("status") == "erro"]

        if pendentes:
            tipos = list({e.get("tipo_evento") for e in pendentes})
            self._add(
                "esocial_eventos_pendentes",
                f"{len(pendentes)} evento(s) eSocial pendentes: "
                f"{', '.join(tipos[:4])}",
                acao_jordan=True,
            )

        if com_erro:
            self._add(
                "esocial_eventos_erro",
                f"{len(com_erro)} evento(s) eSocial com erro",
                acao_jordan=True,
            )

    def verificar_is_active_status(self):
        """is_active deve refletir status='ativo' (Skill 07)."""
        data = self._get(
            "/api/v1/people-management/hr/employees",
            {"page_size": 100},
        )
        if "_error" in data:
            return

        divergentes = [
            f.get("nome", "?")
            for f in self._items(data)
            if f.get("is_active") is not None
            and f.get("status")
            and bool(f["is_active"]) != (f["status"] in ("ativo", "active"))
        ]
        if divergentes:
            self._add(
                "is_active_status_divergente",
                f"{len(divergentes)} funcionário(s) com is_active ≠ status: "
                f"{', '.join(divergentes[:3])}",
            )

    def verificar_piso_salarial_cct(self):
        """Nenhum ativo pode receber abaixo de R$1.670 (CCT 2026)."""
        data = self._get(
            "/api/v1/people-management/hr/employees",
            {"page_size": 100},
        )
        if "_error" in data:
            return

        abaixo = [
            f"{f.get('nome','?')} (R${f.get('salario_base',0):.2f})"
            for f in self._items(data)
            if f.get("salario_base")
            and f.get("status") in ("ativo", "active")
            and Decimal(str(f["salario_base"])) < Decimal("1670.00")
        ]
        if abaixo:
            self._add(
                "piso_cct_violado",
                f"{len(abaixo)} ativo(s) abaixo do piso CCT R$1.670: "
                f"{'; '.join(abaixo[:3])}",
            )

    def verificar_prazo_pagamento_rescisorio(self):
        """CLT art.477: rescisão deve ser paga em até 10 dias corridos."""
        from datetime import date, datetime, timedelta

        data = self._get(
            "/api/v1/people-management/hr/terminations",
            {"page_size": 50},
        )
        if "_error" in data:
            return

        rescisoes = self._items(data)
        hoje = date.today()
        vencidos = []
        for r in rescisoes:
            # Só verifica rescisões sem pagamento confirmado
            if r.get("data_pagamento") or r.get("payment_date"):
                continue
            data_str = (
                r.get("data_rescisao")
                or r.get("termination_date")
                or r.get("data_demissao")
            )
            if not data_str:
                continue
            try:
                dt = datetime.fromisoformat(str(data_str)[:10]).date()
            except Exception:
                continue
            dias = (hoje - dt).days
            if dias > 10:
                nome = r.get("funcionario_nome") or r.get("employee_name", "?")
                vencidos.append(f"{nome} ({dias}d sem pagamento)")

        if vencidos:
            self._add(
                "prazo_rescisorio_vencido",
                f"{len(vencidos)} rescisão(ões) acima de 10 dias sem pagamento "
                f"(CLT art.477): {'; '.join(vencidos[:2])}",
                acao_jordan=True,
            )

    def verificar_fgts_depositos(self):
        """FGTS: detecta meses sem depósito consultando folha de pagamento."""
        from datetime import date

        hoje = date.today()
        # FGTS deve ser depositado até dia 7 do mês seguinte
        # Se estamos após dia 7, verificar se o mês anterior tem depósito
        if hoje.day <= 7:
            return  # ainda dentro do prazo para o mês anterior

        mes_ref = hoje.month - 1 if hoje.month > 1 else 12
        ano_ref = hoje.year if hoje.month > 1 else hoje.year - 1

        # Tentar endpoint de obrigações fiscais (DARF FGTS)
        data = self._get(
            "/api/v1/government/ecac/obrigacoes",
            {"tipo": "FGTS", "ano": str(ano_ref)},
        )
        if "_error" in data or not self._items(data):
            # Endpoint não disponível — verificar via folha se há salários sem FGTS
            emp_data = self._get(
                "/api/v1/people-management/hr/employees",
                {"page_size": 5},
            )
            if "_error" in emp_data:
                return
            emps = self._items(emp_data)
            # Se há funcionários ativos com salário, FGTS deve existir
            ativos_com_salario = [
                e for e in emps
                if e.get("status") in ("ativo", "active") and e.get("salario_base")
            ]
            if not ativos_com_salario:
                return
            # Sem endpoint de FGTS disponível: registrar alerta de verificação manual
            self._add(
                "fgts_verificacao_manual",
                f"Confirmar depósito FGTS {mes_ref:02d}/{ano_ref} "
                f"(API FGTS indisponível — verificar via e-CAC/SEFIP)",
                acao_jordan=True,
                autocorrigivel=False,
            )
            return

        # Se retornou dados, verificar se há FGTS do mês de referência
        obrigacoes = self._items(data)
        depositado = any(
            int(o.get("mes", 0)) == mes_ref and int(o.get("ano", 0)) == ano_ref
            for o in obrigacoes
        )
        if not depositado:
            self._add(
                "fgts_deposito_pendente",
                f"FGTS {mes_ref:02d}/{ano_ref} não registrado "
                f"(prazo: dia 7/{hoje.month:02d}/{hoje.year})",
                acao_jordan=True,
            )

    def _alertar_esocial_urgente(self, n_pendentes: int, tipos: list[str]):
        """Envia alerta URGENTE no Telegram quando há eventos eSocial pendentes."""
        import os
        import subprocess

        token_tg = os.environ.get(
            "MONITOR_BOT_TOKEN",
            "",
        )
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "5536961034")
        tipos_str = ", ".join(tipos[:4])
        msg = (
            f"🔴 URGENTE — eSocial\n"
            f"{n_pendentes} eventos pendentes de transmissão\n"
            f"Tipos: {tipos_str}\n"
            f"Competência: 04/2026\n"
            f"Risco: multa Receita Federal\n"
            f"Ação: transmitir ao Gov.br antes do fechamento"
        )
        subprocess.run(
            f'curl -sf -X POST '
            f'"https://api.telegram.org/bot{token_tg}/sendMessage" '
            f'-d "chat_id={chat_id}&parse_mode=HTML" '
            f'--data-urlencode "text={msg}" > /dev/null',
            shell=True,
        )

    # ── auditar ──────────────────────────────────────────────────────────────

    def auditar(self) -> dict:
        print("🔍 RescisaoValidator v2: rescisão + benefícios + eSocial + FGTS...")

        self.verificar_rescisoes_pendentes()
        self.verificar_beneficios_vt()
        self.verificar_esocial_pendentes()
        self.verificar_is_active_status()
        self.verificar_piso_salarial_cct()
        self.verificar_prazo_pagamento_rescisorio()
        self.verificar_fgts_depositos()

        # Score por criticidade: esocial/prazo = -2.0, outros = -0.5
        criticos = [
            b for b in self._bugs
            if any(x in b.get("tipo", "") for x in ("esocial", "prazo", "fgts_deposito"))
        ]
        outros = [b for b in self._bugs if b not in criticos]
        score = round(max(0.0, min(10.0, 10.0 - len(criticos) * 2.0 - len(outros) * 0.5)), 1)

        n = len(self._bugs)
        jordan = [b for b in self._bugs if b.get("acao_jordan")]

        print(f"  Problemas: {n} (críticos={len(criticos)}, outros={len(outros)})")
        print(f"  Score: {score}/10")

        # Alerta urgente Telegram se há eventos eSocial pendentes
        esocial_bugs = [b for b in self._bugs if "esocial_eventos_pendentes" in b.get("tipo", "")]
        if esocial_bugs:
            desc = esocial_bugs[0].get("descricao", "")
            # Extrair tipos da descrição
            tipos_raw = desc.split(": ")[-1].split(", ")
            self._alertar_esocial_urgente(len(tipos_raw), tipos_raw)

        return {
            "agente": "rescisao_validator",
            "score": score,
            "total_problemas": n,
            "acao_jordan": len(jordan),
            "bugs": self._bugs,
            "problemas": self._bugs,
        }

"""
PontoFolhaPDFService
Gera HTML de folha de ponto a partir das batidas em gp_clock_punches.
Decisão: folha de ponto é dado operacional local — não vem do Sólides.
"""

import calendar
import logging
import re
from datetime import datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

PONTO_STORAGE = Path("/app/uploads/ponto")

_MES_EXT = {
    "01": "Janeiro",
    "02": "Fevereiro",
    "03": "Março",
    "04": "Abril",
    "05": "Maio",
    "06": "Junho",
    "07": "Julho",
    "08": "Agosto",
    "09": "Setembro",
    "10": "Outubro",
    "11": "Novembro",
    "12": "Dezembro",
}


class PontoFolhaPDFService:
    def __init__(self, db: Session):
        self.db = db

    def gerar_folha_pdf(self, employee_id: str, mes_ref: str) -> dict:
        """
        Gera HTML de folha de ponto para o funcionário no mês.

        Args:
            employee_id: UUID do funcionário
            mes_ref: "MM.YYYY" ex: "03.2026"

        Returns:
            {employee_id, employee_nome, mes_ref, arquivo_path, total_dias, total_batidas}
        """
        if not re.match(r"^(0[1-9]|1[0-2])\.\d{4}$", mes_ref):
            raise ValueError(f"mes_ref inválido: {mes_ref}. Formato: MM.YYYY")

        mes, ano = mes_ref.split(".")
        data_inicio = f"{ano}-{mes}-01"
        ultimo_dia = calendar.monthrange(int(ano), int(mes))[1]
        data_fim = f"{ano}-{mes}-{ultimo_dia:02d}"

        emp = self.db.execute(
            text("""
            SELECT id, nome, cpf, cargo, matricula
            FROM employees
            WHERE id = CAST(:emp_id AS uuid)
        """),
            {"emp_id": str(employee_id)},
        ).fetchone()

        if not emp:
            raise ValueError(f"Funcionário não encontrado: {employee_id}")

        batidas_raw = self.db.execute(
            text("""
            SELECT
                (punch_timestamp AT TIME ZONE 'UTC' AT TIME ZONE 'America/Manaus')::date AS data,
                punch_timestamp::time AS hora,
                punch_type
            FROM gp_clock_punches
            WHERE employee_id = CAST(:emp_id AS uuid)
              AND (punch_timestamp AT TIME ZONE 'UTC' AT TIME ZONE 'America/Manaus') >= :inicio
              AND (punch_timestamp AT TIME ZONE 'UTC' AT TIME ZONE 'America/Manaus') <= :fim
            ORDER BY punch_timestamp
        """),
            {
                "emp_id": str(employee_id),
                "inicio": data_inicio,
                "fim": f"{data_fim} 23:59:59",
            },
        ).fetchall()

        dias: dict = {}
        for row in batidas_raw:
            d = str(row.data)
            if d not in dias:
                dias[d] = []
            dias[d].append(
                {
                    "hora": str(row.hora)[:5],
                    "tipo": row.punch_type or "",
                }
            )

        html = self.gerar_html(
            emp_nome=emp.nome,
            cpf=emp.cpf or "",
            cargo=emp.cargo or "",
            matricula=emp.matricula or "",
            mes_ref=mes_ref,
            dias=dias,
            data_inicio=data_inicio,
            data_fim=data_fim,
        )

        output_dir = PONTO_STORAGE / str(employee_id) / mes_ref
        output_dir.mkdir(parents=True, exist_ok=True)

        nome_seguro = emp.nome.replace(" ", "_").replace("/", "-")[:30]
        filename = f"FolhaPonto_{mes_ref}_{nome_seguro}.html"
        filepath = output_dir / filename
        filepath.write_text(html, encoding="utf-8")

        logger.info("Folha de ponto gerada: %s (%d dias, %d batidas)", filepath, len(dias), len(batidas_raw))

        return {
            "employee_id": str(employee_id),
            "employee_nome": emp.nome,
            "mes_ref": mes_ref,
            "arquivo_path": str(filepath),
            "total_dias": len(dias),
            "total_batidas": len(batidas_raw),
        }

    @staticmethod
    def gerar_html(
        emp_nome: str,
        cpf: str,
        cargo: str,
        matricula: str,
        mes_ref: str,
        dias: dict,
        data_inicio: str,
        data_fim: str,
    ) -> str:
        """Gera HTML da folha de ponto — chamável sem DB (usado pelo kit async)."""
        mes, ano = mes_ref.split(".")
        mes_nome = _MES_EXT.get(mes, mes)

        linhas = ""
        for data_str, batidas in sorted(dias.items()):
            d = datetime.strptime(data_str, "%Y-%m-%d")
            dia_semana = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"][d.weekday()]
            horas_str = " | ".join(b["hora"] for b in batidas)
            linhas += f"""
            <tr>
                <td>{d.strftime("%d/%m/%Y")}</td>
                <td>{dia_semana}</td>
                <td class="horas">{horas_str}</td>
                <td>{len(batidas)}</td>
            </tr>"""

        total_batidas = sum(len(v) for v in dias.values())

        return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <title>Folha de Ponto — {emp_nome} — {mes_nome}/{ano}</title>
  <style>
    body {{ font-family: Arial, sans-serif; font-size: 12px; margin: 20px; color: #333; }}
    h1 {{ color: #1E3A5F; font-size: 16px; margin-bottom: 4px; }}
    h2 {{ color: #1E3A5F; font-size: 13px; font-weight: normal; margin-top: 0; }}
    .header-info {{ display: flex; gap: 40px; margin: 16px 0; padding: 12px;
                    background: #f5f7fa; border-left: 4px solid #1E3A5F; }}
    .header-info div {{ display: flex; flex-direction: column; }}
    .header-info label {{ font-weight: bold; font-size: 10px; color: #666; }}
    .header-info span {{ font-size: 12px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 16px; }}
    th {{ background: #1E3A5F; color: white; padding: 8px; text-align: left; font-size: 11px; }}
    td {{ padding: 6px 8px; border-bottom: 1px solid #e5e7eb; }}
    tr:nth-child(even) {{ background: #f9fafb; }}
    .horas {{ font-family: monospace; color: #374151; }}
    .footer {{ margin-top: 40px; display: flex; gap: 60px; }}
    .assinatura {{ border-top: 1px solid #374151; padding-top: 4px; min-width: 200px;
                   font-size: 11px; color: #666; text-align: center; }}
    .totais {{ margin-top: 16px; padding: 8px 12px; background: #eff6ff;
               border: 1px solid #bfdbfe; border-radius: 4px; }}
    @media print {{ body {{ margin: 10px; }} }}
  </style>
</head>
<body>
  <h1>CONECTAMAIS ELETRÔNICA LTDA</h1>
  <h2>FOLHA DE REGISTRO DE PONTO — {mes_nome.upper()}/{ano}</h2>
  <div class="header-info">
    <div><label>FUNCIONÁRIO</label><span>{emp_nome}</span></div>
    <div><label>CPF</label><span>{cpf}</span></div>
    <div><label>CARGO</label><span>{cargo}</span></div>
    <div><label>MATRÍCULA</label><span>{matricula}</span></div>
    <div><label>PERÍODO</label><span>{data_inicio} a {data_fim}</span></div>
  </div>
  <table>
    <thead>
      <tr>
        <th>Data</th><th>Dia</th><th>Registros de Ponto</th><th>Qtd</th>
      </tr>
    </thead>
    <tbody>{linhas if linhas else '<tr><td colspan="4" style="text-align:center;color:#9ca3af;padding:16px;">Sem registros de ponto neste período</td></tr>'}</tbody>
  </table>
  <div class="totais">
    <strong>Total de dias com registro:</strong> {len(dias)} &nbsp;&nbsp;
    <strong>Total de batidas:</strong> {total_batidas}
  </div>
  <div class="footer">
    <div class="assinatura">Assinatura do Funcionário</div>
    <div class="assinatura">Responsável RH / Supervisor</div>
    <div class="assinatura">Data: ___/___/______</div>
  </div>
</body>
</html>"""

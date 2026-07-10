"""
Repository para relatorios operacionais.
"""

from datetime import date

from sqlalchemy import case, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.operacional.models.allocation import Allocation, AllocationStatus
from modules.operacional.models.employee import Employee
from modules.operacional.models.post import Post
from modules.operacional.models.shift import Shift


class ReportsRepository:
    """Repository de relatorios para o modulo operacional."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_coverage(
        self,
        start_date: date,
        end_date: date,
        post_id: str | None = None,
    ) -> list[dict]:
        """Retorna cobertura por posto (alocacoes ativas vs quadro requerido).

        Semantica padronizada (coerente com /postos):
        - Postos considerados: status='active' (mesma conta de "postos ativos"
          em todas as telas — nao a flag is_active, que diverge do status).
        - Vagas: required_headcount REAL do posto (nao a coluna desnormalizada
          current_headcount, que esta podre no banco).
        - coverage_rate = alocacoes ativas / required_headcount (cap em 100).
          Posto com required_headcount=0 (ex. portaria remota) nao tem quadro
          presencial a preencher: coverage_rate=100 e o frontend rotula como
          "sem quadro presencial" (neutro, nunca "em risco").
        """
        posts_query = select(Post.id, Post.name, Post.required_headcount).where(Post.status == "active")
        if post_id:
            posts_query = posts_query.where(Post.id == post_id)

        posts_result = await self.db.execute(posts_query)
        posts = list(posts_result.all())

        alloc_query = (
            select(
                Allocation.post_id,
                func.count(Allocation.id).label("total_allocations"),
                func.sum(
                    case(
                        (Allocation.status == AllocationStatus.ACTIVE.value, 1),
                        else_=0,
                    )
                ).label("active_allocations"),
            )
            .where(Allocation.is_active.is_(True))
            .where(Allocation.start_date <= end_date)
            .where(or_(Allocation.end_date.is_(None), Allocation.end_date >= start_date))
            .group_by(Allocation.post_id)
        )

        if post_id:
            alloc_query = alloc_query.where(Allocation.post_id == post_id)

        alloc_result = await self.db.execute(alloc_query)
        alloc_map = {
            row.post_id: {
                "total_allocations": int(row.total_allocations or 0),
                "active_allocations": int(row.active_allocations or 0),
            }
            for row in alloc_result.all()
        }

        items: list[dict] = []
        for post in posts:
            counts = alloc_map.get(post.id, {"total_allocations": 0, "active_allocations": 0})
            total_allocations = counts["total_allocations"]
            active_allocations = counts["active_allocations"]
            required_headcount = int(post.required_headcount or 0)
            if required_headcount > 0:
                coverage_rate = min(100.0, active_allocations / required_headcount * 100)
            else:
                # Sem quadro presencial requerido: nada a preencher
                coverage_rate = 100.0
            items.append(
                {
                    "post_id": str(post.id),
                    "post_name": post.name,
                    "required_headcount": required_headcount,
                    "total_allocations": total_allocations,
                    "active_allocations": active_allocations,
                    "coverage_rate": round(coverage_rate, 2),
                }
            )

        return items

    async def get_hours(
        self,
        start_date: date,
        end_date: date,
        employee_id: str | None = None,
    ) -> list[dict]:
        """Retorna horas trabalhadas por funcionario.

        Privacidade: o item carrega employee_name = employees.nome (JOIN).
        Sem nome cadastrado, exibe '—' — NUNCA e-mail nem UUID.
        """
        query = (
            select(
                Shift.employee_id,
                Employee.nome.label("employee_name"),
                func.count(Shift.id).label("total_shifts"),
                func.sum(Shift.actual_hours).label("total_hours"),
                func.sum(Shift.overtime_hours).label("overtime_hours"),
            )
            .join(Employee, Employee.id == Shift.employee_id, isouter=True)
            .where(Shift.is_active.is_(True))
            .where(Shift.employee_id.isnot(None))
            .where(Shift.shift_date >= start_date)
            .where(Shift.shift_date <= end_date)
            .group_by(Shift.employee_id, Employee.nome)
        )

        if employee_id:
            query = query.where(Shift.employee_id == employee_id)

        result = await self.db.execute(query)

        # Horas REAIS por batidas do ponto (pares entrada→saída, UTC→Manaus).
        # shifts.actual_hours fica sempre 0 (checkout via sistema é raro) — a fonte
        # honesta de horas trabalhadas é gp_clock_punches (sync Sólides).
        punch_rows = (
            await self.db.execute(
                text(
                    """
                    WITH p AS (
                      SELECT employee_id,
                             (punch_timestamp AT TIME ZONE 'UTC' AT TIME ZONE 'America/Manaus') AS ts,
                             punch_type,
                             ROW_NUMBER() OVER (PARTITION BY employee_id ORDER BY punch_timestamp) AS rn
                      FROM gp_clock_punches
                      WHERE COALESCE(status,'') NOT IN ('rejected','cancelado')
                        AND (punch_timestamp AT TIME ZONE 'UTC' AT TIME ZONE 'America/Manaus')::date
                            BETWEEN :ini AND :fim
                    ),
                    pares AS (
                      SELECT e.employee_id, e.ts AS entrada, s.ts AS saida
                      FROM p e
                      JOIN p s ON s.employee_id = e.employee_id AND s.rn = e.rn + 1
                      WHERE e.punch_type = 'entrada' AND s.punch_type = 'saida'
                        AND s.ts - e.ts BETWEEN interval '1 minute' AND interval '16 hours'
                    )
                    SELECT employee_id::text AS emp,
                           ROUND(SUM(EXTRACT(EPOCH FROM (saida - entrada)) / 3600.0)::numeric, 1) AS horas
                    FROM pares GROUP BY employee_id
                    """
                ),
                {"ini": start_date, "fim": end_date},
            )
        ).all()
        horas_ponto = {r.emp: float(r.horas or 0) for r in punch_rows}

        items = []
        for row in result.all():
            emp = str(row.employee_id)
            items.append(
                {
                    "employee_id": emp,
                    "employee_name": row.employee_name or "—",
                    "total_shifts": int(row.total_shifts or 0),
                    "total_hours": horas_ponto.get(emp, 0.0),
                    "overtime_hours": float(row.overtime_hours or 0.0),
                    "fonte_horas": "batidas de ponto (pares entrada→saída)",
                }
            )
        return items

    async def get_costs(
        self,
        start_date: date,
        end_date: date,
        post_id: str | None = None,
    ) -> list[dict]:
        """Retorna custos estimados por posto."""
        # Custo REAL estimado: horas de PONTO (pares entrada→saída) × salário-base/220 (divisor CLT).
        # shifts.total_pay nunca é preenchido (sempre 0) — a fonte honesta é batidas + salario_base
        # (50/50 employees ativos têm salário-base CCT cadastrado). O posto da hora vem do turno
        # agendado do funcionário no dia da batida.
        cost_sql = text(
            """
            WITH p AS (
              SELECT employee_id,
                     (punch_timestamp AT TIME ZONE 'UTC' AT TIME ZONE 'America/Manaus') AS ts,
                     punch_type,
                     ROW_NUMBER() OVER (PARTITION BY employee_id ORDER BY punch_timestamp) AS rn
              FROM gp_clock_punches
              WHERE COALESCE(status,'') NOT IN ('rejected','cancelado')
                AND (punch_timestamp AT TIME ZONE 'UTC' AT TIME ZONE 'America/Manaus')::date
                    BETWEEN :ini AND :fim
            ),
            pares AS (
              SELECT e.employee_id, e.ts::date AS dia,
                     EXTRACT(EPOCH FROM (s.ts - e.ts)) / 3600.0 AS horas
              FROM p e
              JOIN p s ON s.employee_id = e.employee_id AND s.rn = e.rn + 1
              WHERE e.punch_type = 'entrada' AND s.punch_type = 'saida'
                AND s.ts - e.ts BETWEEN interval '1 minute' AND interval '16 hours'
            ),
            horas_posto AS (
              SELECT COALESCE(sh.post_id, a.post_id) AS post_id, pr.employee_id,
                     SUM(pr.horas) AS horas
              FROM pares pr
              LEFT JOIN LATERAL (
                SELECT post_id FROM shifts s
                WHERE s.employee_id = pr.employee_id AND s.shift_date = pr.dia
                  AND s.is_active AND s.status <> 'cancelled'
                LIMIT 1
              ) sh ON true
              LEFT JOIN LATERAL (
                SELECT post_id FROM allocations a2
                WHERE a2.employee_id = pr.employee_id AND a2.status = 'active' AND a2.is_active
                ORDER BY a2.is_primary DESC LIMIT 1
              ) a ON true
              GROUP BY 1, 2
            )
            SELECT hp.post_id,
                   COUNT(DISTINCT hp.employee_id) AS funcionarios,
                   ROUND(SUM(hp.horas)::numeric, 1) AS total_horas,
                   ROUND(SUM(hp.horas * COALESCE(e.salario_base, 0) / 220.0)::numeric, 2) AS custo
            FROM horas_posto hp
            JOIN employees e ON e.id = hp.employee_id
            WHERE hp.post_id IS NOT NULL
            GROUP BY hp.post_id
            """
        )
        cost_rows = (await self.db.execute(cost_sql, {"ini": start_date, "fim": end_date})).all()
        custo_por_posto = {str(r.post_id): (float(r.custo or 0), float(r.total_horas or 0)) for r in cost_rows}

        query = (
            select(
                Shift.post_id,
                func.count(Shift.id).label("total_shifts"),
                func.sum(Shift.total_pay).label("total_cost"),
            )
            .where(Shift.is_active.is_(True))
            .where(Shift.shift_date >= start_date)
            .where(Shift.shift_date <= end_date)
            .group_by(Shift.post_id)
        )

        if post_id:
            query = query.where(Shift.post_id == post_id)

        result = await self.db.execute(query)
        raw_items = list(result.all())

        post_ids = [row.post_id for row in raw_items]
        post_names: dict[str, str] = {}
        if post_ids:
            posts_result = await self.db.execute(select(Post.id, Post.name).where(Post.id.in_(post_ids)))
            post_names = {str(row.id): row.name for row in posts_result.all()}

        items: list[dict] = []
        for row in raw_items:
            pid = str(row.post_id)
            custo, horas = custo_por_posto.get(pid, (0.0, 0.0))
            items.append(
                {
                    "post_id": pid,
                    "post_name": post_names.get(pid, "Posto"),
                    "total_shifts": int(row.total_shifts or 0),
                    "total_cost": custo,
                    "total_hours_ponto": horas,
                    "fonte_custo": "horas de ponto × salário-base/220 (CLT)",
                }
            )
        return items

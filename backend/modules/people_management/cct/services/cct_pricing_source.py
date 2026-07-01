"""
Fonte ÚNICA de custo de mão de obra da CCT SINDECOMPRESTS 2026.

Todos os motores de precificação (bidding/PRICER, financial/precificacao,
financial/custeio, crm/pricing_cct) devem consumir estas constantes e o
piso lido da tabela `cct_cargos` — nunca hardcodar categorias de vigilância
armada nem encargos de 42%.

Categoria: agentes de portaria/serviços para condomínios (NÃO vigilância).
Referências:
- Piso da categoria: R$1.670 (menor piso da tabela cct_cargos, 52 cargos).
- Periculosidade 30%: SÓ Vigia, Eletricista Alta/Baixa Tensão, Téc. Manut. Máquinas.
- Insalubridade 10%: SÓ Piscineiro, Aux. Controle Pragas.
- Repasse contratual OBRIGATÓRIO 7,5% (CCT Cláusula 2ª §3º) sobre o custo.
- Encargos reais ≈ 61% (INSS 20 + FGTS 8 + RAT 3 + terceiros 5,8 +
  férias 11,11 + 13º 8,33 + rescisão 5).
- VR R$22/dia. VT desconto 4%.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text

# ── CONSTANTES CANÔNICAS CCT SINDECOMPRESTS 2026 ─────────────────────────────
PISO_CATEGORIA = Decimal("1670.00")  # menor piso da tabela cct_cargos (fallback)

# Encargos reais (~61,24%) — NÃO 42%
ENCARGOS = {
    "inss": Decimal("0.20"),
    "fgts": Decimal("0.08"),
    "rat_fap": Decimal("0.03"),
    "terceiros": Decimal("0.058"),
    "ferias_terco": Decimal("0.1111"),
    "decimo_terceiro": Decimal("0.0833"),
    "rescisao": Decimal("0.05"),
}
ENCARGOS_PCT = sum(ENCARGOS.values())  # ≈ 0.6124

# Repasse contratual OBRIGATÓRIO — CCT Cláusula 2ª §3º
REPASSE_PCT = Decimal("0.075")  # 7,5% sobre o custo

# Adicionais (só para cargos com direito, conforme cct_cargos.adicional_tipo)
PERICULOSIDADE_PCT = Decimal("0.30")  # Vigia, Eletricista AT/BT, Téc. Manut. Máquinas
INSALUBRIDADE_PCT = Decimal("0.10")  # Piscineiro, Aux. Controle Pragas
ADICIONAL_NOTURNO_PCT = Decimal("0.20")

# Benefícios
VR_DIA = Decimal("22.00")  # NÃO 26,40 nem 28,00
VT_DESCONTO_PCT = Decimal("0.04")


def repasse(custo: Decimal | float) -> Decimal:
    """Repasse obrigatório de 7,5% (CCT Cláusula 2ª §3º) sobre o custo."""
    return (Decimal(str(custo)) * REPASSE_PCT).quantize(Decimal("0.01"))


async def piso_cargo(db, cargo: str | None = None) -> Decimal:
    """
    Piso salarial lido da tabela `cct_cargos` (fonte única).

    Se `cargo` for informado, busca por nome (ILIKE); senão retorna o MENOR
    piso da convenção vigente (piso da categoria). Fallback: PISO_CATEGORIA.
    """
    try:
        if cargo:
            row = (
                await db.execute(
                    text(
                        "SELECT piso_salarial FROM cct_cargos "
                        "WHERE is_active AND cargo_nome ILIKE :n "
                        "ORDER BY piso_salarial LIMIT 1"
                    ),
                    {"n": f"%{cargo}%"},
                )
            ).first()
            if row and row[0]:
                return Decimal(str(row[0]))
        row = (
            await db.execute(
                text("SELECT MIN(piso_salarial) FROM cct_cargos WHERE is_active")
            )
        ).first()
        if row and row[0]:
            return Decimal(str(row[0]))
    except Exception:
        pass
    return PISO_CATEGORIA


async def adicionais_cargo(db, cargo: str) -> dict:
    """
    Direitos de adicional lidos de `cct_cargos` (fonte única).

    Retorna dict com piso e flags de periculosidade/insalubridade conforme a
    coluna `adicional_tipo` — só quem tem direito recebe o adicional.
    """
    try:
        row = (
            await db.execute(
                text(
                    "SELECT piso_salarial, adicional_tipo, "
                    "adicional_periculosidade_percentual, adicional_insalubridade_percentual "
                    "FROM cct_cargos WHERE is_active AND cargo_nome ILIKE :n "
                    "ORDER BY piso_salarial LIMIT 1"
                ),
                {"n": f"%{cargo}%"},
            )
        ).first()
        if row:
            tipo = (row[1] or "").lower()
            return {
                "piso": Decimal(str(row[0])),
                "periculosidade": "pericul" in tipo,
                "insalubridade": "insalub" in tipo,
                "periculosidade_pct": Decimal(str(row[2])) / 100,
                "insalubridade_pct": Decimal(str(row[3])) / 100,
            }
    except Exception:
        pass
    return {
        "piso": PISO_CATEGORIA,
        "periculosidade": False,
        "insalubridade": False,
        "periculosidade_pct": PERICULOSIDADE_PCT,
        "insalubridade_pct": INSALUBRIDADE_PCT,
    }

"""Multi-CNPJ E8: codifica os server_default de empresa_id (fim do drift).

Achado de integridade (auditoria 20/07 #3): os DEFAULTs de empresa_id em contracts/
employees/hr_payslips foram aplicados FORA do Alembic (script de flip manual). Num DB
novo (DR/staging), `alembic upgrade` criava as colunas SEM default → comportamento
divergente da produção. Esta migration regulariza: o mesmo default que já está na prod
entra no Alembic, então DR/staging reproduz igual.

UUIDs canônicos das empresas (os mesmos hardcoded em E2/E3/E5 e no seed):
- contracts   → Eletrônica (619a3df1-…): contrato novo sem empresa = principal.
- employees   → Patrimonial (7d79ed12-…): mão de obra é a maioria; PJ/Eletrônica é setado
  EXPLÍCITO no autocadastro (nunca depende deste default cego).
- hr_payslips → Patrimonial (7d79ed12-…): folha de 2026-07+ é da Patrimonial; histórico já
  gravado fica Eletrônica (imutável).

Revision ID: multicnpj_e8_server_defaults
Revises: multicnpj_e7_bank_empresa
Create Date: 2026-07-20
"""

from alembic import op

revision = "multicnpj_e8_server_defaults"
down_revision = "multicnpj_e7_bank_empresa"
branch_labels = None
depends_on = None

_ELET = "619a3df1-8bce-49ce-b77a-04f80a0e8491"
_PATR = "7d79ed12-d480-4906-b2e0-2b2c4d299bab"


def upgrade() -> None:
    op.execute(f"ALTER TABLE contracts   ALTER COLUMN empresa_id SET DEFAULT '{_ELET}'")
    op.execute(f"ALTER TABLE employees   ALTER COLUMN empresa_id SET DEFAULT '{_PATR}'")
    op.execute(f"ALTER TABLE hr_payslips ALTER COLUMN empresa_id SET DEFAULT '{_PATR}'")


def downgrade() -> None:
    op.execute("ALTER TABLE contracts   ALTER COLUMN empresa_id DROP DEFAULT")
    op.execute("ALTER TABLE employees   ALTER COLUMN empresa_id DROP DEFAULT")
    op.execute("ALTER TABLE hr_payslips ALTER COLUMN empresa_id DROP DEFAULT")

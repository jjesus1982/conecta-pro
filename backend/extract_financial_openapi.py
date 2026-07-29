#!/usr/bin/env python3
"""
Script para extrair OpenAPI spec completo do módulo FINANCIAL.
Extrai todos os endpoints dos 15 submódulos (~251 endpoints).
"""

import json
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

# Import all financial routers
from modules.financial.controllers import (
    # Contabilidade
    accounting_router,
    # Fluxo de Caixa
    bank_account_router,
    bank_reconciliation_router,
    bank_transaction_router,
    billing_rule_router,
    cashflow_router,
    # Contas a Receber
    customer_router,
    # Fiscal
    fiscal_router,
    # Estoque
    inventory_router,
    payable_router,
    # Compras
    purchase_router,
    receivable_category_router,
    receivable_router,
    # Contas a Pagar
    supplier_router,
)
from modules.financial.costing import router as costing_router


def extract_financial_openapi():
    """Extrai OpenAPI spec completo do módulo FINANCIAL."""

    # Create temporary FastAPI app
    app = FastAPI(
        title="Conecta PRO - Financial Module",
        description="Gestão Financeira Completa - 251 endpoints em 15 submódulos",
        version="1.0.0",
    )

    # Add all financial routers
    print("Registrando routers do módulo FINANCIAL...")

    # Contas a Pagar (Suppliers + Payables)
    app.include_router(supplier_router, prefix="/api/v1/financial/suppliers", tags=["Financial - Suppliers"])
    app.include_router(payable_router, prefix="/api/v1/financial/payables", tags=["Financial - Payables"])

    # Contas a Receber (Customers + Receivables)
    app.include_router(customer_router, prefix="/api/v1/financial/customers", tags=["Financial - Customers"])
    app.include_router(
        receivable_category_router,
        prefix="/api/v1/financial/receivable-categories",
        tags=["Financial - Receivable Categories"],
    )
    app.include_router(receivable_router, prefix="/api/v1/financial/receivables", tags=["Financial - Receivables"])
    app.include_router(
        billing_rule_router, prefix="/api/v1/financial/billing-rules", tags=["Financial - Billing Rules"]
    )

    # Fluxo de Caixa (Banks + Cashflow)
    app.include_router(
        bank_account_router, prefix="/api/v1/financial/bank-accounts", tags=["Financial - Bank Accounts"]
    )
    app.include_router(
        bank_transaction_router, prefix="/api/v1/financial/bank-transactions", tags=["Financial - Bank Transactions"]
    )
    app.include_router(
        bank_reconciliation_router,
        prefix="/api/v1/financial/bank-reconciliation",
        tags=["Financial - Bank Reconciliation"],
    )
    app.include_router(cashflow_router, prefix="/api/v1/financial/cashflow", tags=["Financial - Cashflow"])

    # Compras (Purchase)
    app.include_router(purchase_router, prefix="/api/v1/financial/purchase", tags=["Financial - Purchase"])

    # Estoque (Inventory)
    app.include_router(inventory_router, prefix="/api/v1/financial/inventory", tags=["Financial - Inventory"])

    # Contabilidade (Accounting)
    app.include_router(accounting_router, prefix="/api/v1/financial/accounting", tags=["Financial - Accounting"])

    # Fiscal
    app.include_router(fiscal_router, prefix="/api/v1/financial/fiscal", tags=["Financial - Fiscal"])

    # Custeio ABC
    app.include_router(costing_router, prefix="/api/v1/financial/costing", tags=["Financial - ABC Costing"])

    # Generate OpenAPI schema
    print("Gerando OpenAPI schema...")
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    # Count endpoints
    endpoint_count = len([route for route in app.routes if hasattr(route, "methods")])
    print(f"\n✅ Total de endpoints extraídos: {endpoint_count}")

    # Count by tag
    print("\n📊 Endpoints por submódulo:")
    paths = openapi_schema.get("paths", {})
    tag_counts = {}
    for path_data in paths.values():
        for method_data in path_data.values():
            if isinstance(method_data, dict) and "tags" in method_data:
                for tag in method_data["tags"]:
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1

    for tag, count in sorted(tag_counts.items()):
        print(f"  - {tag}: {count} endpoints")

    # Save to file
    output_file = Path(__file__).parent / "openapi-financial.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(openapi_schema, f, indent=2, ensure_ascii=False)

    print(f"\n✅ OpenAPI spec salvo em: {output_file}")
    print(f"📦 Tamanho: {output_file.stat().st_size / 1024:.1f} KB")

    return openapi_schema


if __name__ == "__main__":
    try:
        extract_financial_openapi()
        print("\n✅ Extração concluída com sucesso!")
    except Exception as e:
        print(f"\n❌ Erro ao extrair OpenAPI: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)

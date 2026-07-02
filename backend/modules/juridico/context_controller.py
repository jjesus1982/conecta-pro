"""Contexto Jurídico / Discovery — endpoints read-only que montam dossiês cross-módulo.

Dá ao Escritório Jurídico IA "acesso a todos os módulos": funcionário, contrato,
cliente e panorama da empresa, reunindo a prova documental para análise e defesa.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_active_user
from core.database import get_db

from modules.juridico import context_engine as CE

router = APIRouter(prefix="/juridico/contexto", tags=["Jurídico - Contexto/Discovery"])


@router.get("/funcionario/{identificador}")
async def contexto_funcionario(
    identificador: str,
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Dossiê probatório completo de um funcionário (id, CPF, matrícula ou nome).

    Cruza DP, folha, ponto, férias, rescisão, benefícios, SST, operacional e GED.
    """
    return await CE.dossie_funcionario(db, identificador)


@router.get("/pessoa")
async def contexto_pessoa(
    nome: str = "",
    cpf: str | None = None,
    cnpj: str | None = None,
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Busca AUTOMÁTICA de uma pessoa em todo o ERP (empregado OU prestador PJ/fornecedor/cliente).

    Varre employees, NFS-e (prestador/tomador), contas a pagar, clientes e GED por nome/CPF/CNPJ.
    """
    return await CE.dossie_pessoa(db, nome=nome, cpf=cpf, cnpj=cnpj)


@router.get("/contrato/{contrato_id}")
async def contexto_contrato(
    contrato_id: str,
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Dossiê de um contrato: partes, vigência, aditivos, SLA."""
    dossie = await CE.dossie_contrato(db, contrato_id)
    if not dossie.get("encontrado"):
        raise HTTPException(status_code=404, detail="Contrato não encontrado")
    return dossie


@router.get("/cliente/{cliente_id}")
async def contexto_cliente(
    cliente_id: str,
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Dossiê de um cliente: condomínios, contratos, faturamento (NFS-e)."""
    dossie = await CE.dossie_cliente(db, cliente_id)
    if not dossie.get("encontrado"):
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return dossie


@router.get("/panorama")
async def contexto_panorama(
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Panorama jurídico da empresa: regime, quadro, certidões e obrigações fiscais."""
    return await CE.panorama_empresa(db)

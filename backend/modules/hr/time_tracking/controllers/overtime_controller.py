"""Controller para Overtime (Horas Extras)."""
# pylint: disable=unused-argument


from fastapi import APIRouter


router = APIRouter(
    prefix="/overtime",
    tags=["Ponto Eletrônico - Horas Extras"],
)



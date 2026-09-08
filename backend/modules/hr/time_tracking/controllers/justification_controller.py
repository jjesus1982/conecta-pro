"""Controller para TimeJustification (Justificativas)."""
# pylint: disable=unused-argument


from fastapi import APIRouter


router = APIRouter(
    prefix="/justifications",
    tags=["Ponto Eletrônico - Justificativas"],
)



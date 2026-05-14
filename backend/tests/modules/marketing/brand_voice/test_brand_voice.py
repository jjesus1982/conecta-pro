"""
Tests do submodulo marketing/brand_voice (Slice 1).

Cobertura sem DB real (mocks AsyncSession) — testa estrutura e logica
sem precisar de banco. Tests de integracao virao apos migration aplicada.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from modules.marketing.brand_voice.models import BrandVoiceConfig
from modules.marketing.brand_voice.repositories import BrandVoiceRepository
from modules.marketing.brand_voice.schemas import (
    BrandVoiceResponse,
    BrandVoiceUpdate,
    PersonalityTrait,
    ToneRule,
)


# ---------------------------------------------------------------- Model


def test_model_tablename_e_marketing_brand_voice() -> None:
    assert BrandVoiceConfig.__tablename__ == "marketing_brand_voice"


def test_model_tem_colunas_obrigatorias() -> None:
    cols = {c.name for c in BrandVoiceConfig.__table__.columns}
    obrigatorios = {
        "id",
        "condominio_id",
        "personality",
        "tone_of_voice",
        "keywords",
        "avoid_list",
        "slogan",
        "updated_by_user_id",
        "created_at",
        "updated_at",
        "is_active",
    }
    assert obrigatorios.issubset(cols), f"faltam: {obrigatorios - cols}"


def test_model_tem_unique_em_condominio_id() -> None:
    """1 brand voice por condominio."""
    from sqlalchemy import UniqueConstraint

    unique = [
        c for c in BrandVoiceConfig.__table__.constraints if isinstance(c, UniqueConstraint)
    ]
    assert any(
        {col.name for col in uc.columns} == {"condominio_id"} for uc in unique
    )


# ---------------------------------------------------------------- Schemas


def test_personality_trait_aceita_dados_validos() -> None:
    trait = PersonalityTrait(label="Profissional", description="Transmitimos expertise")
    assert trait.label == "Profissional"


def test_personality_trait_rejeita_label_curto_demais() -> None:
    with pytest.raises(ValidationError):
        PersonalityTrait(label="X", description="descricao valida ok aqui")


def test_personality_trait_rejeita_descricao_muito_curta() -> None:
    with pytest.raises(ValidationError):
        PersonalityTrait(label="Profissional", description="abc")  # < 5 chars


def test_tone_rule_aceita_dados_validos() -> None:
    rule = ToneRule(title="Formal mas acessivel", description="sem jargoes excessivos")
    assert rule.title == "Formal mas acessivel"


def test_brand_voice_update_aceita_todos_campos_opcionais() -> None:
    """PUT parcial: pode mandar so um campo."""
    payload = BrandVoiceUpdate(slogan="Novo slogan")
    assert payload.slogan == "Novo slogan"
    assert payload.keywords is None
    assert payload.personality is None


def test_brand_voice_update_rejeita_poucas_keywords() -> None:
    """min_length=3 nas keywords."""
    with pytest.raises(ValidationError):
        BrandVoiceUpdate(keywords=["uma", "duas"])  # so 2


def test_brand_voice_update_rejeita_muitas_keywords() -> None:
    """max_length=20 nas keywords."""
    with pytest.raises(ValidationError):
        BrandVoiceUpdate(keywords=[f"keyword-{i}" for i in range(25)])


def test_brand_voice_update_aceita_quantidade_valida_de_keywords() -> None:
    payload = BrandVoiceUpdate(keywords=["a", "b", "c", "d", "e"])
    assert len(payload.keywords) == 5


# ---------------------------------------------------------------- Repository


@pytest.mark.asyncio
async def test_repository_get_by_condominio_chama_session_execute() -> None:
    session = AsyncMock()
    fake_obj = MagicMock()
    session.execute.return_value.scalar_one_or_none = MagicMock(return_value=fake_obj)
    repo = BrandVoiceRepository(session)

    result = await repo.get_by_condominio(uuid.uuid4())

    assert result is fake_obj
    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_repository_get_by_condominio_retorna_none_se_nao_existe() -> None:
    session = AsyncMock()
    session.execute.return_value.scalar_one_or_none = MagicMock(return_value=None)
    repo = BrandVoiceRepository(session)

    result = await repo.get_by_condominio(uuid.uuid4())

    assert result is None


@pytest.mark.asyncio
async def test_repository_update_ignora_campos_none() -> None:
    """PUT parcial: campos None nao devem sobrescrever."""
    session = AsyncMock()
    fake_obj = MagicMock(
        slogan="Slogan antigo",
        keywords=["antiga"],
        updated_by_user_id=None,
    )
    repo = BrandVoiceRepository(session)

    await repo.update(
        fake_obj,
        slogan="Novo slogan",
        keywords=None,  # nao deve atualizar
        updated_by_user_id=uuid.uuid4(),
    )

    # Slogan foi setado, keywords nao
    assert fake_obj.slogan == "Novo slogan"


@pytest.mark.asyncio
async def test_repository_update_aplica_updated_by() -> None:
    session = AsyncMock()
    fake_obj = MagicMock(updated_by_user_id=None)
    repo = BrandVoiceRepository(session)

    user_id = uuid.uuid4()
    await repo.update(fake_obj, updated_by_user_id=user_id, slogan="X")

    assert fake_obj.updated_by_user_id == user_id


# ---------------------------------------------------------------- Controller


def test_controller_router_tem_prefix_correto() -> None:
    from modules.marketing.brand_voice.controllers import router

    assert router.prefix == "/marketing/brand-voice"


def test_controller_tem_endpoint_get() -> None:
    from modules.marketing.brand_voice.controllers import router

    get_routes = [r for r in router.routes if "GET" in r.methods]
    assert len(get_routes) == 1
    assert get_routes[0].name == "get_brand_voice"

"""Feature Store para ML."""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any
from uuid import UUID

import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class FeatureType(Enum):
    """Tipos de features."""

    NUMERIC = "numeric"
    CATEGORICAL = "categorical"
    BOOLEAN = "boolean"
    DATETIME = "datetime"
    TEXT = "text"
    EMBEDDING = "embedding"
    ARRAY = "array"


class FeatureAggregation(Enum):
    """Tipos de agregação."""

    SUM = "sum"
    MEAN = "mean"
    COUNT = "count"
    MIN = "min"
    MAX = "max"
    STD = "std"
    MEDIAN = "median"
    MODE = "mode"
    LAST = "last"
    FIRST = "first"


@dataclass
class FeatureDefinition:
    """Definição de uma feature."""

    name: str
    description: str
    feature_type: FeatureType
    source_table: str
    source_column: str
    aggregation: FeatureAggregation | None = None
    transformation: str | None = None
    default_value: Any = None
    is_derived: bool = False
    dependencies: list[str] = field(default_factory=list)
    version: str = "1.0"
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class FeatureSet:
    """Conjunto de features."""

    id: UUID
    name: str
    description: str
    entity_type: str  # user, transaction, lead, etc.
    features: list[FeatureDefinition]
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class FeatureValue:
    """Valor de uma feature."""

    feature_name: str
    value: Any
    timestamp: datetime
    version: str


class FeatureStore:
    """
    Feature Store para ML.

    Centraliza:
    - Definição de features
    - Cálculo e armazenamento
    - Versionamento
    - Cache
    - Servindo para treinamento e inferência
    """

    # Cache TTL padrão
    DEFAULT_CACHE_TTL = 3600  # 1 hora

    # Features pré-definidas para cada entidade
    USER_FEATURES = {
        "tenure_days": FeatureDefinition(
            name="tenure_days",
            description="Dias desde o cadastro",
            feature_type=FeatureType.NUMERIC,
            source_table="users",
            source_column="created_at",
            transformation="days_since",
        ),
        "total_spent": FeatureDefinition(
            name="total_spent",
            description="Total gasto pelo usuário",
            feature_type=FeatureType.NUMERIC,
            source_table="transactions",
            source_column="amount",
            aggregation=FeatureAggregation.SUM,
        ),
        "avg_order_value": FeatureDefinition(
            name="avg_order_value",
            description="Valor médio por pedido",
            feature_type=FeatureType.NUMERIC,
            source_table="transactions",
            source_column="amount",
            aggregation=FeatureAggregation.MEAN,
        ),
        "order_frequency": FeatureDefinition(
            name="order_frequency",
            description="Frequência de pedidos",
            feature_type=FeatureType.NUMERIC,
            source_table="transactions",
            source_column="id",
            aggregation=FeatureAggregation.COUNT,
        ),
        "last_activity_days": FeatureDefinition(
            name="last_activity_days",
            description="Dias desde última atividade",
            feature_type=FeatureType.NUMERIC,
            source_table="user_activities",
            source_column="created_at",
            aggregation=FeatureAggregation.LAST,
            transformation="days_since",
        ),
        "login_frequency": FeatureDefinition(
            name="login_frequency",
            description="Frequência de logins nos últimos 30 dias",
            feature_type=FeatureType.NUMERIC,
            source_table="user_sessions",
            source_column="id",
            aggregation=FeatureAggregation.COUNT,
        ),
    }

    ENGAGEMENT_FEATURES = {
        "session_duration_avg": FeatureDefinition(
            name="session_duration_avg",
            description="Duração média de sessão",
            feature_type=FeatureType.NUMERIC,
            source_table="user_sessions",
            source_column="duration_seconds",
            aggregation=FeatureAggregation.MEAN,
        ),
        "pages_per_session": FeatureDefinition(
            name="pages_per_session",
            description="Páginas por sessão",
            feature_type=FeatureType.NUMERIC,
            source_table="page_views",
            source_column="id",
            aggregation=FeatureAggregation.MEAN,
        ),
        "notification_response_rate": FeatureDefinition(
            name="notification_response_rate",
            description="Taxa de resposta a notificações",
            feature_type=FeatureType.NUMERIC,
            source_table="notifications",
            source_column="opened",
            transformation="rate",
        ),
    }

    TRANSACTION_FEATURES = {
        "transaction_count_30d": FeatureDefinition(
            name="transaction_count_30d",
            description="Transações nos últimos 30 dias",
            feature_type=FeatureType.NUMERIC,
            source_table="transactions",
            source_column="id",
            aggregation=FeatureAggregation.COUNT,
        ),
        "transaction_value_30d": FeatureDefinition(
            name="transaction_value_30d",
            description="Valor transacionado nos últimos 30 dias",
            feature_type=FeatureType.NUMERIC,
            source_table="transactions",
            source_column="amount",
            aggregation=FeatureAggregation.SUM,
        ),
        "refund_rate": FeatureDefinition(
            name="refund_rate",
            description="Taxa de reembolso",
            feature_type=FeatureType.NUMERIC,
            source_table="transactions",
            source_column="is_refunded",
            transformation="rate",
        ),
    }

    def __init__(
        self,
        cache_enabled: bool = True,
        cache_ttl: int = DEFAULT_CACHE_TTL,
    ) -> None:
        """
        Inicializa o Feature Store.

        Args:
            cache_enabled: Habilitar cache
            cache_ttl: TTL do cache em segundos
        """
        self.cache_enabled = cache_enabled
        self.cache_ttl = cache_ttl
        self._cache: dict[str, tuple[Any, datetime]] = {}
        self._feature_sets: dict[str, FeatureSet] = {}
        # Features solicitadas cuja fonte real não existe neste ERP; usado
        # para o endpoint de scoring sinalizar "features reais indisponíveis"
        # em vez de pontuar sobre valores fabricados.
        self._unsourced_features: set[str] = set()

    @property
    def unsourced_features(self) -> set[str]:
        """Nomes de features solicitadas sem fonte real disponível."""
        return set(self._unsourced_features)

    def features_are_sourced(self, computed: dict[str, Any]) -> bool:
        """Retorna True se ao menos uma feature real (não-default) foi obtida.

        Um scorer deve checar isto antes de pontuar: se a maioria das features
        veio de default por falta de fonte, o score não é confiável.
        """
        real = [
            k
            for k, v in computed.items()
            if not k.endswith("_id") and v is not None and k not in self._unsourced_features
        ]
        return len(real) > 0

    async def get_user_features(
        self,
        db: AsyncSession,
        user_id: int,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        include: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Obtém features de um usuário.

        Args:
            db: Sessão do banco
            user_id: ID do usuário
            start_date: Data inicial
            end_date: Data final
            include: Features específicas a incluir

        Returns:
            Dict com features do usuário
        """
        cache_key = self._get_cache_key("user", user_id, start_date, end_date, include)

        # Verificar cache
        if self.cache_enabled:
            cached = self._get_from_cache(cache_key)
            if cached is not None:
                return cached

        end_date = end_date or datetime.utcnow()
        start_date = start_date or (end_date - timedelta(days=365))

        # Selecionar features
        features_to_compute = include or list(self.USER_FEATURES.keys())

        result = {"user_id": user_id}

        for feature_name in features_to_compute:
            if feature_name in self.USER_FEATURES:
                value = await self._compute_feature(
                    db,
                    self.USER_FEATURES[feature_name],
                    entity_id=user_id,
                    entity_type="user",
                    start_date=start_date,
                    end_date=end_date,
                )
                result[feature_name] = value

        # Adicionar ao cache
        if self.cache_enabled:
            self._add_to_cache(cache_key, result)

        return result

    async def get_engagement_features(
        self,
        db: AsyncSession,
        user_id: int,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        include: list[str] | None = None,
    ) -> dict[str, Any]:
        """Obtém features de engagement de um usuário."""
        end_date = end_date or datetime.utcnow()
        start_date = start_date or (end_date - timedelta(days=30))

        features_to_compute = include or list(self.ENGAGEMENT_FEATURES.keys())

        result = {"user_id": user_id}

        for feature_name in features_to_compute:
            if feature_name in self.ENGAGEMENT_FEATURES:
                value = await self._compute_feature(
                    db,
                    self.ENGAGEMENT_FEATURES[feature_name],
                    entity_id=user_id,
                    entity_type="user",
                    start_date=start_date,
                    end_date=end_date,
                )
                result[feature_name] = value

        return result

    async def get_transaction_features(
        self,
        db: AsyncSession,
        user_id: int,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        include: list[str] | None = None,
    ) -> dict[str, Any]:
        """Obtém features de transação de um usuário."""
        end_date = end_date or datetime.utcnow()
        start_date = start_date or (end_date - timedelta(days=30))

        features_to_compute = include or list(self.TRANSACTION_FEATURES.keys())

        result = {"user_id": user_id}

        for feature_name in features_to_compute:
            if feature_name in self.TRANSACTION_FEATURES:
                value = await self._compute_feature(
                    db,
                    self.TRANSACTION_FEATURES[feature_name],
                    entity_id=user_id,
                    entity_type="user",
                    start_date=start_date,
                    end_date=end_date,
                )
                result[feature_name] = value

        return result

    async def get_features_for_training(
        self,
        db: AsyncSession,
        entity_type: str,
        entity_ids: list[int],
        feature_names: list[str],
        start_date: datetime,
        end_date: datetime,
    ) -> pd.DataFrame:
        """
        Obtém features para treinamento em batch.

        Args:
            db: Sessão do banco
            entity_type: Tipo da entidade
            entity_ids: IDs das entidades
            feature_names: Features a calcular
            start_date: Data inicial
            end_date: Data final

        Returns:
            DataFrame com features
        """
        rows = []

        for entity_id in entity_ids:
            row = {f"{entity_type}_id": entity_id}

            for feature_name in feature_names:
                feature_def = self._get_feature_definition(feature_name)
                if feature_def:
                    value = await self._compute_feature(
                        db,
                        feature_def,
                        entity_id=entity_id,
                        entity_type=entity_type,
                        start_date=start_date,
                        end_date=end_date,
                    )
                    row[feature_name] = value

            rows.append(row)

        return pd.DataFrame(rows)

    async def get_features_for_inference(
        self,
        db: AsyncSession,
        entity_type: str,
        entity_id: int,
        feature_names: list[str],
    ) -> dict[str, Any]:
        """
        Obtém features para inferência em tempo real.

        Args:
            db: Sessão do banco
            entity_type: Tipo da entidade
            entity_id: ID da entidade
            feature_names: Features necessárias

        Returns:
            Dict com features
        """
        result = {f"{entity_type}_id": entity_id}
        now = datetime.utcnow()

        for feature_name in feature_names:
            feature_def = self._get_feature_definition(feature_name)
            if feature_def:
                value = await self._compute_feature(
                    db,
                    feature_def,
                    entity_id=entity_id,
                    entity_type=entity_type,
                    start_date=now - timedelta(days=365),
                    end_date=now,
                )
                result[feature_name] = value

        return result

    async def _compute_feature(
        self,
        db: AsyncSession,
        feature_def: FeatureDefinition,
        entity_id: int,
        entity_type: str,
        start_date: datetime,
        end_date: datetime,
    ) -> Any:
        """Computa valor real de uma feature a partir da fonte no banco.

        Honestidade > invenção: NÃO usa np.random. Onde existe fonte real,
        computa; onde a fonte não existe neste ERP, retorna o default honesto
        (tipicamente None) e marca a feature como sem fonte via
        ``self._unsourced_features``.
        """
        from sqlalchemy import text

        name = feature_def.name

        # tenure_days: fonte real = clients.created_at (idade do cadastro).
        if name == "tenure_days" and entity_type in ("client", "user"):
            try:
                query = text(
                    "SELECT EXTRACT(DAY FROM (now() - created_at))::int "
                    "FROM clients WHERE id = :eid"
                )
                res = await db.execute(query, {"eid": str(entity_id)})
                row = res.first()
                if row is not None and row[0] is not None:
                    return int(row[0])
                return feature_def.default_value
            except Exception:  # noqa: BLE001 - fonte indisponível => honesto
                logger.warning("tenure_days: fonte clients indisponível para %s", entity_id)
                return feature_def.default_value

        # Demais features dependem de tabelas inexistentes neste ERP
        # (users/transactions/user_sessions/page_views/notifications) e
        # inter_transactions não possui vínculo confiável por entidade/cliente.
        # Sem fonte real -> default honesto (não fabricamos ruído).
        self._unsourced_features.add(name)
        return feature_def.default_value

    def _get_feature_definition(self, name: str) -> FeatureDefinition | None:
        """Obtém definição de feature por nome."""
        all_features = {
            **self.USER_FEATURES,
            **self.ENGAGEMENT_FEATURES,
            **self.TRANSACTION_FEATURES,
        }
        return all_features.get(name)

    def _get_cache_key(
        self,
        entity_type: str,
        entity_id: int,
        start_date: datetime | None,
        end_date: datetime | None,
        include: list[str] | None,
    ) -> str:
        """Gera chave de cache."""
        key_parts = [
            entity_type,
            str(entity_id),
            str(start_date),
            str(end_date),
            str(sorted(include) if include else "all"),
        ]
        return hashlib.sha256(":".join(key_parts).encode()).hexdigest()

    def _get_from_cache(self, key: str) -> Any | None:
        """Obtém valor do cache."""
        if key not in self._cache:
            return None

        value, timestamp = self._cache[key]
        if datetime.utcnow() - timestamp > timedelta(seconds=self.cache_ttl):
            del self._cache[key]
            return None

        return value

    def _add_to_cache(self, key: str, value: Any) -> None:
        """Adiciona valor ao cache."""
        self._cache[key] = (value, datetime.utcnow())

    def clear_cache(self) -> None:
        """Limpa cache."""
        self._cache.clear()

    def register_feature_set(self, feature_set: FeatureSet) -> None:
        """Registra conjunto de features."""
        self._feature_sets[feature_set.name] = feature_set
        logger.info(f"Feature set registrado: {feature_set.name}")

    def get_feature_set(self, name: str) -> FeatureSet | None:
        """Obtém conjunto de features por nome."""
        return self._feature_sets.get(name)

    def list_feature_sets(self) -> list[str]:
        """Lista conjuntos de features disponíveis."""
        return list(self._feature_sets.keys())

    def get_feature_metadata(self, name: str) -> dict | None:
        """Obtém metadados de uma feature."""
        feature_def = self._get_feature_definition(name)
        if not feature_def:
            return None

        return {
            "name": feature_def.name,
            "description": feature_def.description,
            "type": feature_def.feature_type.value,
            "source_table": feature_def.source_table,
            "source_column": feature_def.source_column,
            "aggregation": feature_def.aggregation.value if feature_def.aggregation else None,
            "version": feature_def.version,
        }

    def list_available_features(self) -> list[str]:
        """Lista todas as features disponíveis."""
        all_features = {
            **self.USER_FEATURES,
            **self.ENGAGEMENT_FEATURES,
            **self.TRANSACTION_FEATURES,
        }
        return list(all_features.keys())

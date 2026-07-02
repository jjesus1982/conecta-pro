# Mapa do create/update de proposta — extensão para term_options/composition/billing_type (READ-ONLY)

- **Data:** 2026-06-10
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Modo:** 100% READ-ONLY (só leitura; zero escrita/commit/deploy).
- **Objetivo:** Mapear o caminho exato a estender (repo.create + models + schemas + response) sem reintroduzir o bug do client_email (500 na resposta) nem MissingGreenlet (lazy-load async).

---

## 1. `proposal_repository.create` (consertado em eb60ea82) — método inteiro
```python
async def create(self, data: ProposalCreate, created_by_id: str | None = None) -> Proposal:
    # Calcular validade padrao se nao fornecida
    valid_until = data.valid_until
    if not valid_until:
        if data.template_id:
            template = await self.get_template_by_id(data.template_id)
            if template:
                valid_until = date.today() + timedelta(days=template.validity_days)
        if not valid_until:
            valid_until = date.today() + timedelta(days=30)

    proposal = Proposal(
        id=str(uuid4()),
        number=self._generate_proposal_number(),
        version=1,
        opportunity_id=data.opportunity_id, template_id=data.template_id,
        client_name=data.client_name, client_email=data.client_email, client_phone=data.client_phone,
        client_company=data.client_company, client_document=data.client_document, client_address=data.client_address,
        title=data.title, description=data.description, proposal_type=data.proposal_type.value,
        terms_conditions=data.terms_conditions, payment_terms=data.payment_terms,
        payment_conditions=data.payment_conditions, installments=data.installments, notes=data.notes,
        discount_type=data.discount_type.value if data.discount_type else None,
        discount_value=data.discount_value, discount_reason=data.discount_reason, taxes=data.taxes,
        valid_until=valid_until, status=ProposalStatus.DRAFT.value, created_by_id=created_by_id,
    )

    # Itens em memória — _create_item já calcula item.total (sem IO)
    items = [self._create_item(proposal.id, item_data, i) for i, item_data in enumerate(data.items)]

    # Atribui a coleção em memória e calcula os totais SEM lazy-load async
    proposal.items = items
    proposal.calculate_totals()

    # Persiste tudo de uma vez (ATÔMICO): cascade='all, delete-orphan' adiciona os itens.
    self.db.add(proposal)
    try:
        await self.db.commit()
    except Exception:
        await self.db.rollback()
        raise

    # Eager-load dos itens dentro do greenlet (evita lazy-load na serializacao da resposta)
    await self.db.refresh(proposal, ["items"])
    logger.info(f"Proposal criada: {proposal.id} ({proposal.number})")
    return proposal
```
**Padrão a replicar p/ term_options:** montar `term_options = [self._create_term_option(proposal.id, t, i) for i,t in enumerate(data.term_options)]` → `proposal.term_options = term_options` (memória) → `db.add` (cascade persiste) → trocar `refresh(["items"])` por **`refresh(["items","term_options"])`**. Commit único já cobre tudo.

## 2. Model `Proposal` — relationships (padrão items)
```python
from core.models import Base   # sem mixin; created_at/updated_at são colunas explícitas

class Proposal(Base):
    __tablename__ = "proposals"
    id = Column(UUID(as_uuid=False), primary_key=True)   # string uuid, setado no app
    ...
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    items     = relationship("ProposalItem", back_populates="proposal", cascade="all, delete-orphan")
    versions  = relationship("Proposal", backref="parent", remote_side=[id])
    approvals = relationship("ProposalApproval", back_populates="proposal", cascade="all, delete-orphan")
```
➡️ **Adicionar (espelhando `items`):**
`term_options = relationship("ProposalTermOption", back_populates="proposal", cascade="all, delete-orphan")`.

## 3. Model `ProposalItem` (espelho p/ ProposalTermOption)
```python
class ProposalItem(Base):
    __tablename__ = "proposal_items"
    id = Column(UUID(as_uuid=False), primary_key=True)        # str uuid (app-set)
    proposal_id = Column(UUID(as_uuid=False), ForeignKey("proposals.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(50), nullable=True)
    name = Column(String(255), nullable=False)
    ... (quantity/unit_price/discount_percent/total Float; sort_order; is_optional/is_active Boolean) ...
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    proposal = relationship("Proposal", back_populates="items")
```
➡️ **`ProposalTermOption`** (mesmo estilo): `id=UUID(as_uuid=False) PK` (app-set via `str(uuid4())`, igual ProposalItem) + `proposal_id` FK CASCADE + `term_months Integer`, `monthly_value Float`, `composition` (JSONB), `is_recommended Boolean`, `sort_order Integer`, `created_at/updated_at` + `proposal = relationship("Proposal", back_populates="term_options")`.
> ⚠️ **Nota de consistência:** a migration sprint94 criou `proposal_term_options.id` como `uuid` com default `gen_random_uuid()`. Mirrorando ProposalItem (`as_uuid=False`, id setado no app), o default do banco fica inerte — funciona. Alternativa: `as_uuid=True` + omitir id no app (DB preenche). Recomendado: mirrorar ProposalItem (app-set) p/ consistência com o `_create_item`.

## 4. Schema do item + iteração + helper
```python
class ProposalItemBase(BaseModel):
    code: str | None = Field(None, max_length=50)
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    unit: str = Field(default="un", max_length=20)
    quantity: float = Field(default=1.0, ge=0)
    unit_price: float = Field(default=0.0, ge=0)
    discount_percent: float = Field(default=0.0, ge=0, le=100)
    is_optional: bool = False

class ProposalItemCreate(ProposalItemBase):
    sort_order: int = 0
```
**Helper repo (`_create_item`) — espelho p/ `_create_term_option`:**
```python
def _create_item(self, proposal_id: str, data: ProposalItemCreate, sort_order: int) -> ProposalItem:
    item = ProposalItem(id=str(uuid4()), proposal_id=proposal_id, code=data.code, name=data.name,
        description=data.description, unit=data.unit, quantity=data.quantity, unit_price=data.unit_price,
        discount_percent=data.discount_percent, is_optional=data.is_optional,
        sort_order=data.sort_order if data.sort_order else sort_order)
    item.calculate_total()
    return item
```
- **Onde adiciono o processamento:** em `ProposalCreate` adicionar `term_options: list[ProposalTermOptionCreate] = []` (igual `items: list[ProposalItemCreate] = []`, linha 175/186); e no `repo.create` o loop espelho (ponto §1). O **controller chama `await repo.create(data, ...)` direto** (proposal_controller:49) — nenhuma mudança no controller necessária.

## 5. Análise da RESPONSE (evitar 500, lição client_email)
- `ProposalResponse(BaseModel)` tem `model_config = ConfigDict(from_attributes=True)` (linha 255). **Pydantic v2 só lê os campos DECLARADOS** e ignora atributos extras do ORM.
- ➡️ **Adicionar `billing_type`/`reference_number` (colunas) e a relationship `term_options` ao MODEL NÃO quebra** `ProposalResponse`/`ProposalDetailResponse` por padrão (campos não declarados são ignorados). **Sem 500 só por adicionar.**
- O bug do `client_email` foi diferente: o campo **estava declarado** como `str` (não-nulável) e o valor virou `None` → erro. A regra: campo declarado na response deve aceitar o valor.
- **`ProposalDetailResponse(ProposalResponse)`** já tem `items: list[ProposalItemResponse] = []` (linha 331) → serializa items (por isso o `refresh(["items"])`).

### O que mudar na response SE for expor os novos campos (para NÃO dar 500)
1. `billing_type: str | None = None` (ou default `"recurring"`) e `reference_number: str | None = None` em **`ProposalResponse`** — nuláveis/com default → seguro mesmo se None.
2. `term_options: list[ProposalTermOptionResponse] = []` em **`ProposalDetailResponse`** (+ criar `ProposalTermOptionResponse`).
3. 🔴 **OBRIGATÓRIO:** se expuser `term_options` na response, **eager-load** no repo (`refresh(proposal, ["items","term_options"])` no create, e o equivalente no get_by_id/list). Sem isso → **lazy-load async → MissingGreenlet 500** (mesma classe do bug original). Esta é a única armadilha a evitar.

---

## Resumo (o que vou fazer no próximo passo, sem bug)
1. **Model** `ProposalTermOption` espelhando `ProposalItem` (as_uuid=False, app-set id) + relationship `term_options` (cascade all,delete-orphan) em Proposal + colunas `billing_type`/`reference_number` no model.
2. **Schema** `ProposalTermOptionCreate` espelhando `ProposalItemCreate` + `term_options: list[...] = []` em ProposalCreate.
3. **Repo.create** (+update/new_version): loop `_create_term_option`, `proposal.term_options = [...]`, e `refresh(["items","term_options"])`.
4. **Response:** adicionar `billing_type`/`reference_number` nuláveis em ProposalResponse e `term_options` em ProposalDetailResponse **com eager-load** (senão 500).
- Nenhum bug pré-existente novo encontrado; a estrutura está limpa. A única regra crítica é o eager-load do term_options na response.

*Read-only: leitura de create/_create_item, model Proposal/ProposalItem, schemas ProposalItemCreate/ProposalResponse/ProposalDetailResponse, controller. Nada escrito.*

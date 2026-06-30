"""Modelos do módulo CRM."""

from .activity_task import CrmActivity, CrmTask
from .commission import (
    Commission,
    CommissionPayment,
    CommissionRule,
    CommissionStatus,
    CommissionSummary,
    CommissionTrigger,
    CommissionType,
    PaymentMethod,
    SellerCommissionRule,
)
from .contract import (
    AddendumType,
    AdjustmentIndex,
    Contract,
    ContractAddendum,
    ContractItem,
    ContractSLAReport,
    ContractStatus,
    ContractTemplate,
    ContractType,
    ServiceType,
)
from .growth import (
    CrmBooking,
    CrmBookingLink,
    CrmCustomProperty,
    CrmForm,
    CrmFormSubmission,
    CrmProduct,
    CrmQuota,
    CrmScoringRule,
    CrmSegment,
    CrmSequence,
    CrmSequenceEnrollment,
    CrmWorkflow,
    CrmWorkflowRun,
)
from .lead import Lead, LeadSource, LeadStatus
from .marketing_content import ContentStatus, MarketingContentDraft
from .opportunity import (
    LossReason,
    Opportunity,
    OpportunityPriority,
    OpportunityStage,
)
from .proposal import (
    ApprovalAction,
    DiscountType,
    Proposal,
    ProposalApproval,
    ProposalItem,
    ProposalStatus,
    ProposalTemplate,
    ProposalType,
)

__all__ = [
    # Lead
    "Lead",
    "LeadStatus",
    "LeadSource",
    # Marketing content
    "MarketingContentDraft",
    "ContentStatus",
    # Timeline + Tarefas
    "CrmActivity",
    "CrmTask",
    # Opportunity
    "Opportunity",
    "OpportunityStage",
    "OpportunityPriority",
    "LossReason",
    # Proposal
    "Proposal",
    "ProposalItem",
    "ProposalTemplate",
    "ProposalApproval",
    "ProposalStatus",
    "ProposalType",
    "DiscountType",
    "ApprovalAction",
    # Commission
    "Commission",
    "CommissionRule",
    "CommissionPayment",
    "CommissionSummary",
    "SellerCommissionRule",
    "CommissionType",
    "CommissionTrigger",
    "CommissionStatus",
    "PaymentMethod",
    # Contract
    "Contract",
    "ContractItem",
    "ContractTemplate",
    "ContractAddendum",
    "ContractSLAReport",
    "ContractType",
    "ContractStatus",
    "AdjustmentIndex",
    "AddendumType",
    "ServiceType",
]

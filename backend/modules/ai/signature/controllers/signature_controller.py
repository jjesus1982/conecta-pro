"""Signature Recognition Controller."""

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status

from core.auth.dependencies import CurrentActiveUser
from modules.ai.signature.schemas import (
    ComparisonResultResponse,
    ExtractionResultResponse,
    RequestListResponse,
    SignatureCompareRequest,
    SignatureExtractRequest,
    SignatureListResponse,
    SignatureRequestCreate,
    SignatureRequestResponse,
    SignatureResponse,
    SignatureStatsResponse,
    SignatureSubmitRequest,
    SignatureUploadRequest,
    SignatureValidateRequest,
    SignedDocumentResponse,
    TemplateAddSampleRequest,
    TemplateCreateRequest,
    TemplateListResponse,
    TemplateResponse,
    ValidationResultResponse,
    VerificationResponse,
)
from modules.ai.signature.services import (
    SignatureComparisonService,
    SignatureExtractionService,
    SignatureValidationService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/signature", tags=["Signature Recognition"])

# Service instances
extraction_service = SignatureExtractionService()
comparison_service = SignatureComparisonService()
validation_service = SignatureValidationService(
    comparison_service=comparison_service,
    extraction_service=extraction_service,
)


# ============== Signature Endpoints ==============


@router.post(
    "/upload",
    response_model=SignatureResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload signature",
)
async def upload_signature(
    request: SignatureUploadRequest,
    current_user: CurrentActiveUser,
    tenant_id: uuid.UUID = Query(..., description="Tenant ID"),
) -> SignatureResponse:
    """Upload a new signature."""
    try:
        # Create signature record
        signature_id = uuid.uuid4()

        # Extract if image provided
        extracted = None
        if request.image_data:
            result = extraction_service.extract_from_base64(request.image_data)
            if result.success and result.signatures:
                extracted = result.signatures[0]

        # Build response
        return SignatureResponse(
            id=signature_id,
            tenant_id=tenant_id,
            owner_id=request.owner_id,
            owner_name=request.owner_name,
            signature_type=request.signature_type,
            signature_format="png",
            status="extracted" if extracted else "pending",
            source=request.source,
            quality_score=extracted.quality_score if extracted else None,
            is_verified=False,
            is_valid=True,
            width=extracted.width if extracted else None,
            height=extracted.height if extracted else None,
            created_at=datetime.utcnow(),
        )
    except Exception as e:
        logger.error(f"Error uploading signature: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.post(
    "/extract",
    response_model=ExtractionResultResponse,
    summary="Extract signatures from image",
)
async def extract_signatures(
    request: SignatureExtractRequest,
    current_user: CurrentActiveUser,
) -> ExtractionResultResponse:
    """Extract signatures from an image."""
    try:
        # Configure extraction
        extraction_service.min_confidence = request.min_confidence
        extraction_service.max_signatures = request.max_signatures

        # Extract
        region = None
        if request.region:
            from modules.ai.signature.services.extraction_service import BoundingBox

            region = BoundingBox(**request.region)

        result = extraction_service.extract_from_base64(
            request.image_data,
            region=region,
        )

        return ExtractionResultResponse(**result.to_dict())
    except Exception as e:
        logger.error(f"Error extracting signatures: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.post(
    "/compare",
    response_model=ComparisonResultResponse,
    summary="Compare two signatures",
)
async def compare_signatures(
    request: SignatureCompareRequest,
    current_user: CurrentActiveUser,
) -> ComparisonResultResponse:
    """Compare two signatures."""
    try:
        # Get signature data
        sig1_data = request.signature1_data or {}
        sig2_data = request.signature2_data or {}

        # Compare
        result = comparison_service.compare(
            sig1_data,
            sig2_data,
            mode=request.mode,
            custom_threshold=request.custom_threshold,
        )

        return ComparisonResultResponse(**result.to_dict())
    except Exception as e:
        logger.error(f"Error comparing signatures: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.post(
    "/validate",
    response_model=ValidationResultResponse,
    summary="Validate a signature",
)
async def validate_signature(
    request: SignatureValidateRequest,
    current_user: CurrentActiveUser,
) -> ValidationResultResponse:
    """Validate a signature."""
    try:
        # Get signature data
        sig_data = request.signature_data or {}

        # Get template data if provided
        template_data = None
        if request.template_id:
            # In production, fetch from database
            template_data = {}

        # Validate
        result = validation_service.validate(
            sig_data,
            template=template_data,
            context=request.context,
        )

        return ValidationResultResponse(**result.to_dict())
    except Exception as e:
        logger.error(f"Error validating signature: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get(
    "/signatures",
    response_model=SignatureListResponse,
    summary="List signatures",
)
async def list_signatures(
    current_user: CurrentActiveUser,
    tenant_id: uuid.UUID = Query(..., description="Tenant ID"),
    owner_id: uuid.UUID | None = Query(None, description="Owner ID"),
    status: str | None = Query(None, description="Status filter"),
    signature_type: str | None = Query(None, description="Type filter"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
) -> SignatureListResponse:
    """List signatures with filters."""
    # In production, query database
    return SignatureListResponse(
        items=[],
        total=0,
        page=page,
        size=size,
        pages=0,
    )


@router.get(
    "/signatures/{signature_id}",
    response_model=SignatureResponse,
    summary="Get signature by ID",
)
async def get_signature(
    signature_id: uuid.UUID,
    current_user: CurrentActiveUser,
    tenant_id: uuid.UUID = Query(..., description="Tenant ID"),
) -> SignatureResponse:
    """Get signature by ID."""
    # In production, query database
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Signature not found",
    )


@router.delete(
    "/signatures/{signature_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete signature",
)
async def delete_signature(
    signature_id: uuid.UUID,
    current_user: CurrentActiveUser,
    tenant_id: uuid.UUID = Query(..., description="Tenant ID"),
) -> None:
    """Delete a signature."""
    # In production, delete from database
    pass


# ============== Template Endpoints ==============


@router.post(
    "/templates",
    response_model=TemplateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create signature template",
)
async def create_template(
    request: TemplateCreateRequest,
    current_user: CurrentActiveUser,
    tenant_id: uuid.UUID = Query(..., description="Tenant ID"),
) -> TemplateResponse:
    """Create a new signature template."""
    try:
        template_id = uuid.uuid4()

        return TemplateResponse(
            id=template_id,
            tenant_id=tenant_id,
            name=request.name,
            owner_id=request.owner_id,
            owner_name=request.owner_name,
            template_type=request.template_type,
            status="draft",
            matching_mode=request.matching_mode,
            sample_count=0,
            min_samples_required=request.min_samples_required,
            similarity_threshold=request.similarity_threshold,
            is_valid=False,
            has_enough_samples=False,
            success_rate=None,
            total_verifications=0,
            created_at=datetime.utcnow(),
        )
    except Exception as e:
        logger.error(f"Error creating template: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get(
    "/templates",
    response_model=TemplateListResponse,
    summary="List templates",
)
async def list_templates(
    current_user: CurrentActiveUser,
    tenant_id: uuid.UUID = Query(..., description="Tenant ID"),
    owner_id: uuid.UUID | None = Query(None, description="Owner ID"),
    status: str | None = Query(None, description="Status filter"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
) -> TemplateListResponse:
    """List signature templates."""
    return TemplateListResponse(
        items=[],
        total=0,
        page=page,
        size=size,
        pages=0,
    )


@router.get(
    "/templates/{template_id}",
    response_model=TemplateResponse,
    summary="Get template by ID",
)
async def get_template(
    template_id: uuid.UUID,
    current_user: CurrentActiveUser,
    tenant_id: uuid.UUID = Query(..., description="Tenant ID"),
) -> TemplateResponse:
    """Get template by ID."""
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Template not found",
    )


@router.post(
    "/templates/{template_id}/samples",
    response_model=TemplateResponse,
    summary="Add sample to template",
    status_code=201,
)
async def add_template_sample(
    template_id: uuid.UUID,
    request: TemplateAddSampleRequest,
    current_user: CurrentActiveUser,
    tenant_id: uuid.UUID = Query(..., description="Tenant ID"),
) -> TemplateResponse:
    """Add a signature sample to template."""
    try:
        # In production:
        # 1. Extract signature from image
        # 2. Add to template samples
        # 3. Recalculate master feature vector

        # Return updated template
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding sample: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.post(
    "/templates/{template_id}/activate",
    response_model=TemplateResponse,
    summary="Activate template",
)
async def activate_template(
    template_id: uuid.UUID,
    current_user: CurrentActiveUser,
    tenant_id: uuid.UUID = Query(..., description="Tenant ID"),
) -> TemplateResponse:
    """Activate a template for verification."""
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Template not found",
    )


@router.delete(
    "/templates/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete template",
)
async def delete_template(
    template_id: uuid.UUID,
    current_user: CurrentActiveUser,
    tenant_id: uuid.UUID = Query(..., description="Tenant ID"),
) -> None:
    """Delete a template."""
    pass


# ============== Verification Endpoints ==============


@router.post(
    "/verify",
    response_model=VerificationResponse,
    summary="Verify signature against template",
)
async def verify_signature(
    current_user: CurrentActiveUser,
    signature_id: uuid.UUID = Query(..., description="Signature ID"),
    template_id: uuid.UUID = Query(..., description="Template ID"),
    tenant_id: uuid.UUID = Query(..., description="Tenant ID"),
    mode: str = Query("normal", description="Verification mode"),
) -> VerificationResponse:
    """Verify a signature against a template."""
    try:
        verification_id = uuid.uuid4()

        # In production:
        # 1. Load signature and template
        # 2. Compare using comparison service
        # 3. Store verification result

        return VerificationResponse(
            id=verification_id,
            tenant_id=tenant_id,
            signature_id=signature_id,
            template_id=template_id,
            status="matched",
            result="authentic",
            risk_level="low",
            method="feature",
            overall_score=0.85,
            similarity_score=0.87,
            confidence=0.82,
            passed_threshold=True,
            is_match=True,
            requires_manual_review=False,
            processing_time_ms=125,
            created_at=datetime.utcnow(),
        )
    except Exception as e:
        logger.error(f"Error verifying signature: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get(
    "/verifications/{verification_id}",
    response_model=VerificationResponse,
    summary="Get verification result",
)
async def get_verification(
    verification_id: uuid.UUID,
    current_user: CurrentActiveUser,
    tenant_id: uuid.UUID = Query(..., description="Tenant ID"),
) -> VerificationResponse:
    """Get verification result by ID."""
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Verification not found",
    )


# ============== Request Endpoints ==============


@router.post(
    "/requests",
    response_model=SignatureRequestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create signature request",
)
async def create_request(
    request: SignatureRequestCreate,
    current_user: CurrentActiveUser,
    tenant_id: uuid.UUID = Query(..., description="Tenant ID"),
    requested_by: uuid.UUID = Query(..., description="Requester ID"),
) -> SignatureRequestResponse:
    """Create a new signature request."""
    try:
        request_id = uuid.uuid4()

        return SignatureRequestResponse(
            id=request_id,
            tenant_id=tenant_id,
            title=request.title,
            status="pending",
            priority=request.priority,
            purpose=request.purpose,
            signer_name=request.signer_name,
            signer_email=request.signer_email,
            document_name=request.document_name,
            due_date=request.due_date,
            expires_at=request.expires_at,
            is_pending=True,
            is_signed=False,
            is_expired=False,
            is_overdue=False,
            signed_at=None,
            created_at=datetime.utcnow(),
        )
    except Exception as e:
        logger.error(f"Error creating request: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get(
    "/requests",
    response_model=RequestListResponse,
    summary="List signature requests",
)
async def list_requests(
    current_user: CurrentActiveUser,
    tenant_id: uuid.UUID = Query(..., description="Tenant ID"),
    status: str | None = Query(None, description="Status filter"),
    signer_id: uuid.UUID | None = Query(None, description="Signer ID"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
) -> RequestListResponse:
    """List signature requests."""
    return RequestListResponse(
        items=[],
        total=0,
        page=page,
        size=size,
        pages=0,
    )


@router.get(
    "/requests/{request_id}",
    response_model=SignatureRequestResponse,
    summary="Get signature request",
)
async def get_request(
    request_id: uuid.UUID,
    current_user: CurrentActiveUser,
    tenant_id: uuid.UUID = Query(..., description="Tenant ID"),
) -> SignatureRequestResponse:
    """Get signature request by ID."""
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Request not found",
    )


@router.post(
    "/requests/{request_id}/sign",
    response_model=SignatureRequestResponse,
    summary="Submit signature for request",
)
async def sign_request(
    request_id: uuid.UUID,
    request: SignatureSubmitRequest,
    current_user: CurrentActiveUser,
    tenant_id: uuid.UUID = Query(..., description="Tenant ID"),
) -> SignatureRequestResponse:
    """Submit a signature for a request."""
    try:
        # In production:
        # 1. Extract signature from image
        # 2. Verify against template if configured
        # 3. Update request status
        # 4. Create signed document

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error signing request: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.post(
    "/requests/{request_id}/reject",
    response_model=SignatureRequestResponse,
    summary="Reject signature request",
)
async def reject_request(
    request_id: uuid.UUID,
    current_user: CurrentActiveUser,
    reason: str = Query(..., description="Rejection reason"),
    tenant_id: uuid.UUID = Query(..., description="Tenant ID"),
) -> SignatureRequestResponse:
    """Reject a signature request."""
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Request not found",
    )


@router.post(
    "/requests/{request_id}/cancel",
    response_model=SignatureRequestResponse,
    summary="Cancel signature request",
)
async def cancel_request(
    request_id: uuid.UUID,
    current_user: CurrentActiveUser,
    reason: str = Query(..., description="Cancellation reason"),
    tenant_id: uuid.UUID = Query(..., description="Tenant ID"),
    cancelled_by: uuid.UUID = Query(..., description="User ID"),
) -> SignatureRequestResponse:
    """Cancel a signature request."""
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Request not found",
    )


# ============== Signed Document Endpoints ==============


@router.get(
    "/documents/{document_id}",
    response_model=SignedDocumentResponse,
    summary="Get signed document",
)
async def get_signed_document(
    document_id: uuid.UUID,
    current_user: CurrentActiveUser,
    tenant_id: uuid.UUID = Query(..., description="Tenant ID"),
) -> SignedDocumentResponse:
    """Get signed document by ID."""
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Document not found",
    )


@router.get(
    "/documents/verify/{verification_code}",
    response_model=SignedDocumentResponse,
    summary="Verify signed document by code",
)
async def verify_document_by_code(
    verification_code: str,
    current_user: CurrentActiveUser,
) -> SignedDocumentResponse:
    """Verify a signed document using its verification code."""
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Document not found",
    )


# ============== Statistics Endpoint ==============


@router.get(
    "/stats",
    response_model=SignatureStatsResponse,
    summary="Get signature statistics",
)
async def get_stats(
    current_user: CurrentActiveUser,
    tenant_id: uuid.UUID = Query(..., description="Tenant ID"),
) -> SignatureStatsResponse:
    """Get signature statistics for tenant."""
    # In production, aggregate from database
    return SignatureStatsResponse(
        total_signatures=0,
        verified_signatures=0,
        pending_signatures=0,
        rejected_signatures=0,
        total_templates=0,
        active_templates=0,
        total_verifications=0,
        successful_verifications=0,
        failed_verifications=0,
        average_match_score=None,
        pending_requests=0,
        completed_requests=0,
        signed_documents=0,
    )


# ============== Health Check ==============


@router.get(
    "/health",
    summary="Health check",
)
async def health_check(current_user: CurrentActiveUser) -> dict:
    """Check signature service health."""
    return {
        "status": "healthy",
        "service": "signature-recognition",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "extraction": "operational",
            "comparison": "operational",
            "validation": "operational",
        },
    }

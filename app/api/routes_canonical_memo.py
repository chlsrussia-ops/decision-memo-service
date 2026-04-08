"""Canonical Memo API — Phase 6 standard endpoints.

These wrap the existing DMS logic with canonical paths
matching the Commerce OS blueprint.
"""
from fastapi import APIRouter, HTTPException, Query

from app.schemas.decision import HumanAction
from app.services import memo_service, decision_store

router = APIRouter(prefix="/api/memo", tags=["canonical-memo"])


@router.post("/generate")
async def generate_memo(product_id: str = Query(...)):
    """Generate decision memo for a product — canonical endpoint."""
    try:
        memo = await memo_service.generate_memo(product_id=product_id)
        return memo
    except Exception as e:
        raise HTTPException(500, f"Memo generation failed: {e}")


@router.get("/{product_id}")
async def get_memo(product_id: str):
    """Get decision memo for product."""
    try:
        memo = await memo_service.generate_memo(product_id=product_id)
        return memo
    except Exception as e:
        raise HTTPException(500, f"Memo retrieval failed: {e}")


@router.get("/review-queue")
async def review_queue(limit: int = Query(50, ge=1, le=200)):
    """Get prioritized review queue — products needing human decision."""
    from app.api.routes_decision_memo import _collect_product_ids
    from app.services import prioritization_service
    
    product_ids = await _collect_product_ids()
    memos = await memo_service.generate_memos_batch(product_ids[:limit])
    sorted_memos = prioritization_service.rank_memos(memos)
    
    return {
        "queue": [
            {
                "product_id": m.product_id,
                "recommended_action": m.recommended_action,
                "confidence": m.confidence,
                "summary": m.summary,
                "red_flags": len(m.red_flags),
                "missing_data": len(m.unknowns),
            }
            for m in sorted_memos
        ],
        "total": len(sorted_memos),
    }


@router.post("/{product_id}/approve")
async def approve_memo(product_id: str, note: str = Query("")):
    """Operator approves product — records human decision."""
    result = decision_store.save_decision(
        product_id=product_id,
        action=HumanAction.APPROVE,
        note=note or "Approved by operator",
    )
    return {"status": "approved", "product_id": product_id, "decision": result}


@router.post("/{product_id}/reject")
async def reject_memo(product_id: str, note: str = Query("")):
    """Operator rejects product."""
    result = decision_store.save_decision(
        product_id=product_id,
        action=HumanAction.REJECT,
        note=note or "Rejected by operator",
    )
    return {"status": "rejected", "product_id": product_id, "decision": result}


@router.post("/{product_id}/observe")
async def observe_memo(product_id: str, note: str = Query("")):
    """Operator marks product for observation — watch but don't act."""
    result = decision_store.save_decision(
        product_id=product_id,
        action=HumanAction.WATCH,
        note=note or "Marked for observation",
    )
    return {"status": "observing", "product_id": product_id, "decision": result}

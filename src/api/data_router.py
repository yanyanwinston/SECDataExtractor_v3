"""FastAPI router exposing the `/data` endpoints."""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from .data_service import (
    DataRetrievalError,
    FilingRetrievalService,
    StatementRetrievalService,
)


router = APIRouter(prefix="/data", tags=["data"])
_filing_service = FilingRetrievalService()
_statement_service = StatementRetrievalService(_filing_service)
logger = logging.getLogger(__name__)


@router.get("/{ticker}/filings")
def list_filings(
    ticker: str,
    start_date: Optional[date] = Query(None, alias="startDate"),
    end_date: Optional[date] = Query(None, alias="endDate"),
    document_type: Optional[str] = Query(None, alias="documentType"),
):
    """Return filings for ``ticker`` matching the requested date range."""

    logger.info(
        "Listing filings for ticker=%s start=%s end=%s documentType=%s",
        ticker,
        start_date,
        end_date,
        document_type,
    )
    try:
        records = _filing_service.get_filings_by_date_range(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            document_type=document_type,
        )
    except DataRetrievalError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    effective_end = end_date or date.today()
    logger.info("Returning %d filings for ticker=%s", len(records), ticker)
    response = {
        "ticker": ticker.upper(),
        "query": {
            "startDate": start_date.isoformat() if start_date else None,
            "endDate": effective_end.isoformat(),
            "documentType": document_type.upper() if document_type else "ALL",
        },
        "count": len(records),
        "filings": [record.to_dict() for record in records],
    }
    return response


@router.get("/{ticker}/filings/latest")
def latest_filings(
    ticker: str,
    limit: int = Query(4, alias="limit", ge=1, le=8),
    document_type: Optional[str] = Query(None, alias="documentType"),
):
    """Return ``limit`` most recent filings for ``ticker``."""

    logger.info(
        "Fetching latest filings for ticker=%s limit=%s documentType=%s",
        ticker,
        limit,
        document_type,
    )
    try:
        records = _filing_service.get_latest_filings(
            ticker=ticker,
            limit=limit,
            document_type=document_type,
        )
    except DataRetrievalError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    logger.info("Returning %d latest filings for ticker=%s", len(records), ticker)
    response = {
        "ticker": ticker.upper(),
        "query": {
            "limit": limit,
            "documentType": document_type.upper() if document_type else "ALL",
        },
        "count": len(records),
        "filings": [record.to_dict() for record in records],
    }
    return response


@router.get("/{ticker}/statements")
def list_statements(
    ticker: str,
    statement_type: str = Query(..., alias="statementType"),
    start_date: Optional[date] = Query(None, alias="startDate"),
    end_date: Optional[date] = Query(None, alias="endDate"),
):
    """Return statements for ``ticker`` within the requested date window."""

    try:
        records = _statement_service.get_statements_by_date_range(
            ticker=ticker,
            statement_type=statement_type,
            start_date=start_date,
            end_date=end_date,
        )
    except DataRetrievalError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    effective_end = end_date or date.today()
    resolved_type = records[0].statement_type if records else statement_type
    response = {
        "ticker": ticker.upper(),
        "statementType": resolved_type,
        "query": {
            "startDate": start_date.isoformat() if start_date else None,
            "endDate": effective_end.isoformat(),
        },
        "count": len(records),
        "statements": [record.to_dict() for record in records],
    }
    return response


@router.get("/{ticker}/statements/latest")
def latest_statements(
    ticker: str,
    statement_type: str = Query(..., alias="statementType"),
    limit: int = Query(4, alias="limit", ge=1, le=8),
):
    """Return the most recent statements for ``ticker``."""

    try:
        records = _statement_service.get_latest_statements(
            ticker=ticker,
            statement_type=statement_type,
            limit=limit,
        )
    except DataRetrievalError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    resolved_type = records[0].statement_type if records else statement_type
    response = {
        "ticker": ticker.upper(),
        "statementType": resolved_type,
        "query": {
            "limit": limit,
        },
        "count": len(records),
        "statements": [record.to_dict() for record in records],
    }
    return response

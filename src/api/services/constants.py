"""Shared constants and mappings for API services."""

_ALLOWED_FORM_TYPES = ["10-K", "10-Q"]

STATEMENT_TYPE_ALIASES = {
    "INCOME STATEMENT": "Income Statement",
    "STATEMENT OF INCOME": "Income Statement",
    "STATEMENTS OF INCOME": "Income Statement",
    "STATEMENT OF OPERATIONS": "Income Statement",
    "STATEMENTS OF OPERATIONS": "Income Statement",
    "STATEMENT OF EARNINGS": "Income Statement",
    "STATEMENTS OF EARNINGS": "Income Statement",
    "BALANCE SHEET": "Balance Sheet",
    "STATEMENT OF FINANCIAL POSITION": "Balance Sheet",
    "STATEMENTS OF FINANCIAL POSITION": "Balance Sheet",
    "STATEMENT OF FINANCIAL CONDITION": "Balance Sheet",
    "STATEMENTS OF FINANCIAL CONDITION": "Balance Sheet",
    "CASH FLOWS": "Cash Flows",
    "STATEMENT OF CASH FLOWS": "Cash Flows",
    "STATEMENTS OF CASH FLOWS": "Cash Flows",
    "STATEMENT OF CASH FLOW": "Cash Flows",
    "STATEMENTS OF CASH FLOW": "Cash Flows",
    "STOCKHOLDERS' EQUITY": "Stockholders' Equity",
    "STOCKHOLDER' EQUITY": "Stockholders' Equity",
    "SHAREHOLDERS' EQUITY": "Stockholders' Equity",
    "STATEMENT OF STOCKHOLDERS' EQUITY": "Stockholders' Equity",
    "STATEMENTS OF STOCKHOLDERS' EQUITY": "Stockholders' Equity",
    "STATEMENT OF SHAREHOLDERS' EQUITY": "Stockholders' Equity",
    "STATEMENTS OF SHAREHOLDERS' EQUITY": "Stockholders' Equity",
    "STATEMENT OF CHANGES IN STOCKHOLDERS' EQUITY": "Stockholders' Equity",
    "STATEMENTS OF CHANGES IN STOCKHOLDERS' EQUITY": "Stockholders' Equity",
    "STATEMENT OF CHANGES IN SHAREHOLDERS' EQUITY": "Stockholders' Equity",
    "STATEMENTS OF CHANGES IN SHAREHOLDERS' EQUITY": "Stockholders' Equity",
    "STATEMENT OF CHANGES IN EQUITY": "Stockholders' Equity",
    "STATEMENTS OF CHANGES IN EQUITY": "Stockholders' Equity",
    "EQUITY": "Stockholders' Equity",
}

STATEMENT_SHEET_NORMALIZATION = {
    "INCOME STATEMENT": "Income Statement",
    "BALANCE SHEET": "Balance Sheet",
    "CASH FLOWS": "Cash Flows",
    "STOCKHOLDERS' EQUITY": "Stockholders' Equity",
    "EQUITY": "Stockholders' Equity",
}

"""Tests for multi-filing ensemble assembly."""

from src.processor import (
    Cell,
    DimensionHierarchy,
    FilingSlice,
    Period,
    ProcessingResult,
    Row,
    Statement,
    build_ensemble_result,
)


def _make_cell(period_label: str, raw_value: float) -> Cell:
    return Cell(
        value=str(raw_value),
        raw_value=raw_value,
        unit="usd",
        decimals=-6,
        period=period_label,
    )


def _make_row(
    label: str,
    concept: str,
    period_values: dict[str, float],
    *,
    dimension_signature: tuple[tuple[str, str], ...] | None = None,
) -> Row:
    cells = {period: _make_cell(period, value) for period, value in period_values.items()}
    return Row(
        label=label,
        concept=concept,
        is_abstract=False,
        depth=0,
        cells=cells,
        dimension_signature=dimension_signature,
    )


def _make_statement(name: str, period_specs: list[tuple[str, str, bool]], rows: list[Row]) -> Statement:
    periods = [Period(label=label, end_date=end_date, instant=instant) for label, end_date, instant in period_specs]
    return Statement(name=name, short_name=name, periods=periods, rows=rows)


def _make_result(
    statement: Statement,
    company: str,
    filing_date: str,
    dimension_hierarchy: DimensionHierarchy | None = None,
) -> ProcessingResult:
    return ProcessingResult(
        statements=[statement],
        company_name=company,
        filing_date=filing_date,
        form_type="10-K",
        success=True,
        dimension_hierarchy=dimension_hierarchy,
    )


def test_build_ensemble_result_selects_primary_periods():
    anchor_statement = _make_statement(
        "Income Statement",
        [
            ("FY2023", "2023-12-31", False),
            ("FY2022", "2022-12-31", False),
        ],
        [
            _make_row("Revenue", "us-gaap:Revenue", {"FY2023": 1000.0, "FY2022": 900.0}),
            _make_row("Gross Profit", "us-gaap:GrossProfit", {"FY2023": 400.0, "FY2022": 350.0}),
        ],
    )
    anchor_result = _make_result(anchor_statement, "Example Co", "2024-02-15")

    prior_statement = _make_statement(
        "Income Statement",
        [
            ("FY2022", "2022-12-31", False),
            ("FY2021", "2021-12-31", False),
        ],
        [
            _make_row("Revenue", "us-gaap:Revenue", {"FY2022": 900.0, "FY2021": 850.0}),
            _make_row("Gross Profit", "us-gaap:GrossProfit", {"FY2022": 350.0, "FY2021": 320.0}),
            _make_row("New Disclosure", "us-gaap:OtherIncome", {"FY2022": 42.0}),
        ],
    )
    prior_result = _make_result(prior_statement, "Example Co", "2023-02-20")

    slices = [
        FilingSlice.from_processing_result("2024 filing", anchor_result),
        FilingSlice.from_processing_result("2023 filing", prior_result),
    ]

    ensemble = build_ensemble_result(slices)

    assert len(ensemble.statements) == 1
    combined_statement = ensemble.statements[0]

    period_labels = [period.label for period in combined_statement.periods]
    assert period_labels == ["FY2023", "FY2022"]

    revenue_row = next(row for row in combined_statement.rows if row.label == "Revenue")
    assert revenue_row.cells["FY2023"].raw_value == 1000.0
    assert revenue_row.cells["FY2022"].raw_value == 900.0
    assert "FY2021" not in revenue_row.cells  # Prior filing extra period is ignored

    extra_row = next(row for row in combined_statement.rows if row.label == "New Disclosure")
    assert "FY2023" not in extra_row.cells
    assert extra_row.cells["FY2022"].raw_value == 42.0


def test_build_ensemble_result_warns_when_statement_missing():
    anchor_statement = _make_statement(
        "Balance Sheet",
        [("FY2023", "2023-12-31", True)],
        [_make_row("Cash", "us-gaap:Cash", {"FY2023": 50.0})],
    )
    anchor_result = _make_result(anchor_statement, "Example Co", "2024-03-15")

    missing_result = ProcessingResult(
        statements=[],
        company_name="Example Co",
        filing_date="2023-03-20",
        form_type="10-K",
        success=True,
    )

    slices = [
        FilingSlice.from_processing_result("2024 filing", anchor_result),
        FilingSlice.from_processing_result("2023 filing", missing_result),
    ]

    ensemble = build_ensemble_result(slices)

    assert len(ensemble.statements[0].periods) == 2

    warnings = ensemble.warnings or []
    assert any("missing" in warning.lower() for warning in warnings)


def test_rows_align_when_concept_namespace_changes():
    anchor_statement = _make_statement(
        "Balance Sheet",
        [("Dec 31, 2024", "2024-12-31", True), ("Dec 31, 2023", "2023-12-31", True)],
        [
            _make_row(
                "Digital assets, net",
                "ns0:DigitalAssetsNetNonCurrent",
                {"Dec 31, 2024": 120.0, "Dec 31, 2023": 110.0},
            )
        ],
    )
    anchor_result = _make_result(anchor_statement, "Example Co", "2025-02-01")

    prior_statement = _make_statement(
        "Balance Sheet",
        [("Dec 31, 2023", "2023-12-31", True), ("Dec 31, 2022", "2022-12-31", True)],
        [
            _make_row(
                "Digital assets, net",
                "tsla:DigitalAssetsNetNonCurrent",
                {"Dec 31, 2023": 110.0, "Dec 31, 2022": 90.0},
            )
        ],
    )
    prior_result = _make_result(prior_statement, "Example Co", "2024-02-01")

    slices = [
        FilingSlice.from_processing_result("2025 filing", anchor_result),
        FilingSlice.from_processing_result("2024 filing", prior_result),
    ]

    ensemble = build_ensemble_result(slices)
    combined_statement = ensemble.statements[0]
    row = next(r for r in combined_statement.rows if r.label == "Digital assets, net")
    assert set(row.cells.keys()) == {"Dec 31, 2024", "Dec 31, 2023"}


def test_rows_align_when_labels_drift_but_concept_matches():
    anchor_statement = _make_statement(
        "Balance Sheet",
        [("Dec 31, 2024", "2024-12-31", True)],
        [
            _make_row(
                "Solar energy systems, net",
                "ns0:LeasedAssetsNet",
                {"Dec 31, 2024": 4924.0},
            )
        ],
    )
    anchor_result = _make_result(anchor_statement, "Example Co", "2025-01-29")

    prior_statement = _make_statement(
        "Balance Sheet",
        [("Dec 31, 2023", "2023-12-31", True)],
        [
            _make_row(
                "Solar Energy Systems",
                "tsla:LeasedAssetsNet",
                {"Dec 31, 2023": 5229.0},
            )
        ],
    )
    prior_result = _make_result(prior_statement, "Example Co", "2024-01-25")

    slices = [
        FilingSlice.from_processing_result("2024 filing", anchor_result),
        FilingSlice.from_processing_result("2023 filing", prior_result),
    ]

    ensemble = build_ensemble_result(slices)
    combined_statement = ensemble.statements[0]

    solar_rows = [row for row in combined_statement.rows if "solar" in (row.label or "").lower()]
    assert [row.label for row in solar_rows] == ["Solar energy systems, net"]

    solar_row = solar_rows[0]
    assert {
        period: cell.raw_value for period, cell in solar_row.cells.items()
    } == {"Dec 31, 2024": 4924.0, "Dec 31, 2023": 5229.0}


def test_dimension_signature_prevents_cross_context_alignment():
    balance_signature = (
        ("propertyplantandequipmentbytypeaxis", "operatingleasevehiclesmember"),
    )
    disclosure_signature = (
        ("guaranteeobligationsbynatureaxis", "salestoleasingcompanieswithguaranteemember"),
    )

    anchor_statement = _make_statement(
        "Balance Sheet",
        [("Dec 31, 2024", "2024-12-31", True)],
        [
            _make_row(
                "Operating Lease Vehicles",
                "us-gaap:DeferredCostsLeasingNetNoncurrent",
                {"Dec 31, 2024": 4123.0},
                dimension_signature=balance_signature,
            )
        ],
    )
    anchor_result = _make_result(anchor_statement, "Tesla, Inc.", "2025-02-05")

    prior_statement = _make_statement(
        "Balance Sheet",
        [("Dec 31, 2023", "2023-12-31", True)],
        [
            _make_row(
                "Operating Lease Vehicles",
                "us-gaap:DeferredCostsLeasingNetNoncurrent",
                {"Dec 31, 2023": 43.0},
                dimension_signature=disclosure_signature,
            ),
            _make_row(
                "Operating Lease Vehicles",
                "us-gaap:DeferredCostsLeasingNetNoncurrent",
                {"Dec 31, 2023": 3091.0},
                dimension_signature=balance_signature,
            ),
        ],
    )
    prior_result = _make_result(prior_statement, "Tesla, Inc.", "2024-02-10")

    slices = [
        FilingSlice.from_processing_result("2024 filing", anchor_result),
        FilingSlice.from_processing_result("2023 filing", prior_result),
    ]

    ensemble = build_ensemble_result(slices)
    combined_statement = ensemble.statements[0]

    matched_row = next(
        row
        for row in combined_statement.rows
        if row.label == "Operating Lease Vehicles"
        and row.dimension_signature == balance_signature
    )
    assert {
        period: cell.raw_value for period, cell in matched_row.cells.items()
    } == {"Dec 31, 2024": 4123.0, "Dec 31, 2023": 3091.0}

    extra_row = next(
        row
        for row in combined_statement.rows
        if row.label == "Operating Lease Vehicles"
        and row.dimension_signature == disclosure_signature
    )
    assert extra_row.cells["Dec 31, 2023"].raw_value == 43.0


def test_dimension_semantic_matching_with_hierarchy():
    """Test that dimension signatures align when one is parent/child of the other.

    This regression test addresses the TSLA automotive revenue alignment issue where:
    - 2024 filing uses granular members (automotivesalesmember, automotiveleasingmember)
    - 2023 filing uses broad parent member (automotiverevenuesmember)

    With hierarchy awareness, these should align on the same row.
    """
    # Build dimension hierarchy: automotiverevenuesmember has 3 children
    hierarchy = DimensionHierarchy()
    hierarchy.add_relationship(
        "tsla:AutomotiveRevenuesMember", "tsla:AutomotiveSalesMember"
    )
    hierarchy.add_relationship(
        "tsla:AutomotiveRevenuesMember", "tsla:AutomotiveLeasingMember"
    )
    hierarchy.add_relationship(
        "tsla:AutomotiveRevenuesMember",
        "tsla:AutomotiveRegulatoryCreditsMember",
    )

    # 2024 filing uses granular member for automotive sales
    anchor_sig_sales = (("productorserviceaxis", "automotivesalesmember"),)
    anchor_sig_leasing = (("productorserviceaxis", "automotiveleasingmember"),)
    anchor_sig_credits = (
        ("productorserviceaxis", "automotiveregulatorycreditsmember"),
    )

    anchor_statement = _make_statement(
        "Income Statement",
        [("Dec 31, 2024", "2024-12-31", False)],
        [
            _make_row(
                "Automotive sales",
                "tsla:AutomotiveRevenue",
                {"Dec 31, 2024": 85000.0},
                dimension_signature=anchor_sig_sales,
            ),
            _make_row(
                "Automotive leasing",
                "tsla:AutomotiveRevenue",
                {"Dec 31, 2024": 2000.0},
                dimension_signature=anchor_sig_leasing,
            ),
            _make_row(
                "Automotive regulatory credits",
                "tsla:AutomotiveRevenue",
                {"Dec 31, 2024": 1800.0},
                dimension_signature=anchor_sig_credits,
            ),
        ],
    )
    anchor_result = _make_result(
        anchor_statement, "Tesla, Inc.", "2025-01-29", hierarchy
    )

    # 2023 filing uses parent member for all automotive revenues
    prior_sig = (("productorserviceaxis", "automotiverevenuesmember"),)
    prior_statement = _make_statement(
        "Income Statement",
        [("Dec 31, 2023", "2023-12-31", False)],
        [
            _make_row(
                "Automotive sales",
                "tsla:AutomotiveRevenue",
                {"Dec 31, 2023": 75000.0},
                dimension_signature=prior_sig,
            ),
            _make_row(
                "Automotive leasing",
                "tsla:AutomotiveRevenue",
                {"Dec 31, 2023": 1900.0},
                dimension_signature=prior_sig,
            ),
            _make_row(
                "Automotive regulatory credits",
                "tsla:AutomotiveRevenue",
                {"Dec 31, 2023": 1700.0},
                dimension_signature=prior_sig,
            ),
        ],
    )
    prior_result = _make_result(
        prior_statement, "Tesla, Inc.", "2024-02-01", hierarchy
    )

    slices = [
        FilingSlice.from_processing_result("2024 filing", anchor_result),
        FilingSlice.from_processing_result("2023 filing", prior_result),
    ]

    ensemble = build_ensemble_result(slices)
    combined_statement = ensemble.statements[0]

    # With semantic matching, all three rows should align across periods
    sales_rows = [
        row for row in combined_statement.rows if row.label == "Automotive sales"
    ]
    assert (
        len(sales_rows) == 1
    ), f"Expected 1 automotive sales row, got {len(sales_rows)}"

    sales_row = sales_rows[0]
    assert set(sales_row.cells.keys()) == {
        "Dec 31, 2024",
        "Dec 31, 2023",
    }, "Automotive sales should have both periods"
    assert sales_row.cells["Dec 31, 2024"].raw_value == 85000.0
    assert sales_row.cells["Dec 31, 2023"].raw_value == 75000.0

    leasing_rows = [
        row for row in combined_statement.rows if row.label == "Automotive leasing"
    ]
    assert (
        len(leasing_rows) == 1
    ), f"Expected 1 automotive leasing row, got {len(leasing_rows)}"

    leasing_row = leasing_rows[0]
    assert set(leasing_row.cells.keys()) == {"Dec 31, 2024", "Dec 31, 2023"}
    assert leasing_row.cells["Dec 31, 2024"].raw_value == 2000.0
    assert leasing_row.cells["Dec 31, 2023"].raw_value == 1900.0

    credits_rows = [
        row
        for row in combined_statement.rows
        if row.label == "Automotive regulatory credits"
    ]
    assert (
        len(credits_rows) == 1
    ), f"Expected 1 automotive credits row, got {len(credits_rows)}"

    credits_row = credits_rows[0]
    assert set(credits_row.cells.keys()) == {"Dec 31, 2024", "Dec 31, 2023"}
    assert credits_row.cells["Dec 31, 2024"].raw_value == 1800.0
    assert credits_row.cells["Dec 31, 2023"].raw_value == 1700.0

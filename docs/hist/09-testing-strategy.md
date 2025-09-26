# 09 - Testing Strategy and Acceptance Criteria

## Overview

This document outlines the comprehensive testing approach for validating the SEC Data Extractor functionality. Testing focuses on accuracy, visual fidelity, and reliability across different filing types and edge cases.

## Testing Levels

### Unit Tests
Test individual components in isolation.

### Integration Tests
Verify component interactions and data flow.

### End-to-End Tests
Validate complete pipeline from iXBRL input to Excel output.

### Acceptance Tests
Confirm output matches iXBRL viewer presentation exactly.

## Acceptance Criteria

### Primary Success Criteria

#### 1. Visual Fidelity Match
**Requirement**: Excel output must match iXBRL viewer presentation exactly.

**Validation Method**:
- Manual comparison between Excel sheets and browser viewer
- Row labels and order identical
- Period captions identical
- Section headers (abstract rows) in correct positions
- Indentation levels preserved

**Test Cases**:
```python
def test_visual_fidelity():
    """Verify Excel matches viewer presentation exactly."""

    # Load test filing
    filing_url = "https://www.sec.gov/Archives/edgar/data/320193/000032019324000007/aapl-20231230.htm"

    # Generate viewer and Excel
    viewer_data = generate_viewer(filing_url)
    excel_file = generate_excel(viewer_data)

    # Compare structure
    assert_row_labels_match(viewer_data, excel_file)
    assert_period_headers_match(viewer_data, excel_file)
    assert_section_structure_match(viewer_data, excel_file)
```

#### 2. Data Accuracy
**Requirement**: All numerical values must be correctly extracted and formatted.

**Validation Method**:
- Spot-check 10 random values per statement
- Verify scaling (millions) applied correctly
- Confirm negative value formatting (parentheses)
- Validate EPS precision (2 decimals)

**Test Cases**:
```python
def test_data_accuracy():
    """Verify numerical accuracy of extracted data."""

    # Test currency scaling
    assert_currency_scaled_to_millions()

    # Test EPS precision
    assert_eps_has_two_decimals()

    # Test negative formatting
    assert_negatives_use_parentheses()

    # Test missing values
    assert_missing_values_show_em_dash()
```

#### 3. Period Captions
**Requirement**: Period headers must match viewer captions exactly.

**Expected**: "Year Ended December 31, 2024", not "2024"

**Test Cases**:
```python
def test_period_captions():
    """Verify period headers match viewer exactly."""

    viewer_periods = extract_viewer_periods()
    excel_headers = extract_excel_headers()

    for viewer_period, excel_header in zip(viewer_periods, excel_headers):
        assert viewer_period.label == excel_header
```

#### 4. Styling Requirements
**Requirement**: Excel formatting must highlight structure appropriately.

**Validation**:
- Abstract rows are bold
- Data rows have appropriate indentation
- Total rows have bottom borders
- Numbers are right-aligned

## Test Data Management

### Test Filing Repository
```python
TEST_FILINGS = {
    'apple_2023_10k': {
        'url': 'https://www.sec.gov/Archives/edgar/data/320193/000032019324000007/aapl-20231230.htm',
        'description': 'Apple 2023 10-K - Standard large cap filing',
        'expected_statements': 3,  # BS, IS, CF
        'expected_periods': 3,    # 2023, 2022, 2021
    },
    'microsoft_2023_10k': {
        'url': 'https://www.sec.gov/Archives/edgar/data/789019/000178401924000007/msft-20240630.htm',
        'description': 'Microsoft 2024 10-K - Different fiscal year end',
        'expected_statements': 3,
        'expected_periods': 3,
    },
    'small_company_10k': {
        'path': './test_data/small-company-10k.htm',
        'description': 'Small company filing - simpler structure',
        'expected_statements': 3,
        'expected_periods': 2,
    }
}
```

### Golden Reference Files
For each test filing, maintain reference files:
- `viewer-data.json` - Expected viewer JSON structure
- `reference-output.xlsx` - Expected Excel output
- `spot-check-values.json` - Key values for validation

## Automated Test Suite

### Test Categories

#### Component Tests

```python
def test_arelle_processing():
    """Test Arelle viewer generation."""
    viewer_html = generate_viewer(TEST_FILING_URL)
    assert viewer_html_contains_data(viewer_html)

def test_json_extraction():
    """Test JSON extraction from viewer HTML."""
    json_data = extract_viewer_json(VIEWER_HTML_PATH)
    assert validate_json_structure(json_data)

def test_presentation_tree_parsing():
    """Test presentation tree construction from relationships."""
    viewer_data = load_test_viewer_data()
    parser = PresentationParser()

    # Build tree for balance sheet role
    tree = parser.build_presentation_tree(
        role_id="http://example.com/role/BalanceSheet",
        relationships=viewer_data['rels'],
        concepts=viewer_data['concepts']
    )

    # Verify tree structure
    assert len(tree) > 0  # Has root nodes
    assert tree[0].concept == "us-gaap:Assets"  # Assets is first
    assert tree[0].children  # Assets has children
    assert tree[0].depth == 0  # Root level

def test_fact_matching():
    """Test fact matching to presentation concepts."""
    viewer_data = load_test_viewer_data()
    parser = DataParser()

    # Test matching specific fact
    period = Period(label="2023-09-30", end_date="2023-09-30", instant=True)
    cell = parser._match_fact_to_concept(
        concept="us-gaap:Assets",
        period=period,
        facts=viewer_data['facts']
    )

    assert cell is not None
    assert cell.concept == "us-gaap:Assets"
    assert cell.period == "2023-09-30"
    assert cell.raw_value > 0

def test_preferred_label_resolution():
    """Test preferred label extraction from concepts."""
    concept_info = {
        'labels': {
            'http://www.xbrl.org/2003/role/totalLabel': 'Total Assets',
            'http://www.xbrl.org/2003/role/label': 'Assets'
        }
    }

    parser = DataParser()

    # Should use total label when specified
    total_label = parser._get_preferred_label(
        concept_info,
        'http://www.xbrl.org/2003/role/totalLabel'
    )
    assert total_label == 'Total Assets'

    # Should fallback to standard label
    std_label = parser._get_preferred_label(concept_info, None)
    assert std_label == 'Assets'

def test_data_transformation():
    """Test value transformation and formatting."""
    raw_value = "1000000000"
    transformed = transform_currency_value(raw_value, "usd", -6)
    assert transformed == "1,000"

def test_excel_generation():
    """Test Excel file creation."""
    excel_file = generate_excel(STATEMENTS_DATA)
    assert excel_file_is_valid(excel_file)
```

#### Integration Tests

```python
def test_presentation_to_excel_pipeline():
    """Test complete presentation-based pipeline."""
    viewer_data = load_test_viewer_data()

    # Parse using presentation structure
    parser = DataParser()
    result = parser.parse_viewer_data(viewer_data)

    assert result.success
    assert len(result.statements) == 3  # BS, IS, CF

    # Verify balance sheet structure
    balance_sheet = next(s for s in result.statements if 'balance' in s.name.lower())
    assert balance_sheet.rows[0].label == "Assets:"  # First row is Assets header
    assert balance_sheet.rows[0].is_abstract is True  # Headers are abstract
    assert balance_sheet.rows[1].depth > 0  # Child rows are indented

def test_tree_traversal_order():
    """Test that tree traversal maintains presentation order."""
    viewer_data = load_test_viewer_data()
    parser = DataParser()
    result = parser.parse_viewer_data(viewer_data)

    # Get balance sheet rows
    balance_sheet = next(s for s in result.statements if 'balance' in s.name.lower())
    row_labels = [row.label for row in balance_sheet.rows]

    # Verify expected order (Assets before Liabilities)
    assets_index = next(i for i, label in enumerate(row_labels) if 'assets' in label.lower())
    liabilities_index = next(i for i, label in enumerate(row_labels) if 'liabilities' in label.lower())
    assert assets_index < liabilities_index

def test_end_to_end_pipeline():
    """Test complete processing pipeline."""
    filing_url = TEST_FILINGS['apple_2023_10k']['url']

    # Run complete pipeline
    result = process_filing(filing_url, 'test_output.xlsx')

    # Verify success
    assert result.success
    assert os.path.exists('test_output.xlsx')

    # Verify content
    workbook = load_workbook('test_output.xlsx')
    assert len(workbook.worksheets) == 3  # BS, IS, CF

def test_cli_interface():
    """Test command-line interface."""
    cmd = [
        'python', 'render_viewer_to_xlsx.py',
        '--filing', TEST_FILING_URL,
        '--out', 'cli_test.xlsx'
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0
    assert os.path.exists('cli_test.xlsx')
```

### Performance Tests

```python
def test_processing_performance():
    """Verify processing completes within reasonable time."""

    start_time = time.time()
    process_filing(TEST_FILING_URL, 'perf_test.xlsx')
    duration = time.time() - start_time

    # Should complete within 5 minutes for typical filing
    assert duration < 300

def test_memory_usage():
    """Monitor memory usage during processing."""

    import psutil
    process = psutil.Process()

    initial_memory = process.memory_info().rss
    process_filing(TEST_FILING_URL, 'memory_test.xlsx')
    peak_memory = process.memory_info().rss

    # Should not use more than 1GB additional memory
    memory_increase = peak_memory - initial_memory
    assert memory_increase < 1_073_741_824  # 1GB
```

## Manual Testing Procedures

### Visual Comparison Checklist

#### Pre-Test Setup
1. Open iXBRL filing in browser
2. Navigate to each financial statement
3. Take screenshots of viewer tables
4. Generate Excel output using tool
5. Open Excel file for comparison

#### Statement-by-Statement Validation

**Balance Sheet Validation**:
- [ ] Asset section headers match
- [ ] Liability section headers match
- [ ] Equity section headers match
- [ ] Row labels identical to viewer
- [ ] Row order preserved exactly
- [ ] Indentation levels correct
- [ ] Period headers match viewer captions
- [ ] Total rows have bottom borders

**Income Statement Validation**:
- [ ] Revenue section matches
- [ ] Cost of sales/expenses section matches
- [ ] Operating income calculation correct
- [ ] Net income matches viewer
- [ ] EPS values have 2 decimals
- [ ] Share count values scaled to millions

**Cash Flow Statement Validation**:
- [ ] Operating activities section complete
- [ ] Investing activities section complete
- [ ] Financing activities section complete
- [ ] Net change in cash matches
- [ ] Beginning/ending cash balances correct

### Data Accuracy Spot Checks

#### Random Value Verification
For each statement, randomly select 10 line items:
1. Locate value in Excel
2. Find same value in iXBRL viewer
3. Verify scaled values are correct
4. Check sign/formatting matches expectations

#### Calculation Verification
Verify key calculations where possible:
- Total assets = Total liabilities + Equity
- Revenue - Expenses = Net Income (simplified)
- Operating + Investing + Financing = Net Change in Cash

## Error Testing

### Invalid Input Testing
```python
def test_invalid_filings():
    """Test handling of invalid input files."""

    # Non-existent URL
    with pytest.raises(FileNotFoundError):
        process_filing("https://invalid-url.com/fake.htm", "out.xlsx")

    # Corrupted HTML file
    with pytest.raises(ValueError):
        process_filing("./test_data/corrupted.htm", "out.xlsx")

    # Non-iXBRL file
    with pytest.raises(ValueError):
        process_filing("./test_data/regular.html", "out.xlsx")
```

### Edge Case Testing
```python
def test_edge_cases():
    """Test handling of unusual but valid scenarios."""

    # Filing with only one period
    result = process_filing(SINGLE_PERIOD_FILING, "single.xlsx")
    assert result.success

    # Filing with non-USD currency
    result = process_filing(NON_USD_FILING, "euro.xlsx")
    assert result.success

    # Very large filing
    result = process_filing(LARGE_FILING, "large.xlsx", timeout=1800)
    assert result.success
```

## Regression Testing

### Reference Data Management
```python
def update_reference_data():
    """Update golden reference files after verified changes."""

    for filing_key, filing_data in TEST_FILINGS.items():
        # Generate fresh reference output
        reference_path = f"./reference/{filing_key}-reference.xlsx"
        process_filing(filing_data['url'], reference_path)

        # Extract key values for spot checking
        spot_check_data = extract_key_values(reference_path)
        with open(f"./reference/{filing_key}-values.json", 'w') as f:
            json.dump(spot_check_data, f, indent=2)

def test_against_reference():
    """Compare current output against reference files."""

    for filing_key in TEST_FILINGS.keys():
        current_output = f"./test_output/{filing_key}-current.xlsx"
        reference_output = f"./reference/{filing_key}-reference.xlsx"

        # Generate current output
        process_filing(TEST_FILINGS[filing_key]['url'], current_output)

        # Compare against reference
        assert_excel_files_equivalent(current_output, reference_output)
```

## Continuous Integration

### Automated Test Pipeline
```yaml
# .github/workflows/test.yml
name: Test SEC Data Extractor

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: 3.9

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest

      - name: Run unit tests
        run: pytest tests/unit/

      - name: Run integration tests
        run: pytest tests/integration/

      - name: Run acceptance tests
        run: pytest tests/acceptance/ -v
```

### Test Reporting
Generate comprehensive test reports including:
- Pass/fail status for each test filing
- Performance metrics (processing time, memory usage)
- Visual diff reports for changed outputs
- Coverage reports for code testing

## Test Maintenance

### Regular Test Updates
- **Monthly**: Update test filings with recent SEC filings
- **Quarterly**: Review and update reference outputs
- **Annually**: Comprehensive review of test coverage

### Test Data Refresh
- Monitor SEC EDGAR for filing format changes
- Add new test cases for unusual filing structures
- Retire obsolete test cases when format changes

## Success Metrics

### Quality Gates
Before release, all tests must pass:
- ✅ 100% unit test pass rate
- ✅ 100% integration test pass rate
- ✅ All acceptance criteria met
- ✅ Performance benchmarks met
- ✅ Manual visual validation complete

### Performance Benchmarks
- Processing time < 5 minutes for typical filing
- Memory usage < 2GB peak
- Output file size < 10MB for typical statements
- Error rate < 1% on supported filing types

This comprehensive testing strategy ensures the SEC Data Extractor produces reliable, accurate financial statement extractions that maintain fidelity to the original iXBRL presentations.
#!/usr/bin/env python3
"""
Test script for the SEC processor pipeline.
Tests the pipeline with mock data to validate functionality.
"""

import json
import tempfile
from pathlib import Path

from src.processor import (
    ViewerDataExtractor, DataParser, ValueFormatter,
    ExcelGenerator, ProcessingResult
)


def create_mock_viewer_data():
    """Create mock iXBRL viewer data for testing."""
    return {
        "facts": {
            "fact_1": {
                "c": "us-gaap:Assets",
                "v": 120000000000,  # $120B
                "u": "usd",
                "d": -6,
                "context": "ctx_2023"
            },
            "fact_2": {
                "c": "us-gaap:Liabilities",
                "v": 80000000000,  # $80B
                "u": "usd",
                "d": -6,
                "context": "ctx_2023"
            },
            "fact_3": {
                "c": "us-gaap:StockholdersEquity",
                "v": 40000000000,  # $40B
                "u": "usd",
                "d": -6,
                "context": "ctx_2023"
            },
            "fact_4": {
                "c": "dei:EntityRegistrantName",
                "v": "Tesla, Inc.",
                "context": "ctx_company"
            }
        },
        "contexts": {
            "ctx_2023": {
                "period": {
                    "instant": "2023-12-31"
                }
            },
            "ctx_company": {
                "period": {
                    "instant": "2023-12-31"
                }
            }
        },
        "concepts": {
            "us-gaap:Assets": {
                "label": "Total Assets",
                "abstract": False
            },
            "us-gaap:Liabilities": {
                "label": "Total Liabilities",
                "abstract": False
            },
            "us-gaap:StockholdersEquity": {
                "label": "Stockholders Equity",
                "abstract": False
            },
            "dei:EntityRegistrantName": {
                "label": "Company Name",
                "abstract": False
            }
        },
        "roles": {
            "http://example.com/role/BalanceSheet": {
                "definition": "Consolidated Balance Sheet",
                "presentation": [
                    {"concept": "us-gaap:Assets", "depth": 0},
                    {"concept": "us-gaap:Liabilities", "depth": 0},
                    {"concept": "us-gaap:StockholdersEquity", "depth": 0}
                ]
            }
        }
    }


def create_mock_html_with_json(json_data, html_path):
    """Create mock HTML file with embedded JSON data."""
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Test iXBRL Viewer</title>
</head>
<body>
    <h1>Test Viewer</h1>
    <script>
        var viewer_data = {json.dumps(json_data)};
    </script>
</body>
</html>
"""

    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)


def test_json_extraction():
    """Test JSON extraction from HTML."""
    print("Testing JSON extraction...")

    # Create mock data and HTML file
    mock_data = create_mock_viewer_data()

    with tempfile.NamedTemporaryFile(mode='w', suffix='.htm', delete=False) as f:
        create_mock_html_with_json(mock_data, f.name)
        html_path = f.name

    try:
        # Test extraction
        extractor = ViewerDataExtractor()
        extracted_data = extractor.extract_viewer_data(html_path)

        print(f"✅ JSON extraction successful")
        print(f"   Found {len(extracted_data.get('facts', {}))} facts")
        return extracted_data

    finally:
        Path(html_path).unlink(missing_ok=True)


def test_data_parsing(viewer_data):
    """Test data parsing."""
    print("Testing data parsing...")

    formatter = ValueFormatter(currency="USD", scale_millions=True)
    parser = DataParser(formatter)

    result = parser.parse_viewer_data(viewer_data)

    if result.success:
        print(f"✅ Data parsing successful")
        print(f"   Company: {result.company_name}")
        print(f"   Statements: {len(result.statements)}")

        for stmt in result.statements:
            print(f"     - {stmt.name}: {len(stmt.periods)} periods, {len(stmt.rows)} rows")

        return result
    else:
        print(f"❌ Data parsing failed: {result.error}")
        return None


def test_excel_generation(result):
    """Test Excel generation."""
    print("Testing Excel generation...")

    output_path = "test_output.xlsx"

    try:
        generator = ExcelGenerator()
        generator.generate_excel(result, output_path, single_period=False)

        if Path(output_path).exists():
            file_size = Path(output_path).stat().st_size
            print(f"✅ Excel generation successful")
            print(f"   File: {output_path} ({file_size} bytes)")
            return True
        else:
            print(f"❌ Excel file not created")
            return False

    except Exception as e:
        print(f"❌ Excel generation failed: {e}")
        return False

    finally:
        # Clean up
        Path(output_path).unlink(missing_ok=True)


def main():
    """Run all tests."""
    print("🧪 Testing SEC Processor Pipeline")
    print("=" * 40)

    try:
        # Test 1: JSON Extraction
        viewer_data = test_json_extraction()
        print()

        # Test 2: Data Parsing
        result = test_data_parsing(viewer_data)
        if not result:
            return
        print()

        # Test 3: Excel Generation
        success = test_excel_generation(result)
        print()

        if success:
            print("🎉 All tests passed! The processor pipeline is working.")
        else:
            print("❌ Some tests failed.")

    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
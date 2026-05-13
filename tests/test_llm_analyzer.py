"""Test LLM Analyzer with httpx implementation"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import date
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from bill_notify.llm_analyzer import LLMAnalyzer
from bill_notify.models import BillAnalysisResult


@pytest.mark.asyncio
async def test_analyze_pdf_success():
    """Test successful PDF analysis with mocked response"""
    print("Testing analyze_pdf with successful response...")

    analyzer = LLMAnalyzer(api_key="test_api_key", model="test/model")

    mock_response_data = {
        "choices": [
            {
                "message": {
                    "content": "DUE_DATE: 2025-03-15\nSUMMARY: Test Bill\nAMOUNT: $100.00",
                    "role": "assistant",
                }
            }
        ]
    }

    mock_response = MagicMock()
    mock_response.json.return_value = mock_response_data
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await analyzer.analyze_pdf(
            "Sample PDF text content",
            email_subject="Test Bill Email"
        )

        assert isinstance(result, BillAnalysisResult)
        assert result.status == "success"
        assert result.bill is not None
        assert result.bill.due_date == date(2025, 3, 15)
        assert result.bill.summary == "Test Bill"
        assert result.bill.amount == "$100.00"
        print(f"✓ Successfully extracted date: {result.bill.due_date}")
        return True


@pytest.mark.asyncio
async def test_analyze_pdf_not_bill():
    """Test PDF analysis when document is determined NOT to be a bill requiring payment"""
    print("\nTesting analyze_pdf with NOT_BILL response...")

    analyzer = LLMAnalyzer(api_key="test_api_key", model="test/model")

    mock_response_data = {
        "choices": [
            {
                "message": {
                    "content": "DUE_DATE: NOT_BILL\nSUMMARY:\nAMOUNT:",
                    "role": "assistant",
                }
            }
        ]
    }

    mock_response = MagicMock()
    mock_response.json.return_value = mock_response_data
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await analyzer.analyze_pdf("Receipt content")

        assert isinstance(result, BillAnalysisResult)
        assert result.status == "not_bill"
        assert result.bill is None
        print("✓ Correctly returned not_bill status")
        return True


@pytest.mark.asyncio
async def test_analyze_pdf_extraction_failed():
    """Test PDF analysis when due date extraction failed"""
    print("\nTesting analyze_pdf with EXTRACTION_FAILED response...")

    analyzer = LLMAnalyzer(api_key="test_api_key", model="test/model")

    mock_response_data = {
        "choices": [
            {
                "message": {
                    "content": "DUE_DATE: EXTRACTION_FAILED\nSUMMARY:\nAMOUNT:",
                    "role": "assistant",
                }
            }
        ]
    }

    mock_response = MagicMock()
    mock_response.json.return_value = mock_response_data
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await analyzer.analyze_pdf("Unclear document content")

        assert isinstance(result, BillAnalysisResult)
        assert result.status == "failed"
        assert result.error is not None
        print("✓ Correctly returned failed status")
        return True


@pytest.mark.asyncio
async def test_http_error_handling():
    """Test HTTP error handling"""
    print("\nTesting HTTP error handling...")

    analyzer = LLMAnalyzer(api_key="test_api_key", model="test/model")

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.post.side_effect = Exception("Connection error")
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await analyzer.analyze_pdf("Test content")

        assert isinstance(result, BillAnalysisResult)
        assert result.status == "failed"
        print("✓ Correctly handled HTTP error")
        return True


@pytest.mark.asyncio
async def test_request_payload():
    """Test that the request payload is correctly built"""
    print("\nTesting request payload construction...")

    analyzer = LLMAnalyzer(api_key="test_api_key", model="test/model")

    captured_payload = None

    def capture_post(*args, **kwargs):
        nonlocal captured_payload
        captured_payload = kwargs.get("json", {})
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "DUE_DATE: 2025-03-15\nSUMMARY: Test\nAMOUNT: $0"
                    }
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()
        return mock_response

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.post.side_effect = capture_post
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        await analyzer.analyze_pdf("Test PDF content", email_subject="Test Subject")

        assert captured_payload is not None
        assert "model" in captured_payload
        assert "messages" in captured_payload
        assert "temperature" in captured_payload
        assert "max_tokens" in captured_payload

        messages = captured_payload["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

        print("✓ Payload structure is correct")
        return True


@pytest.mark.asyncio
async def test_date_parsing():
    """Test date parsing from various formats"""
    print("\nTesting date parsing...")

    analyzer = LLMAnalyzer(api_key="test_api_key")

    # Test various date formats
    test_cases = [
        ("2025-03-15", date(2025, 3, 15)),
        ("2025/03/15", date(2025, 3, 15)),
        ("March 15, 2025", date(2025, 3, 15)),
        ("15 March 2025", date(2025, 3, 15)),
    ]

    for text, expected in test_cases:
        result = analyzer._extract_date_from_text(text)
        assert result == expected, f"Failed for {text}: got {result}, expected {expected}"

    print("✓ Date parsing works for all formats")
    return True


async def run_all_tests():
    """Run all tests"""
    print("=" * 60)
    print("LLM Analyzer Tests")
    print("=" * 60)

    tests = [
        test_analyze_pdf_success,
        test_analyze_pdf_not_bill,
        test_analyze_pdf_extraction_failed,
        test_http_error_handling,
        test_request_payload,
        test_date_parsing,
    ]

    results = []
    for test in tests:
        try:
            result = await test()
            results.append(result)
        except Exception as e:
            print(f"✗ Test {test.__name__} raised exception: {e}")
            import traceback
            traceback.print_exc()
            results.append(False)

    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} tests passed")
    print("=" * 60)

    return all(results)


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
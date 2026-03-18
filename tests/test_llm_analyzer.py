"""Test LLM Analyzer with httpx implementation"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
import json
import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from bill_notify.config import AppConfig, OpenRouterConfig, GmailConfig, CalendarConfig
from bill_notify.llm_analyzer import LLMAnalyzer


def create_mock_config() -> AppConfig:
    """Create a mock configuration for testing"""
    return AppConfig(
        gmail=GmailConfig(),
        openrouter=OpenRouterConfig(
            api_key="test_api_key",
            model="test/model",
            base_url="https://openrouter.ai/api/v1",
            pdf_engine="pdf-text"
        ),
        calendar=CalendarConfig(),
        download_dir="./downloads",
        processed_log="./processed_emails.log",
        pdf_passwords=None
    )


@pytest.mark.asyncio
async def test_analyze_pdf_success():
    """Test successful PDF analysis with mocked response"""
    print("Testing analyze_pdf with successful response...")
    
    config = create_mock_config()
    analyzer = LLMAnalyzer(config)
    
    # Mock response data
    mock_response_data = {
        "choices": [
            {
                "message": {
                    "content": "2025-03-15",
                    "role": "assistant"
                }
            }
        ]
    }
    
    # Create a mock response
    mock_response = MagicMock()
    mock_response.json.return_value = mock_response_data
    mock_response.raise_for_status = MagicMock()
    
    # Mock httpx.AsyncClient
    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)
        
        # Test with sample base64 PDF (minimal valid PDF)
        base64_pdf = "data:application/pdf;base64,JVBERi0xLjQKJcOkw7zD..."  # truncated
        result = await analyzer.analyze_pdf([base64_pdf])
        
        if result:
            print(f"✓ Successfully extracted date: {result}")
            return True
        else:
            print("✗ Failed to extract date")
            return False


@pytest.mark.asyncio
async def test_analyze_pdf_not_found():
    """Test PDF analysis when due date not found"""
    print("\nTesting analyze_pdf with NOT_FOUND response...")
    
    config = create_mock_config()
    analyzer = LLMAnalyzer(config)
    
    mock_response_data = {
        "choices": [
            {
                "message": {
                    "content": "NOT_FOUND",
                    "role": "assistant"
                }
            }
        ]
    }
    
    mock_response = MagicMock()
    mock_response.json.return_value = mock_response_data
    mock_response.raise_for_status = MagicMock()
    
    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)
        
        base64_pdf = "data:application/pdf;base64,JVBERi0xLjQKJcOkw7zD..."
        result = await analyzer.analyze_pdf([base64_pdf])
        
        if result is None:
            print("✓ Correctly returned None for NOT_FOUND")
            return True
        else:
            print(f"✗ Expected None but got: {result}")
            return False


@pytest.mark.asyncio
async def test_http_error_handling():
    """Test HTTP error handling"""
    print("\nTesting HTTP error handling...")
    
    config = create_mock_config()
    analyzer = LLMAnalyzer(config)
    
    # Mock httpx.HTTPError
    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_client.post.side_effect = Exception("Connection error")
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)
        
        base64_pdf = "data:application/pdf;base64,JVBERi0xLjQKJcOkw7zD..."
        result = await analyzer.analyze_pdf([base64_pdf])
        
        if result is None:
            print("✓ Correctly handled HTTP error and returned None")
            return True
        else:
            print(f"✗ Expected None but got: {result}")
            return False


@pytest.mark.asyncio
async def test_request_payload():
    """Test that the request payload is correctly built"""
    print("\nTesting request payload construction...")
    
    config = create_mock_config()
    analyzer = LLMAnalyzer(config)
    
    # Capture the payload sent to the API
    captured_payload = None
    
    def capture_post(*args, **kwargs):
        nonlocal captured_payload
        captured_payload = kwargs.get('json', {})
        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "2025-03-15"}}]}
        mock_response.raise_for_status = MagicMock()
        return mock_response
    
    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_client.post.side_effect = capture_post
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)
        
        base64_pdf = "data:application/pdf;base64,JVBERi0xLjQKJcOkw7zD..."
        await analyzer.analyze_pdf([base64_pdf])
        
        if captured_payload:
            print(f"✓ Captured payload: {json.dumps(captured_payload, indent=2)}")
            
            # Verify payload structure
            assert 'model' in captured_payload, "Missing 'model' field"
            assert 'messages' in captured_payload, "Missing 'messages' field"
            assert 'temperature' in captured_payload, "Missing 'temperature' field"
            assert 'max_tokens' in captured_payload, "Missing 'max_tokens' field"
            
            # Check messages structure
            messages = captured_payload['messages']
            assert len(messages) == 2, f"Expected 2 messages, got {len(messages)}"
            assert messages[0]['role'] == 'system', "First message should be system"
            assert messages[1]['role'] == 'user', "Second message should be user"
            
            # Check file content
            user_content = messages[1]['content']
            assert len(user_content) == 2, f"Expected 2 content items, got {len(user_content)}"
            assert user_content[0]['type'] == 'text', "First content should be text"
            assert user_content[1]['type'] == 'file', "Second content should be file"
            
            # Check file data
            file_data = user_content[1]['file']
            assert 'filename' in file_data, "Missing filename in file data"
            assert 'file_data' in file_data, "Missing file_data in file data"
            assert file_data['file_data'] == base64_pdf, "file_data doesn't match input"
            
            # Check plugins (should be included for pdf-text engine)
            if config.openrouter.pdf_engine != 'native':
                assert 'plugins' in captured_payload, "Missing 'plugins' field for non-native engine"
                plugins = captured_payload['plugins']
                assert len(plugins) == 1, "Expected 1 plugin"
                assert plugins[0]['id'] == 'file-parser', "Plugin ID should be 'file-parser'"
                assert 'pdf' in plugins[0], "Missing 'pdf' in plugin config"
                assert plugins[0]['pdf']['engine'] == config.openrouter.pdf_engine, "Engine mismatch"
            
            print("✓ Payload structure is correct")
            return True
        else:
            print("✗ Failed to capture payload")
            return False


async def run_all_tests():
    """Run all tests"""
    print("=" * 60)
    print("LLM Analyzer httpx Implementation Tests")
    print("=" * 60)
    
    tests = [
        test_analyze_pdf_success,
        test_analyze_pdf_not_found,
        test_http_error_handling,
        test_request_payload,
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
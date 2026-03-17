"""Basic tests - Verify module imports and configuration"""
import sys
from pathlib import Path

# Test configuration loading
print("Testing configuration loading...")
try:
    from bill_notify.config import AppConfig
    print("✓ Config module import successful")
except ImportError as e:
    print(f"✗ Config module import failed: {e}")
    sys.exit(1)

# Test other module imports
print("\nTesting other module imports...")
modules = [
    ("bill_notify.gmail_fetcher", "GmailFetcher"),
    ("bill_notify.pdf_processor", "PDFProcessor"),
    ("bill_notify.llm_analyzer", "LLMAnalyzer"),
    ("bill_notify.calendar_sync", "CalendarSync"),
    ("bill_notify.main", "BillNotify"),
]

for module_name, class_name in modules:
    try:
        module = __import__(module_name, fromlist=[class_name])
        cls = getattr(module, class_name)
        print(f"✓ {module_name}.{class_name} import successful")
    except ImportError as e:
        print(f"✗ {module_name}.{class_name} import failed: {e}")
        # Don't exit, continue checking other modules

print("\n" + "=" * 60)
print("Basic tests completed")
print("=" * 60)

# Prompt for configuration
print("\nBefore using, please ensure:")
print("1. Dependencies installed: uv sync")
print("2. poppler installed (for PDF conversion)")
print("3. .env file configured (OPENROUTER_API_KEY)")
print("4. config.yaml file configured")
print("5. credentials.json placed (Google OAuth)")
print("\nRun: uv run python -m bill_notify.main")

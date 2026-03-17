"""Environment check script - Verify system configuration readiness"""

import importlib.util
import os
import sys
from pathlib import Path

print("=" * 70)
print("Bill Notification System - Environment Check")
print("=" * 70)

errors = []
warnings = []

# Check Python version
print("\n[1] Checking Python version...")
python_version = sys.version_info
if python_version >= (3, 13):
    print(
        f"  ✓ Python {python_version.major}.{python_version.minor}.{python_version.micro}"
    )
else:
    print(
        f"  ⚠️  Python {python_version.major}.{python_version.minor}.{python_version.micro} (recommended 3.13+)"
    )

# Check uv
print("\n[2] Checking uv package manager...")
try:
    import subprocess

    result = subprocess.run(["uv", "--version"], capture_output=True, text=True)
    if result.returncode == 0:
        print(f"  ✓ uv installed ({result.stdout.strip()})")
    else:
        print("  ⚠️  uv command not available")
except FileNotFoundError:
    print(
        "  ⚠️  uv not installed (installed via virtual environment, won't affect running)"
    )

# Check dependencies
print("\n[3] Checking Python dependencies...")
required_modules = [
    "google.auth",
    "googleapiclient",
    "openai",
    "pdf2image",
    "PIL",
    "dotenv",
    "yaml",
]

for module in required_modules:
    try:
        __import__(module.replace("-", "_"))
        print(f"  ✓ {module}")
    except ImportError:
        errors.append(f"Missing dependency: {module}")
        print(f"  ✗ {module} - not installed")

# Check configuration files
print("\n[4] Checking configuration files...")
config_files = {
    ".env": "Environment variables file",
    "config.yaml": "Application configuration file",
    "credentials.json": "Google OAuth credentials",
}

for file_path, description in config_files.items():
    if Path(file_path).exists():
        print(f"  ✓ {description} ({file_path})")
    else:
        warnings.append(f"Missing: {file_path}")
        print(f"  ⚠️  {description} ({file_path}) - not found")

# Check environment variables
print("\n[5] Checking environment variables...")
if Path(".env").exists():
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        print("  ⚠️  python-dotenv not installed, skipping .env loading")

    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    if openrouter_key and openrouter_key != "your_api_key_here":
        print("  ✓ OPENROUTER_API_KEY is set")
    else:
        errors.append("OPENROUTER_API_KEY not set or is default value")
        print("  ✗ OPENROUTER_API_KEY not set or is default value")

# Check application configuration
print("\n[6] Checking application configuration...")
if Path("config.yaml").exists():
    import yaml

    with open("config.yaml", "r", encoding="utf-8") as f:
        user_config = yaml.safe_load(f) or {}
        gmail_label = user_config.get("gmail_label", "bills")
        print(f"  ✓ Gmail label: {gmail_label}")
        print(f"  ✓ Reminder days: {user_config.get('reminder_days', 3)}")
        print(f"  ✓ Target calendar: {user_config.get('calendar_id', 'primary')}")
else:
    warnings.append("config.yaml does not exist, will use default configuration")
    print("  ⚠️  config.yaml does not exist, will use default values")

# Check poppler
print("\n[7] Checking poppler (PDF conversion tool)...")
spec = importlib.util.find_spec("pdf2image")
if spec is not None:
    print("  ✓ pdf2image module available")
    print("  ⚠️  Please ensure poppler-utils is installed on your system")
    print("     Ubuntu/Debian: sudo apt-get install poppler-utils")
    print("     macOS: brew install poppler")
else:
    errors.append("pdf2image not installed")
    print("  ✗ pdf2image not installed")

# Check token.json
print("\n[8] Checking Google authentication status...")
if Path("token.json").exists():
    print("  ✓ token.json exists (authenticated)")
else:
    warnings.append(
        "token.json does not exist, will require browser authorization on first run"
    )
    print(
        "  ⚠️  token.json does not exist, will require browser authorization on first run"
    )

# Summary
print("\n" + "=" * 70)
print("Check Results:")
print("=" * 70)

if errors:
    print(f"\n❌ Found {len(errors)} error(s):")
    for error in errors:
        print(f"  • {error}")
    print("\nPlease fix the above errors before running the program.")
    sys.exit(1)

if warnings:
    print(f"\n⚠️  Found {len(warnings)} warning(s):")
    for warning in warnings:
        print(f"  • {warning}")
    print("\nThe program can still run, but some features may be limited.")

print("\n✅ System configuration ready!")
print("\nNext steps:")
print(
    "1. Create a label in Gmail (e.g., 'bills') and label bill emails that need processing"
)
print("2. Run the program: uv run python -m bill_notify.main")
print("=" * 70)

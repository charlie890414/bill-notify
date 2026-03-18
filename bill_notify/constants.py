"""Application-wide constants"""

# Gmail related
DEFAULT_GMAIL_LABEL = "bills"
DEFAULT_DAYS_BACK = 7

# Calendar related
DEFAULT_CALENDAR_ID = "primary"
DEFAULT_REMINDER_DAYS = 3
DEFAULT_TIMEZONE = "Asia/Taipei"

# LLM related
DEFAULT_MODEL = "stepfun/step-3.5-flash:free"
DEFAULT_PDF_ENGINE = "pdf-text"
DEFAULT_TEMPERATURE = 0.1
DEFAULT_MAX_TOKENS = 1000

# Event creation
EVENT_SUMMARY_PREFIX = "[Bill]"
EVENT_SUMMARY_SUFFIX = "- Payment Due"
DEFAULT_SUMMARY_KEYWORDS = ["bill", "payment", "due"]
PREFIXES_TO_REMOVE = ["[Bill]", "Bill:", "Invoice:", "Payment:"]

# Logging
DEFAULT_LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# File operations
PROCESSED_LOG_ENCODING = "utf-8"
CONFIG_ENCODING = "utf-8"
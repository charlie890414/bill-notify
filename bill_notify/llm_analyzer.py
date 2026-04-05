"""LLM Analyzer - Using OpenRouter's LLM to extract due dates from PDFs"""

import logging
import re
from datetime import date
from typing import Optional, List, Dict, Any, Tuple, Union
import httpx
from bill_notify.config import AppConfig
from bill_notify.exceptions import LLMAnalysisError


logger = logging.getLogger(__name__)


class LLMAnalyzer:
    """LLM Analyzer"""

    def __init__(self, config: AppConfig):
        self.config = config
        self.api_key = config.openrouter.api_key
        self.base_url = config.openrouter.base_url
        self.model = config.openrouter.model
        self.pdf_engine = config.openrouter.pdf_engine

    def _extract_date_from_text(self, text: str) -> Optional[date]:
        """
        Extract date from LLM response text
        Supports formats: 2025-03-15, 2025/03/15, March 15, 2025, etc.
        """
        # Clean text, remove extra spaces and newlines
        text = text.strip()

        # Common date format patterns
        patterns = [
            r"(\d{4})[-/]\s*(\d{1,2})[-/]\s*(\d{1,2})",  # 2025-03-15, 2025/03/15
            r"(\d{1,2})[-/]\s*(\d{1,2})[-/]\s*(\d{4})",  # 03/15/2025, 03-15-2025
            r"([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})",  # March 15, 2025
            r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})",  # 15 March 2025
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    groups = match.groups()
                    if len(groups) == 3:
                        # Determine year/month/day order based on pattern
                        if pattern.startswith(r"(\d{4})"):
                            year, month, day = (
                                int(groups[0]),
                                int(groups[1]),
                                int(groups[2]),
                            )
                        elif pattern.startswith(r"(\d{1,2})[-/]"):
                            # Could be MM/DD/YYYY or DD/MM/YYYY, prefer MM/DD/YYYY
                            first, second, year = (
                                int(groups[0]),
                                int(groups[1]),
                                int(groups[2]),
                            )
                            # If first > 31, might be year
                            if first > 31:
                                year, month, day = (
                                    first,
                                    second,
                                    int(groups[2]) if len(groups) > 2 else 1,
                                )
                            else:
                                month, day, year = first, second, year
                        else:
                            # English month format
                            month_str, day, year = (
                                groups[0],
                                int(groups[1]),
                                int(groups[2]),
                            )
                            month_map = {
                                "january": 1,
                                "february": 2,
                                "march": 3,
                                "april": 4,
                                "may": 5,
                                "june": 6,
                                "july": 7,
                                "august": 8,
                                "september": 9,
                                "october": 10,
                                "november": 11,
                                "december": 12,
                            }
                            month = month_map.get(month_str.lower()[:3], 1)
                            day = int(day)

                        return date(year, month, day)
                except (ValueError, IndexError):
                    continue

        return None

    async def analyze_pdf(self, base64_pdfs: List[str], email_subject: str = "") -> Tuple[Union[date, bool, None], Optional[str], Optional[str]]:
        """
        Analyze PDF documents, extract due date, amount, and generate event summary
        Args:
            base64_pdfs: List of base64 encoded PDF data URLs (data:application/pdf;base64,...)
            email_subject: Email subject for context (to match language and style)
        Returns:
            Tuple of (due_date, event_summary, amount) if extracted for bill requiring payment
            Tuple of (None, None, None) if due date cannot be extracted (technical issues) - skip, don't log
            Tuple of (False, None, None) if document is determined NOT to be a bill requiring payment - skip but log
        """
        # Build LLM prompt
        system_prompt = """You are a professional bill analysis assistant. Analyze the provided PDF document and determine if it is a bill requiring future payment.

CRITICAL RULE: Only extract a due date if the document is a bill/invoice that requires a future payment. DO NOT extract dates from:
- Receipts or payment confirmations (already paid)
- Account statements or summaries
- Notifications or alerts about bills
- Informational documents

For documents where you CANNOT extract a due date (technical issue, missing information, etc.), return:
DUE_DATE: EXTRACTION_FAILED
SUMMARY: 
AMOUNT:

For documents that do NOT require payment (receipts, statements, etc.), return:
DUE_DATE: NOT_BILL
SUMMARY: 
AMOUNT:

For bills requiring payment, extract:
1. The payment due date (the date by which payment must be made)
2. A concise event title for calendar reminder (e.g., "AT&T Internet Bill", "Water Bill Payment")
3. The bill amount (total amount due)

Important rules:
- Use the same language as the email subject for the summary
- Return in this exact format:
DUE_DATE: YYYY-MM-DD
SUMMARY: Your event title here
AMOUNT: [currency symbol][amount] (e.g., $1,234.56 or NT$ 1,234)

Examples of bills requiring payment:
DUE_DATE: 2025-03-15
SUMMARY: AT&T Internet Bill
AMOUNT: $89.99

Examples of documents where due date cannot be extracted:
DUE_DATE: EXTRACTION_FAILED
SUMMARY: 
AMOUNT:

Examples of documents NOT requiring payment:
DUE_DATE: NOT_BILL
SUMMARY: 
AMOUNT:"""

        # Include email subject in user message for language context
        if email_subject:
            user_message = f"Email subject: {email_subject}\n\nPlease analyze this bill document and extract the due date, a brief event title, and the total bill amount. Use the same language as the email subject."
        else:
            user_message = "Please analyze this bill document and extract the due date, a brief event title, and the total bill amount."

        # Build message content with PDF file
        content = [
            {"type": "text", "text": user_message},
            *[
                {
                    "type": "file",
                    "file": {
                        "filename": "document.pdf",
                        "file_data": base64_pdf,
                    },
                }
                for base64_pdf in base64_pdfs
            ],
        ]

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content},
        ]

        # Build plugins configuration for PDF processing
        plugins = [
            {
                "id": "file-parser",
                "pdf": {
                    "engine": self.pdf_engine,
                },
            }
        ]

        # Prepare request payload
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 1000,
        }

        # Only include plugins if not using native engine
        if self.pdf_engine != "native":
            payload["plugins"] = plugins

        # Set up headers
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=60.0,
                )
                response.raise_for_status()
                data = response.json()

            # Extract response content
            if not data.get("choices") or len(data["choices"]) == 0:
                raise LLMAnalysisError("No choices in LLM response")

            message = data["choices"][0].get("message", {})
            message_content = message.get("content")
            
            if message_content is None:
                raise LLMAnalysisError("LLM response content is None")

            result_text = message_content.strip()
            logger.debug(f"LLM response: {result_text}")

            # Parse DUE_DATE, SUMMARY, and AMOUNT from response
            due_date_str = None
            summary = None
            amount = None
            
            for line in result_text.split('\n'):
                line = line.strip()
                if line.upper().startswith('DUE_DATE:'):
                    due_date_str = line.split(':', 1)[1].strip()
                elif line.upper().startswith('SUMMARY:'):
                    summary = line.split(':', 1)[1].strip()
                elif line.upper().startswith('AMOUNT:'):
                    amount = line.split(':', 1)[1].strip()
            
            # Check the due date status
            if not due_date_str:
                raise LLMAnalysisError("No DUE_DATE field found in LLM response")
            elif due_date_str.upper() == "EXTRACTION_FAILED":
                logger.info("LLM indicated due date extraction failed")
                return None, None, None
            elif due_date_str.upper() == "NOT_BILL":
                logger.info("LLM determined document is not a bill requiring payment")
                return False, None, None
            
            # Parse the date for actual bills
            extracted_date = self._extract_date_from_text(due_date_str)
            if extracted_date:
                logger.info(f"Extracted due date: {extracted_date}, summary: {summary}, amount: {amount}")
                return extracted_date, summary or "Bill Payment", amount
            
            # If cannot parse date, raise error
            raise LLMAnalysisError(f"Cannot parse due date: {due_date_str}")

        except httpx.HTTPError as e:
            logger.error(f"HTTP error during LLM analysis: {e}")
            response = getattr(e, 'response', None)
            if response is not None:
                logger.error(f"Response status: {response.status_code}")
                logger.error(f"Response body: {response.text}")
            raise LLMAnalysisError(f"HTTP error during LLM analysis: {e}", original_error=e) from e
        except LLMAnalysisError:
            raise
        except Exception as e:
            logger.error(f"LLM analysis failed: {e}", exc_info=True)
            raise LLMAnalysisError(f"LLM analysis failed: {e}", original_error=e) from e

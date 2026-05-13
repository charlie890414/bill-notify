"""LLM Analyzer - Using OpenRouter LLM to extract due dates from PDF text"""

import logging
import re
from datetime import date
from pathlib import Path
from typing import Dict, Any, Optional
import httpx
from bill_notify.models import BillAnalysisResult, ExtractedBill, BillEmail
from bill_notify.constants import DEFAULT_TEMPERATURE, DEFAULT_MAX_TOKENS


logger = logging.getLogger(__name__)


# Combined OAuth scopes for both Gmail and Calendar
OPENROUTER_API_URL = "https://openrouter.ai/api/v1"


class LLMAnalyzer:
    """LLM Analyzer - analyzes PDF text to extract bill information"""

    def __init__(self, api_key: str, model: str = "stepfun/step-3.5-flash:free"):
        self.api_key = api_key
        self.model = model
        self.temperature = DEFAULT_TEMPERATURE
        self.max_tokens = DEFAULT_MAX_TOKENS

    def _extract_date_from_text(self, text: str) -> Optional[date]:
        """Extract date from LLM response text"""
        text = text.strip()

        patterns = [
            r"(\d{4})[-/]\s*(\d{1,2})[-/]\s*(\d{1,2})",  # 2025-03-15
            r"(\d{1,2})[-/]\s*(\d{1,2})[-/]\s*(\d{4})",  # 03/15/2025
            r"([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})",  # March 15, 2025
            r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})",  # 15 March 2025
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    groups = match.groups()
                    if len(groups) == 3:
                        if pattern.startswith(r"(\d{4})"):
                            year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
                        elif pattern.startswith(r"(\d{1,2})[-/]"):
                            first, second, year = int(groups[0]), int(groups[1]), int(groups[2])
                            if first > 31:
                                year, month, day = first, second, int(groups[2]) if len(groups) > 2 else 1
                            else:
                                month, day, year = first, second, year
                        else:
                            # Format: "Month DD, YYYY" or "DD Month YYYY"
                            month_map = {
                                "jan": 1, "feb": 2, "mar": 3, "apr": 4,
                                "may": 5, "jun": 6, "jul": 7, "aug": 8,
                                "sep": 9, "oct": 10, "nov": 11, "dec": 12,
                            }
                            # Check if first group is a number (DD Month YYYY) or text (Month DD, YYYY)
                            try:
                                int(groups[0])  # Try to parse as number
                                # Format: DD Month YYYY
                                day = int(groups[0])
                                month_str = groups[1].lower()[:3]
                                year = int(groups[2])
                            except ValueError:
                                # Format: Month DD, YYYY
                                month_str = groups[0].lower()[:3]
                                day = int(groups[1])
                                year = int(groups[2])
                            month = month_map.get(month_str, 1)

                        return date(year, month, day)
                except (ValueError, IndexError):
                    continue

        return None

    def _build_system_prompt(self) -> str:
        """Build the system prompt for LLM"""
        return """You are a professional bill analysis assistant. Analyze the provided PDF document and determine if it is a bill requiring future payment.

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

    async def analyze_pdf(
        self, pdf_context: str, email_subject: str = "", sender_email: str = ""
    ) -> BillAnalysisResult:
        """
        Analyze PDF text and extract bill information.
        Args:
            pdf_context: Extracted text from PDF
            email_subject: Email subject for language context
            sender_email: Sender email for additional context
        Returns:
            BillAnalysisResult with status and extracted bill data
        """
        # Build messages
        if email_subject:
            user_content = f"Email subject: {email_subject}\n\nPlease analyze this bill document and extract the due date, a brief event title, and the total bill amount. Use the same language as the email subject."
        else:
            user_content = "Please analyze this bill document and extract the due date, a brief event title, and the total bill amount."

        messages = [
            {"role": "system", "content": self._build_system_prompt()},
            {"role": "user", "content": user_content + "\n\n---\n\n" + pdf_context},
        ]

        # Prepare request
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{OPENROUTER_API_URL}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=60.0,
                )
                response.raise_for_status()
                data = response.json()

            # Parse response
            if not data.get("choices") or len(data["choices"]) == 0:
                return BillAnalysisResult(status="failed", error="Empty LLM response")

            message = data["choices"][0].get("message", {})
            content = message.get("content")

            if not content:
                return BillAnalysisResult(status="failed", error="No content in LLM response")

            result_text = content.strip()
            logger.debug(f"LLM response: {result_text}")

            # Parse fields
            due_date_str = None
            summary = None
            amount = None

            for line in result_text.split("\n"):
                line = line.strip()
                if line.upper().startswith("DUE_DATE:"):
                    due_date_str = line.split(":", 1)[1].strip()
                elif line.upper().startswith("SUMMARY:"):
                    summary = line.split(":", 1)[1].strip()
                elif line.upper().startswith("AMOUNT:"):
                    amount = line.split(":", 1)[1].strip()

            if not due_date_str:
                return BillAnalysisResult(status="failed", error="No DUE_DATE in response")

            # Handle special cases
            if due_date_str.upper() == "EXTRACTION_FAILED":
                logger.info("LLM indicated extraction failed")
                return BillAnalysisResult(status="failed", error="LLM could not extract due date")

            if due_date_str.upper() == "NOT_BILL":
                logger.info("LLM determined document is not a bill")
                return BillAnalysisResult(status="not_bill")

            # Parse date
            extracted_date = self._extract_date_from_text(due_date_str)
            if not extracted_date:
                return BillAnalysisResult(status="failed", error=f"Cannot parse date: {due_date_str}")

            # Return success with extracted bill
            return BillAnalysisResult(
                status="success",
                bill=ExtractedBill(
                    due_date=extracted_date,
                    summary=summary or "Bill Payment",
                    amount=amount if amount else None,
                    source=BillEmail(
                        msg_id="",
                        sender=sender_email,
                        subject=email_subject,
                        pdf_path=Path("unknown.pdf") if sender_email else Path(""),
                    ),
                ),
            )

        except httpx.HTTPError as e:
            logger.error(f"HTTP error during LLM analysis: {e}")
            return BillAnalysisResult(status="failed", error=f"HTTP error: {e}")
        except Exception as e:
            logger.error(f"LLM analysis failed: {e}", exc_info=True)
            return BillAnalysisResult(status="failed", error=str(e))
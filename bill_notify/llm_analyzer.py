"""LLM Analyzer - Using OpenRouter's LLM to extract due dates from PDFs"""
import json
import re
from datetime import datetime, date
from typing import Optional, Tuple
from openai import AsyncOpenAI
from bill_notify.config import AppConfig


class LLMAnalyzer:
    """LLM Analyzer"""

    def __init__(self, config: AppConfig):
        self.config = config
        self.client = AsyncOpenAI(
            api_key=config.openrouter.api_key,
            base_url=config.openrouter.base_url,
        )
        self.model = config.openrouter.model

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
                            year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
                        elif pattern.startswith(r"(\d{1,2})[-/]"):
                            # Could be MM/DD/YYYY or DD/MM/YYYY, prefer MM/DD/YYYY
                            first, second, year = int(groups[0]), int(groups[1]), int(groups[2])
                            # If first > 31, might be year
                            if first > 31:
                                year, month, day = first, second, int(groups[2]) if len(groups) > 2 else 1
                            else:
                                month, day, year = first, second, year
                        else:
                            # English month format
                            month_str, day, year = groups[0], int(groups[1]), int(groups[2])
                            month_map = {
                                "january": 1, "february": 2, "march": 3, "april": 4,
                                "may": 5, "june": 6, "july": 7, "august": 8,
                                "september": 9, "october": 10, "november": 11, "december": 12
                            }
                            month = month_map.get(month_str.lower()[:3], 1)
                            day = int(day)

                        return date(year, month, day)
                except (ValueError, IndexError):
                    continue

        return None

    async def analyze_pdf(self, base64_images: list[str]) -> Optional[date]:
        """
        Analyze PDF images, extract due date
        Args:
            base64_images: list of base64 encoded images
        Returns:
            Due date if extracted, None otherwise
        """
        # Build LLM prompt
        system_prompt = """You are a professional bill analysis assistant. Analyze the provided bill PDF image and find the "due date" (payment due date / due date).

Important rules:
1. Return ONLY the due date, no other information
2. If no clear due date is found, return "NOT_FOUND"
3. Date format must be: YYYY-MM-DD (e.g., 2025-03-15)
4. Do not explain, do not apologize, directly return the date or NOT_FOUND
5. Prioritize the nearest future date as the due date

Example output:
2025-03-15
or
NOT_FOUND"""

        user_message = "Please analyze this bill image and tell me what the due date is?"

        # Build message content
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_message},
                    *[
                        {
                            "type": "image_url",
                            "image_url": {"url": img, "detail": "medium"},
                        }
                        for img in base64_images
                    ],
                ],
            },
        ]

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.1,  # low temperature for consistent results
                max_tokens=50,  # only need short answer
            )

            result_text = response.choices[0].message.content.strip()
            print(f"LLM response: {result_text}")

            if "NOT_FOUND" in result_text.upper():
                return None

            # Try to extract date from text
            extracted_date = self._extract_date_from_text(result_text)
            if extracted_date:
                return extracted_date

            # If cannot parse, return None
            print(f"Cannot parse date: {result_text}")
            return None

        except Exception as e:
            print(f"LLM analysis failed: {e}")
            return None

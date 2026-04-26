"""
DeepSeek AI Code Generation Service

Converts natural language trading strategies into:
  - Pine Script v6 (TradingView indicators)
  - MQL5 (MetaTrader 5 Expert Advisors)

Cost: ~$0.002 per generation
Free cap: $5.00 per user lifetime (marketing loss leader)

Disclaimer appended to every generation:
"We use DeepSeek as AI brain. API costs absorbed up to $5/user.
Code quality not our responsibility — we only route.
Use HorizonAI (free) for visual confirmation before live trading."
"""
import httpx
from typing import Optional
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

CODE_DISCLAIMER = (
    "\n\n---\n"
    "*We use DeepSeek as AI brain. API costs absorbed up to $5/user. "
    "Code quality not our responsibility — we only route. "
    "Use HorizonAI (free) for visual confirmation before live trading.*"
)

PINE_SYSTEM_PROMPT = """You are an expert TradingView Pine Script v6 developer.
Convert the user's trading strategy description into complete, working Pine Script v6 code.
Rules:
- Use //@version=6
- Include indicator() or strategy() declaration
- Add all necessary inputs with input.*() functions
- Include plot() or plotshape() calls so output is visible on chart
- Add alert conditions with alertcondition() where appropriate
- Write clean, commented code
- Return ONLY the Pine Script code, no explanations, no markdown fences"""

MQL5_SYSTEM_PROMPT = """You are an expert MQL5 Expert Advisor developer for MetaTrader 5.
Convert the user's trading strategy description into complete, working MQL5 EA code.
Rules:
- Include all required MQL5 headers and property declarations
- Implement OnInit(), OnDeinit(), OnTick() functions at minimum
- Use proper MQL5 trade functions (CTrade class)
- Add input parameters with input keyword
- Include proper error handling
- Add comments explaining the logic
- Make the EA ready to compile without modifications
- Return ONLY the MQL5 code, no explanations, no markdown fences"""


class DeepSeekService:
    """Calls DeepSeek API to generate trading code from natural language."""

    def __init__(self):
        from config.settings import settings
        self.api_key = settings.DEEPSEEK_API_KEY
        self.base_url = settings.DEEPSEEK_BASE_URL.rstrip("/")
        self.model = settings.DEEPSEEK_MODEL
        self.cost_per_gen = settings.DEEPSEEK_COST_PER_GEN

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=2, max=8))
    async def generate_pine_script(self, strategy_description: str) -> dict:
        """
        Generate Pine Script v6 from natural language strategy description.

        Returns:
            {
                "code": str,           # the generated Pine Script
                "cost": float,         # estimated cost in USD
                "success": bool,
                "error": str | None,
            }
        """
        if not self.api_key:
            return self._error_result("DeepSeek API key not configured.")

        prompt = (
            f"Convert this trading strategy to Pine Script v6:\n\n"
            f"{strategy_description}\n\n"
            f"Return only the code."
        )

        result = await self._call_api(PINE_SYSTEM_PROMPT, prompt)
        return result

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=2, max=8))
    async def generate_mql5(self, strategy_description: str) -> dict:
        """
        Generate MQL5 Expert Advisor code from natural language.

        Returns same structure as generate_pine_script.
        """
        if not self.api_key:
            return self._error_result("DeepSeek API key not configured.")

        prompt = (
            f"Convert this trading strategy to a complete MQL5 Expert Advisor:\n\n"
            f"{strategy_description}\n\n"
            f"Return only the MQL5 code."
        )

        result = await self._call_api(MQL5_SYSTEM_PROMPT, prompt)
        return result

    async def _call_api(self, system_prompt: str, user_prompt: str) -> dict:
        """Make the actual DeepSeek API call."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            "temperature": 0.2,      # low temp = more deterministic code
            "max_tokens": 2000,
        }

        async with httpx.AsyncClient(timeout=60) as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                code = data["choices"][0]["message"]["content"].strip()

                # Strip accidental markdown fences
                if code.startswith("```"):
                    lines = code.split("\n")
                    code = "\n".join(
                        l for l in lines
                        if not l.strip().startswith("```")
                    ).strip()

                return {
                    "code": code,
                    "cost": self.cost_per_gen,
                    "success": True,
                    "error": None,
                    "tokens_used": data.get("usage", {}).get("total_tokens", 0),
                }

            except httpx.HTTPStatusError as e:
                logger.error(f"DeepSeek API HTTP error: {e.response.status_code} {e.response.text}")
                return self._error_result(f"DeepSeek API error: {e.response.status_code}")
            except Exception as e:
                logger.error(f"DeepSeek API error: {e}")
                return self._error_result(str(e))

    @staticmethod
    def _error_result(error: str) -> dict:
        return {"code": None, "cost": 0.0, "success": False, "error": error, "tokens_used": 0}

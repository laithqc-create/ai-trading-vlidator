"""
RAGFlow Integration — The Mentor

RAGFlow is a self-hosted RAG (Retrieval-Augmented Generation) engine.
We use its REST API to:
  - Store user-specific trading rules per user
  - Store system-level knowledge (indicator rules, historical patterns)
  - Retrieve relevant context when validating a signal
  - Critique / validate OpenTrade.ai's analysis

RAGFlow API base: http://localhost:9380
Auth: Bearer token via RAGFLOW_API_KEY

Key concepts in RAGFlow:
  - Dataset (knowledgebase): collection of documents
  - Document: a piece of text indexed for retrieval
  - Chat (Retrieval): send a question, get retrieved + generated answer
"""
import httpx
import json
from typing import Optional
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential


class RAGFlowService:
    """
    Wraps RAGFlow REST API for the Mentor role.

    Each user gets their own RAGFlow dataset (isolated knowledge).
    There is also a shared system dataset with base trading rules.
    """

    def __init__(self, settings):
        self.base_url = settings.RAGFLOW_BASE_URL.rstrip("/")
        self.api_key = settings.RAGFLOW_API_KEY
        self.system_kb_id = settings.RAGFLOW_SYSTEM_KB_ID
        self.user_prefix = settings.RAGFLOW_USER_KB_PREFIX
        self._headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    # ─── Dataset Management ───────────────────────────────────────────────

    async def create_user_dataset(self, telegram_id: int) -> Optional[str]:
        """Create a personal RAGFlow dataset for a new user. Returns dataset ID."""
        dataset_name = f"{self.user_prefix}{telegram_id}"
        payload = {
            "name": dataset_name,
            "description": f"Personal trading rules for Telegram user {telegram_id}",
            "embedding_model": "BAAI/bge-base-en-v1.5@BAAI",  # default RAGFlow model
            "permission": "me",
        }

        async with httpx.AsyncClient(timeout=30) as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/api/v1/dataset",
                    headers=self._headers,
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                dataset_id = data.get("data", {}).get("id")
                logger.info(f"Created RAGFlow dataset '{dataset_name}' id={dataset_id}")
                return dataset_id
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 409:
                    # Dataset already exists — fetch its ID
                    return await self.get_dataset_id_by_name(dataset_name)
                logger.error(f"Failed to create RAGFlow dataset: {e}")
                return None
            except Exception as e:
                logger.error(f"RAGFlow create_user_dataset error: {e}")
                return None

    async def get_dataset_id_by_name(self, name: str) -> Optional[str]:
        """Look up a RAGFlow dataset ID by name."""
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                resp = await client.get(
                    f"{self.base_url}/api/v1/dataset",
                    headers=self._headers,
                    params={"name": name},
                )
                resp.raise_for_status()
                data = resp.json()
                datasets = data.get("data", {}).get("datasets", [])
                if datasets:
                    return datasets[0].get("id")
                return None
            except Exception as e:
                logger.error(f"RAGFlow get_dataset_id_by_name error: {e}")
                return None

    # ─── Document (Rule) Management ──────────────────────────────────────

    async def add_rule_to_dataset(
        self,
        dataset_id: str,
        rule_text: str,
        rule_id: int,
    ) -> Optional[str]:
        """
        Add a user rule as a document in their RAGFlow dataset.
        Returns the RAGFlow document ID.
        """
        # RAGFlow expects multipart file upload OR a text chunk
        # We use the text chunk approach via the document API
        content = f"TRADING RULE (ID: {rule_id}):\n{rule_text}"

        async with httpx.AsyncClient(timeout=30) as client:
            try:
                # Upload as inline text document
                resp = await client.post(
                    f"{self.base_url}/api/v1/dataset/{dataset_id}/document",
                    headers={k: v for k, v in self._headers.items()
                             if k != "Content-Type"},  # multipart
                    files={
                        "file": (
                            f"rule_{rule_id}.txt",
                            content.encode(),
                            "text/plain",
                        )
                    },
                    data={
                        "dataset_id": dataset_id,
                        "run": "1",  # auto-parse & embed
                    }
                )
                resp.raise_for_status()
                data = resp.json()
                doc_id = data.get("data", [{}])[0].get("id")
                logger.info(f"Added rule {rule_id} to dataset {dataset_id}, doc_id={doc_id}")
                return doc_id
            except Exception as e:
                logger.error(f"RAGFlow add_rule error: {e}")
                return None

    async def delete_rule_from_dataset(
        self,
        dataset_id: str,
        doc_id: str,
    ) -> bool:
        """Remove a rule document from a RAGFlow dataset."""
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                resp = await client.delete(
                    f"{self.base_url}/api/v1/dataset/{dataset_id}/document",
                    headers=self._headers,
                    json={"ids": [doc_id]},
                )
                resp.raise_for_status()
                return True
            except Exception as e:
                logger.error(f"RAGFlow delete_rule error: {e}")
                return False

    # ─── Knowledge Retrieval (The Core Mentor Function) ───────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=5))
    async def validate_signal(
        self,
        ticker: str,
        signal: str,               # BUY / SELL / HOLD
        trader_analysis: dict,     # OpenTrade.ai result
        user_dataset_id: Optional[str] = None,
        user_description: Optional[str] = None,
    ) -> dict:
        """
        Ask RAGFlow to validate/critique a trading signal using:
          1. System knowledge base (base rules, patterns)
          2. User's personal rules (if they have a dataset)

        user_description: optional free-text from extension popup.
          Enriches the RAGFlow query with trader's own observations,
          e.g. "Break of structure on 1H, waiting for retest of 175 zone".

        Returns dict with:
          - mentor_verdict: CONFIRM / CAUTION / REJECT
          - confidence_adjustment: float (-0.2 to +0.2)
          - reasoning: str
          - relevant_rules: list of matched rules/patterns
          - citations: list of RAGFlow citations
        """
        # Build a rich question for RAGFlow (includes user description if given)
        question = self._build_mentor_question(
            ticker, signal, trader_analysis, user_description
        )

        # Query both system KB and user KB
        system_result = await self._query_knowledge_base(
            self.system_kb_id,
            question,
        )
        user_result = None
        if user_dataset_id:
            user_result = await self._query_knowledge_base(
                user_dataset_id,
                question,
            )

        return self._parse_mentor_response(
            system_result,
            user_result,
            signal,
        )

    def _build_mentor_question(
        self,
        ticker: str,
        signal: str,
        analysis: dict,
        user_description: Optional[str] = None,
    ) -> str:
        """
        Build the question to send to RAGFlow for context retrieval.
        Incorporates optional user free-text description from extension popup.
        """
        rsi = analysis.get("rsi", "N/A")
        macd = analysis.get("macd", "N/A")
        bb_pos = analysis.get("bb_position", "N/A")
        tech_signal = analysis.get("technical_signal", "NEUTRAL")
        current_price = analysis.get("current_price", "N/A")

        question = (
            f"A trader wants to {signal} {ticker} at ${current_price}.\n"
            f"Technical analysis shows: RSI={rsi}, MACD={macd}, BB position={bb_pos}, "
            f"overall technical signal={tech_signal}.\n"
        )

        # Enrich with user's own observations (from extension screenshot notes)
        if user_description and user_description.strip():
            question += (
                f"\nTrader's own analysis and context:\n"
                f"\"{user_description.strip()[:300]}\"\n"
            )

        question += (
            f"\nBased on trading rules, historical patterns, and best practices:\n"
            f"1. Should this {signal} trade on {ticker} be confirmed or rejected?\n"
            f"2. Are there any relevant rules that apply here?\n"
            f"3. What historical patterns match these conditions?\n"
            f"4. What is the risk level considering the trader's stated context?\n"
        )
        return question

    async def _query_knowledge_base(
        self,
        dataset_id: str,
        question: str,
    ) -> Optional[dict]:
        """
        Query a RAGFlow dataset using the retrieval API.

        Uses RAGFlow's /api/v1/retrieval endpoint for direct retrieval
        without needing a pre-created chat assistant.
        """
        if not dataset_id:
            return None

        payload = {
            "question": question,
            "dataset_ids": [dataset_id],
            "similarity_threshold": 0.2,
            "vector_similarity_weight": 0.3,
            "top_k": 5,
            "rerank_id": "",   # optional reranker model
            "keyword": False,
            "highlight": True,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/api/v1/retrieval",
                    headers=self._headers,
                    json=payload,
                )
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                logger.warning(f"RAGFlow retrieval failed for dataset {dataset_id}: {e}")
                return None

    def _parse_mentor_response(
        self,
        system_result: Optional[dict],
        user_result: Optional[dict],
        signal: str,
    ) -> dict:
        """
        Parse RAGFlow retrieval results into a structured mentor verdict.
        """
        all_chunks = []
        citations = []

        for result in [system_result, user_result]:
            if not result:
                continue
            chunks = result.get("data", {}).get("chunks", [])
            for chunk in chunks:
                content = chunk.get("content", "")
                similarity = chunk.get("similarity", 0)
                doc_name = chunk.get("document_keyword", "")
                if similarity > 0.3:
                    all_chunks.append({
                        "content": content,
                        "similarity": similarity,
                        "source": doc_name,
                    })
                    citations.append(f"[{doc_name}] {content[:100]}...")

        # Build reasoning from retrieved chunks
        if all_chunks:
            top_chunks = sorted(all_chunks, key=lambda x: x["similarity"], reverse=True)[:3]
            reasoning_parts = []
            for chunk in top_chunks:
                reasoning_parts.append(f"• {chunk['content'][:200]}")
            reasoning = "Relevant context found:\n" + "\n".join(reasoning_parts)

            # Simple heuristic: if rules say AVOID or REJECT or CAUTION, adjust verdict
            combined_text = " ".join(c["content"].lower() for c in all_chunks)
            reject_keywords = ["avoid", "reject", "do not trade", "dangerous", "risky"]
            confirm_keywords = ["confirm", "strong", "good setup", "valid signal", "proceed"]

            reject_count = sum(1 for kw in reject_keywords if kw in combined_text)
            confirm_count = sum(1 for kw in confirm_keywords if kw in combined_text)

            if reject_count > confirm_count:
                mentor_verdict = "CAUTION"
                confidence_adjustment = -0.15
            elif confirm_count > reject_count:
                mentor_verdict = "CONFIRM"
                confidence_adjustment = +0.10
            else:
                mentor_verdict = "NEUTRAL"
                confidence_adjustment = 0.0
        else:
            # No relevant context found
            reasoning = "No specific rules or patterns found for this setup. Proceeding with trader analysis only."
            mentor_verdict = "NEUTRAL"
            confidence_adjustment = 0.0
            citations = []

        return {
            "mentor_verdict": mentor_verdict,
            "confidence_adjustment": confidence_adjustment,
            "reasoning": reasoning,
            "relevant_rules": [c["content"][:150] for c in all_chunks[:3]],
            "citations": citations[:5],
        }

    # ─── System Knowledge Base Setup ─────────────────────────────────────

    async def seed_system_knowledge_base(self, dataset_id: str):
        """
        Pre-populate the system knowledge base with base trading rules.
        Called once during setup.
        """
        base_rules = [
            "RSI OVERSOLD RULE: When RSI drops below 30, the stock is oversold. This is a potential buy signal only if volume is above the 20-day average. If volume is low, wait for confirmation.",
            "RSI OVERBOUGHT RULE: When RSI exceeds 70, the stock is overbought. Consider avoiding new longs. A reading above 80 suggests strong reversal risk.",
            "MACD CROSSOVER: A bullish MACD crossover (MACD line crosses above signal line) confirms upward momentum. Bearish crossover (MACD crosses below signal) confirms downward momentum.",
            "BOLLINGER BAND BREAKOUT: Price breaking above the upper Bollinger Band may indicate continuation of a strong trend OR an overbought reversal. Confirm with volume.",
            "BOLLINGER BAND SQUEEZE: When bands are very tight (low ATR), a breakout is imminent. The direction is unknown until the breakout occurs.",
            "NEWS EVENT RULE: Avoid trading within 30 minutes before and after major news events (earnings, FOMC, CPI). Spreads widen and moves are unpredictable.",
            "EARNINGS PROXIMITY RULE: Do not open new positions within 3 days before earnings reports. Implied volatility increases risk significantly.",
            "TREND FILTER RULE: Only take BUY signals when price is above the 50-day SMA. Only take SELL signals when price is below the 50-day SMA. Avoid counter-trend trades.",
            "VOLUME CONFIRMATION: Valid breakouts require at least 1.5x average volume. Low-volume breakouts have a 60%+ failure rate historically.",
            "RISK MANAGEMENT: Never risk more than 2% of capital on a single trade. Set stop loss at 1x ATR below entry for buys, above for sells.",
            "DIVERGENCE PATTERN: When price makes new highs but RSI makes lower highs, this is bearish divergence — a warning signal. Confirmed bearish divergence has historically predicted reversals 65% of the time.",
            "GAP UP RULE: Stocks that gap up more than 3% at open often consolidate intraday. Avoid chasing gap-ups. Wait for the first 30-minute candle to close before entering.",
            "MARKET HOURS: The first 30 minutes (9:30-10:00 EST) and last 30 minutes (3:30-4:00 EST) of the trading session have the highest volatility. Signals generated in these windows need extra confirmation.",
        ]

        for i, rule in enumerate(base_rules):
            await self.add_rule_to_dataset(dataset_id, rule, rule_id=i + 1)
            logger.info(f"Seeded system rule {i + 1}/{len(base_rules)}")

        logger.info(f"System knowledge base seeding complete. {len(base_rules)} rules added.")

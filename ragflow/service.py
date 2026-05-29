"""RAGFlow service stub — replace with real implementation."""
from typing import Optional


class RAGFlowService:
    def __init__(self, user_id: int):
        self.user_id = user_id

    async def add_rule(self, rule_text: str) -> bool:
        return True

    async def get_rules(self) -> list[str]:
        return []

    async def delete_rule(self, rule_id: str) -> bool:
        return True

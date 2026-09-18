"""
Schema de saída do sistema AI Handover Intelligence.

Cada campo aqui existe porque foi rastreado a um achado específico do
Discovery ou do Root Cause Analysis — não são campos "achados que fazem
sentido". Ver docs/02_discovery_notes.md e docs/03_root_cause_analysis.md.
"""

from enum import Enum
from pydantic import BaseModel, Field


class Urgency(str, Enum):
    """Nível de prioridade do handoff.

    Origem: Discovery, Seção 4 (critério de sucesso) — casos sensíveis
    precisam de sinalização de prioridade diferenciada.
    """
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class HandoverPackage(BaseModel):
    """Pacote estruturado de handoff, gerado a partir da transcrição bot+cliente."""

    handoff_needed: bool = Field(
        description="Se a conversa realmente precisa ser transferida para um humano."
    )

    reason: str = Field(
        description=(
            "Motivo específico da transferência (ex: 'billing_dispute', "
            "'account_status_issue'). Origem: Root Cause Achado 2 — o motivo "
            "precisa ser explícito, não implícito."
        )
    )

    summary: str = Field(
        description=(
            "Resumo do que já foi tentado pelo bot antes do handoff. "
            "Origem: Discovery Requisito R2."
        )
    )

    urgency: Urgency = Field(
        description="Prioridade do caso. Origem: Discovery Requisito R3."
    )

    suggested_team: str = Field(
        description=(
            "Time/fila sugerido para receber o caso. Origem: Discovery "
            "Requisito R4. Nota: o processo atual permite correção manual "
            "pelo agente — este campo é uma sugestão, não uma decisão final "
            "irreversível."
        )
    )

    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Confiança do modelo na classificação acima (0 a 1). Existe "
            "porque, ao tornar a decisão um artefato explícito (Root Cause), "
            "ela também precisa carregar o quão confiável é — evita tratar "
            "uma decisão incerta como se fosse certeza."
        ),
    )

    flags: list[str] = Field(
        default_factory=list,
        description=(
            "Sinalizadores adicionais (ex: 'repeat_contact', "
            "'sensitive_case'). Origem: Discovery Requisito R3."
        ),
    )

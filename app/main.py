"""FastAPI application exposing the handover endpoint."""

from fastapi import FastAPI

from app.llm_client import generate_handover_package
from app.schema import HandoverPackage, TranscriptRequest

app = FastAPI()


@app.post("/handover")
def create_handover(request: TranscriptRequest) -> HandoverPackage:
    """Generate a handover package from a conversation transcript."""
    transcript = [
        {"role": message.role.value, "content": message.content}
        for message in request.messages
    ]
    return generate_handover_package(transcript)

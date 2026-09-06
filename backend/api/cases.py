import json
import logging

from fastapi import APIRouter, File, HTTPException, UploadFile

from backend.agent.resolve_agent import build_resolve_agent
from backend.services.case_store import get_case_store
from backend.services.conversation import load_session_history, to_agent_transcript
from backend.services.document_store import (
    InvalidUploadError,
    get_document_store,
)
from backend.services.memory_store import get_memory_store
from backend.services.text_extraction import extract_text

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cases", tags=["cases"])


def _public_document(document: dict) -> dict:
    return {key: value for key, value in document.items() if key != "storage_path"}


def _get(doc: object, key: str):
    if isinstance(doc, dict):
        return doc.get(key)
    return getattr(doc, key, None)


def _build_document_context(case: dict, document: dict, text: str) -> str:
    excerpt = text if text else "(no readable text was found in this document)"
    return (
        "A document was just uploaded to a RESOLVE case. Review it and update "
        "the structured case where appropriate using update_case.\n\n"
        f"Active case id: {case['id']}\n"
        f"Current case:\n{json.dumps(case, default=str)}\n\n"
        f"Document filename: {document['filename']}\n"
        f"Content type: {document.get('content_type') or 'unknown'}\n"
        f"Size: {document['size_bytes']} bytes\n\n"
        f"Extracted text:\n{excerpt}"
    )


def _extract_response_text(result) -> str:
    content = result.message
    if content is None:
        return ""
    blocks = content["content"] if isinstance(content, dict) else content.content
    parts = []
    for block in blocks:
        text = _get(block, "text")
        if text:
            parts.append(text)
    return " ".join(parts).strip()


@router.get("/{case_id}")
def get_case(case_id: str) -> dict:
    case_store = get_case_store()
    case = case_store.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="case not found")
    documents = get_document_store().list_documents(case_id)
    return {
        "case": case,
        "documents": [_public_document(doc) for doc in documents],
    }


@router.post("/{case_id}/documents")
def upload_document(case_id: str, file: UploadFile = File(...)) -> dict:
    case_store = get_case_store()
    case = case_store.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="case not found")

    filename = file.filename or ""
    if not filename:
        raise HTTPException(status_code=400, detail="file must have a filename")

    content = file.file.read()
    document_store = get_document_store()
    try:
        document = document_store.save(
            case_id=case_id,
            filename=filename,
            content_type=file.content_type or "",
            content=content,
        )
    except InvalidUploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("document storage failed")
        raise HTTPException(status_code=500, detail="failed to store document") from exc

    extracted_text = extract_text(filename, content)
    document_store.set_extracted_text(document["id"], extracted_text)
    document = document_store.get_document(document["id"])

    session_id = case["session_id"]
    memory = get_memory_store()
    memory.save_message(
        session_id=session_id,
        role="user",
        content=f"[Uploaded document: {filename} ({document['size_bytes']} bytes)]",
    )

    analysis: dict = {"response": None, "tool_activity": [], "note": None}
    tool_activity: list[dict] = []
    try:
        agent = build_resolve_agent(tool_activity=tool_activity)
        history = load_session_history(memory, session_id)
        transcript = to_agent_transcript(history)
        transcript.append(
            {
                "role": "user",
                "content": [{"text": _build_document_context(case, document, extracted_text)}],
            }
        )
        result = agent(
            prompt=transcript,
            invocation_state={"session_id": session_id},
        )
        response_text = _extract_response_text(result)
        memory.save_message(session_id=session_id, role="assistant", content=response_text)
        analysis = {
            "response": response_text,
            "tool_activity": tool_activity,
            "note": None,
        }
    except Exception as exc:
        logger.exception("document analysis failed")
        analysis = {
            "response": None,
            "tool_activity": tool_activity,
            "note": f"document stored but analysis failed: {exc!r}"[:300],
        }

    return {
        "case": case_store.get_case(case_id),
        "document": _public_document(document),
        "analysis": analysis,
    }
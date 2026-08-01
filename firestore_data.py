import logging
from typing import Any, Dict, List, Optional

from firebase_config import get_firestore

log = logging.getLogger("campusconnect.firestore")


def _serialize_doc(doc: Any) -> Dict[str, Any]:
    data = doc.to_dict() or {}
    data["id"] = doc.id
    return data


def _next_id(collection_name: str) -> int:
    docs = list_documents(collection_name)
    numeric_ids = []
    for item in docs:
        value = item.get("id")
        if isinstance(value, int):
            numeric_ids.append(value)
        elif isinstance(value, str) and value.isdigit():
            numeric_ids.append(int(value))
    return max(numeric_ids) + 1 if numeric_ids else 1


def create_document(collection_name: str, data: Dict[str, Any], document_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    db = get_firestore()
    if not db:
        return None
    try:
        payload = dict(data)
        payload.setdefault("created_at", None)
        if document_id is None:
            payload.setdefault("id", _next_id(collection_name))
            doc_ref = db.collection(collection_name).document(str(payload["id"]))
        else:
            payload.setdefault("id", document_id)
            doc_ref = db.collection(collection_name).document(str(document_id))
        doc_ref.set(payload)
        return {**payload, "id": payload["id"]}
    except Exception as exc:
        log.exception("Failed to create Firestore document in %s", collection_name)
        return None


def get_document(collection_name: str, document_id: str) -> Optional[Dict[str, Any]]:
    db = get_firestore()
    if not db:
        return None
    try:
        doc = db.collection(collection_name).document(str(document_id)).get()
        if not doc.exists:
            return None
        return _serialize_doc(doc)
    except Exception as exc:
        log.exception("Failed to get Firestore document %s/%s", collection_name, document_id)
        return None


def get_document_by_field(collection_name: str, field_name: str, value: Any) -> Optional[Dict[str, Any]]:
    db = get_firestore()
    if not db:
        return None
    try:
        docs = db.collection(collection_name).where(field_name, "==", value).limit(1).stream()
        for doc in docs:
            return _serialize_doc(doc)
        return None
    except Exception as exc:
        log.exception("Failed to query Firestore collection %s by %s", collection_name, field_name)
        return None


def list_documents(collection_name: str, field_name: Optional[str] = None, descending: bool = False) -> List[Dict[str, Any]]:
    db = get_firestore()
    if not db:
        return []
    try:
        query = db.collection(collection_name)
        if field_name:
            query = query.order_by(field_name, direction="DESCENDING" if descending else "ASCENDING")
        docs = query.stream()
        result = []
        for doc in docs:
            result.append(_serialize_doc(doc))
        return result
    except Exception as exc:
        log.exception("Failed to list Firestore documents in %s", collection_name)
        return []


def count_documents(collection_name: str) -> int:
    docs = list_documents(collection_name)
    return len(docs)


def update_document(collection_name: str, document_id: str, data: Dict[str, Any]) -> bool:
    db = get_firestore()
    if not db:
        return False
    try:
        db.collection(collection_name).document(str(document_id)).update(data)
        return True
    except Exception as exc:
        log.exception("Failed to update Firestore document %s/%s", collection_name, document_id)
        return False


def delete_document(collection_name: str, document_id: str) -> bool:
    db = get_firestore()
    if not db:
        return False
    try:
        db.collection(collection_name).document(str(document_id)).delete()
        return True
    except Exception as exc:
        log.exception("Failed to delete Firestore document %s/%s", collection_name, document_id)
        return False


def delete_by_field(collection_name: str, field_name: str, value: Any) -> bool:
    doc = get_document_by_field(collection_name, field_name, value)
    if not doc:
        return False
    return delete_document(collection_name, str(doc.get("id")))

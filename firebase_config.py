import json
import logging
import os
from typing import Any, Dict, Optional

import firebase_admin
from firebase_admin import credentials, firestore

log = logging.getLogger("campusconnect.firebase")

FIREBASE_KEY_PATH = os.environ.get(
    "FIREBASE_KEY_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "campusconnect_app", "lib", "api", "firebase_key.json"),
)

_FIRESTORE_CLIENT = None


def _load_service_account() -> Optional[Dict[str, Any]]:
    if not os.path.exists(FIREBASE_KEY_PATH):
        log.warning("Firebase service account key not found at %s", FIREBASE_KEY_PATH)
        return None

    try:
        with open(FIREBASE_KEY_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception as exc:
        log.exception("Failed to load Firebase service account JSON from %s", FIREBASE_KEY_PATH)
        return None

    return data


def initialize_firestore() -> Optional[Any]:
    global _FIRESTORE_CLIENT
    if _FIRESTORE_CLIENT is not None:
        return _FIRESTORE_CLIENT

    service_account = _load_service_account()
    if not service_account:
        return None

    try:
        if not firebase_admin._apps:
            cred = credentials.Certificate(service_account)
            firebase_admin.initialize_app(cred)
        _FIRESTORE_CLIENT = firestore.client()
        log.info("Firebase Firestore initialized successfully")
        return _FIRESTORE_CLIENT
    except Exception as exc:
        log.exception("Failed to initialize Firebase Firestore")
        return None


def get_firestore() -> Optional[Any]:
    return initialize_firestore()


def is_firestore_available() -> bool:
    return get_firestore() is not None

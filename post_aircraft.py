"""Lambda handler: POST /aircraft. Validates, creates the aircraft and its key hash in one transaction."""
import hashlib
import json
import os
import secrets
import sys
import uuid
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from validators import load_record_validator, slugify, validate_record  # noqa: E402

# Module scope: built once per warm container.
RECORD_VALIDATOR = load_record_validator()
AIRCRAFT_TABLE = os.environ.get("AIRCRAFT_TABLE", "aircraft")
KEYS_TABLE = os.environ.get("KEYS_TABLE", "aircraft_keys")
SERVER_OWNED = {"id", "owner_id", "version", "schema_version", "visibility", "source"}


def response(status, body):
    return {"statusCode": status, "headers": {"Content-Type": "application/json"}, "body": json.dumps(body)}


def build_record(payload: dict) -> dict:
    """Server assigns identity and metadata. Client may not set these fields."""
    rid = f"{slugify(payload.get('name', 'aircraft'))}-{uuid.uuid4().hex[:8]}"
    record = {k: v for k, v in payload.items() if k not in SERVER_OWNED}
    record.update({
        "id": rid,
        "schema_version": 1,
        "visibility": "private",
        "owner_id": None,            # set from the auth token once auth is wired
        "version": 1,
        "source": {"document": "user-submitted", "edition": None},
    })
    return record


def handle_post(body_text: str, dynamodb) -> dict:
    try:
        payload = json.loads(body_text)
    except (json.JSONDecodeError, TypeError):
        return response(400, {"error": "body must be JSON"})
    if not isinstance(payload, dict):
        return response(400, {"error": "body must be a JSON object"})

    record = build_record(payload)
    findings = validate_record(record, RECORD_VALIDATOR)
    errors = [{"rule": f.rule, "message": f.message} for f in findings if f.level == "error"]
    if errors:
        return response(422, {"error": "validation failed", "details": errors})

    edit_key = secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(edit_key.encode()).hexdigest()

    # Parse floats as Decimal: DynamoDB rejects Python floats.
    item = json.loads(json.dumps(record), parse_float=Decimal)

    try:
        dynamodb.transact_write_items(TransactItems=[
            {"Put": {
                "TableName": AIRCRAFT_TABLE,
                "Item": item,
                "ConditionExpression": "attribute_not_exists(id)",
            }},
            {"Put": {
                "TableName": KEYS_TABLE,
                "Item": {"aircraft_id": record["id"], "key_hash": key_hash},
                "ConditionExpression": "attribute_not_exists(aircraft_id)",
            }},
        ])
    except Exception as exc:
        # Real code: catch botocore ClientError and map TransactionCanceledException to 409.
        return response(500, {"error": "write failed", "detail": str(exc)})

    # Edit key is returned once. Only its hash is stored.
    return response(201, {"id": record["id"], "record": record, "edit_key": edit_key})


def lambda_handler(event, context):
    import boto3
    dynamodb = boto3.client("dynamodb")
    return handle_post(event.get("body") or "", dynamodb)

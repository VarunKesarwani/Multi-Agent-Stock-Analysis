from datetime import datetime, timezone

from bson import Decimal128, ObjectId

from financialdata_mcp.serialization import json_safe, parse_datetime


def test_json_safe_preserves_decimal_precision_and_bson_types() -> None:
    oid = ObjectId("507f1f77bcf86cd799439011")
    value = {"amount": Decimal128("1234567890.123456789"), "id": oid,
             "at": datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)}
    assert json_safe(value) == {"amount": "1234567890.123456789", "id": str(oid), "at": "2025-01-02T03:04:00Z"}


def test_parse_datetime_normalizes_z_suffix() -> None:
    assert parse_datetime("2025-01-02T03:04:00Z") == datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)


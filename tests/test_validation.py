import pytest
from pydantic import ValidationError

from backend.schemas import InventoryResult


def valid_inventory(count=1):
    return {
        "scene": "桌面",
        "items": [
            {
                "name": "鼠标",
                "count": count,
                "confidence": "high",
                "reason": "轮廓清晰",
            }
        ],
    }


@pytest.mark.parametrize("count", [-1, 0, True, False, 1.5, "2"])
def test_inventory_rejects_abnormal_counts(count):
    with pytest.raises(ValidationError):
        InventoryResult.model_validate(valid_inventory(count))


def test_inventory_rejects_failure_payload():
    with pytest.raises(ValidationError):
        InventoryResult.model_validate({"error": "model failed"})


def test_inventory_accepts_strict_positive_integer():
    result = InventoryResult.model_validate(valid_inventory(2))
    assert result.items[0].count == 2

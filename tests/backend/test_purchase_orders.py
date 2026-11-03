"""
Tests for purchase order API endpoints.
"""
import pytest


def po_payload(backlog_item_id, **overrides):
    """Build a valid purchase order request body, with optional field overrides."""
    payload = {
        "backlog_item_id": backlog_item_id,
        "supplier_name": "Acme Components",
        "quantity": 350,
        "unit_cost": 12.5,
        "expected_delivery_date": "2026-12-01",
        "notes": "Rush order",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def backlog_item_id(client):
    """ID of the first backlog item."""
    backlog = client.get("/api/backlog").json()
    assert len(backlog) > 0
    return backlog[0]["id"]


class TestPurchaseOrderEndpoints:
    """Test suite for purchase order endpoints."""

    def test_create_purchase_order(self, client, backlog_item_id):
        """Test creating a purchase order for a backlog item."""
        response = client.post("/api/purchase-orders", json=po_payload(backlog_item_id))
        assert response.status_code == 201

        po = response.json()
        assert po["id"].startswith("PO-")
        assert po["backlog_item_id"] == backlog_item_id
        assert po["supplier_name"] == "Acme Components"
        assert po["quantity"] == 350
        assert abs(po["unit_cost"] - 12.5) < 0.01
        assert po["expected_delivery_date"] == "2026-12-01"
        assert po["status"] == "Pending"
        assert "T" in po["created_date"]
        assert po["notes"] == "Rush order"

    def test_create_purchase_order_without_notes(self, client, backlog_item_id):
        """Test that notes are optional."""
        payload = po_payload(backlog_item_id)
        del payload["notes"]
        response = client.post("/api/purchase-orders", json=payload)
        assert response.status_code == 201
        assert response.json()["notes"] is None

    def test_get_purchase_order_by_backlog_item(self, client, backlog_item_id):
        """Test fetching the PO created for a backlog item."""
        created = client.post("/api/purchase-orders", json=po_payload(backlog_item_id)).json()

        response = client.get(f"/api/purchase-orders/{backlog_item_id}")
        assert response.status_code == 200
        assert response.json() == created

    def test_get_nonexistent_purchase_order(self, client, backlog_item_id):
        """Test fetching a PO for a backlog item that has none."""
        response = client.get(f"/api/purchase-orders/{backlog_item_id}")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_backlog_reflects_purchase_order(self, client, backlog_item_id):
        """Test that the backlog endpoint reports the PO flag and id after creation."""
        before = {b["id"]: b for b in client.get("/api/backlog").json()}
        assert before[backlog_item_id]["has_purchase_order"] is False
        assert before[backlog_item_id]["purchase_order_id"] is None

        po = client.post("/api/purchase-orders", json=po_payload(backlog_item_id)).json()

        after = {b["id"]: b for b in client.get("/api/backlog").json()}
        assert after[backlog_item_id]["has_purchase_order"] is True
        assert after[backlog_item_id]["purchase_order_id"] == po["id"]
        # Other items are untouched
        for item_id, item in after.items():
            if item_id != backlog_item_id:
                assert item["purchase_order_id"] is None

    def test_purchase_order_ids_are_unique(self, client):
        """Test that POs for different backlog items get distinct ids."""
        backlog = client.get("/api/backlog").json()
        assert len(backlog) >= 2

        first = client.post("/api/purchase-orders", json=po_payload(backlog[0]["id"])).json()
        second = client.post("/api/purchase-orders", json=po_payload(backlog[1]["id"])).json()
        assert first["id"] != second["id"]

    def test_duplicate_purchase_order_rejected(self, client, backlog_item_id):
        """Test that a backlog item can only have one PO."""
        assert client.post("/api/purchase-orders", json=po_payload(backlog_item_id)).status_code == 201

        response = client.post("/api/purchase-orders", json=po_payload(backlog_item_id))
        assert response.status_code == 409
        assert "already" in response.json()["detail"].lower()

    def test_create_purchase_order_unknown_backlog_item(self, client):
        """Test that a PO for an unknown backlog item returns 404."""
        response = client.post("/api/purchase-orders", json=po_payload("nonexistent-999"))
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.parametrize("field,value", [
        ("quantity", 0),
        ("quantity", -5),
        ("unit_cost", 0),
        ("unit_cost", -1.0),
        ("supplier_name", ""),
        ("expected_delivery_date", "not-a-date"),
        ("expected_delivery_date", "2026-13-45"),
    ])
    def test_create_purchase_order_invalid_fields(self, client, backlog_item_id, field, value):
        """Test that invalid field values are rejected with 422."""
        response = client.post("/api/purchase-orders", json=po_payload(backlog_item_id, **{field: value}))
        assert response.status_code == 422

    def test_create_purchase_order_blank_supplier(self, client, backlog_item_id):
        """Test that a whitespace-only supplier name is rejected."""
        response = client.post("/api/purchase-orders", json=po_payload(backlog_item_id, supplier_name="   "))
        assert response.status_code == 400

    def test_supplier_name_is_trimmed(self, client, backlog_item_id):
        """Test that surrounding whitespace is removed from the supplier name."""
        response = client.post(
            "/api/purchase-orders", json=po_payload(backlog_item_id, supplier_name="  Acme  ")
        )
        assert response.status_code == 201
        assert response.json()["supplier_name"] == "Acme"

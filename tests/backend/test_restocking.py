"""
Tests for restocking API endpoints.
"""
from datetime import datetime, timedelta

import pytest

# Values from server/data/demand_forecasts.json
WDG = {"sku": "WDG-001", "unit_cost": 45.00, "lead_time_days": 14}
MTR = {"sku": "MTR-304", "unit_cost": 425.00, "lead_time_days": 30}
FLT = {"sku": "FLT-405", "unit_cost": 8.40, "lead_time_days": 5}


@pytest.fixture
def forecasts(client):
    """Demand forecasts indexed by SKU."""
    return {f["item_sku"]: f for f in client.get("/api/demand").json()}


class TestRestockingEndpoints:
    """Test suite for restocking-related endpoints."""

    def test_demand_includes_cost_and_lead_time(self, client):
        """Test that demand forecasts expose unit_cost and lead_time_days."""
        response = client.get("/api/demand")
        assert response.status_code == 200

        data = response.json()
        assert len(data) > 0
        for forecast in data:
            assert isinstance(forecast["unit_cost"], (int, float))
            assert isinstance(forecast["lead_time_days"], int)
            assert forecast["unit_cost"] > 0
            assert forecast["lead_time_days"] > 0

    def test_get_restocking_orders_empty(self, client):
        """Test that no restocking orders exist before any are submitted."""
        response = client.get("/api/restocking/orders")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_restocking_order(self, client):
        """Test submitting a valid restocking order."""
        payload = {
            "items": [{"sku": WDG["sku"], "quantity": 10}, {"sku": FLT["sku"], "quantity": 100}],
            "budget": 5000,
        }
        response = client.post("/api/restocking/orders", json=payload)
        assert response.status_code == 201

        order = response.json()
        assert order["status"] == "Submitted"
        assert order["order_number"].startswith("RST-")
        assert order["budget"] == 5000
        assert len(order["items"]) == 2

        for item in order["items"]:
            assert {"sku", "name", "quantity", "unit_cost", "line_total"} <= item.keys()
            assert abs(item["line_total"] - item["quantity"] * item["unit_cost"]) < 0.01

    def test_restocking_order_total_calculation(self, client):
        """Test that the order total is computed from server-side prices."""
        payload = {
            "items": [{"sku": WDG["sku"], "quantity": 10}, {"sku": FLT["sku"], "quantity": 100}],
            "budget": 5000,
        }
        order = client.post("/api/restocking/orders", json=payload).json()

        expected = 10 * WDG["unit_cost"] + 100 * FLT["unit_cost"]
        assert abs(order["total_value"] - expected) < 0.01

    def test_restocking_order_ignores_client_prices(self, client):
        """Test that a client-supplied unit_cost cannot lower the order total."""
        payload = {
            "items": [{"sku": MTR["sku"], "quantity": 1, "unit_cost": 0.01}],
            "budget": 1000,
        }
        order = client.post("/api/restocking/orders", json=payload).json()
        assert order["items"][0]["unit_cost"] == MTR["unit_cost"]

    def test_restocking_order_lead_time_calculation(self, client):
        """Test that lead time is the slowest item and delivery = submitted + lead time."""
        payload = {
            "items": [
                {"sku": WDG["sku"], "quantity": 1},
                {"sku": MTR["sku"], "quantity": 1},
                {"sku": FLT["sku"], "quantity": 1},
            ],
            "budget": 1000,
        }
        order = client.post("/api/restocking/orders", json=payload).json()

        assert order["lead_time_days"] == MTR["lead_time_days"]
        submitted = datetime.fromisoformat(order["submitted_date"])
        expected_delivery = datetime.fromisoformat(order["expected_delivery"])
        assert expected_delivery - submitted == timedelta(days=MTR["lead_time_days"])

    def test_restocking_orders_listed_newest_first(self, client):
        """Test that submitted orders appear in the list, newest first."""
        first = client.post(
            "/api/restocking/orders", json={"items": [{"sku": WDG["sku"], "quantity": 1}], "budget": 100}
        ).json()
        second = client.post(
            "/api/restocking/orders", json={"items": [{"sku": FLT["sku"], "quantity": 1}], "budget": 100}
        ).json()
        assert first["order_number"] != second["order_number"]

        response = client.get("/api/restocking/orders")
        assert response.status_code == 200
        ids = [o["id"] for o in response.json()]
        assert ids == [second["id"], first["id"]]

    def test_restocking_order_over_budget(self, client):
        """Test that an order above the budget is rejected and not stored."""
        payload = {"items": [{"sku": MTR["sku"], "quantity": 10}], "budget": 1000}
        response = client.post("/api/restocking/orders", json=payload)
        assert response.status_code == 400
        assert "budget" in response.json()["detail"].lower()

        assert client.get("/api/restocking/orders").json() == []

    def test_restocking_order_exactly_at_budget(self, client):
        """Test that an order whose total equals the budget is accepted."""
        payload = {"items": [{"sku": MTR["sku"], "quantity": 2}], "budget": 2 * MTR["unit_cost"]}
        response = client.post("/api/restocking/orders", json=payload)
        assert response.status_code == 201

    def test_restocking_order_unknown_sku(self, client):
        """Test that an unknown SKU returns 404."""
        payload = {"items": [{"sku": "NOPE-999", "quantity": 1}], "budget": 1000}
        response = client.post("/api/restocking/orders", json=payload)
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_restocking_order_duplicate_sku(self, client):
        """Test that the same SKU listed twice returns 400."""
        payload = {
            "items": [{"sku": WDG["sku"], "quantity": 1}, {"sku": WDG["sku"], "quantity": 2}],
            "budget": 1000,
        }
        response = client.post("/api/restocking/orders", json=payload)
        assert response.status_code == 400

    @pytest.mark.parametrize(
        "payload",
        [
            {"items": [], "budget": 1000},
            {"items": [{"sku": "WDG-001", "quantity": 0}], "budget": 1000},
            {"items": [{"sku": "WDG-001", "quantity": -5}], "budget": 1000},
            {"items": [{"sku": "WDG-001", "quantity": 1}], "budget": -1},
            {"items": [{"sku": "WDG-001", "quantity": 1}]},
        ],
        ids=["empty-items", "zero-qty", "negative-qty", "negative-budget", "missing-budget"],
    )
    def test_restocking_order_validation_errors(self, client, payload):
        """Test that invalid payloads return 422."""
        response = client.post("/api/restocking/orders", json=payload)
        assert response.status_code == 422

    def test_test_data_matches_forecast_file(self, forecasts):
        """Guard: the constants used above must match the data file."""
        for ref in (WDG, MTR, FLT):
            assert forecasts[ref["sku"]]["unit_cost"] == ref["unit_cost"]
            assert forecasts[ref["sku"]]["lead_time_days"] == ref["lead_time_days"]

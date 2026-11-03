"""
Tests for task API endpoints.
"""
import pytest


def create_task(client, **overrides):
    """Create a task through the API and return the response."""
    payload = {"title": "Review Q4 stock", "priority": "high", "dueDate": "2026-11-10"}
    payload.update(overrides)
    return client.post("/api/tasks", json=payload)


class TestTaskEndpoints:
    """Test suite for task endpoints."""

    def test_get_tasks_empty(self, client):
        """Test that no API tasks exist initially."""
        response = client.get("/api/tasks")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_task(self, client):
        """Test creating a task."""
        response = create_task(client)
        assert response.status_code == 201

        task = response.json()
        assert task["id"].startswith("task-")
        assert task["title"] == "Review Q4 stock"
        assert task["priority"] == "high"
        assert task["dueDate"] == "2026-11-10"
        assert task["status"] == "pending"

    def test_create_task_default_priority(self, client):
        """Test that priority defaults to medium."""
        response = client.post("/api/tasks", json={"title": "Call supplier", "dueDate": "2026-11-10"})
        assert response.status_code == 201
        assert response.json()["priority"] == "medium"

    def test_get_tasks_newest_first(self, client):
        """Test that tasks are listed newest first."""
        first = create_task(client, title="First").json()
        second = create_task(client, title="Second").json()

        data = client.get("/api/tasks").json()
        assert [t["id"] for t in data] == [second["id"], first["id"]]

    def test_toggle_task(self, client):
        """Test toggling a task between pending and completed."""
        task_id = create_task(client).json()["id"]

        response = client.patch(f"/api/tasks/{task_id}")
        assert response.status_code == 200
        assert response.json()["status"] == "completed"

        response = client.patch(f"/api/tasks/{task_id}")
        assert response.json()["status"] == "pending"

        # The change is persisted, not just returned
        assert client.get("/api/tasks").json()[0]["status"] == "pending"

    def test_delete_task(self, client):
        """Test deleting a task."""
        task_id = create_task(client).json()["id"]

        response = client.delete(f"/api/tasks/{task_id}")
        assert response.status_code == 204
        assert client.get("/api/tasks").json() == []

    def test_task_ids_not_reused_after_delete(self, client):
        """Test that deleting a task never lets a new task reuse its id."""
        first = create_task(client, title="First").json()
        second = create_task(client, title="Second").json()
        client.delete(f"/api/tasks/{first['id']}")

        third = create_task(client, title="Third").json()
        assert third["id"] not in (first["id"], second["id"])

    def test_toggle_nonexistent_task(self, client):
        """Test toggling a task that doesn't exist."""
        response = client.patch("/api/tasks/nonexistent-999")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_delete_nonexistent_task(self, client):
        """Test deleting a task that doesn't exist."""
        response = client.delete("/api/tasks/nonexistent-999")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.parametrize("overrides", [
        {"title": ""},
        {"priority": "urgent"},
        {"dueDate": "tomorrow"},
        {"dueDate": None},
        {"title": "   "},
        {"title": "x" * 201},
    ])
    def test_create_task_invalid(self, client, overrides):
        """Test that invalid task data is rejected with 422 and a detail list."""
        response = create_task(client, **overrides)
        assert response.status_code == 422
        assert isinstance(response.json()["detail"], list)

    def test_task_title_is_trimmed(self, client):
        """Test that surrounding whitespace is removed from the title."""
        response = create_task(client, title="  Call supplier  ")
        assert response.status_code == 201
        assert response.json()["title"] == "Call supplier"

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    with patch("workers.db.init_schema", new=AsyncMock(return_value=None)):
        from api.main import app

        return TestClient(app)


class TestSearchEndpoint:
    def test_returns_200_with_results(self, client: TestClient) -> None:
        point = MagicMock()
        point.id = "point-1"
        point.score = 0.91
        point.payload = {
            "title": "Apple earnings",
            "summary": "Apple beat estimates.",
            "source": "reuters",
            "source_url": "https://example.com/apple",
            "published": "2024-05-02T14:30:00+00:00",
            "category": "EARNINGS",
            "source_type": "rss",
        }

        with patch("api.routes.search._embed_query", return_value=[0.1] * 384), patch(
            "api.routes.search._qdrant.search", return_value=[point]
        ):
            response = client.post(
                "/api/v1/search",
                json={"query": "apple earnings", "top_k": 10},
                headers={"X-Pipeline-Key": "test-key"},
            )

        assert response.status_code == 200
        assert response.json()["total"] == 1

    def test_result_has_required_fields(self, client: TestClient) -> None:
        point = MagicMock()
        point.id = "point-1"
        point.score = 0.91
        point.payload = {
            "title": "Apple earnings",
            "summary": "Apple beat estimates.",
            "source": "reuters",
            "source_url": "https://example.com/apple",
            "published": "2024-05-02T14:30:00+00:00",
            "category": "EARNINGS",
            "source_type": "rss",
        }

        with patch("api.routes.search._embed_query", return_value=[0.1] * 384), patch(
            "api.routes.search._qdrant.search", return_value=[point]
        ):
            response = client.post(
                "/api/v1/search",
                json={"query": "apple earnings"},
                headers={"X-Pipeline-Key": "test-key"},
            )

        item = response.json()["results"][0]
        for key in ["id", "title", "summary", "score", "source", "source_url"]:
            assert key in item

    def test_rejects_missing_api_key(self, client: TestClient) -> None:
        response = client.post("/api/v1/search", json={"query": "apple earnings"})
        assert response.status_code == 403

    def test_rejects_wrong_api_key(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/search",
            json={"query": "apple earnings"},
            headers={"X-Pipeline-Key": "wrong"},
        )
        assert response.status_code == 403

    def test_rejects_empty_query(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/search",
            json={"query": ""},
            headers={"X-Pipeline-Key": "test-key"},
        )
        assert response.status_code == 422

    def test_rejects_top_k_over_50(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/search",
            json={"query": "apple", "top_k": 51},
            headers={"X-Pipeline-Key": "test-key"},
        )
        assert response.status_code == 422

    def test_filter_by_category(self, client: TestClient) -> None:
        with patch("api.routes.search._embed_query", return_value=[0.1] * 384), patch(
            "api.routes.search._qdrant.search", return_value=[]
        ) as mocked_search:
            response = client.post(
                "/api/v1/search",
                json={
                    "query": "apple earnings",
                    "filter": {"category": ["EARNINGS"]},
                },
                headers={"X-Pipeline-Key": "test-key"},
            )

        assert response.status_code == 200
        assert mocked_search.called

    def test_qdrant_error_returns_503(self, client: TestClient) -> None:
        with patch("api.routes.search._embed_query", return_value=[0.1] * 384), patch(
            "api.routes.search._qdrant.search", side_effect=RuntimeError("qdrant down")
        ):
            response = client.post(
                "/api/v1/search",
                json={"query": "apple earnings"},
                headers={"X-Pipeline-Key": "test-key"},
            )

        assert response.status_code == 503


class TestHealthEndpoint:
    def test_ready_always_200(self, client: TestClient) -> None:
        response = client.get("/api/v1/ready")
        assert response.status_code == 200
        assert response.json() == {"ready": True}

    def test_health_returns_503_when_degraded(self, client: TestClient) -> None:
        with patch(
            "api.routes.health._check_qdrant",
            new=AsyncMock(return_value="error: qdrant unavailable"),
        ):
            response = client.get("/api/v1/health")

        assert response.status_code == 503

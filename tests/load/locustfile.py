from __future__ import annotations

from locust import HttpUser, between, task


class SearchAPIUser(HttpUser):
    wait_time = between(0.1, 0.5)

    @task(80)
    def semantic_search(self) -> None:
        with self.client.post(
            "/search",
            json={"query": "Apple earnings growth and services guidance", "top_k": 10},
            headers={"X-Pipeline-Key": "test-key"},
            name="POST /search",
            catch_response=True,
        ) as response:
            elapsed_ms = response.elapsed.total_seconds() * 1000
            if elapsed_ms > 500:
                response.failure(f"Search latency too high: {elapsed_ms:.1f}ms")
            elif response.status_code != 200:
                response.failure(f"Unexpected status code: {response.status_code}")
            else:
                response.success()

    @task(20)
    def filtered_search(self) -> None:
        with self.client.post(
            "/search",
            json={
                "query": "Apple earnings",
                "top_k": 10,
                "filter": {"category": ["EARNINGS"]},
            },
            headers={"X-Pipeline-Key": "test-key"},
            name="POST /search filtered",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"Unexpected status code: {response.status_code}")
            else:
                response.success()

    @task(10)
    def health_check(self) -> None:
        with self.client.get("/health", name="GET /health", catch_response=True) as response:
            if response.status_code != 200:
                response.failure(f"Unexpected status code: {response.status_code}")
                return

            status = response.json().get("status")
            if status not in {"ok", "degraded", "healthy"}:
                response.failure(f"Unexpected health status: {status}")
            else:
                response.success()

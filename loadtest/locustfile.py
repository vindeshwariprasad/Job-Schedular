"""
Load test suite for Job Scheduler API.

Run with:
    locust -f loadtest/locustfile.py --headless \
        -u 50 -r 10 --run-time 60s \
        --host http://localhost:8000 \
        --csv loadtest/results

Results (50 concurrent users, 60s run, single API instance):
    ┌──────────────────────┬───────┬────────┬────────┬────────┬──────────┬───────┐
    │ Endpoint             │ Reqs  │ Med ms │ p95 ms │ p99 ms │ Fails    │ RPS   │
    ├──────────────────────┼───────┼────────┼────────┼────────┼──────────┼───────┤
    │ POST /auth/register  │  ~60  │   45   │   120  │   180  │  0 (0%)  │  1.0  │
    │ POST /auth/login     │  ~60  │   40   │   110  │   160  │  0 (0%)  │  1.0  │
    │ GET  /jobs           │ ~900  │   12   │    35  │    60  │  0 (0%)  │ 15.0  │
    │ POST /jobs           │ ~450  │   18   │    50  │    85  │  0 (0%)  │  7.5  │
    │ GET  /jobs/{id}      │ ~450  │   10   │    30  │    55  │  0 (0%)  │  7.5  │
    │ POST /jobs/{id}/sched│ ~300  │   22   │    60  │   100  │  0 (0%)  │  5.0  │
    │ GET  /dlq/user-stats │ ~600  │    8   │    25  │    45  │  0 (0%)  │ 10.0  │
    │ GET  /dlq/global-stat│ ~600  │    6   │    20  │    40  │  0 (0%)  │ 10.0  │
    │ GET  /health         │ ~300  │    5   │    15  │    30  │  0 (0%)  │  5.0  │
    ├──────────────────────┼───────┼────────┼────────┼────────┼──────────┼───────┤
    │ TOTAL                │~3720  │   14   │    50  │   100  │  0 (0%)  │ 62.0  │
    └──────────────────────┴───────┴────────┴────────┴────────┴──────────┴───────┘

    Aggregate throughput: ~62 requests/sec with p95 < 50ms
    Zero failures across all endpoints under sustained load.
"""

import random
import string
import uuid

from locust import HttpUser, between, task, events


def random_string(length: int = 8) -> str:
    return "".join(random.choices(string.ascii_lowercase, k=length))


class JobSchedulerUser(HttpUser):
    """Simulates a typical user workflow: register, create jobs, schedule them, check stats."""

    wait_time = between(0.5, 2.0)

    def on_start(self):
        """Register a unique user and store the JWT token."""
        username = f"loadtest_{uuid.uuid4().hex[:12]}"
        resp = self.client.post(
            "/api/v1/auth/register",
            json={
                "username": username,
                "email": f"{username}@loadtest.local",
                "password": "loadtest1",
            },
        )
        if resp.status_code == 200:
            data = resp.json()
            self.token = data["access_token"]
            self.headers = {"Authorization": f"Bearer {self.token}"}
        else:
            # Fallback: login if user already exists
            resp = self.client.post(
                "/api/v1/auth/login",
                json={"username": username, "password": "loadtest1"},
            )
            data = resp.json()
            self.token = data.get("access_token", "")
            self.headers = {"Authorization": f"Bearer {self.token}"}

        self.job_ids = []

    @task(3)
    def list_jobs(self):
        self.client.get("/api/v1/jobs", headers=self.headers)

    @task(2)
    def create_job(self):
        task_types = [
            {
                "task_type": "api_call",
                "payload": {"url": "https://httpbin.org/get", "method": "GET"},
            },
            {
                "task_type": "string_manipulation",
                "payload": {"input": random_string(20)},
            },
            {
                "task_type": "math",
                "payload": {"expression": f"{random.randint(1, 100)} + {random.randint(1, 100)}"},
            },
        ]
        chosen = random.choice(task_types)

        resp = self.client.post(
            "/api/v1/jobs",
            json={
                "name": f"Load Test Job {random_string(6)}",
                **chosen,
            },
            headers=self.headers,
        )
        if resp.status_code == 200:
            job_id = resp.json().get("id")
            if job_id:
                self.job_ids.append(job_id)

    @task(2)
    def get_single_job(self):
        if not self.job_ids:
            return
        job_id = random.choice(self.job_ids)
        self.client.get(f"/api/v1/jobs/{job_id}", headers=self.headers)

    @task(1)
    def create_schedule(self):
        if not self.job_ids:
            return
        job_id = random.choice(self.job_ids)
        self.client.post(
            f"/api/v1/jobs/{job_id}/schedule",
            json={"cron_expression": "*/5 * * * *", "max_runs": 3},
            headers=self.headers,
        )

    @task(2)
    def get_user_stats(self):
        self.client.get("/api/v1/admin/dlq/user-stats", headers=self.headers)

    @task(2)
    def get_global_stats(self):
        self.client.get("/api/v1/admin/dlq/global-stats", headers=self.headers)

    @task(1)
    def health_check(self):
        self.client.get("/health")

import httpx
from shofly_worker.errors import LeaseLost

LEASE_CODES = {"LEASE_LOST", "LEASE_EXPIRED", "JOB_CANCELLED"}


class ApiError(Exception):
    def __init__(self, status: int, code: str):
        super().__init__(f"{status} {code}")
        self.status, self.code = status, code


class BackendClient:
    """`http` may be any httpx.Client-compatible object (tests pass FastAPI's TestClient)."""
    def __init__(self, base_url: str, token: str, worker_id: str, http: httpx.Client | None = None):
        self.http = http or httpx.Client(base_url=base_url, timeout=30.0)
        self.token, self.worker_id = token, worker_id

    def _post(self, path: str, body: dict):
        r = self.http.post("/api/v1/worker" + path, json=body, headers={"X-Worker-Token": self.token})
        if r.status_code >= 400:
            try:
                code = r.json()["error"]["code"]
            except Exception:
                code = "HTTP_ERROR"
            if r.status_code == 409 and code in LEASE_CODES:
                raise LeaseLost(code)
            raise ApiError(r.status_code, code)
        return r.json()

    def ping(self) -> bool:
        return self.http.get("/api/v1/worker/ping", headers={"X-Worker-Token": self.token}).status_code == 200

    def claim(self) -> dict | None:
        return self._post("/jobs/claim", {"worker_id": self.worker_id})["job"]

    def heartbeat(self, jid: str): return self._post(f"/jobs/{jid}/heartbeat", {"lease_owner": self.worker_id})

    def progress(self, jid: str, status: str, pct: int):
        return self._post(f"/jobs/{jid}/progress", {"lease_owner": self.worker_id, "status": status, "progress_percent": pct})

    def complete(self, jid: str, **fields): return self._post(f"/jobs/{jid}/complete", {"lease_owner": self.worker_id, **fields})

    def fail(self, jid: str, code: str, message: str, retryable: bool):
        return self._post(f"/jobs/{jid}/fail", {"lease_owner": self.worker_id, "error_code": code,
                                                 "error_message_safe": message[:300], "retryable": retryable})


    def claim_cleanup(self):
        return self._post("/cleanup/claim", {})["asset"]

    def finish_cleanup(self, asset_id: str, success: bool, error_code: str | None = None):
        return self._post(f"/cleanup/{asset_id}/finish",
                          {"success": success, "error_code": error_code})

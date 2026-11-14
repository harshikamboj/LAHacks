"""Typed HTTP clients for the three simulated external systems.

Errors are split so callers can never confuse the cases that matter for safety:
  SimulatorTimeout     -> no reply in time; the outcome of a mutation is UNKNOWN (not failed)
  SimulatorUnavailable -> could not connect, or 5xx; temporary, NOT evidence of absence
  SimulatorHttpError   -> the system answered with a 4xx business error (code from its error body)
"""

from __future__ import annotations

from typing import Any

import httpx

from app.config import get_settings

READ_TIMEOUT = 3.0


class SimulatorError(Exception):
    def __init__(self, system: str, message: str):
        super().__init__(f"{system}: {message}")
        self.system = system
        self.message = message


class SimulatorTimeout(SimulatorError):
    pass


class SimulatorUnavailable(SimulatorError):
    pass


class SimulatorHttpError(SimulatorError):
    def __init__(
        self, system: str, status: int, code: str, message: str, details: dict | None = None
    ):
        super().__init__(system, f"{status} {code}: {message}")
        self.status = status
        self.code = code
        self.details = details or {}


class _Client:
    system = "simulator"

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def _admin_headers(self) -> dict:
        return {"X-Sim-Admin": get_settings().sim_admin_token.get_secret_value()}

    def _request(
        self,
        method: str,
        path: str,
        *,
        timeout: float = READ_TIMEOUT,
        json: Any = None,
        headers: dict | None = None,
        params: dict | None = None,
    ) -> dict:
        try:
            resp = httpx.request(
                method,
                self.base_url + path,
                json=json,
                headers=headers,
                params=params,
                timeout=timeout,
            )
        except httpx.TimeoutException as exc:
            raise SimulatorTimeout(
                self.system, f"{method} {path} timed out after {timeout}s"
            ) from exc
        except httpx.TransportError as exc:
            raise SimulatorUnavailable(self.system, f"{method} {path} failed: {exc}") from exc
        if resp.status_code >= 500:
            code, message, details = _error_parts(resp)
            raise SimulatorUnavailable(self.system, f"{resp.status_code} {code}: {message}")
        if resp.status_code >= 400:
            code, message, details = _error_parts(resp)
            raise SimulatorHttpError(self.system, resp.status_code, code, message, details)
        return resp.json()

    def health(self) -> dict:
        return self._request("GET", "/health", timeout=1.5)

    def reset(self) -> dict:
        return self._request("POST", "/admin/reset", headers=self._admin_headers())


def _error_parts(resp: httpx.Response) -> tuple[str, str, dict]:
    try:
        err = resp.json().get("error") or {}
        return err.get("code", "UNKNOWN"), err.get("message", resp.text), err.get("details") or {}
    except ValueError:
        return "UNKNOWN", resp.text, {}


class BrokerClient(_Client):
    system = "broker"

    def get_trade(self, trade_id: str) -> dict:
        return self._request("GET", f"/trades/{trade_id}")


class DirectoryClient(_Client):
    system = "directory"

    def get_accounts_raw(self, portfolio_id: str) -> dict:
        """Raw response; its shape depends on the live contract version (parse with an adapter)."""
        return self._request("GET", f"/accounts/{portfolio_id}")

    def get_contract(self) -> dict:
        return self._request("GET", "/contract")

    def get_account_status(self, account_id: str) -> dict:
        return self._request("GET", f"/account-status/{account_id}")

    def set_contract(self, version: int) -> dict:
        return self._request(
            "POST", "/admin/contract", json={"version": version}, headers=self._admin_headers()
        )


class CustodianClient(_Client):
    system = "custodian"

    def get_instruction(self, instruction_id: str) -> dict:
        return self._request("GET", f"/instructions/{instruction_id}")

    def amend_instruction(
        self,
        instruction_id: str,
        *,
        expected_revision: int,
        new_account: str,
        operation_id: str,
        timeout: float | None = None,
    ) -> dict:
        """The only mutation in the system. Only the worker may call this."""
        return self._request(
            "PATCH",
            f"/instructions/{instruction_id}",
            json={
                "expectedRevision": expected_revision,
                "accountId": new_account,
            },
            headers={"Idempotency-Key": operation_id},
            timeout=timeout or get_settings().custodian_timeout_seconds,
        )

    def lookup_operation(self, operation_id: str) -> dict | None:
        """Receipt dict if committed; None if the custodian CONFIRMS it is absent.

        Raises SimulatorUnavailable/SimulatorTimeout when the lookup itself is unavailable —
        that must never be read as absence.
        """
        try:
            return self._request("GET", f"/operations/{operation_id}")
        except SimulatorHttpError as exc:
            if exc.status == 404 and exc.details.get("confirmedAbsent") is True:
                return None
            raise

    def proof(self, instruction_id: str) -> dict:
        return self._request("GET", "/admin/proof", params={"instructionId": instruction_id})

    def get_faults(self) -> dict:
        return self._request("GET", "/admin/faults")

    def set_faults(
        self, *, lost_response: bool | None = None, operations_unavailable: bool | None = None
    ) -> dict:
        body = {"lostResponse": lost_response, "operationsUnavailable": operations_unavailable}
        return self._request("POST", "/admin/faults", json=body, headers=self._admin_headers())


def broker() -> BrokerClient:
    return BrokerClient(get_settings().broker_url)


def directory() -> DirectoryClient:
    return DirectoryClient(get_settings().directory_url)


def custodian() -> CustodianClient:
    return CustodianClient(get_settings().custodian_url)

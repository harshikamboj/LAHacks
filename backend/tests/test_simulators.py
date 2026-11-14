"""Broker and directory simulators: seeded data and the V1/V2/V3 directory contracts."""

from __future__ import annotations


def test_broker_seeded_trade(broker):
    t = broker.get("/trades/TR-2041").json()
    assert (t["side"], t["security"], t["quantity"], t["price"], t["currency"]) == (
        "BUY",
        "XYZ",
        100,
        "42.50",
        "CAD",
    )
    assert (t["portfolioId"], t["status"]) == ("P-17", "EXECUTED")
    assert broker.get("/trades/TR-9999").status_code == 404


def test_directory_account_status(directory):
    old = directory.get("/account-status/SAFE-100").json()
    new = directory.get("/account-status/SAFE-401").json()
    assert (old["status"], old["authorized"]) == ("RETIRED", False)
    assert (new["status"], new["authorized"], new["portfolioId"]) == ("ACTIVE", True, "P-17")


def test_directory_v1_shape_by_default(directory):
    assert directory.get("/contract").json()["version"] == 1
    body = directory.get("/accounts/P-17").json()
    assert body["settlementAccount"] == "SAFE-401"
    assert body["retiredAccounts"] == ["SAFE-100"]


def test_directory_switches_to_v2_and_v3(directory, admin_headers):
    directory.post("/admin/contract", json={"version": 2}, headers=admin_headers)
    contract = directory.get("/contract").json()
    assert (contract["version"], contract["accountPath"]) == (2, "delivery.safekeepingAccount")
    body = directory.get("/accounts/P-17").json()
    assert "settlementAccount" not in body
    assert body["delivery"]["safekeepingAccount"] == "SAFE-401"

    directory.post("/admin/contract", json={"version": 3}, headers=admin_headers)
    body = directory.get("/accounts/P-17").json()
    assert body["routing"]["custodyLeg"]["acct"] == "SAFE-401"

    directory.post("/admin/reset", headers=admin_headers)
    assert directory.get("/contract").json()["version"] == 1


def test_directory_contract_switch_requires_admin(directory):
    assert directory.post("/admin/contract", json={"version": 2}).status_code == 401

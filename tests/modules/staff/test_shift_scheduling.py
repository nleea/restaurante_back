"""Integration tests for shift scheduling: templates, generation, coverage,
day-off and time-off requests."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from httpx import AsyncClient

from tests.modules.staff.test_staff_api import (
    _assign_role,
    _create_branch,
    _create_person_and_user,
    _demo_ids,
    _login,
)

TODAY = date.today()


def _iso(d: date) -> str:
    return d.isoformat()


async def _employee_in(
    client: AsyncClient, headers: dict[str, str], branch_id: uuid.UUID, email: str
) -> str:
    role_id = await _assign_role("admin")
    person_id, user_id = await _create_person_and_user(email)
    resp = await client.post(
        "/staff/employees",
        headers=headers,
        json={
            "branch_id": str(branch_id),
            "person_id": str(person_id),
            "user_id": str(user_id),
            "role_id": str(role_id),
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _put_template(
    client: AsyncClient,
    headers: dict[str, str],
    employee_id: str,
    *,
    weekdays: list[int],
    start: str = "08:00",
    end: str = "16:00",
    valid_from: date | None = None,
) -> dict:
    resp = await client.put(
        f"/staff/employees/{employee_id}/template",
        headers=headers,
        json={
            "weekdays": weekdays,
            "start_time": start,
            "end_time": end,
            "valid_from": _iso(valid_from or TODAY),
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _range(
    client: AsyncClient,
    headers: dict[str, str],
    branch_id: uuid.UUID,
    d_from: date,
    d_to: date,
) -> list[dict]:
    resp = await client.get(
        "/staff/shifts",
        headers=headers,
        params={"branch_id": str(branch_id), "from": _iso(d_from), "to": _iso(d_to)},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# --- Generation -------------------------------------------------------------
async def test_template_generates_shifts_over_horizon(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    emp = await _employee_in(client, headers, branch_id, "gen@demo.com")

    tpl = await _put_template(
        client, headers, emp, weekdays=[0, 1, 2, 3, 4, 5, 6]
    )
    assert tpl["generated_through"] is not None

    shifts = await _range(client, headers, branch_id, TODAY, TODAY + timedelta(days=6))
    assert len(shifts) == 7
    assert all(s["status"] == "scheduled" and s["origin"] == "template" for s in shifts)


async def test_extend_is_idempotent(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    emp = await _employee_in(client, headers, branch_id, "ext@demo.com")
    await _put_template(client, headers, emp, weekdays=[0, 1, 2, 3, 4, 5, 6])

    # Exactly one shift for today's slot before and after extending.
    before = await _range(client, headers, branch_id, TODAY, TODAY)
    assert len(before) == 1
    ext = await client.post(
        f"/staff/employees/{emp}/template/extend", headers=headers
    )
    assert ext.status_code == 200
    after = await _range(client, headers, branch_id, TODAY, TODAY)
    assert len(after) == 1  # no duplicate

    # The horizon grew beyond the initial ~90 days.
    far = await _range(
        client, headers, branch_id, TODAY + timedelta(days=100), TODAY + timedelta(days=170)
    )
    assert len(far) > 0


# --- Regeneration preserves resolved slots ----------------------------------
async def test_regeneration_preserves_day_off(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    emp = await _employee_in(client, headers, branch_id, "regen@demo.com")
    await _put_template(client, headers, emp, weekdays=[0, 1, 2, 3, 4, 5, 6])

    off_day = TODAY + timedelta(days=3)
    slot = (await _range(client, headers, branch_id, off_day, off_day))[0]
    marked = await client.post(
        f"/staff/shifts/{slot['id']}/day-off",
        headers=headers,
        json={"reason": "Cita médica"},
    )
    assert marked.status_code == 200
    assert marked.json()["status"] == "day_off"

    # Edit the template (new hours) → regenerate future scheduled shifts.
    await _put_template(
        client, headers, emp, weekdays=[0, 1, 2, 3, 4, 5, 6], start="09:00", end="17:00"
    )

    off_after = (await _range(client, headers, branch_id, off_day, off_day))[0]
    assert off_after["status"] == "day_off"  # preserved
    assert off_after["start_time"] in ("08:00", "08:00:00")  # kept old hours

    other = TODAY + timedelta(days=5)
    other_shift = (await _range(client, headers, branch_id, other, other))[0]
    assert other_shift["start_time"] in ("09:00", "09:00:00")  # regenerated


# --- Coverage ---------------------------------------------------------------
async def test_coverage_preserves_audit_trail(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    absent = await _employee_in(client, headers, branch_id, "absent@demo.com")
    sub = await _employee_in(client, headers, branch_id, "sub@demo.com")
    await _put_template(client, headers, absent, weekdays=[0, 1, 2, 3, 4, 5, 6])
    # `sub` has no template → free (available to cover) any day.

    day = TODAY + timedelta(days=2)
    slot = (await _range(client, headers, branch_id, day, day))[0]
    covered = await client.post(
        f"/staff/shifts/{slot['id']}/day-off",
        headers=headers,
        json={"reason": "Permiso", "cover_employee_id": sub},
    )
    assert covered.status_code == 200

    rows = await _range(client, headers, branch_id, day, day)
    by_status = {r["status"]: r for r in rows}
    assert by_status["day_off"]["employee_id"] == absent
    assert by_status["covered"]["employee_id"] == sub
    assert by_status["covered"]["covered_by_employee_id"] == absent
    assert by_status["covered"]["origin"] == "coverage"


async def test_available_covers_excludes_busy(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    busy = await _employee_in(client, headers, branch_id, "busy@demo.com")
    free = await _employee_in(client, headers, branch_id, "free@demo.com")
    await _put_template(client, headers, busy, weekdays=[0, 1, 2, 3, 4, 5, 6])

    day = TODAY + timedelta(days=1)
    resp = await client.get(
        "/staff/coverage",
        headers=headers,
        params={"branch_id": str(branch_id), "date": _iso(day)},
    )
    assert resp.status_code == 200
    ids = {e["id"] for e in resp.json()}
    assert free in ids
    assert busy not in ids


# --- Time-off requests ------------------------------------------------------
async def test_time_off_request_approve_and_reject(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    emp = await _employee_in(client, headers, branch_id, "req@demo.com")
    await _put_template(client, headers, emp, weekdays=[0, 1, 2, 3, 4, 5, 6])

    approve_day = TODAY + timedelta(days=2)
    created = await client.post(
        f"/staff/employees/{emp}/time-off-requests",
        headers=headers,
        json={"request_date": _iso(approve_day), "reason": "Vacaciones"},
    )
    assert created.status_code == 201
    req_id = created.json()["id"]

    pending = await client.get(
        "/staff/time-off-requests",
        headers=headers,
        params={"branch_id": str(branch_id), "status": "pending"},
    )
    assert any(r["id"] == req_id for r in pending.json())

    approved = await client.post(
        f"/staff/time-off-requests/{req_id}/approve", headers=headers, json={}
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    slot = (await _range(client, headers, branch_id, approve_day, approve_day))[0]
    assert slot["status"] == "day_off"

    # Reject leaves the shift scheduled.
    reject_day = TODAY + timedelta(days=4)
    created2 = await client.post(
        f"/staff/employees/{emp}/time-off-requests",
        headers=headers,
        json={"request_date": _iso(reject_day), "reason": "Personal"},
    )
    req2 = created2.json()["id"]
    rejected = await client.post(
        f"/staff/time-off-requests/{req2}/reject",
        headers=headers,
        json={"reason": "Semana ocupada"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    slot2 = (await _range(client, headers, branch_id, reject_day, reject_day))[0]
    assert slot2["status"] == "scheduled"


# --- Employee self-service (authenticated-only "me" endpoints) --------------
async def test_my_schedule_and_request(client: AsyncClient) -> None:
    # Link the demo (logged-in) user to an employee, then read its own shifts and
    # file its own day-off request via the authenticated-only "me" routes.
    _, demo_user_id = await _demo_ids()
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    role_id = await _assign_role("admin")
    person_id, _ = await _create_person_and_user("adminperson@demo.com")
    linked = await client.post(
        "/staff/employees",
        headers=headers,
        json={
            "branch_id": str(branch_id),
            "person_id": str(person_id),
            "user_id": str(demo_user_id),
            "role_id": str(role_id),
        },
    )
    assert linked.status_code == 201, linked.text
    await _put_template(
        client, headers, linked.json()["id"], weekdays=[0, 1, 2, 3, 4, 5, 6]
    )

    me = await client.get("/staff/employees/me", headers=headers)
    assert me.status_code == 200

    mine = await client.get("/staff/employees/me/shifts", headers=headers)
    assert mine.status_code == 200
    assert len(mine.json()) > 0

    req = await client.post(
        "/staff/employees/me/time-off-requests",
        headers=headers,
        json={"request_date": _iso(TODAY + timedelta(days=3)), "reason": "Asunto personal"},
    )
    assert req.status_code == 201
    assert req.json()["status"] == "pending"


# --- Slot uniqueness --------------------------------------------------------
async def test_duplicate_slot_rejected(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    emp = await _employee_in(client, headers, branch_id, "dup@demo.com")

    day = _iso(TODAY + timedelta(days=1))
    first = await client.post(
        f"/staff/employees/{emp}/shifts",
        headers=headers,
        json={"shift_date": day, "start_time": "08:00", "end_time": "16:00"},
    )
    assert first.status_code == 201
    second = await client.post(
        f"/staff/employees/{emp}/shifts",
        headers=headers,
        json={"shift_date": day, "start_time": "10:00", "end_time": "18:00"},
    )
    assert second.status_code == 409

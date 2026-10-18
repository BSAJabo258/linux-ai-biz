import pytest

from bau.adapters import AdapterBase, AdapterRegistry, ExecutionResult
from bau.executive import ExecutiveController, InMemoryJobStore, TaskContract
from bau.jobs import JobStore


class EchoAdapter(AdapterBase):
    adapter_id = "echo"
    capabilities = ("draft",)

    def __init__(self, result: ExecutionResult | None = None):
        self.result = result or ExecutionResult(artifacts=["drafts/post.md"])
        self.calls = 0
        self.contract = None
        self.context = None

    def run(self, contract, context):
        self.calls += 1
        self.contract = contract
        self.context = context
        return self.result


class ExplodingAdapter(AdapterBase):
    adapter_id = "explode"
    capabilities = ()

    def run(self, contract, context):
        raise RuntimeError("kaboom")


class WrongResultAdapter(AdapterBase):
    adapter_id = "wrong"
    capabilities = ()

    def run(self, contract, context):
        return {"status": "COMPLETED"}


class CancellingAdapter(AdapterBase):
    adapter_id = "slow"
    capabilities = ()

    def __init__(self, controller):
        self.controller = controller
        self.saw_cancel = False

    def run(self, contract, context):
        self.controller.cancel(context.task_id)
        self.saw_cancel = context.should_cancel()
        return ExecutionResult(status="COMPLETED", artifacts=["partial.txt"])


def contract(**kw):
    base = {"mission_id": "msn_1", "objective": "Draft a post", "agent": "agent:writer"}
    base.update(kw)
    return TaskContract(**base)


def controller_with(*adapters, **kw):
    c = ExecutiveController(**kw)
    for adapter in adapters:
        c.register(adapter)
    return c


def test_create_task_uses_the_existing_job_record():
    c = ExecutiveController()
    task_id = c.create_task(contract(model="qwen", tools=["artifact.write_draft"],
                                     budget_usd=0.5))
    job = c.get_status(task_id)
    assert job.job_id == task_id and job.status == "PENDING"
    assert job.mission_id == "msn_1" and job.objective == "Draft a post"
    assert job.agent == "agent:writer" and job.model == "qwen"
    assert job.tools == ["artifact.write_draft"]
    assert job.budget_usd == pytest.approx(0.5)
    assert job.risk == "LOW"


def test_default_store_has_no_filesystem_side_effects(isolated_home):
    c = controller_with(EchoAdapter())
    assert isinstance(c.store, InMemoryJobStore)
    task_id = c.create_task(contract())
    assert c.dispatch(task_id, "echo").success

    assert not (isolated_home / "jobs").exists()


@pytest.mark.parametrize("bad, needle", [
    ({"mission_id": ""}, "mission_id"),
    ({"objective": "  "}, "objective"),
    ({"agent": ""}, "agent"),
    ({"model": ""}, "model"),
    ({"risk": "SEVERE"}, "risk"),
    ({"budget_usd": -1}, "budget_usd"),
    ({"budget_usd": float("nan")}, "budget_usd"),
    ({"tools": ["ok", ""]}, "tools"),
    ({"tools": ["ok", "ok"]}, "tools"),
])
def test_contract_validation(bad, needle):
    c = ExecutiveController()
    problems = c.validate_task(contract(**bad))
    assert any(needle in p for p in problems)
    with pytest.raises(ValueError, match=needle):
        c.create_task(contract(**bad))


def test_dispatch_success_records_the_result_on_the_job():
    result = ExecutionResult(artifacts=["drafts/post.md"], evidence={"tokens": 3})
    adapter = EchoAdapter(result)
    c = controller_with(adapter)
    task_id = c.create_task(contract())

    out = c.dispatch(task_id, "echo")

    assert out is result and out.success and out.evidence == {"tokens": 3}
    job = c.get_status(task_id)
    assert job.status == "COMPLETED"
    assert job.artifacts == ["drafts/post.md"]
    assert adapter.contract.objective == "Draft a post"
    assert adapter.context.task_id == task_id
    assert adapter.context.mission_id == "msn_1"
    assert adapter.context.cancelled() is False


def test_dispatch_records_a_failed_result():
    adapter = EchoAdapter(ExecutionResult(status="FAILED", errors=["no model"]))
    c = controller_with(adapter)
    task_id = c.create_task(contract())

    out = c.dispatch(task_id, "echo")

    assert out.status == "FAILED" and not out.success
    job = c.get_status(task_id)
    assert job.status == "FAILED" and job.errors == ["no model"]


def test_an_adapter_exception_becomes_a_failed_job():
    c = controller_with(ExplodingAdapter())
    task_id = c.create_task(contract())

    out = c.dispatch(task_id, "explode")

    assert out.status == "FAILED"
    job = c.get_status(task_id)
    assert job.status == "FAILED"
    assert "RuntimeError: kaboom" in job.errors[0]


def test_a_wrong_adapter_return_value_is_a_failure_not_a_crash():
    c = controller_with(WrongResultAdapter())
    task_id = c.create_task(contract())

    out = c.dispatch(task_id, "wrong")

    assert out.status == "FAILED"
    assert "ExecutionResult" in c.get_status(task_id).errors[0]


def test_unknown_adapter_leaves_the_task_untouched():
    c = ExecutiveController()
    task_id = c.create_task(contract())

    with pytest.raises(KeyError, match="nope"):
        c.dispatch(task_id, "nope")

    assert c.get_status(task_id).status == "PENDING"


def test_registry_rejects_duplicates_and_bad_ids_but_shares_capabilities():
    first = EchoAdapter()
    second = EchoAdapter()
    second.adapter_id = "echo-two"
    second.capabilities = ("draft", "video")
    reg = AdapterRegistry()
    reg.register(first)
    reg.register(second)

    with pytest.raises(ValueError, match="already registered"):
        reg.register(EchoAdapter())

    class Nameless(EchoAdapter):
        adapter_id = ""

    with pytest.raises(ValueError, match="adapter_id"):
        reg.register(Nameless())
    with pytest.raises(KeyError, match="unknown adapter"):
        reg.get("missing")
    assert reg.ids() == ["echo", "echo-two"]
    assert reg.for_capability("draft") == [first, second]
    assert reg.for_capability("video") == [second]
    assert reg.for_capability("none") == []


def test_high_risk_waits_for_a_human_and_records_the_reference():
    adapter = EchoAdapter()
    c = controller_with(adapter)
    task_id = c.create_task(contract(risk="HIGH"))

    waiting = c.get_status(task_id)
    assert waiting.status == "WAITING_FOR_APPROVAL"
    assert "human" in waiting.next_action
    with pytest.raises(PermissionError, match="human approval"):
        c.dispatch(task_id, "echo")
    assert adapter.calls == 0
    assert c.get_status(task_id).status == "WAITING_FOR_APPROVAL"

    assert c.dispatch(task_id, "echo", approval_ref="ssh-sig:owner").success
    job = c.get_status(task_id)
    assert job.status == "COMPLETED" and job.approvals == ["ssh-sig:owner"]


def test_a_governor_hold_stops_dispatch():
    adapter = EchoAdapter()
    c = controller_with(adapter, hold=lambda: "security review")
    task_id = c.create_task(contract())

    with pytest.raises(PermissionError, match="HOLD"):
        c.dispatch(task_id, "echo")

    assert adapter.calls == 0
    assert c.get_status(task_id).status == "PENDING"


def test_cancel_before_dispatch_prevents_the_run():
    adapter = EchoAdapter()
    c = controller_with(adapter)
    task_id = c.create_task(contract())

    cancelled = c.cancel(task_id)
    assert cancelled.status == "CANCELLED"
    with pytest.raises(ValueError, match="cannot run again"):
        c.dispatch(task_id, "echo")
    assert adapter.calls == 0


def test_cancel_during_a_run_is_cooperative_and_wins():
    c = ExecutiveController()
    adapter = CancellingAdapter(c)
    c.register(adapter)
    task_id = c.create_task(contract())

    out = c.dispatch(task_id, "slow")

    assert out.status == "COMPLETED"          # the adapter's own claim
    assert adapter.saw_cancel is True
    job = c.get_status(task_id)
    assert job.status == "CANCELLED"
    assert job.artifacts == ["partial.txt"]   # partial work is not thrown away


def test_terminal_tasks_do_not_run_or_get_resurrected():
    c = controller_with(EchoAdapter())
    task_id = c.create_task(contract())
    assert c.dispatch(task_id, "echo").success

    with pytest.raises(ValueError, match="cannot run again"):
        c.dispatch(task_id, "echo")
    assert c.cancel(task_id).status == "COMPLETED"


def test_an_injected_job_store_is_used_for_durable_checkpoints(tmp_path):
    c = ExecutiveController(store=JobStore(tmp_path))
    c.register(EchoAdapter())
    task_id = c.create_task(contract(model="qwen"))

    path = tmp_path / "jobs" / f"{task_id}.json"
    assert path.exists()
    assert c.dispatch(task_id, "echo").success

    reloaded = JobStore(tmp_path).load(task_id)
    assert reloaded.status == "COMPLETED"
    assert reloaded.model == "qwen"
    assert reloaded.artifacts == ["drafts/post.md"]


class CancelThenExplodeAdapter(AdapterBase):
    adapter_id = "cancel-explode"
    capabilities = ()

    def __init__(self, controller):
        self.controller = controller

    def run(self, contract, context):
        self.controller.cancel(context.task_id)
        raise RuntimeError("stopped mid-way")


def test_a_cancel_during_a_run_still_wins_when_the_adapter_then_raises():
    c = ExecutiveController()
    c.register(CancelThenExplodeAdapter(c))
    task_id = c.create_task(contract())

    out = c.dispatch(task_id, "cancel-explode")

    assert out.status == "FAILED"                       # what the call returned
    job = c.get_status(task_id)
    assert job.status == "CANCELLED"                    # the owner's cancel stands
    assert "RuntimeError: stopped mid-way" in job.errors[0]


def test_the_in_memory_store_refuses_an_unknown_status():
    store = InMemoryJobStore()
    job = store.create("msn_1", "Draft a post", "agent:writer", [])
    job.status = "DONE-ISH"
    with pytest.raises(ValueError, match="bad job status"):
        store.checkpoint(job)


def test_the_contract_is_rebuilt_from_the_persisted_job():
    original = contract(model="qwen", tools=["memory.search"], budget_usd=1.25, risk="MEDIUM")
    c = ExecutiveController()
    task_id = c.create_task(original)

    assert TaskContract.from_job(c.get_status(task_id)) == original

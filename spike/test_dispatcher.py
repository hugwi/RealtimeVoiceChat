import asyncio
import dispatcher
from dispatcher import Payload, Dispatcher


async def _tick(n=4):
    for _ in range(n):
        await asyncio.sleep(0)


def test_build_message_includes_instruction_and_transcript():
    msg = dispatcher.build_message(Payload("s", "Commit and push", "I said commit\nand push", "commit"))
    assert "Commit and push" in msg
    assert "I said commit" in msg


def test_build_message_falls_back_to_user_request():
    msg = dispatcher.build_message(Payload("s", "", "", "just do it"))
    assert msg == "just do it"


def test_same_session_serializes_and_drains_fifo():
    started = []
    gates = {}

    async def worker(p):
        started.append(p.instruction)
        gates[p.instruction] = asyncio.Event()
        await gates[p.instruction].wait()

    async def run():
        d = Dispatcher()
        d.set_worker(worker)
        d.submit(Payload("s", "i1", "", ""))
        d.submit(Payload("s", "i2", "", ""))
        await _tick()
        assert started == ["i1"]
        assert d.in_flight("s") is True
        assert d.pending("s") == 1
        gates["i1"].set()
        await _tick()
        assert started == ["i1", "i2"]
        assert d.pending("s") == 0
        gates["i2"].set()
        await _tick()
        assert d.in_flight("s") is False

    asyncio.run(run())


def test_different_sessions_run_in_parallel():
    started = []
    gates = {}

    async def worker(p):
        started.append(p.session_id)
        gates[p.session_id] = asyncio.Event()
        await gates[p.session_id].wait()

    async def run():
        d = Dispatcher()
        d.set_worker(worker)
        d.submit(Payload("a", "ia", "", ""))
        d.submit(Payload("b", "ib", "", ""))
        await _tick()
        assert set(started) == {"a", "b"}
        assert d.in_flight("a") and d.in_flight("b")
        gates["a"].set()
        gates["b"].set()
        await _tick()

    asyncio.run(run())


def test_worker_error_frees_session_and_drains_next():
    started = []

    async def worker(p):
        started.append(p.instruction)
        if p.instruction == "boom":
            raise RuntimeError("worker blew up")

    async def run():
        d = Dispatcher()
        d.set_worker(worker)
        d.submit(Payload("s", "boom", "", ""))
        d.submit(Payload("s", "next", "", ""))
        await _tick()
        assert started == ["boom", "next"]
        assert d.in_flight("s") is False
        assert d.pending("s") == 0

    asyncio.run(run())

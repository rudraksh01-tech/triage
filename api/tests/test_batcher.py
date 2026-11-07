import asyncio

import pytest

from triage_api.batcher import MicroBatcher


async def test_concurrent_requests_share_a_batch():
    calls = []

    def fn(items):
        calls.append(list(items))
        return [x * 2 for x in items]

    b = MicroBatcher(fn, max_batch=8, max_wait_s=0.02)
    b.start()
    results = await asyncio.gather(*(b.submit(i) for i in range(5)))
    await b.stop()

    assert results == [0, 2, 4, 6, 8]  # each caller gets its own answer, in order
    assert len(calls) == 1 and len(calls[0]) == 5


async def test_full_batch_does_not_wait_and_overflow_splits():
    sizes = []
    b = MicroBatcher(lambda xs: sizes.append(len(xs)) or xs, max_batch=4, max_wait_s=10)
    b.start()
    await asyncio.wait_for(asyncio.gather(*(b.submit(i) for i in range(8))), timeout=2)
    await b.stop()
    assert sizes == [4, 4]


async def test_error_reaches_every_caller_and_loop_survives():
    def fn(items):
        if "boom" in items:
            raise RuntimeError("model fell over")
        return items

    b = MicroBatcher(fn, max_batch=2, max_wait_s=0.01)
    b.start()
    with pytest.raises(RuntimeError):
        await b.submit("boom")
    assert await b.submit("fine") == "fine"
    await b.stop()

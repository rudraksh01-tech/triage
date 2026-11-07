import asyncio
from collections.abc import Callable
from typing import Generic, TypeVar

In = TypeVar("In")
Out = TypeVar("Out")


class MicroBatcher(Generic[In, Out]):
    """Collects concurrent single requests into one batched model call.

    The first request in an empty queue waits at most `max_wait_s` for company;
    a full batch goes immediately. Under light load a request pays ~max_wait_s
    extra; under heavy load the per-ticket cost drops because one ONNX run over
    32 short tweets is far cheaper than 32 separate runs.
    """

    def __init__(self, fn: Callable[[list[In]], list[Out]], max_batch: int = 32, max_wait_s: float = 0.003):
        self.fn = fn
        self.max_batch = max_batch
        self.max_wait_s = max_wait_s
        self.queue: asyncio.Queue[tuple[In, asyncio.Future[Out]]] = asyncio.Queue()
        self.task: asyncio.Task | None = None
        self.batches = 0
        self.items = 0

    def start(self) -> None:
        self.task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self.task:
            self.task.cancel()

    async def submit(self, item: In) -> Out:
        fut: asyncio.Future[Out] = asyncio.get_running_loop().create_future()
        await self.queue.put((item, fut))
        return await fut

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            batch = [await self.queue.get()]
            deadline = loop.time() + self.max_wait_s
            while len(batch) < self.max_batch:
                timeout = deadline - loop.time()
                if timeout <= 0:
                    break
                try:
                    batch.append(await asyncio.wait_for(self.queue.get(), timeout))
                except TimeoutError:
                    break
            items, futures = zip(*batch)
            try:
                results = await asyncio.to_thread(self.fn, list(items))
            except Exception as e:  # one bad batch shouldn't kill the loop
                for f in futures:
                    if not f.done():
                        f.set_exception(e)
                continue
            self.batches += 1
            self.items += len(items)
            for f, r in zip(futures, results):
                if not f.done():
                    f.set_result(r)

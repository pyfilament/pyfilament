import anyio
import fire

import filament.setup_logging
from filament.filament import lookup, print_task_registry
from filament.test_app import d, f, root


async def main():
    async with anyio.create_task_group() as task_group:
        task_group.start_soon(root.serve)
        task_group.start_soon(f.serve)
        task_group.start_soon(d.serve)
        await root.request()
        task_group.cancel_scope.cancel()


class Filament:
    def serve(self, task_address):
        anyio.run(lookup(task_address).serve)

    def request(self, task_address, count=1):
        async def _request():
            await lookup(task_address).request()

        async def _request_all():
            async with anyio.create_task_group() as task_group:
                for _ in range(count):
                    task_group.start_soon(_request)

        anyio.run(_request_all)

    def call(self, task_address, *args, **kwargs):
        # async def _call():
        #     await lookup(task_address)()

        # anyio.run(_call)
        anyio.run(lookup(task_address)(*args, **kwargs).call)

    def print(self):
        print_task_registry()


if __name__ == '__main__':
    # anyio.run(main)
    fire.Fire(Filament)

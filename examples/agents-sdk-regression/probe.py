"""Synthetic actual-SDK tool invocation; no Runner, model, credentials or telemetry."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import asyncio, json, time, importlib.metadata
network_attempts = []
def no_network(event, args):
    if event in {'socket.connect', 'socket.connect_ex', 'socket.getaddrinfo', 'socket.sendto', 'socket.bind'}:
        network_attempts.append(event)
        raise RuntimeError('Network disabled in synthetic probe')
sys.addaudithook(no_network)
from agents import function_tool, set_tracing_disabled
from agents.tool_context import ToolContext
from fanout_check import Recorder, check
set_tracing_disabled(True)
version = importlib.metadata.version('openai-agents')
if version not in {'0.7.0', '0.8.0', '0.23.1'}:
    raise SystemExit('Use one of the three explicitly tested SDK versions in this example.')

async def case(mode):
    r = Recorder()
    @function_tool
    def synchronous(label: str) -> str:
        """Perform synthetic blocking work."""
        with r.span(label, group='batch'):
            time.sleep(0.08)
        return 'ok'
    @function_tool
    async def cooperative(label: str) -> str:
        """Perform synthetic cooperative work."""
        with r.span(label, group='batch'):
            await asyncio.sleep(0.08)
        return 'ok'
    @function_tool
    async def async_blocking(label: str) -> str:
        """Deliberately block within an async tool as an application regression."""
        with r.span(label, group='batch'):
            time.sleep(0.08)
        return 'ok'
    semaphore = asyncio.Semaphore(2)
    @function_tool
    async def capped(label: str) -> str:
        """Measure admitted synthetic work inside a semaphore."""
        async with semaphore:
            with r.span(label, group='batch'):
                await asyncio.sleep(0.08)
        return 'ok'
    tool = {'sync_parallel':synchronous, 'async_parallel':cooperative,
            'async_sequential':cooperative, 'async_blocking':async_blocking,
            'capped_inside':capped}[mode]
    calls = [tool.on_invoke_tool(ToolContext(None, tool_name=tool.name, tool_call_id=n,
             tool_arguments=json.dumps({'label':n})), json.dumps({'label':n})) for n in ['a','b','c']]
    if mode == 'async_sequential':
        outputs = [await call for call in calls]
    else:
        outputs = await asyncio.gather(*calls)
    assert outputs == ['ok','ok','ok'], outputs
    limits = {'min_peak':2, 'max_peak':2} if mode=='capped_inside' else {'min_peak':3}
    contract = {'version':1, 'groups':[{'name':'batch','members':['a','b','c'], **limits}]}
    report = check(r.trace(),contract)
    expected = 'fail' if mode in ['async_sequential','async_blocking'] or (mode=='sync_parallel' and version=='0.7.0') else 'pass'
    assert report['status']==expected, (version,mode,report)
    return {'case':mode,'expected':expected,'trace':r.trace(),'contract':contract,'report':report}

async def main():
    rows=[]
    for repeat in range(3):
        for mode in ['sync_parallel','async_parallel','async_sequential','async_blocking','capped_inside']:
            rows.append({'repeat':repeat, **await case(mode)})
    assert not network_attempts
    print(json.dumps({'sdk_version':version,'python':sys.version,'network_attempts':network_attempts,'cases':rows},indent=2))
asyncio.run(main())

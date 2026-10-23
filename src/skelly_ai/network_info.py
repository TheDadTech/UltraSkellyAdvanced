"""Read-only network identity for the dashboard; never changes interfaces."""
import asyncio
import ipaddress
import json
import socket
import shutil


def summarize_network(addresses, routes, route_to_client=None):
    defaults = sorted((r for r in routes if r.get('dev')), key=lambda r:r.get('metric',0))
    chosen = (route_to_client or [{}])[0]
    if not chosen.get('dev'):
        chosen = defaults[0] if defaults else {}
    primary = chosen.get('dev')
    interfaces=[]
    for item in addresses:
        if item.get('ifname')=='lo' or item.get('operstate') not in {'UP','UNKNOWN'}:
            continue
        ips=[a['local'] for a in item.get('addr_info',[]) if a.get('local') and a.get('scope')=='global']
        if not ips:
            continue
        interfaces.append({'name':item['ifname'],'ip_addresses':ips,'mac_address':item.get('address'),
                           'primary':item['ifname']==primary})
    interfaces.sort(key=lambda i:not i['primary'])
    return {'hostname':socket.gethostname(),'interfaces':interfaces,'gateway':chosen.get('gateway'),
            'primary_interface':primary,'selection':'dashboard connection' if route_to_client and route_to_client[0].get('dev') else 'default route' if primary else 'active interfaces'}


async def collect_network_info(peer=None):
    executable=shutil.which('ip')
    if not executable:
        return {'hostname':socket.gethostname(),'interfaces':[],'error':'Network details unavailable: ip tool is not installed'}
    async def read(*args):
        process=await asyncio.create_subprocess_exec(executable,'-j',*args,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        try:
            stdout,_=await asyncio.wait_for(process.communicate(),timeout=4)
        except (TimeoutError,asyncio.CancelledError):
            process.kill();await process.wait();raise
        if process.returncode:
            return []
        value=json.loads(stdout)
        return value if isinstance(value,list) else []
    try:
        addresses,routes=await asyncio.gather(read('address','show'),read('route','show','default'))
        target=[]
        try:
            ip=ipaddress.ip_address(peer or '')
            if not ip.is_loopback and not ip.is_unspecified:
                target=await read('route','get',str(ip))
        except ValueError:
            pass
        return summarize_network(addresses,routes,target)
    except (OSError,ValueError,TimeoutError):
        return {'hostname':socket.gethostname(),'interfaces':[],'error':'Network details unavailable; refresh to retry'}

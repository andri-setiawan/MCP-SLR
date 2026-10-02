"""End-to-end public tunnel MCP test; never prints credentials."""
import asyncio
import json
import urllib.error
import urllib.request
from pathlib import Path
import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

root = Path(__file__).resolve().parent
cfg = json.loads((root / 'private/credentials.json').read_text())
urls = cfg['public_urls']

async def run():
 for name,url in urls.items():
  try:
   urllib.request.urlopen(urllib.request.Request(url, headers={'Accept':'application/json'}), timeout=15)
   raise AssertionError('public access without token: '+name)
  except urllib.error.HTTPError as e:
   print(name,'anonymous HTTP',e.code,flush=True)
   assert e.code == 401,(name,e.code)
  async with httpx2.AsyncClient(headers={'Authorization':'Bearer '+cfg['access_tokens'][name]},timeout=45) as client:
   async with streamable_http_client(url,http_client=client) as (read,write,*_):
    async with ClientSession(read,write) as s:
     await s.initialize()
     tools=[t.name for t in (await s.list_tools()).tools]
     assert tools
     print(name,'remote MCP tools',tools,flush=True)
asyncio.run(run())

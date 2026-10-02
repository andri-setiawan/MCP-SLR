"""Runnable auth + MCP + live upstream smoke checks (no secrets printed)."""
import asyncio
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

P = Path(__file__).resolve().parent
cfg = json.loads((P / 'private/credentials.json').read_text())

async def main():
    for name,port,args in [
        ('semantic',8761,('recommendations',{'doi':'10.1016/j.mex.2019.100777','limit':1})),
        ('elsevier',8762,('search_scopus',{'query':'TITLE-ABS-KEY("systematic literature review")','count':1})),
        ('openalex',8763,('search_works',{'query':'systematic literature review','count':1}))]:
        url = f'http://127.0.0.1:{port}/mcp'
        try:
            urllib.request.urlopen(url, timeout=4)
            raise AssertionError(f'{name} unauthenticated request accepted')
        except urllib.error.HTTPError as e:
            assert e.code == 401, (name,e.code)
        async with httpx2.AsyncClient(headers={'Authorization':'Bearer '+cfg['access_tokens'][name]},timeout=45) as client:
            async with streamable_http_client(url,http_client=client) as (read,write,*_):
                async with ClientSession(read,write) as session:
                    await session.initialize()
                    names=[t.name for t in (await session.list_tools()).tools]
                    assert args[0] in names,(name,names)
                    result=await session.call_tool(*args)
                    text=''.join(getattr(x,'text','') for x in result.content)
                    data=json.loads(text)
                    assert not result.is_error,(name,text[:200])
                    assert data.get('status') in (200, 429) or 'error' in data, (name,str(data)[:250])
                    print(name,'401 without token; tools',names,'upstream status',data.get('status','key pending'))

asyncio.run(main())

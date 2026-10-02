"""Show the three remote MCP servers without printing credentials or raw keys.

Usage: .venv/bin/python showcase.py {tools|search|recommend|verify}
Outputs are live, summarized, and safe for terminal capture.
"""
import asyncio
import json
import sys
import urllib.request
from pathlib import Path

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / 'private' / 'credentials.json').read_text())


async def call(provider, tool, args=None):
    token = CONFIG['access_tokens'][provider]
    async with httpx2.AsyncClient(headers={'Authorization': 'Bearer ' + token}, timeout=45) as client:
        async with streamable_http_client(CONFIG['public_urls'][provider], http_client=client) as (read, write, *_):
            async with ClientSession(read, write) as session:
                await session.initialize()
                if tool == '_tools':
                    return [t.name for t in (await session.list_tools()).tools]
                response = await session.call_tool(tool, args or {})
                if response.is_error:
                    raise RuntimeError('MCP tool error')
                return json.loads(response.content[0].text)


async def run(mode):
    if mode == 'tools':
        for provider in ('semantic', 'elsevier', 'openalex'):
            print(f'{provider}: {", ".join(await call(provider, "_tools"))}')
    elif mode == 'search':
        query = 'TITLE-ABS-KEY("AI coding agent" OR "software engineering agent") AND PUBYEAR > 2022 AND PUBYEAR < 2027'
        data = await call('elsevier', 'search_scopus', {'query': query, 'count': 5, 'start': 0})
        print('SCOPUS |', query)
        print('HTTP:', data.get('status'))
        sr = data.get('data', {}).get('search-results', {})
        print('Index matches:', sr.get('opensearch:totalResults'), '| Preview:', len(sr.get('entry', [])))
        for p in sr.get('entry', []):
            if p.get('prism:doi') and int((p.get('prism:coverDate') or '9999')[:4]) <= 2026:
                print('-', p.get('dc:title'), '| DOI:', p['prism:doi'])
        if data.get('error'): print('API error:', data['error'][:150])
    elif mode == 'recommend':
        doi = '10.1016/j.mex.2019.100777'
        data = await call('semantic', 'recommendations', {'doi': doi, 'limit': 2})
        print('SEMANTIC SCHOLAR | seed DOI:', doi, '| HTTP:', data.get('status'))
        for p in data.get('data', {}).get('recommendedPapers', []):
            print('-', p.get('title'), '| DOI:', (p.get('externalIds') or {}).get('DOI', '(none)'))
        if data.get('error'): print('API error:', data['error'][:150])
        print('Recommendation != SLR inclusion; screen each candidate.')
    elif mode == 'verify':
        doi = '10.1016/j.softx.2026.102919'
        data = await call('openalex', 'work_by_doi', {'doi': doi})
        print('OPENALEX | DOI:', doi, '| HTTP:', data.get('status'))
        paper = data.get('data', {})
        print('Title:', paper.get('title'))
        print('Year:', paper.get('publication_year'), '| OA:', paper.get('open_access', {}).get('is_oa'))
        if data.get('error'): print('API error:', data['error'][:150])
        req = urllib.request.Request('https://api.crossref.org/works/' + doi, headers={'User-Agent': 'SLR-demo/1.0 (mailto:035230102@uii.ac.id)'})
        with urllib.request.urlopen(req, timeout=20) as response:
            record = json.load(response)['message']
            print('CROSSREF | HTTP:', response.status, '| Title:', record['title'][0])
        print('DOI verified; eligibility still requires screening.')
    else:
        raise SystemExit('Choose tools, search, recommend, or verify')


if __name__ == '__main__':
    asyncio.run(run(sys.argv[1] if len(sys.argv) > 1 else 'tools'))

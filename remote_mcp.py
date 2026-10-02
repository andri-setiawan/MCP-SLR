"""Three read-only scholarly MCP servers. Streamable HTTP + bearer gate.

Run: .venv/bin/python remote_mcp.py {semantic|elsevier|openalex} [port]
Secrets: ./private/credentials.json (0600), never publish its contents.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

ROOT = Path(__file__).resolve().parent
MAIL = '035230102@uii.ac.id'


def credentials():
    p = ROOT / 'private' / 'credentials.json'
    if p.is_symlink() or not p.exists() or p.stat().st_mode & 0o077:
        raise RuntimeError('private/credentials.json must be a regular mode-0600 file')
    return json.loads(p.read_text())


def fetch(url, headers=None):
    request = urllib.request.Request(url, headers={'User-Agent': f'UII-SLR-MCP/1 (mailto:{MAIL})', **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=25) as r:
            return {'status': r.status, 'retrieved_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'data': json.load(r)}
    except urllib.error.HTTPError as e:
        return {'status': e.code, 'retry_after': e.headers.get('Retry-After'), 'error': e.read(300).decode('utf-8', 'replace')}
    except (OSError, ValueError) as e:
        return {'status': 0, 'error': str(e)}


def valid_doi(doi):
    doi = doi.strip().removeprefix('https://doi.org/')
    if not doi.startswith('10.') or '/' not in doi or len(doi) > 250:
        raise ValueError('Expected a DOI such as 10.1016/j.mex.2019.100777')
    return doi


def make_server(provider, config):
    server = MCPServer('slr-' + provider)
    key = (config.get('api_keys') or {}).get(provider) or ''
    if provider == 'semantic':
        headers = {'x-api-key': key} if key else {}

        @server.tool()
        def search_papers(query: str, limit: int = 5) -> dict:
            """Search Semantic Scholar; explicit 429 is not zero papers."""
            if not 1 <= limit <= 25 or not 2 <= len(query) <= 500: return {'error': 'Invalid query or limit'}
            url = 'https://api.semanticscholar.org/graph/v1/paper/search?' + urllib.parse.urlencode({'query': query, 'limit': limit, 'fields': 'title,year,authors,abstract,citationCount,externalIds,openAccessPdf'})
            return fetch(url, headers)

        @server.tool()
        def paper_by_doi(doi: str) -> dict:
            """Get title, abstract, citations, authors, identifiers and OA PDF for a DOI."""
            try: doi = valid_doi(doi)
            except ValueError as e: return {'error': str(e)}
            fields = 'title,year,authors,abstract,citationCount,externalIds,openAccessPdf'
            return fetch('https://api.semanticscholar.org/graph/v1/paper/DOI:' + urllib.parse.quote(doi, safe='') + '?fields=' + fields, headers)

        @server.tool()
        def recommendations(doi: str, limit: int = 5) -> dict:
            """Find candidate papers from a seed DOI; results are NOT screened."""
            if not 1 <= limit <= 25: return {'error': 'limit must be 1..25'}
            try: doi = valid_doi(doi)
            except ValueError as e: return {'error': str(e)}
            return fetch('https://api.semanticscholar.org/recommendations/v1/papers/forpaper/DOI:' + urllib.parse.quote(doi, safe='') + '?' + urllib.parse.urlencode({'limit': limit, 'fields': 'title,year,externalIds,citationCount'}), headers)

    elif provider == 'elsevier':
        @server.tool()
        def search_scopus(query: str, count: int = 10, start: int = 0) -> dict:
            """Search Scopus TITLE-ABS-KEY Boolean query; metadata only, subject to entitlement."""
            if not key: return {'error': 'Set api_keys.elsevier in private/credentials.json'}
            if not 1 <= count <= 25 or start < 0 or not 2 <= len(query) <= 1000: return {'error': 'Invalid query/count/start'}
            url = 'https://api.elsevier.com/content/search/scopus?' + urllib.parse.urlencode({'query': query, 'count': count, 'start': start})
            return fetch(url, {'X-ELS-APIKey': key, 'Accept': 'application/json'})

    elif provider == 'openalex':
        headers = {'Authorization': 'Bearer ' + key} if key else {}
        @server.tool()
        def search_works(query: str, count: int = 10) -> dict:
            """Search OpenAlex work metadata, OA links and cited_by_count."""
            if not 1 <= count <= 25 or not 2 <= len(query) <= 500: return {'error': 'Invalid query/count'}
            url = 'https://api.openalex.org/works?' + urllib.parse.urlencode({'search': query, 'per_page': count, 'mailto': MAIL})
            return fetch(url, headers)

        @server.tool()
        def work_by_doi(doi: str) -> dict:
            """Get one OpenAlex work by DOI, including locations and open-access status."""
            try: doi = valid_doi(doi)
            except ValueError as e: return {'error': str(e)}
            return fetch('https://api.openalex.org/works/' + urllib.parse.quote('https://doi.org/' + doi, safe='') + '?' + urllib.parse.urlencode({'mailto': MAIL}), headers)
    return server


class BearerGate:
    """ASGI bearer gate: reject before MCP initialization or tool disclosure."""
    def __init__(self, app, token): self.app, self.token = app, token

    async def __call__(self, scope, receive, send):
        import hmac
        if scope['type'] == 'http':
            auth = next((v for k, v in scope.get('headers', []) if k.lower() == b'authorization'), b'')
            if not hmac.compare_digest(auth, b'Bearer ' + self.token.encode('ascii')):
                await send({'type': 'http.response.start', 'status': 401, 'headers': [(b'content-type', b'text/plain'), (b'cache-control', b'no-store')]})
                await send({'type': 'http.response.body', 'body': b'Unauthorized'})
                return
        await self.app(scope, receive, send)


def app_for(provider, config):
    token = (config.get('access_tokens') or {}).get(provider)
    if not isinstance(token, str) or len(token) < 32: raise RuntimeError('Missing access token (>=32 characters) for ' + provider)
    server = make_server(provider, config)
    # Permit only the configured public hostname and localhost; reject foreign Origin.
    from urllib.parse import urlparse
    hostname = urlparse((config.get('public_urls') or {}).get(provider, '')).netloc
    if not hostname or not hostname.endswith('.trycloudflare.com'):
        raise RuntimeError('Set public_urls.' + provider + ' to its exact quick-tunnel URL')
    transport = TransportSecuritySettings(
        allowed_hosts=[hostname, '127.0.0.1:*', 'localhost:*'],
        allowed_origins=['https://' + hostname],
    )
    return BearerGate(server.streamable_http_app(stateless_http=True, json_response=True, host='127.0.0.1', transport_security=transport), token)


if __name__ == '__main__':
    import uvicorn
    if len(sys.argv) not in (2, 3) or sys.argv[1] not in ('semantic', 'elsevier', 'openalex'):
        raise SystemExit('Usage: remote_mcp.py {semantic|elsevier|openalex} [port]')
    provider = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) == 3 else {'semantic': 8761, 'elsevier': 8762, 'openalex': 8763}[provider]
    uvicorn.run(app_for(provider, credentials()), host='127.0.0.1', port=port, log_level='warning')

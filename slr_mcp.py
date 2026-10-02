"""Read-only scholarly discovery MCP; run with `.venv/bin/python slr_mcp.py`."""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from mcp.server.mcpserver import MCPServer

mcp = MCPServer('slr-evidence')
MAIL = '035230102@uii.ac.id'
BASE = 'https://api.semanticscholar.org'

def request(url, headers=None):
    req = urllib.request.Request(url, headers={'User-Agent': f'SLR-methods-tutorial/1.0 (mailto:{MAIL})', **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return {'status': r.status, 'url': url, 'retrieved_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'data': json.load(r)}
    except urllib.error.HTTPError as e:
        return {'status': e.code, 'url': url, 'error': e.read(300).decode('utf-8', 'replace'), 'retry_after': e.headers.get('Retry-After')}
    except Exception as e:
        return {'status': 0, 'url': url, 'error': str(e)}

@mcp.tool()
def search_scopus(query: str, count: int = 10, start: int = 0) -> dict:
    """Search Scopus using explicit TITLE-ABS-KEY Boolean syntax; retains raw result and query."""
    if not 1 <= count <= 25 or start < 0 or len(query) > 1000:
        return {'error': 'count must be 1..25, start >= 0, query <= 1000 characters'}
    key = os.getenv('SCOPUS_API_KEY')
    if not key: return {'error': 'SCOPUS_API_KEY missing'}
    url = 'https://api.elsevier.com/content/search/scopus?' + urllib.parse.urlencode({'query': query, 'count': count, 'start': start, 'sort': 'citedby-count'})
    return request(url, {'X-ELS-APIKey': key, 'Accept': 'application/json'})

@mcp.tool()
def get_semantic_scholar_paper(doi: str) -> dict:
    """Get abstract, citations, identifiers and OA link by DOI; 429 is surfaced, never suppressed."""
    fields = 'title,year,abstract,authors,citationCount,externalIds,openAccessPdf'
    url = BASE + '/graph/v1/paper/DOI:' + urllib.parse.quote(doi.removeprefix('https://doi.org/'), safe='') + '?' + urllib.parse.urlencode({'fields': fields})
    return request(url)

@mcp.tool()
def recommend_semantic_scholar(doi: str, limit: int = 5) -> dict:
    """Get recommendation candidates from a DOI seed; candidates need independent screening."""
    if not 1 <= limit <= 25: return {'error': 'limit must be 1..25'}
    url = BASE + '/recommendations/v1/papers/forpaper/DOI:' + urllib.parse.quote(doi.removeprefix('https://doi.org/'), safe='') + '?' + urllib.parse.urlencode({'fields': 'title,year,externalIds,citationCount', 'limit': limit})
    return request(url)

@mcp.tool()
def search_openalex(query: str, count: int = 10) -> dict:
    """Search OpenAlex works with provenance and OA metadata; relevance must be screened."""
    if not 1 <= count <= 25 or len(query) > 500: return {'error': 'count must be 1..25, query <= 500 characters'}
    key = os.getenv('OPENALEX_API_KEY')
    if not key: return {'error': 'OPENALEX_API_KEY missing'}
    url = 'https://api.openalex.org/works?' + urllib.parse.urlencode({'search': query, 'per_page': count, 'mailto': MAIL})
    return request(url, {'Authorization': 'Bearer ' + key})

@mcp.tool()
def verify_doi(doi: str) -> dict:
    """Resolve DOI metadata in Crossref; DOI resolution alone does not establish topical eligibility."""
    return request('https://api.crossref.org/works/' + urllib.parse.quote(doi.removeprefix('https://doi.org/'), safe=''))

if __name__ == '__main__':
    mcp.run(transport='stdio')

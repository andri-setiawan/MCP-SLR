"""Create a private, mode-0600 Claude Code MCP config from local credentials.

Run: python make_claude_config.py
Never commit or print the generated file; pass it via claude --mcp-config.
"""
import json
import os
from pathlib import Path

root = Path(__file__).resolve().parent
private = root / 'private'
source = private / 'credentials.json'
if not source.is_file() or source.is_symlink() or source.stat().st_mode & 0o077:
    raise SystemExit('Expected regular private/credentials.json with permissions 0600')
config = json.loads(source.read_text())
servers = {}
for provider in ('semantic', 'elsevier', 'openalex'):
    token = config['access_tokens'][provider]
    url = config['public_urls'][provider]
    if not isinstance(token, str) or len(token) < 32 or not url.startswith('https://') or not url.endswith('/mcp'):
        raise SystemExit(f'Invalid access token or MCP URL for {provider}')
    servers[f'slr-{provider}'] = {'type': 'http', 'url': url, 'headers': {'Authorization': 'Bearer ' + token}}
private.mkdir(mode=0o700, exist_ok=True)
target = private / 'claude-mcp.json'
fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
with os.fdopen(fd, 'w') as file:
    json.dump({'mcpServers': servers}, file)
os.chmod(target, 0o600)
print('Created private/claude-mcp.json (0600); 3 MCP servers; secrets not displayed')

"""Render credential-free, real Claude Code MCP tool calls from private traces.

Run locally after capturing `claude -p --output-format stream-json --verbose`.
Never copy raw JSONL traces (which could contain credentials) into this repo.
"""
import html
import json
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
out = root / 'screenshots'
private = Path(sys.argv[1]) if len(sys.argv) > 1 else root / 'private'
traces = {
    '09-claude-scopus': private / 'claude-mcp-trace.jsonl',
    '10-claude-s2-openalex': private / 'claude-mcp-trace-2.jsonl',
}
style = '''<style>*{box-sizing:border-box}body{margin:0;background:#0e1525;color:#d9e5f4;font-family:ui-monospace,Consolas,"DejaVu Sans Mono",monospace;padding:38px}.window{border:1px solid #3a4f72;border-radius:15px;overflow:hidden;box-shadow:0 24px 60px #050b18;width:1120px;min-height:600px;background:#111b2f}.bar{height:55px;background:#23324c;display:flex;align-items:center;padding:0 21px;gap:9px;color:#b9cce6;font:15px Arial}.dot{width:12px;height:12px;border-radius:50%}.red{background:#fa7778}.yellow{background:#f8cc66}.green{background:#67d8a2}.title{margin-left:28px}pre{white-space:pre-wrap;overflow-wrap:anywhere;margin:0;padding:24px;font-size:16px;line-height:1.52}footer{position:absolute;left:45px;bottom:16px;font:12px Arial;color:#8091ad}</style>'''
for slug, path in traces.items():
    calls = []
    result = None
    for line in path.read_text().splitlines():
        event = json.loads(line)
        if event.get('type') == 'assistant':
            for part in event.get('message', {}).get('content', []):
                if part.get('type') == 'tool_use' and part.get('name', '').startswith('mcp__slr-'):
                    calls.append((part['name'], part.get('input', {})))
        if event.get('type') == 'result':
            assert event.get('subtype') == 'success', slug
            result = event.get('result', '')
    assert result and calls, slug
    expected = ('mcp__slr-elsevier__search_scopus',) if slug.startswith('09') else ('mcp__slr-semantic__recommendations', 'mcp__slr-openalex__work_by_doi')
    assert all(any(name == tool for name, _ in calls) for tool in expected), (slug, calls)
    lines = ['Claude Code — direct MCP tools (actual stream-json trace)', '$ claude -p --mcp-config private/claude-mcp.json --strict-mcp-config ...', '']
    for name, args in calls:
        lines.extend(['tool_use: ' + name, 'args: ' + json.dumps(args, ensure_ascii=False), ''])
    lines += ['Claude response (excerpt):', result[:820].strip()]
    text = '\n'.join(lines)
    # Check known live tokens/keys absent, without printing them.
    creds = json.loads((private / 'credentials.json').read_text())
    for field in ('api_keys', 'access_tokens'):
        for secret in creds[field].values():
            if isinstance(secret, str) and len(secret) >= 10:
                assert secret not in text, slug
    page = f'<!doctype html><html><head><meta charset="utf-8">{style}</head><body><div class="window"><div class="bar"><span class="dot red"></span><span class="dot yellow"></span><span class="dot green"></span><span class="title">{html.escape(slug)} · Claude Code native MCP</span></div><pre>{html.escape(text)}</pre></div><footer>Recorded actual tool invocation; secrets and raw trace excluded</footer></body></html>'
    temp = private / (slug + '.html')
    temp.write_text(page)
    png = out / (slug + '.png')
    cmd = ['chromium', '--headless', '--no-sandbox', '--disable-gpu', '--hide-scrollbars', '--window-size=1200,820', '--screenshot=' + str(png), 'file://' + str(temp)]
    run = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
    assert run.returncode == 0 and png.stat().st_size > 10000, run.stderr[-400:]
    temp.unlink()
    print(slug, 'tools', len(calls), 'png_bytes', png.stat().st_size)

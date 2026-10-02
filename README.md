# MCP-SLR

Kode pendamping [slide PSALSAR–agentic SLR](https://docs.google.com/presentation/d/1yPLyujTAlK_rhoS_Q3C0oPVTqHV1UuSFl9L1s3dc50k/edit) dan [manual praktik](https://docs.google.com/document/d/12E7sTSrYFPolKCj4bo8v7INUnAUOIvtXFB-WdI3xgW4/edit). Contoh **bukan** SLR lengkap; keputusan inklusi/eksklusi tetap dilakukan peneliti.

## Arsitektur

`Codex / Hermes / terminal → showcase.py → tiga MCP Streamable HTTP → Scopus, Semantic Scholar, OpenAlex`. `remote_mcp.py` menjalankan server *read-only* terpisah pada `127.0.0.1:8761`, `8762`, `8763`; masing-masing dapat diekspos melalui Cloudflare Tunnel. `slr_mcp.py` adalah alternatif satu server stdio dengan lima tools, memakai env vars untuk API upstream. Jangan mencampur kedua mode tanpa memahami konfigurasi.

| Server | Tools | Kegunaan PSALSAR |
|---|---|---|
| Semantic Scholar | `search_papers`, `paper_by_doi`, `recommendations` | Kandidat pencarian/snowballing; rekomendasi **bukan** inklusi |
| Elsevier/Scopus | `search_scopus` | Kueri Boolean `TITLE-ABS-KEY`, pagination dan metadata |
| OpenAlex | `search_works`, `work_by_doi` | Metadata DOI, lokasi OA, sitasi |

## Persiapan

Python 3.11+; dependensi `mcp==2.2.0`, `httpx2==2.13.1`, `uvicorn==0.54.0` (lihat `requirements.txt`).

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
mkdir -p private && chmod 700 private
cp credentials.example.json private/credentials.json && chmod 600 private/credentials.json
```

Isi `private/credentials.json` **secara lokal**. `api_keys` ialah key *penyedia*; `access_tokens` ialah token akses *MCP* yang **berbeda untuk setiap server** (minimal 32 karakter acak); `public_urls` ialah alamat `/mcp` tunnel Anda sendiri. File privat tidak dilacak Git. Jangan menaruh key dalam slide, screenshot, argumen terminal, issue, atau repo. Jika URL Quick Tunnel berubah, ganti `public_urls`, restart server lalu ulangi tes. Untuk produksi gunakan named tunnel/Access; Quick Tunnel bukan hostname stabil.

Jalankan tiap server di terminal sendiri:

```bash
.venv/bin/python remote_mcp.py semantic 8761
.venv/bin/python remote_mcp.py elsevier 8762
.venv/bin/python remote_mcp.py openalex 8763
```

Di terminal terpisah, arahkan tunnel HTTPS ke masing-masing port lokal (`cloudflared tunnel --url http://127.0.0.1:8761`, dst.). Salin hostname baru ke `public_urls` lalu **restart server** agar daftar host diizinkan tepat. Jangan nyalakan logging debug cloudflared: header `Authorization` dapat ikut tercatat.

## Demo Python dan agent

```bash
.venv/bin/python test_remote.py      # local: request anonim 401, tool + API upstream
.venv/bin/python verify_tunnels.py   # publik: request anonim 401, tool authenticated
.venv/bin/python showcase.py tools
.venv/bin/python showcase.py search
.venv/bin/python showcase.py recommend
.venv/bin/python showcase.py verify
```

`showcase.py` memakai `httpx2.AsyncClient` dengan Bearer token dari file privat; `streamable_http_client` → `ClientSession.initialize()` → `list_tools()`/`call_tool()`. `search` memanggil Scopus; `recommend` memanggil Semantic Scholar; `verify` memanggil OpenAlex lalu Crossref. DOI contoh hanya demonstrasi; angka indeks/sitasi dapat berubah dan HTTP 429 harus dicatat, bukan dipalsukan.

**Codex** (contoh menjalankan Python client; bukan registrasi native MCP):

```bash
codex exec --skip-git-repo-check --sandbox read-only -C "$PWD" \
  'Jalankan .venv/bin/python showcase.py tools; laporkan tools tanpa menampilkan token.'
```

Jika sandbox jaringan lokal menolak DNS, jalankan dari terminal biasa atau lingkungan sandbox yang mengizinkan network. `--sandbox danger-full-access` hanya untuk lingkungan tepercaya karena memberi akses luas; jangan pakai untuk prompt tidak tepercaya.

**Hermes** (juga menjalankan Python client):

```bash
hermes chat --in "$PWD" -Q -q \
  'Jalankan .venv/bin/python showcase.py tools; laporkan tools MCP. Jangan tampilkan kredensial.'
```

`--in` memastikan Hermes masuk direktori proyek. Integrasi MCP native dengan Codex/Hermes memerlukan konfigurasi klien tersendiri; demo ini tidak mengklaim keduanya sudah didaftarkan secara native. Screenshot eksekusi dan potongan kode nyata, tanpa secret, terdapat di `screenshots/`.

## Claude Code: panggil tools MCP **secara native**

Berbeda dari demo Codex/Hermes di atas, Claude Code dapat memakai ketiga tools MCP **langsung**, tanpa memerintahkan Python client. Siapkan `private/credentials.json` sesuai contoh; lalu:

```bash
python make_claude_config.py  # menghasilkan private/claude-mcp.json (0600)
claude -p --mcp-config private/claude-mcp.json --strict-mcp-config \
  --allowedTools 'mcp__slr-elsevier__search_scopus' --max-turns 3 \
  'Call slr-elsevier search_scopus directly for TITLE-ABS-KEY("AI coding agent") AND PUBYEAR > 2022 AND PUBYEAR < 2027; count=2, start=0. Report status, total, titles and DOIs. Do not read files or reveal credentials.'
```

Contoh tambahan: `--allowedTools 'mcp__slr-semantic__recommendations' 'mcp__slr-openalex__work_by_doi'` dengan prompt DOI seed dan DOI verifikasi. Hasil eksekusi sungguhan ada di `screenshots/09-claude-scopus.png` dan `screenshots/10-claude-s2-openalex.png`; HTTP 200 yang tertangkap adalah status saat pengambilan, bukan jaminan layanan selalu aktif. `--mcp-config` mengisolasi demo dari daftar server pribadi yang besar; file konfigurasi berisi Bearer token dan **tidak boleh dipublikasikan**. Jangan menulis token dalam perintah `claude mcp add -H ...`, karena dapat masuk history shell.

## PSALSAR dan batas metodologis

**Protocol**: tetapkan pertanyaan, kriteria, tahun, string pencarian. **Search**: simpan string lengkap, basis data, tanggal, status, pagination/total. **Appraisal**: deduplikasi DOI, screening judul–abstrak dan full text dengan alasan eksklusi. **Synthesis/Analysis**: ekstrak dan analisis hanya studi eligible. **Report**: tabel provenance dan diagram PRISMA. API dan rekomendasi menghasilkan **kandidat**, bukan keputusan ilmiah. Jangan menyamakan jumlah hasil indeks dengan jumlah studi yang masuk SLR.

## Keamanan

`private/`, `.env`, token, key, dan cache dikecualikan `.gitignore`. Repository ini menggunakan **allowlist** saat publikasi; jangan pernah `git add .` pada direktori kerja berisi secret. `BearerGate` menolak permintaan tanpa token sebelum inisialisasi MCP. Penggunaan server/API tunduk pada batas lisensi penyedia.

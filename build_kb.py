#!/usr/bin/env python3
"""
一鍵建立台灣高空知識庫
用法：
  export RAG_DATABASE_URL="postgresql://..."
  export OPENAI_API_KEY="sk-..."
  python3 build_kb.py           # 全量建立
  python3 build_kb.py --scrape-only   # 只爬蟲，存 rag_raw.json
  python3 build_kb.py --from-file     # 跳過爬蟲，用現有 rag_raw.json
"""
import os, sys, json, pathlib

RAW_FILE = pathlib.Path(__file__).parent / 'rag_raw.json'

scrape_only = '--scrape-only' in sys.argv
from_file   = '--from-file'   in sys.argv

def check_env():
    missing = []
    if not from_file and not RAW_FILE.exists():
        pass  # will scrape
    # OPENAI_API_KEY only needed if not using Ollama
    if not os.environ.get('OPENAI_API_KEY') and not os.environ.get('EMBED_MODEL'):
        pass  # Ollama is the default, no key needed
    if not scrape_only and not os.environ.get('RAG_DATABASE_URL') and not os.environ.get('DATABASE_URL'):
        missing.append('RAG_DATABASE_URL (或 DATABASE_URL)')
    if missing:
        print('❌ 缺少環境變數：')
        for m in missing: print(f'   export {m}="..."')
        sys.exit(1)

check_env()

from scraper import run_all as scrape_all
from embed   import process_docs
from db      import setup, upsert_chunks, get_conn

# ── Step 1: 爬蟲 ────────────────────────────────────────────────
if not from_file:
    print('='*50)
    print('Step 1 / 3：爬蟲')
    print('='*50)
    docs = scrape_all(save_path=str(RAW_FILE))
else:
    print(f'從 {RAW_FILE} 讀取…')
    docs = json.load(open(RAW_FILE, encoding='utf-8'))
    print(f'讀取 {len(docs)} 筆文件')

if scrape_only:
    print(f'\n✅ 爬蟲完成，結果存至 {RAW_FILE}')
    sys.exit(0)

# ── Step 2: Chunk + Embed ───────────────────────────────────────
print('\n' + '='*50)
print('Step 2 / 3：Chunking + Embedding')
print('='*50)
chunks = process_docs(docs)

# ── Step 3: 存入 pgvector ───────────────────────────────────────
print('\n' + '='*50)
print('Step 3 / 3：存入 PostgreSQL pgvector')
print('='*50)
conn = get_conn()
setup(conn)
upsert_chunks(chunks, conn)
conn.close()

blog_c    = sum(1 for c in chunks if c['doc_type']=='blog')
product_c = sum(1 for c in chunks if c['doc_type']=='product')
print(f'''
╔══════════════════════════════════════╗
║  知識庫建立完成！                    ║
║  Blog chunks   : {blog_c:<5}                ║
║  Product chunks: {product_c:<5}                ║
║  Total         : {len(chunks):<5}                ║
╚══════════════════════════════════════╝
''')

#!/usr/bin/env python3
"""
Chunking + Embedding pipeline
blog  → 語義分塊（600 tokens, 80 overlap）
product → 整頁作為一個 unit（model+specs）
"""
import os, json, re, time, urllib.request
import tiktoken

GEMINI_KEY   = os.environ.get('GEMINI_API_KEY', '')
EMBED_MODEL  = 'gemini-embedding-001'   # 3072 dims, free
CHUNK_SIZE   = 600
CHUNK_OVERLAP = 80

enc = tiktoken.get_encoding('cl100k_base')

# ── Chunking ────────────────────────────────────────────────────

def _token_len(text):
    return len(enc.encode(text))

def chunk_blog(text: str, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP) -> list[str]:
    """語義分塊：優先在段落邊界切分，不強行截斷物理原理段落"""
    paragraphs = [p.strip() for p in re.split(r'\n{2,}', text) if len(p.strip()) > 20]
    chunks, current, current_len = [], [], 0
    for para in paragraphs:
        p_len = _token_len(para)
        if current_len + p_len > chunk_size and current:
            chunks.append('\n\n'.join(current))
            # overlap：保留最後一段
            if _token_len(current[-1]) < overlap:
                current = [current[-1]]
                current_len = _token_len(current[-1])
            else:
                current, current_len = [], 0
        current.append(para)
        current_len += p_len
    if current:
        chunks.append('\n\n'.join(current))
    return chunks or [text[:3000]]

def chunk_product(title: str, content: str) -> list[str]:
    """產品頁：title + 規格作為一個 unit；若過長再細切"""
    full = f'產品：{title}\n\n{content}'
    if _token_len(full) <= CHUNK_SIZE * 2:
        return [full]
    # 過長則切成 2 段
    return chunk_blog(full, chunk_size=CHUNK_SIZE * 2, overlap=100)

# ── Embedding ───────────────────────────────────────────────────

def embed_texts(texts: list[str], batch=1) -> list[list[float]]:
    """用 Gemini embedding-001（免費，3072 dims），逐筆送，rate limit 保護"""
    all_vecs = []
    for i, text in enumerate(texts):
        tokens = enc.encode(text)
        if len(tokens) > 2000:
            text = enc.decode(tokens[:2000])
        body = json.dumps({'content': {'parts': [{'text': text}]}}, ensure_ascii=False).encode('utf-8')
        req  = urllib.request.Request(
            f'https://generativelanguage.googleapis.com/v1beta/models/{EMBED_MODEL}:embedContent?key={GEMINI_KEY}',
            data=body, headers={'Content-Type': 'application/json'}
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read())
            all_vecs.append(data['embedding']['values'])
        except Exception as e:
            print(f'  ⚠️ [{i+1}] embedding 失敗，重試: {e}')
            time.sleep(5)
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    data = json.loads(r.read())
                all_vecs.append(data['embedding']['values'])
            except Exception:
                all_vecs.append([0.0] * 3072)
        time.sleep(0.5)  # 避免超過 rate limit
        if (i + 1) % 10 == 0:
            print(f'  [{i+1}/{len(texts)}] 向量化中…')
    return all_vecs

# ── Main pipeline ───────────────────────────────────────────────

def process_docs(docs: list[dict]) -> list[dict]:
    """
    輸入：scraper.py 的原始文件清單
    輸出：帶 chunk_index + embedding 的 chunk 清單，可直接 upsert 進 DB
    """
    all_chunks = []
    texts_to_embed = []
    chunk_meta = []

    for doc in docs:
        if doc['doc_type'] == 'blog':
            raw_chunks = chunk_blog(doc['content'])
        else:
            raw_chunks = chunk_product(doc['title'], doc['content'])

        for idx, chunk_text in enumerate(raw_chunks):
            meta = {
                'tags': doc.get('tags', []),
                'specs': doc.get('specs', {}),
            }
            chunk_meta.append({
                'url': doc['url'],
                'title': doc['title'],
                'doc_type': doc['doc_type'],
                'brand': doc.get('brand', ''),
                'product_type': doc.get('product_type', ''),
                'chunk_index': idx,
                'chunk_text': chunk_text,
                'metadata': meta,
            })
            texts_to_embed.append(chunk_text)

    print(f'[Embed] {len(docs)} 文件 → {len(texts_to_embed)} 個 chunks，開始向量化…')
    embeddings = embed_texts(texts_to_embed)

    for meta, emb in zip(chunk_meta, embeddings):
        meta['embedding'] = emb
        all_chunks.append(meta)

    print(f'[Embed] 完成 {len(all_chunks)} 個向量')
    return all_chunks

if __name__ == '__main__':
    import sys
    raw_path = sys.argv[1] if len(sys.argv) > 1 else 'rag_raw.json'
    docs = json.load(open(raw_path, encoding='utf-8'))
    chunks = process_docs(docs)
    out = 'rag_chunks.json'
    # 不存 embedding（太大），只存 metadata 供 debug
    debug = [{k:v for k,v in c.items() if k != 'embedding'} for c in chunks]
    json.dump(debug, open(out,'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(f'Chunk metadata 存至 {out}')

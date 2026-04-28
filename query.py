#!/usr/bin/env python3
"""
RAG 查詢核心
embedding backend: Ollama (local) 或 HuggingFace API (cloud)
generation backend: Ollama (local) 或 Gemini API (cloud)
"""
import os, json, urllib.request, urllib.error

# ── Config ──────────────────────────────────────────────────────
GEMINI_KEY    = os.environ.get('GEMINI_API_KEY', '')
EMBED_MODEL   = 'gemini-embedding-001'   # 3072 dims
GEMINI_GEN    = 'gemini-2.0-flash'
OLLAMA_URL    = os.environ.get('OLLAMA_URL', 'http://localhost:11434')
OLLAMA_LLM    = os.environ.get('OLLAMA_LLM', 'qwen3:14b')
LLM_BACKEND   = os.environ.get('LLM_BACKEND', 'gemini')  # 'gemini' | 'ollama'

def embed_query(text: str) -> list[float]:
    if len(text) > 8000:
        text = text[:8000]
    body = json.dumps({'content': {'parts': [{'text': text}]}}, ensure_ascii=False).encode('utf-8')
    url  = f'https://generativelanguage.googleapis.com/v1beta/models/{EMBED_MODEL}:embedContent?key={GEMINI_KEY}'
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())['embedding']['values']
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:
                time.sleep(8 * (attempt + 1))
                continue
            raise

def retrieve(question: str, top_k=5, doc_type=None, brand=None) -> list[dict]:
    """向量搜尋，回傳最相關的 chunks"""
    from db import search
    vec = embed_query(question)
    return search(vec, top_k=top_k, doc_type=doc_type, brand=brand)

def generate_answer(question: str, chunks: list[dict]) -> str:
    context = '\n\n---\n\n'.join([
        f"【{c['doc_type']}】{c['title']}\n{c['chunk_text'][:800]}"
        for c in chunks
    ])
    system = (
        '你是台灣高空（taiwanaccess.com.tw）的專業音響顧問。'
        '根據以下資料回答問題，以繁體中文回覆，語氣專業但親切。'
        '若問題涉及主觀玄學（如「聲音會變溫潤」），請用科學角度（頻率響應、電感、容抗）解釋。'
        '若資料不足，誠實說明並建議聯繫台灣高空。'
    )
    prompt = f'{system}\n\n參考資料：\n{context}\n\n問題：{question}\n\n回答：'

    if LLM_BACKEND == 'gemini':
        return _generate_gemini(prompt)
    return _generate_ollama(prompt)

def _generate_gemini(prompt: str) -> str:
    body = json.dumps({
        'contents': [{'parts': [{'text': prompt}]}],
        'generationConfig': {'temperature': 0.3, 'maxOutputTokens': 1024}
    }).encode()
    url = f'https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_GEN}:generateContent?key={GEMINI_KEY}'
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read())
            return data['candidates'][0]['content']['parts'][0]['text']
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:
                time.sleep(8 * (attempt + 1))
                continue
            raise
    raise Exception('Gemini rate limit')

def _generate_ollama(prompt: str) -> str:
    body = json.dumps({'model': OLLAMA_LLM, 'prompt': prompt, 'stream': False}).encode()
    req  = urllib.request.Request(
        f'{OLLAMA_URL}/api/generate',
        data=body, headers={'Content-Type': 'application/json'}
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read())
    return data['response']

def ask(question: str, top_k=5, doc_type=None, brand=None) -> dict:
    chunks  = retrieve(question, top_k=top_k, doc_type=doc_type, brand=brand)
    answer  = generate_answer(question, chunks)
    sources = [{'title': c['title'], 'url': c['url'], 'score': round(c['score'], 3)} for c in chunks]
    return {'answer': answer, 'sources': sources}

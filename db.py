#!/usr/bin/env python3
"""
pgvector schema 初始化
建立 knowledge_chunks 表，含向量欄位與 metadata
"""
import os, psycopg2
from psycopg2.extras import execute_values

DATABASE_URL = os.environ.get('RAG_DATABASE_URL') or os.environ.get('DATABASE_URL')

def get_conn():
    url = DATABASE_URL
    if not url:
        raise ValueError('請設定 RAG_DATABASE_URL 環境變數（PostgreSQL 連線字串）')
    if url.startswith('postgres://'):
        url = url.replace('postgres://', 'postgresql://', 1)
    return psycopg2.connect(url, sslmode='require')

def setup(conn=None):
    """建立 pgvector extension 和 knowledge_chunks 表"""
    close_after = conn is None
    if conn is None:
        conn = get_conn()
    cur = conn.cursor()
    cur.execute('CREATE EXTENSION IF NOT EXISTS vector')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS knowledge_chunks (
            id          SERIAL PRIMARY KEY,
            url         TEXT NOT NULL,
            title       TEXT,
            doc_type    TEXT,          -- 'blog' | 'product'
            brand       TEXT,
            product_type TEXT,
            chunk_index INTEGER,
            chunk_text  TEXT NOT NULL,
            embedding   vector(3072),
            metadata    JSONB DEFAULT '{}',
            updated_at  TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(url, chunk_index)
        )
    ''')
    # 向量索引（資料量小時略過，全表掃描已夠快）
    # 快速 metadata 過濾索引
    cur.execute('CREATE INDEX IF NOT EXISTS kb_brand_idx ON knowledge_chunks (brand)')
    cur.execute('CREATE INDEX IF NOT EXISTS kb_type_idx  ON knowledge_chunks (doc_type)')
    conn.commit()
    cur.close()
    if close_after:
        conn.close()
    print('[DB] Schema 建立完成')

def upsert_chunks(chunks: list[dict], conn=None):
    """
    chunks: [{url, title, doc_type, brand, product_type, chunk_index,
               chunk_text, embedding(list[float]), metadata(dict)}]
    """
    close_after = conn is None
    if conn is None:
        conn = get_conn()
    cur = conn.cursor()
    import json as _json
    rows = [
        (
            c['url'], c['title'], c['doc_type'], c.get('brand',''),
            c.get('product_type',''), c['chunk_index'], c['chunk_text'],
            c['embedding'], _json.dumps(c.get('metadata', {}), ensure_ascii=False),
        )
        for c in chunks
    ]
    execute_values(cur, '''
        INSERT INTO knowledge_chunks
            (url, title, doc_type, brand, product_type, chunk_index,
             chunk_text, embedding, metadata, updated_at)
        VALUES %s
        ON CONFLICT (url, chunk_index) DO UPDATE SET
            chunk_text   = EXCLUDED.chunk_text,
            embedding    = EXCLUDED.embedding,
            metadata     = EXCLUDED.metadata,
            updated_at   = NOW()
    ''', rows, template='''(
        %s, %s, %s, %s, %s, %s, %s,
        %s::vector, %s::jsonb, NOW()
    )''')
    conn.commit()
    cur.close()
    if close_after:
        conn.close()

def search(query_embedding: list[float], top_k=5, doc_type=None, brand=None, conn=None):
    """向量相似度搜尋，支援 doc_type / brand 前置過濾"""
    close_after = conn is None
    if conn is None:
        conn = get_conn()
    cur = conn.cursor()
    filters, params = [], []
    if doc_type:
        filters.append('doc_type = %s'); params.append(doc_type)
    if brand:
        filters.append('brand ILIKE %s'); params.append(f'%{brand}%')
    where = ('WHERE ' + ' AND '.join(filters)) if filters else ''
    params += [str(query_embedding), top_k]
    cur.execute(f'''
        SELECT url, title, doc_type, brand, chunk_text,
               1 - (embedding <=> %s::vector) AS score
        FROM knowledge_chunks
        {where}
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    ''', [str(query_embedding)] + ([doc_type] if doc_type else []) +
         ([f'%{brand}%'] if brand else []) +
         [str(query_embedding), top_k])
    rows = cur.fetchall()
    cur.close()
    if close_after:
        conn.close()
    return [{'url':r[0],'title':r[1],'doc_type':r[2],'brand':r[3],
             'chunk_text':r[4],'score':float(r[5])} for r in rows]

if __name__ == '__main__':
    setup()

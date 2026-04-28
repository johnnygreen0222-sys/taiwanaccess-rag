#!/usr/bin/env python3
"""
台灣高空 RAG 爬蟲
抓取 blog/posts 和 /products 頁面，回傳結構化文件清單
"""
import time, re, json
import requests
from bs4 import BeautifulSoup
from datetime import datetime

BASE = 'https://www.taiwanaccess.com.tw'
HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}

def _get_soup(url, delay=1.0):
    time.sleep(delay)
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return BeautifulSoup(r.text, 'html.parser')

def _clean_text(soup, remove_tags=None):
    for tag in (remove_tags or ['script','style','nav','footer','header','iframe','noscript','aside','.announcement-bar','.header']):
        for el in soup.select(tag) if tag.startswith('.') else soup.find_all(tag):
            el.decompose()
    text = soup.get_text(separator='\n', strip=True)
    lines = [l.strip() for l in text.splitlines() if len(l.strip()) > 10]
    # 移除促銷/限時優惠字樣
    promo_re = re.compile(r'(限時|特價|折扣碼|coupon|promo|sale|off\s*\d+%)', re.I)
    lines = [l for l in lines if not promo_re.search(l)]
    return '\n'.join(lines)

def _extract_brand(text, title=''):
    brands = ['Yamaha','Focusrite','Universal Audio','UA','RME','Audient','SSL',
              'Neve','API','Warm Audio','Shure','Rode','Neumann','Schoeps',
              'AKG','Sennheiser','Audio-Technica','Beyerdynamic','Austrian Audio',
              'IK Multimedia','Waves','iZotope','Plugin Alliance','Avid',
              'Zoom','Tascam','Behringer','MOTU','Apogee']
    combined = title + ' ' + text[:500]
    for b in brands:
        if re.search(re.escape(b), combined, re.I):
            return b
    return ''

def discover_blog_urls():
    soup = _get_soup(f'{BASE}/blog/posts', delay=0.5)
    urls = set()
    for a in soup.find_all('a', href=True):
        h = a['href']
        if '/blog/posts/' in h and h != f'{BASE}/blog/posts':
            urls.add(h if h.startswith('http') else BASE + h)
    print(f'[Scraper] 發現 {len(urls)} 篇文章')
    return sorted(urls)

def discover_product_urls(max_pages=5):
    urls = set()
    for page in range(1, max_pages+1):
        url = f'{BASE}/collections/all?page={page}'
        try:
            soup = _get_soup(url, delay=0.8)
            found = 0
            for a in soup.find_all('a', href=True):
                h = a['href']
                if '/products/' in h:
                    full = h if h.startswith('http') else BASE + h
                    if full not in urls:
                        urls.add(full)
                        found += 1
            if found == 0:
                break
        except Exception as e:
            print(f'[Scraper] 產品頁 {page} 失敗: {e}')
            break
    print(f'[Scraper] 發現 {len(urls)} 個產品頁')
    return sorted(urls)

def scrape_blog(url):
    try:
        soup = _get_soup(url)
        title_el = soup.find('h1') or soup.find('h2')
        title = title_el.get_text(strip=True) if title_el else url.split('/')[-1]
        article = soup.find('article') or soup.find(class_=re.compile(r'blog|post|content', re.I)) or soup.find('main')
        content = _clean_text(article or soup)
        if len(content) < 100:
            return None
        brand = _extract_brand(content, title)
        return {
            'url': url,
            'title': title,
            'content': content,
            'doc_type': 'blog',
            'brand': brand,
            'updated_at': datetime.utcnow().isoformat(),
        }
    except Exception as e:
        print(f'[Scraper] 文章失敗 {url}: {e}')
        return None

def scrape_product(url):
    try:
        soup = _get_soup(url)
        title_el = soup.find('h1')
        title = title_el.get_text(strip=True) if title_el else url.split('/')[-1]

        # 找產品描述區塊
        desc = (soup.find(class_=re.compile(r'product.desc|product.detail|product.content', re.I))
                or soup.find(id=re.compile(r'product.desc|description', re.I))
                or soup.find('main'))
        content = _clean_text(desc or soup)

        # 抓規格表（如果有 table）
        specs = {}
        for table in soup.find_all('table'):
            for row in table.find_all('tr'):
                cells = row.find_all(['td','th'])
                if len(cells) == 2:
                    k = cells[0].get_text(strip=True)
                    v = cells[1].get_text(strip=True)
                    if k and v:
                        specs[k] = v

        # 抓 JSON-LD 產品資料
        meta = {}
        for script in soup.find_all('script', type='application/json'):
            try:
                d = json.loads(script.string or '')
                if isinstance(d, dict):
                    meta.update({k:v for k,v in d.items() if k in ['vendor','product_type','tags']})
            except Exception:
                pass

        brand = _extract_brand(content, title) or meta.get('vendor', '')
        product_type = meta.get('product_type', '')
        tags = meta.get('tags', [])

        # 組合規格文字加入 content
        if specs:
            spec_text = '\n規格：\n' + '\n'.join(f'{k}: {v}' for k, v in specs.items())
            content = f'{title}\n{content}\n{spec_text}'

        if len(content) < 50:
            return None

        return {
            'url': url,
            'title': title,
            'content': content,
            'doc_type': 'product',
            'brand': brand,
            'product_type': product_type,
            'tags': tags,
            'specs': specs,
            'updated_at': datetime.utcnow().isoformat(),
        }
    except Exception as e:
        print(f'[Scraper] 產品失敗 {url}: {e}')
        return None

def run_all(save_path='rag_raw.json'):
    docs = []
    blog_urls = discover_blog_urls()
    for i, url in enumerate(blog_urls, 1):
        print(f'[Blog {i}/{len(blog_urls)}] {url.split("/")[-1]}')
        d = scrape_blog(url)
        if d:
            docs.append(d)

    product_urls = discover_product_urls()
    for i, url in enumerate(product_urls, 1):
        print(f'[Product {i}/{len(product_urls)}] {url.split("/")[-1]}')
        d = scrape_product(url)
        if d:
            docs.append(d)

    with open(save_path, 'w', encoding='utf-8') as f:
        json.dump(docs, f, ensure_ascii=False, indent=2)
    print(f'\n✅ 爬完：{len(docs)} 筆，存至 {save_path}')
    return docs

if __name__ == '__main__':
    run_all()

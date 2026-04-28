#!/usr/bin/env python3
"""
台灣高空 RAG 查詢 API + 簡易聊天介面
"""
import os, json, sys
sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)

CHAT_HTML = '''<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>台灣高空 AI 顧問</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Noto Sans TC',sans-serif;background:#f5f0eb;min-height:100vh;display:flex;flex-direction:column;align-items:center;padding:20px}
.header{text-align:center;margin-bottom:24px}
.header h1{font-size:1.5rem;color:#4a3728;letter-spacing:2px}
.header p{color:#888;font-size:.85rem;margin-top:4px}
.chat-box{width:100%;max-width:720px;background:#fff;border-radius:16px;box-shadow:0 2px 20px rgba(0,0,0,.08);display:flex;flex-direction:column;height:70vh}
.messages{flex:1;overflow-y:auto;padding:20px;display:flex;flex-direction:column;gap:14px}
.msg{max-width:85%;padding:12px 16px;border-radius:12px;line-height:1.6;font-size:.9rem}
.msg.user{background:#c9a96e;color:#fff;align-self:flex-end;border-radius:12px 12px 0 12px}
.msg.bot{background:#f5f0eb;color:#333;align-self:flex-start;border-radius:12px 12px 12px 0}
.msg.bot .sources{margin-top:8px;font-size:.75rem;color:#888;border-top:1px solid #e0d8cc;padding-top:6px}
.msg.bot .sources a{color:#c9a96e;text-decoration:none;display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.input-row{display:flex;gap:8px;padding:16px;border-top:1px solid #f0e8df}
.input-row input{flex:1;border:1px solid #ddd;border-radius:8px;padding:10px 14px;font-size:.9rem;outline:none}
.input-row input:focus{border-color:#c9a96e}
.input-row button{background:#c9a96e;color:#fff;border:none;border-radius:8px;padding:10px 20px;cursor:pointer;font-size:.9rem;font-weight:600}
.input-row button:disabled{background:#ddd}
.filter-row{display:flex;gap:8px;padding:0 16px 12px;flex-wrap:wrap}
.filter-row select{border:1px solid #ddd;border-radius:6px;padding:5px 10px;font-size:.8rem;outline:none;background:#fff;cursor:pointer}
.typing{color:#aaa;font-style:italic;font-size:.85rem}
</style>
</head>
<body>
<div class="header">
  <h1>🎵 台灣高空 AI 顧問</h1>
  <p>專業音響技術諮詢</p>
</div>
<div class="chat-box">
  <div class="messages" id="msgs">
    <div class="msg bot">你好！我是台灣高空的 AI 音響顧問，可以幫你解答產品規格、錄音設備選擇、隔音工程等問題。請直接提問 😊</div>
  </div>
  <div class="filter-row">
    <select id="doc-type"><option value="">全部類型</option><option value="blog">部落格文章</option><option value="product">產品頁</option></select>
    <select id="brand"><option value="">全部品牌</option><option value="Yamaha">Yamaha</option><option value="Focusrite">Focusrite</option><option value="Universal Audio">Universal Audio</option><option value="Shure">Shure</option><option value="Rode">Rode</option><option value="Zoom">Zoom</option></select>
  </div>
  <div class="input-row">
    <input id="q" type="text" placeholder="輸入問題…（例：錄音介面怎麼選？）" onkeydown="if(event.key==='Enter')send()"/>
    <button id="btn" onclick="send()">送出</button>
  </div>
</div>
<script>
function send(){
  const q=document.getElementById('q').value.trim();
  if(!q)return;
  const msgs=document.getElementById('msgs');
  const dt=document.getElementById('doc-type').value;
  const br=document.getElementById('brand').value;
  msgs.innerHTML+=`<div class="msg user">${q}</div>`;
  msgs.innerHTML+=`<div class="msg bot typing" id="typing">思考中…</div>`;
  msgs.scrollTop=msgs.scrollHeight;
  document.getElementById('btn').disabled=true;
  document.getElementById('q').value='';
  fetch('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({question:q,doc_type:dt||null,brand:br||null})})
  .then(r=>r.json())
  .then(d=>{
    document.getElementById('typing').remove();
    let src='';
    if(d.sources&&d.sources.length){
      src='<div class="sources">參考來源：'+(d.sources.slice(0,3).map(s=>`<a href="${s.url}" target="_blank">↗ ${s.title}</a>`).join(''))+'</div>';
    }
    msgs.innerHTML+=`<div class="msg bot">${(d.answer||d.error||'').replace(/\\n/g,'<br>')}${src}</div>`;
    msgs.scrollTop=msgs.scrollHeight;
  })
  .catch(e=>{
    document.getElementById('typing').remove();
    msgs.innerHTML+=`<div class="msg bot">⚠️ 查詢失敗：${e.message}</div>`;
  })
  .finally(()=>{ document.getElementById('btn').disabled=false; });
}
</script>
</body>
</html>'''

@app.route('/')
def index():
    return render_template_string(CHAT_HTML)

@app.route('/api/ask', methods=['POST'])
def api_ask():
    try:
        data     = request.get_json()
        question = (data.get('question') or '').strip()
        if not question:
            return jsonify({'error': '請輸入問題'}), 400
        doc_type = data.get('doc_type')
        brand    = data.get('brand')
        from query import ask
        result = ask(question, top_k=5, doc_type=doc_type, brand=brand)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/health')
def health():
    return jsonify({'ok': True})

if __name__ == '__main__':
    app.run(debug=True, port=5002)

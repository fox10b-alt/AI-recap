"""AI agent bản tin: AI trong ngân hàng - tài chính - chứng khoán - kế toán - kiểm toán.
Chạy miễn phí bằng Gemini API (khóa lấy tại https://aistudio.google.com/app/apikey).
Kết quả: docs/index.html
"""
import datetime
import html
import json
import os
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

API_KEY = os.environ["GEMINI_API_KEY"]
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")  # đổi nếu Google đổi tên model
def pick_model():
    url = "https://generativelanguage.googleapis.com/v1beta/models?pageSize=100&key=" + API_KEY
    with urllib.request.urlopen(url, timeout=30) as r:
        models = json.load(r).get("models", [])
    names = [m["name"].split("/")[-1] for m in models
             if "generateContent" in m.get("supportedGenerationMethods", [])]
    print("Models:", names)
    bad = ("lite", "image", "tts", "live", "preview", "exp", "audio", "thinking")
    flash = [n for n in names if "flash" in n and not any(b in n for b in bad)]
    return sorted(flash)[-1] if flash else names[0]


MODEL = os.environ.get("GEMINI_MODEL") or pick_model()
MODEL = "gemini-3.8-flash"
MODEL = "gemini-3.5-flash-lite"

KEYWORDS = [
    "AI ngân hàng",
    "trí tuệ nhân tạo tài chính",
    "AI chứng khoán",
    "AI kế toán",
    "AI kiểm toán",
    "Ngân hàng Nhà nước trí tuệ nhân tạo",
    "AI banking Vietnam",
    "AI in banking",
    "AI in accounting audit",
]


def fetch_news(query):
    params = {"q": query + " when:7d", "hl": "vi", "gl": "VN", "ceid": "VN:vi"}
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=30) as r:
        root = ET.fromstring(r.read())
    items = []
    for it in root.iter("item"):
        src = it.find("source")
        items.append({
            "title": (it.findtext("title") or "").strip(),
            "link": (it.findtext("link") or "").strip(),
            "source": src.text if src is not None else "",
        })
    return items[:8]


def collect():
    seen, items = set(), []
    for kw in KEYWORDS:
        try:
            for it in fetch_news(kw):
                if it["title"] not in seen:
                    seen.add(it["title"])
                    items.append(it)
        except Exception as e:  # một nguồn lỗi thì bỏ qua
            print("Lỗi RSS:", kw, e)
    return items[:70]


def ask_gemini(items):
    listing = "\n".join(f"{i}. {it['title']} ({it['source']})" for i, it in enumerate(items))
    prompt = (
        "Bạn là biên tập viên bản tin tài chính - ngân hàng - kiểm toán tại Việt Nam.\n"
        "Từ danh sách tiêu đề dưới đây, chọn đúng 10 tin quan trọng nhất về ỨNG DỤNG AI trong "
        "ngân hàng, tài chính, chứng khoán, kế toán, kiểm toán (ưu tiên tin Việt Nam và "
        "hướng dẫn/quy định về AI của Ngân hàng Nhà nước). Bỏ tin trùng hoặc không liên quan.\n"
        "Chỉ dựa vào tiêu đề, không bịa thêm số liệu. Trả về JSON: mảng 10 đối tượng "
        '{"id": số thứ tự trong danh sách, "tom_tat": "1 câu tiếng Việt", '
        '"linh_vuc": "Ngân hàng|Tài chính|Chứng khoán|Kế toán|Kiểm toán"}.\n\n' + listing
    )
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{MODEL}:generateContent?key={API_KEY}"
    )
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }).encode()
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, body, {"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=90) as r:
                data = json.load(r)
            return json.loads(data["candidates"][0]["content"]["parts"][0]["text"])
        except Exception as e:
            print("Lỗi Gemini, thử lại:", e)
            time.sleep(20 * (attempt + 1))
    raise SystemExit("Không gọi được Gemini API")


def render(picks, items):
    today = datetime.date.today().strftime("%d/%m/%Y")
    rows = []
    for p in picks:
        try:
            it = items[int(p["id"])]
        except (KeyError, ValueError, IndexError):
            continue
        rows.append(
            f"<li><b>[{html.escape(p.get('linh_vuc', ''))}]</b> {html.escape(p.get('tom_tat', ''))}"
            f'<br><a href="{html.escape(it["link"])}">{html.escape(it["title"])}</a> '
            f"<small>({html.escape(it['source'])})</small></li>"
        )
    page = f"""<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bản tin AI ngành tài chính</title>
<style>body{{font-family:sans-serif;max-width:720px;margin:auto;padding:16px;line-height:1.5}}
li{{margin-bottom:14px}}small{{color:#666}}</style></head><body>
<h1>Bản tin AI: ngân hàng - tài chính - chứng khoán - kế toán - kiểm toán</h1>
<p>Cập nhật: {today}</p><ol>{''.join(rows)}</ol>
<p><small>Tạo tự động bằng AI từ tiêu đề tin; hãy mở link gốc để kiểm chứng.</small></p>
</body></html>"""
    os.makedirs("docs", exist_ok=True)
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(page)


if __name__ == "__main__":
    news = collect()
    print("Số tin thu thập:", len(news))
    render(ask_gemini(news), news)
    print("Đã tạo docs/index.html")

"""Bản tin AI (bản 4) cho kiểm toán viên nội bộ / Ban kiểm soát ngân hàng.
- Gemini tự tìm trên Google, tóm tắt nội dung và nêu ý nghĩa với công việc (khoảng 100 tin).
- Tự chờ khi bị giới hạn hạn mức; nếu tìm Google bị chặn thì chuyển sang chế độ dự phòng.
- Kết quả: docs/index.html (mới nhất), docs/archive/ (các ngày trước), tùy chọn gửi Telegram.
Khóa API miễn phí: https://aistudio.google.com/app/apikey (để trong GitHub Secrets).
"""
import datetime
import html
import json
import os
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

API_KEY = os.environ["GEMINI_API_KEY"]
# Thử lần lượt các model này; model nào lỗi thì chuyển sang model kế tiếp
MODELS = ["gemini-3.5-flash-lite", "gemini-3.7-flash", "gemini-3.8-flash"]

MY_JOB = (
    "thành viên Ban kiểm soát và kiểm toán viên nội bộ của một ngân hàng thương mại ở Việt Nam "
    "(quan tâm kiểm soát nội bộ, quản trị rủi ro, tuân thủ và các quy định của Ngân hàng Nhà nước)"
)

# --- Telegram (tùy chọn): nếu có đủ 2 khóa bí mật thì gửi bản rút gọn qua Telegram ---
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")  # ví dụ: @ten_kenh_cua_ban
PAGE_URL = "https://fox10b-alt.github.io/AI-recap/"  # đổi nếu bạn đổi tên GitHub
TG_PER_TOPIC = 5  # số tin hiển thị mỗi nhóm trong tin nhắn Telegram

PER_TOPIC = 20  # số tin tối đa mỗi nhóm. 5 nhóm x 20 tin = khoảng 100 tin
TOPICS = [
    "quy định, hướng dẫn, chính sách về AI, chuyển đổi số và rủi ro công nghệ của Ngân hàng Nhà nước và các cơ quan quản lý tài chính Việt Nam; các ngân hàng Việt Nam đang triển khai AI vào nghiệp vụ nào",
    "AI trong kiểm toán nội bộ, kiểm soát nội bộ, kiểm toán độc lập, kế toán, thuế, báo cáo tài chính và chuẩn mực (Việt Nam và thế giới)",
    "quản trị rủi ro mô hình AI (model risk), quản trị AI (AI governance), đạo đức AI; hướng dẫn và báo cáo của Basel Committee, BIS, FSB, IMF, IIA, ISACA, IFAC, ACCA",
    "gian lận, lừa đảo, rửa tiền (AML), deepfake, an ninh mạng; AI trong tuân thủ (compliance), RegTech và hoạt động giám sát của cơ quan quản lý ngân hàng",
    "ngân hàng lớn trên thế giới triển khai AI (dự án, kết quả, sự cố, bài học); AI trong chứng khoán, đầu tư, fintech, bảo hiểm, thanh toán và tác động đến ngân hàng",
]

RSS_QUERIES = [
    "AI ngân hàng", "AI kiểm toán nội bộ", "Ngân hàng Nhà nước trí tuệ nhân tạo",
    "AI chứng khoán", "AI kế toán kiểm toán",
    "AI in banking", "AI internal audit", "AI model risk banks",
    "Basel AI banks", "AI compliance banking",
]

FIELDS = ("ID", "TIEU_DE", "TOM_TAT", "ANH_HUONG", "NGUON")
SHOWN = [False]  # chỉ in chi tiết đầy đủ cho lỗi đầu tiên


def build_prompt(topic):
    today = datetime.date.today().strftime("%d/%m/%Y")
    return (
        f"Hôm nay là {today}. Hãy dùng Google Search để tìm các tin và bài phân tích MỚI NHẤT "
        f"(trong khoảng 7 ngày gần đây) thuộc nhóm chủ đề: {topic}.\n\n"
        f"Người đọc bản tin là: {MY_JOB}.\n\n"
        "Hãy tìm cả bằng tiếng Việt lẫn tiếng Anh. Ưu tiên báo và tạp chí chuyên ngành, "
        "cơ quan quản lý và tổ chức nghề nghiệp, ví dụ: sbv.gov.vn, thoibaonganhang.vn, "
        "tapchinganhang.gov.vn, tapchitaichinh.vn, baodautu.vn, vietstock.vn, cafef.vn; "
        "risk.net, ft.com, reuters.com, bloomberg.com, americanbanker.com, finextra.com, "
        "bankingdive.com, accountingtoday.com, complianceweek.com, theiia.org, isaca.org, "
        "ifac.org, accaglobal.com, bis.org, fsb.org, imf.org và báo cáo của PwC, Deloitte, "
        "EY, KPMG. Nếu có nguồn chuyên ngành tốt hơn thì dùng. Với bài bị khóa phí, chỉ tóm "
        "tắt phần công khai.\n\n"
        f"Chọn tối đa {PER_TOPIC} tin khác nhau, quan trọng nhất. Nếu không đủ tin thật "
        "thì viết ít hơn, tuyệt đối không bịa và không lặp lại tin. Luôn viết bằng tiếng Việt, "
        "kể cả khi nguồn là tiếng Anh (giữ nguyên thuật ngữ tiếng Anh quan trọng trong ngoặc). "
        "Với mỗi tin, viết đúng định dạng sau (không dùng markdown, không in đậm). Các tin "
        "ngăn cách nhau bằng một dòng chỉ có ba dấu gạch ngang ---\n\n"
        "TIEU_DE: tiêu đề ngắn gọn bằng tiếng Việt\n"
        "TOM_TAT: 2 câu nêu nội dung chính yếu: ai làm gì, con số hoặc quy định quan trọng nếu có\n"
        "ANH_HUONG: 1 câu nói tin này có ý nghĩa gì với công tác kiểm toán nội bộ, kiểm soát nội "
        "bộ và giám sát của Ban kiểm soát ngân hàng (rủi ro cần soát xét, yêu cầu tuân thủ, kỹ "
        "năng cần có); nếu ít liên quan thì nói thẳng là ít liên quan\n"
        "NGUON: tên miền trang báo, ví dụ risk.net\n\n"
        "Chỉ dùng thông tin có trong các trang tìm được, không bịa số liệu hay trích dẫn. "
        "Không viết lời dẫn hay kết luận ngoài các tin."
    )


def call(model, prompt, use_search=True):
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent?key={API_KEY}")
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 8192},
    }
    if use_search:
        payload["tools"] = [{"google_search": {}}]
    req = urllib.request.Request(
        url, json.dumps(payload).encode(), {"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=240) as r:
        return json.load(r)


def generate(prompt, use_search=True):
    for model in MODELS:
        for attempt in range(2):
            try:
                data = call(model, prompt, use_search)
                cand = data["candidates"][0]
                text = "".join(p.get("text", "") for p in cand["content"]["parts"])
                if text.strip():
                    print("Dùng model:", model)
                    return text, cand.get("groundingMetadata", {})
                print("Model trả về rỗng:", model)
            except Exception as e:
                code = getattr(e, "code", None)
                detail = e.read().decode("utf-8", "ignore") if hasattr(e, "read") else ""
                limit = 150 if SHOWN[0] else 1500
                SHOWN[0] = True
                print("Lỗi", model, code or e, detail[:limit].replace("\n", " "))
                if code == 429:
                    if "perday" in detail.lower().replace("_", ""):
                        print("Hết hạn mức THEO NGÀY của", model)
                        break
                    m = re.search(r'retryDelay"?:\s*"?(\d+)', detail)
                    wait = min(int(m.group(1)) + 3, 90) if m else 60
                    print(f"Bị giới hạn tốc độ, chờ {wait} giây rồi thử lại")
                    time.sleep(wait)
                    continue
                if code in (400, 403, 404):
                    break
            time.sleep(15)
    print("Bỏ qua vì mọi model đều lỗi")
    return None


def parse(text):
    items = []
    for block in re.split(r"\n\s*---+\s*\n", "\n" + text.strip() + "\n"):
        d = {}
        for key in FIELDS:
            nxt = "|".join(FIELDS)
            m = re.search(
                rf"^\W*{key}\W*?:\s*(.+?)(?=^\W*(?:{nxt})\W*?:|\Z)", block, re.S | re.M
            )
            if m:
                d[key] = " ".join(m.group(1).split())
        if "TIEU_DE" in d and "TOM_TAT" in d:
            items.append(d)
    return items


def link_for(nguon, chunks):
    n = (nguon or "").lower().strip()
    for c in chunks:
        web = c.get("web", {})
        title = (web.get("title") or "").lower()
        if title and n and (n in title or title in n):
            return web.get("uri")
    return None


# ---------- Chế độ dự phòng: Google News RSS + Gemini (không dùng tìm Google) ----------
def fetch_news(query):
    params = {"q": query + " when:7d", "hl": "vi", "gl": "VN", "ceid": "VN:vi"}
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=30) as r:
        root = ET.fromstring(r.read())
    out = []
    for it in root.iter("item"):
        src = it.find("source")
        out.append({
            "title": (it.findtext("title") or "").strip(),
            "link": (it.findtext("link") or "").strip(),
            "source": src.text if src is not None else "",
        })
    return out[:10]


def fallback_sections():
    items, seen = [], set()
    for q in RSS_QUERIES:
        try:
            for it in fetch_news(q):
                if it["title"] and it["title"] not in seen:
                    seen.add(it["title"])
                    items.append(it)
        except Exception as e:
            print("Lỗi RSS:", q, e)
    items = items[:90]
    if not items:
        return []
    listing = "\n".join(f"{i}. {it['title']} ({it['source']})" for i, it in enumerate(items))
    prompt = (
        f"Người đọc là: {MY_JOB}.\n"
        "Từ danh sách tiêu đề dưới đây, chọn tối đa 40 tin quan trọng nhất về ỨNG DỤNG AI trong "
        "ngân hàng, kiểm toán, kế toán, tài chính, quản trị rủi ro, tuân thủ. Chỉ dựa vào tiêu đề, "
        "không bịa thêm chi tiết. Viết bằng tiếng Việt. Mỗi tin theo đúng định dạng sau (không "
        "markdown), các tin ngăn cách bằng một dòng chỉ có ba dấu gạch ngang ---\n"
        "ID: số thứ tự của tin trong danh sách\n"
        "TIEU_DE: tiêu đề tiếng Việt\n"
        "TOM_TAT: 1 câu, chỉ dựa trên tiêu đề\n"
        "ANH_HUONG: 1 câu về ý nghĩa với kiểm toán nội bộ và Ban kiểm soát; nếu chưa đủ thông tin "
        "thì ghi: cần đọc bài gốc\n"
        "NGUON: tên báo\n\n" + listing
    )
    res = generate(prompt, use_search=False)
    if not res:
        return []
    out = []
    for it in parse(res[0]):
        try:
            src = items[int(it["ID"])]
        except (KeyError, ValueError, IndexError):
            continue
        it["LINK"] = src["link"]
        it["NGUON"] = src["source"] or it.get("NGUON", "")
        out.append(it)
    if not out:
        return []
    return [("Tin mới (chế độ dự phòng: chỉ dựa trên tiêu đề, hãy mở bài gốc để đọc đầy đủ)", out)]


# ---------- Tạo trang web ----------
PAGE = """<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bản tin AI ngành tài chính</title>
<style>body{font-family:sans-serif;max-width:720px;margin:auto;padding:16px;line-height:1.55}
.card{border:1px solid #ddd;border-radius:10px;padding:12px 14px;margin-bottom:14px}
.card h3{margin:0 0 6px;font-size:1.05em}.imp{background:#fff7e0;padding:8px;border-radius:6px}
h2{margin-top:28px;border-bottom:2px solid #333;padding-bottom:4px;font-size:1.1em}small{color:#666}</style></head><body>
<h1>Bản tin AI: ngân hàng - tài chính - chứng khoán - kế toán - kiểm toán</h1>
<p>Cập nhật: __DATE__ | __TOTAL__ tin | <a href="__ARCHIVE__">Xem các ngày trước</a></p>__BODY__
<p><small>Bản tin do AI tổng hợp, chỉ để tham khảo. Hãy mở bài gốc để kiểm chứng.</small></p>
</body></html>"""


def render(sections, total):
    today = datetime.date.today()
    n = 0
    parts = []
    for topic, items in sections:
        parts.append(f"<h2>{html.escape(topic[:1].upper() + topic[1:])}</h2>")
        for it in items:
            n += 1
            src = html.escape(it.get("NGUON", ""))
            if it.get("LINK"):
                src = f'<a href="{html.escape(it["LINK"])}">Đọc bài gốc: {src}</a>'
            parts.append(
                f"<div class='card'><h3>{n}. {html.escape(it['TIEU_DE'])}</h3>"
                f"<p>{html.escape(it['TOM_TAT'])}</p>"
                f"<p class='imp'><b>Ý nghĩa với công việc của bạn:</b> {html.escape(it.get('ANH_HUONG', ''))}</p>"
                f"<small>{src}</small></div>"
            )
    page = (PAGE.replace("__DATE__", today.strftime("%d/%m/%Y"))
                .replace("__TOTAL__", str(total))
                .replace("__BODY__", "".join(parts)))
    os.makedirs("docs/archive", exist_ok=True)
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(page.replace("__ARCHIVE__", "archive/index.html"))
    with open(f"docs/archive/{today.isoformat()}.html", "w", encoding="utf-8") as f:
        f.write(page.replace("__ARCHIVE__", "index.html"))
    days = sorted(
        (x[:-5] for x in os.listdir("docs/archive") if re.match(r"\d{4}-\d{2}-\d{2}\.html$", x)),
        reverse=True,
    )
    lis = "".join(f'<li><a href="{d}.html">{d}</a></li>' for d in days)
    with open("docs/archive/index.html", "w", encoding="utf-8") as f:
        f.write(
            '<!doctype html><html lang="vi"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Các ngày trước</title></head>'
            '<body style="font-family:sans-serif;max-width:720px;margin:auto;padding:16px">'
            f'<h1>Bản tin các ngày trước</h1><ul>{lis}</ul>'
            '<p><a href="../">Về bản tin mới nhất</a></p></body></html>'
        )
    print("Đã tạo docs/index.html với", total, "tin")


def send_telegram(sections, total):
    if not (TG_TOKEN and TG_CHAT):
        print("Chưa cấu hình Telegram, bỏ qua bước gửi")
        return
    today = datetime.date.today().strftime("%d/%m/%Y")
    lines = [f"<b>Bản tin AI ngân hàng - kiểm toán, {today}</b> ({total} tin)", ""]
    for topic, items in sections:
        short = topic.split(";")[0]
        lines.append(f"<b>{html.escape(short[:1].upper() + short[1:90])}</b>")
        for it in items[:TG_PER_TOPIC]:
            title = html.escape(it["TIEU_DE"])
            if it.get("LINK"):
                title = f'<a href="{html.escape(it["LINK"], quote=True)}">{title}</a>'
            lines.append("• " + title)
        lines.append("")
    lines.append(f"Đọc đầy đủ {total} tin có tóm tắt: {PAGE_URL}")
    chunks, cur = [], ""
    for ln in lines:
        if len(cur) + len(ln) + 1 > 3800:
            chunks.append(cur)
            cur = ""
        cur += ln + "\n"
    chunks.append(cur)
    for c in chunks:
        body = json.dumps({
            "chat_id": TG_CHAT, "text": c, "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            body, {"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(req, timeout=30).read()
            print("Đã gửi 1 tin nhắn Telegram")
        except Exception as e:
            detail = e.read()[:200].decode("utf-8", "ignore") if hasattr(e, "read") else ""
            print("Lỗi gửi Telegram:", e, detail)
        time.sleep(2)


def main():
    sections, seen, fails = [], set(), 0
    for topic in TOPICS:
        print("Nhóm chủ đề:", topic[:70])
        res = generate(build_prompt(topic))
        if res:
            fails = 0
            text, meta = res
            chunks = meta.get("groundingChunks", [])
            items = []
            for it in parse(text):
                key = re.sub(r"\W+", "", it["TIEU_DE"].lower())
                if key in seen:
                    continue
                seen.add(key)
                it["LINK"] = link_for(it.get("NGUON"), chunks)
                items.append(it)
            if items:
                sections.append((topic, items))
        else:
            fails += 1
            if fails >= 2:
                print("Hai nhóm liên tiếp lỗi, dừng sớm để không phí hạn mức")
                break
        time.sleep(30)  # nghỉ giữa các lần gọi để không vượt giới hạn miễn phí
    total = sum(len(items) for _, items in sections)
    if total < 5:
        print("Chế độ tìm Google không đủ tin, chuyển sang chế độ dự phòng")
        sections += fallback_sections()
        total = sum(len(items) for _, items in sections)
    if total == 0:
        raise SystemExit("Không lấy được tin nào")
    render(sections, total)
    send_telegram(sections, total)


if __name__ == "__main__":
    main()

"""Bản tin AI (bản 3): khoảng 100 tin, chia theo 10 chủ đề, mỗi tin có tóm tắt nội dung
và phần "ảnh hưởng đến bạn". Gemini tự tìm trên Google.
Kết quả: docs/index.html (mới nhất) và docs/archive/ (các ngày trước).
Khóa API miễn phí: https://aistudio.google.com/app/apikey (để trong GitHub Secrets).
"""
import datetime
import html
import json
import os
import re
import time
import urllib.request

API_KEY = os.environ["GEMINI_API_KEY"]
# Thử lần lượt các model này; model nào lỗi thì chuyển sang model kế tiếp
MODELS = ["gemini-3.5-flash-lite", "gemini-3.7-flash", "gemini-3.8-flash"]

# >>> ĐỔI DÒNG NÀY cho đúng công việc của bạn (càng cụ thể càng tốt) <<<
MY_JOB = (
    "thành viên Ban kiểm soát và kiểm toán viên nội bộ của một ngân hàng thương mại ở Việt Nam "
    "(quan tâm kiểm soát nội bộ, quản trị rủi ro, tuân thủ và các quy định của Ngân hàng Nhà nước)"
)

PER_TOPIC = 10  # số tin tối đa mỗi chủ đề. 10 chủ đề x 10 tin = khoảng 100 tin
TOPICS = [
    "quy định, hướng dẫn, chính sách về AI, chuyển đổi số và quản lý rủi ro công nghệ của Ngân hàng Nhà nước Việt Nam và các cơ quan quản lý tài chính Việt Nam",
    "ngân hàng Việt Nam đang triển khai AI vào nghiệp vụ nào (tín dụng, chăm sóc khách hàng, vận hành, quản trị rủi ro)",
    "AI trong kiểm toán nội bộ, kiểm soát nội bộ và kiểm toán độc lập (Việt Nam và thế giới)",
    "quản trị rủi ro mô hình AI (model risk), quản trị AI (AI governance), đạo đức AI trong ngân hàng",
    "hướng dẫn, báo cáo của các tổ chức quốc tế về AI trong ngân hàng và kiểm toán: Basel Committee, BIS, FSB, IMF, IIA, ISACA, IFAC, ACCA",
    "gian lận, lừa đảo, rửa tiền (AML), deepfake và an ninh mạng trong ngân hàng",
    "AI trong tuân thủ (compliance), RegTech và hoạt động giám sát của cơ quan quản lý ngân hàng",
    "ngân hàng lớn trên thế giới triển khai AI: dự án, kết quả, sự cố và bài học",
    "AI trong kế toán, thuế, báo cáo tài chính và chuẩn mực kế toán, kiểm toán",
    "AI trong chứng khoán, đầu tư, fintech, bảo hiểm, thanh toán và tác động đến ngân hàng",
]

FIELDS = ("TIEU_DE", "TOM_TAT", "ANH_HUONG", "NGUON")


def build_prompt(topic):
    today = datetime.date.today().strftime("%d/%m/%Y")
    return (
        f"Hôm nay là {today}. Hãy dùng Google Search để tìm các tin và bài phân tích MỚI NHẤT "
        f"(trong khoảng 7 ngày gần đây) thuộc chủ đề: {topic}.\n\n"
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


def call(model, prompt):
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent?key={API_KEY}")
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {"maxOutputTokens": 8192},
    }).encode()
    req = urllib.request.Request(url, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=240) as r:
        return json.load(r)


def generate(prompt):
    for model in MODELS:
        for attempt in range(2):
            try:
                data = call(model, prompt)
                cand = data["candidates"][0]
                text = "".join(p.get("text", "") for p in cand["content"]["parts"])
                if text.strip():
                    print("Dùng model:", model)
                    return text, cand.get("groundingMetadata", {})
                print("Model trả về rỗng:", model)
            except Exception as e:
                detail = ""
                if hasattr(e, "read"):
                    detail = e.read()[:300].decode("utf-8", "ignore")
                print("Lỗi", model, e, detail)
            time.sleep(15)
    print("Bỏ qua chủ đề này vì mọi model đều lỗi")
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


PAGE = """<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bản tin AI ngành tài chính</title>
<style>body{font-family:sans-serif;max-width:720px;margin:auto;padding:16px;line-height:1.55}
.card{border:1px solid #ddd;border-radius:10px;padding:12px 14px;margin-bottom:14px}
.card h3{margin:0 0 6px;font-size:1.05em}.imp{background:#fff7e0;padding:8px;border-radius:6px}
h2{margin-top:28px;border-bottom:2px solid #333;padding-bottom:4px}small{color:#666}</style></head><body>
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


def main():
    sections, seen = [], set()
    for topic in TOPICS:
        print("Chủ đề:", topic)
        res = generate(build_prompt(topic))
        if res:
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
        time.sleep(20)  # nghỉ giữa các lần gọi để không vượt giới hạn miễn phí
    total = sum(len(items) for _, items in sections)
    if total == 0:
        raise SystemExit("Không lấy được tin nào")
    render(sections, total)


if __name__ == "__main__":
    main()

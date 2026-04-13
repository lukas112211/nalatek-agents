import os
import httpx
import asyncio
from datetime import datetime, timezone

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
BOT_TOKEN    = os.environ["BOT_TOKEN"]
CHAT_ID      = os.environ["CHAT_ID"]
GEMINI_KEY   = os.environ["GEMINI_KEY"]

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

KEYWORDS = [
    "jasa pembuatan website",
    "jasa web developer",
    "landing page murah",
    "website toko online",
    "web developer Indonesia"
]

async def tg_send(client, text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    r = await client.post(url, json={"chat_id": CHAT_ID, "text": text})
    print(f"[TG] ok={r.json().get('ok')} | {text[:60]}")

async def sb_insert(client, table, data):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    r = await client.post(url, headers={**HEADERS, "Prefer": "return=minimal"}, json=data)
    return r.status_code in (200, 201)

async def ask_gemini(client, prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent?key={GEMINI_KEY}"
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        r = await client.post(url, json=body, timeout=30)
        data = r.json()
        print(f"[GEMINI RAW] {str(data)[:200]}")
        # Coba ambil text dari berbagai kemungkinan struktur response
        if "candidates" in data:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        elif "error" in data:
            return f"Gemini error: {data['error'].get('message', 'unknown')}"
        else:
            return f"Response tidak dikenal: {str(data)[:100]}"
    except Exception as e:
        return f"Error memanggil Gemini: {str(e)}"

def get_trends():
    results = {}
    try:
        from pytrends.request import TrendReq
        pytrends = TrendReq(hl="id-ID", tz=420)
        pytrends.build_payload(KEYWORDS[:5], cat=0, timeframe="now 7-d", geo="ID")
        df = pytrends.interest_over_time()
        if not df.empty:
            for kw in KEYWORDS[:5]:
                if kw in df.columns:
                    results[kw] = int(df[kw].mean())
    except Exception as e:
        print(f"[TRENDS ERROR] {e}")
    # Kalau gagal atau kosong, isi default 0
    for kw in KEYWORDS:
        if kw not in results:
            results[kw] = 0
    return results

async def main():
    print("[AGENT PEMASARAN] Mulai analisis pasar...")
    async with httpx.AsyncClient(timeout=30) as client:

        # 1. Ambil data tren
        print("[TRENDS] Mengambil data Google Trends...")
        trends = get_trends()
        print(f"[TRENDS] {trends}")

        # 2. Simpan ke Supabase
        now = datetime.now(timezone.utc).isoformat()
        for kw, score in trends.items():
            ok = await sb_insert(client, "market_insights", {
                "keyword": kw,
                "platform": "google_trends",
                "insight_data": {"score_7d": score, "region": "ID"},
                "score": score,
                "created_at": now
            })
            print(f"[DB] Insert {kw}: {ok}")

        # 3. Analisis Gemini
        top = sorted(trends.items(), key=lambda x: x[1], reverse=True)
        top_str = "\n".join([f"- {k}: skor {v}/100" for k, v in top])
        top_keyword = top[0][0] if top else "-"
        top_score = top[0][1] if top else 0

        prompt = f"""Kamu adalah analis pemasaran digital untuk bisnis jasa web development bernama Nalatek di Indonesia.

Data tren pencarian Google 7 hari terakhir:
{top_str}

Berikan analisis singkat (maksimal 150 kata) dalam Bahasa Indonesia:
1. Keyword paling potensial untuk ditarget sekarang
2. Satu ide konten TikTok atau Instagram untuk minggu ini
3. Satu saran strategi pemasaran konkret untuk Nalatek

Jawab langsung tanpa intro."""

        print("[GEMINI] Meminta analisis...")
        analisis = await ask_gemini(client, prompt)
        print(f"[GEMINI] {analisis[:150]}")

        # 4. Kirim ke Telegram
        pesan = (
            f"Laporan Analisis Pasar Nalatek\n"
            f"{datetime.now().strftime('%d %b %Y')}\n\n"
            f"Keyword teratas: {top_keyword} (skor {top_score})\n\n"
            f"Analisis AI:\n{analisis}\n\n"
            f"Data tersimpan di Supabase."
        )
        await tg_send(client, pesan)

        # 5. Log
        await sb_insert(client, "agent_logs", {
            "agent_name": "pemasaran_analisis",
            "action": "analisis_pasar_harian",
            "status": "success",
            "details": {"keywords_tracked": len(trends), "top_keyword": top_keyword}
        })

        # 6. Kirim ke asisten
        await sb_insert(client, "agent_messages", {
            "from_agent": "pemasaran",
            "to_agent": "asisten",
            "message_type": "result",
            "content": {
                "text": f"Analisis pasar selesai. Top keyword: {top_keyword} (skor {top_score})",
                "top_trends": dict(top[:3])
            },
            "status": "pending"
        })

        print("[AGENT PEMASARAN] Selesai!")

if __name__ == "__main__":
    asyncio.run(main())

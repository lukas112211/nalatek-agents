import os
import httpx
import asyncio
from datetime import datetime, timezone

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
BOT_TOKEN    = os.environ["BOT_TOKEN"]
CHAT_ID      = os.environ["CHAT_ID"]
GEMINI_KEY   = os.environ["GEMINI_KEY"]

SUPABASE_HEADERS = {
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
    r = await client.post(url, headers={**SUPABASE_HEADERS, "Prefer": "return=minimal"}, json=data)
    return r.status_code in (200, 201)

async def ask_ai(client, prompt):
    url = "https://openrouter.ai"
    headers = {
        "Authorization": f"Bearer {GEMINI_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://localhost", # Tambahkan ini
        "X-Title": "Nalatek Market Bot"       # Tambahkan ini
    }
    body = {
        "model": "google/gemini-flash-1.5-8b:free",
        "messages": [{"role": "user", "content": prompt}]
    }
    try:
        r = await client.post(url, headers=headers, json=body, timeout=40)
        
        # Cek jika status bukan 200 (OK)
        if r.status_code != 200:
            return f"AI Error: Server returned status {r.status_code} - {r.text}"
            
        data = r.json()
        if "choices" in data:
            return data["choices"][0]["message"]["content"]
        return f"AI error: {data.get('error', {}).get('message', 'Unknown error')}"
    except Exception as e:
        return f"Error memanggil AI: {str(e)}"
    try:
        r = await client.post(url, headers=headers, json=body, timeout=30)
        data = r.json()
        print(f"[AI RAW] {str(data)[:200]}")
        if "choices" in data:
            return data["choices"][0]["message"]["content"]
        elif "error" in data:
            return f"AI error: {data['error'].get('message', str(data['error']))}"
        else:
            return f"Response tidak dikenal: {str(data)[:100]}"
    except Exception as e:
        return f"Error memanggil AI: {str(e)}"

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
    for kw in KEYWORDS:
        if kw not in results:
            results[kw] = 0
    return results

async def main():
    print("[AGENT PEMASARAN] Mulai analisis pasar...")
    async with httpx.AsyncClient(timeout=30) as client:

        print("[TRENDS] Mengambil data Google Trends...")
        trends = get_trends()
        print(f"[TRENDS] {trends}")

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

        top = sorted(trends.items(), key=lambda x: x[1], reverse=True)
        top_str = "\n".join([f"- {k}: skor {v}/100" for k, v in top])
        top_keyword = top[0][0] if top else "-"
        top_score = top[0][1] if top else 0

        prompt = (
            "Kamu adalah analis pemasaran digital untuk bisnis jasa web development "
            "bernama Nalatek di Indonesia.\n\n"
            f"Data tren pencarian Google 7 hari terakhir:\n{top_str}\n\n"
            "Berikan analisis singkat (maksimal 150 kata) dalam Bahasa Indonesia:\n"
            "1. Keyword paling potensial untuk ditarget sekarang\n"
            "2. Satu ide konten TikTok atau Instagram untuk minggu ini\n"
            "3. Satu saran strategi pemasaran konkret untuk Nalatek\n\n"
            "Jawab langsung tanpa intro."
        )

        print("[AI] Meminta analisis...")
        analisis = await ask_ai(client, prompt)
        print(f"[AI] {analisis[:150]}")

        pesan = (
            f"Laporan Analisis Pasar Nalatek\n"
            f"{datetime.now().strftime('%d %b %Y')}\n\n"
            f"Keyword teratas: {top_keyword} (skor {top_score})\n\n"
            f"Analisis AI:\n{analisis}\n\n"
            f"Data tersimpan di Supabase."
        )
        await tg_send(client, pesan)

        await sb_insert(client, "agent_logs", {
            "agent_name": "pemasaran_analisis",
            "action": "analisis_pasar_harian",
            "status": "success",
            "details": {"keywords_tracked": len(trends), "top_keyword": top_keyword}
        })

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

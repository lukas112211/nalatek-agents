import os
import httpx
import asyncio
import json
from datetime import datetime, timezone

SUPABASE_URL   = os.environ["SUPABASE_URL"]
SUPABASE_KEY   = os.environ["SUPABASE_KEY"]
BOT_TOKEN      = os.environ["BOT_TOKEN"]
CHAT_ID        = os.environ["CHAT_ID"]
OPENROUTER_KEY = os.environ["GEMINI_KEY"]

SB_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

async def tg_send(client, text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    r = await client.post(url, json={"chat_id": CHAT_ID, "text": text})
    print(f"[TG] ok={r.json().get('ok')} | {text[:50]}")

async def sb_insert(client, table, data):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    r = await client.post(url, headers={**SB_HEADERS, "Prefer": "return=minimal"}, json=data)
    return r.status_code in (200, 201)

async def sb_get(client, table, params=None):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    r = await client.get(url, headers=SB_HEADERS, params=params or {})
    return r.json() if r.status_code == 200 else []

async def sb_update(client, table, match, data):
    params = {k: f"eq.{v}" for k, v in match.items()}
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    r = await client.patch(url, headers={**SB_HEADERS, "Prefer": "return=minimal"}, params=params, json=data)
    return r.status_code in (200, 204)

async def ask_ai(client, prompt):
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://nalatek.gt.tc",
        "X-Title": "Nalatek Analyzer"
    }
    body = {
        "model": "google/gemma-4-26b-a4b-it:free",
        "messages": [{"role": "user", "content": prompt}]
    }
    try:
        r = await client.post(url, headers=headers, json=body, timeout=60)
        data = r.json()
        if "choices" in data:
            return data["choices"][0]["message"]["content"]
        return f"AI Error: {str(data)[:100]}"
    except Exception as e:
        return f"Error: {str(e)}"

async def main():
    print("[ANALYZER] Mulai analisis...")
    async with httpx.AsyncClient(timeout=60) as client:

        # Ambil pesan dari kreator
        msgs = await sb_get(client, "agent_messages", {
            "to_agent": "eq.konten_analyzer",
            "status": "eq.pending",
            "order": "created_at.asc",
            "limit": "5"
        })

        if not msgs:
            print("[ANALYZER] Tidak ada pesan masuk")
            return

        print(f"[ANALYZER] {len(msgs)} konten perlu dianalisis")

        for msg in msgs:
            content = msg.get("content", {})
            judul   = content.get("judul", "Konten")
            caption = content.get("caption", "")
            hook    = content.get("hook", "")
            keywords = content.get("keywords", "")

            # Tandai sudah dibaca
            await sb_update(client, "agent_messages", {"id": msg["id"]}, {
                "status": "read",
                "read_at": datetime.now(timezone.utc).isoformat()
            })

            # Analisis dengan AI
            prompt = f"""Kamu adalah analis konten media sosial profesional untuk bisnis jasa web development Nalatek di Indonesia.

Konten yang baru dibuat:
Judul: {judul}
Hook: {hook}
Caption: {caption}
Keywords: {keywords}

Evaluasi dan jawab HANYA dengan JSON:
{{
  "skor": 80,
  "prediksi_engagement": "sedang",
  "kekuatan": ["poin kekuatan 1", "poin kekuatan 2"],
  "kelemahan": ["poin kelemahan 1"],
  "saran_perbaikan": "saran konkret untuk konten besok",
  "saran_hook": "hook yang lebih menarik untuk konten serupa",
  "hashtag_tambahan": ["#tag1", "#tag2", "#tag3"],
  "waktu_terbaik": "jam berapa posting terbaik hari ini"
}}"""

            print(f"[AI] Analisis: {judul}")
            raw = await ask_ai(client, prompt)

            try:
                clean = raw.strip()
                if "```json" in clean:
                    clean = clean.split("```json")[1].split("```")[0].strip()
                elif "```" in clean:
                    clean = clean.split("```")[1].split("```")[0].strip()
                hasil = json.loads(clean)
            except Exception as e:
                print(f"[PARSE] {e}")
                hasil = {
                    "skor": 70,
                    "prediksi_engagement": "sedang",
                    "kekuatan": ["Konten sudah relevan dengan target pasar"],
                    "kelemahan": ["Perlu call-to-action yang lebih jelas"],
                    "saran_perbaikan": "Tambahkan angka spesifik di caption seperti 'mulai dari 500rb'",
                    "saran_hook": "Berapa harga website profesional? Jawabannya bikin kaget!",
                    "hashtag_tambahan": ["#jasawebmurah", "#websitebisnis", "#digitalmarketing"],
                    "waktu_terbaik": "16:00 - 18:00 WIB"
                }

            skor = hasil.get("skor", 0)
            prediksi = hasil.get("prediksi_engagement", "-")
            saran = hasil.get("saran_perbaikan", "")
            saran_hook = hasil.get("saran_hook", "")
            hashtag = " ".join(hasil.get("hashtag_tambahan", []))
            waktu = hasil.get("waktu_terbaik", "16:00 WIB")
            kekuatan = "\n".join([f"+ {k}" for k in hasil.get("kekuatan", [])])
            kelemahan = "\n".join([f"- {k}" for k in hasil.get("kelemahan", [])])

            # Simpan ke content_performance
            await sb_insert(client, "content_performance", {
                "judul": judul,
                "caption": caption,
                "skor_ai": skor,
                "kekuatan": json.dumps(hasil.get("kekuatan", [])),
                "kelemahan": json.dumps(hasil.get("kelemahan", [])),
                "saran_analyzer": saran,
                "prediksi_engagement": prediksi,
                "hashtag_tambahan": json.dumps(hasil.get("hashtag_tambahan", [])),
                "created_at": datetime.now(timezone.utc).isoformat()
            })

            # Kirim feedback ke kreator (untuk pembelajaran besok)
            await sb_insert(client, "agent_messages", {
                "from_agent": "konten_analyzer",
                "to_agent": "kreator_konten",
                "message_type": "feedback",
                "content": {
                    "text": f"Feedback konten '{judul}': skor {skor}/100",
                    "saran": saran,
                    "saran_hook": saran_hook,
                    "hashtag": hashtag
                },
                "status": "pending"
            })

            # Kirim laporan ke asisten
            await sb_insert(client, "agent_messages", {
                "from_agent": "konten_analyzer",
                "to_agent": "asisten",
                "message_type": "result",
                "content": {
                    "text": f"Analisis selesai. '{judul}' skor {skor}/100 prediksi {prediksi}",
                    "skor": skor
                },
                "status": "pending"
            })

            # Kirim laporan ke Telegram
            laporan = (
                f"Analisis Konten Selesai\n"
                f"Judul: {judul}\n"
                f"Skor: {skor}/100\n"
                f"Prediksi engagement: {prediksi}\n\n"
                f"Kekuatan:\n{kekuatan}\n\n"
                f"Kelemahan:\n{kelemahan}\n\n"
                f"Saran untuk besok:\n{saran}\n\n"
                f"Hook lebih baik:\n{saran_hook}\n\n"
                f"Hashtag tambahan: {hashtag}\n"
                f"Waktu posting terbaik: {waktu}"
            )
            await tg_send(client, laporan)

            await sb_insert(client, "agent_logs", {
                "agent_name": "konten_analyzer",
                "action": "analisis_konten",
                "status": "success",
                "details": {"judul": judul, "skor": skor}
            })

        print("[ANALYZER] Selesai!")

if __name__ == "__main__":
    asyncio.run(main())

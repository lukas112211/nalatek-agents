import os
import httpx
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

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

# ── SUPABASE ─────────────────────────────────────────────

async def sb_insert(client, table, data):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    r = await client.post(url, headers={**SB_HEADERS, "Prefer": "return=minimal"}, json=data)
    return r.status_code in (200, 201)

async def sb_get(client, table, params=None):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    r = await client.get(url, headers=SB_HEADERS, params=params or {})
    return r.json() if r.status_code == 200 else []

# ── TELEGRAM ─────────────────────────────────────────────

async def tg_send_text(client, text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    r = await client.post(url, json={"chat_id": CHAT_ID, "text": text})
    print(f"[TG TEXT] ok={r.json().get('ok')} | {text[:50]}")

async def tg_send_photo(client, photo_path, caption=""):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    with open(photo_path, "rb") as f:
        files = {"photo": (Path(photo_path).name, f, "image/jpeg")}
        data = {"chat_id": CHAT_ID, "caption": caption[:1024]}
        r = await client.post(url, data=data, files=files, timeout=60)
    result = r.json()
    print(f"[TG PHOTO] ok={result.get('ok')}")
    return result.get("ok", False)

async def tg_send_video(client, video_path, caption=""):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo"
    with open(video_path, "rb") as f:
        files = {"video": (Path(video_path).name, f, "video/mp4")}
        data = {"chat_id": CHAT_ID, "caption": caption[:1024], "supports_streaming": "true"}
        r = await client.post(url, data=data, files=files, timeout=120)
    result = r.json()
    print(f"[TG VIDEO] ok={result.get('ok')}")
    return result.get("ok", False)

async def tg_send_document(client, file_path, caption=""):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
    with open(file_path, "rb") as f:
        files = {"document": (Path(file_path).name, f, "application/octet-stream")}
        data = {"chat_id": CHAT_ID, "caption": caption[:1024]}
        r = await client.post(url, data=data, files=files, timeout=120)
    result = r.json()
    print(f"[TG DOC] ok={result.get('ok')}")
    return result.get("ok", False)

# ── AI ───────────────────────────────────────────────────

async def ask_ai(client, prompt):
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://nalatek.gt.tc",
        "X-Title": "Nalatek Agent"
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

# ── GENERATE GAMBAR ───────────────────────────────────────

async def generate_image(client, prompt_en, filename):
    prompt_encoded = prompt_en.replace(" ", "%20").replace(",", "%2C").replace("(", "").replace(")", "")
    url = f"https://image.pollinations.ai/prompt/{prompt_encoded}?width=1080&height=1080&nologo=true&enhance=true&seed={datetime.now().microsecond}"
    print(f"[IMAGE] Generating...")
    try:
        r = await client.get(url, timeout=90, follow_redirects=True)
        if r.status_code == 200 and len(r.content) > 5000:
            path = f"/tmp/{filename}"
            with open(path, "wb") as f:
                f.write(r.content)
            print(f"[IMAGE] OK: {len(r.content)} bytes")
            return path
        print(f"[IMAGE] Failed: {r.status_code} size={len(r.content)}")
        return None
    except Exception as e:
        print(f"[IMAGE] Error: {e}")
        return None

# ── GENERATE VIDEO ────────────────────────────────────────

def create_video(image_path, caption_text, hook_text, output_path):
    try:
        from moviepy.editor import ImageClip, TextClip, CompositeVideoClip
        from PIL import Image
        import numpy as np

        img = Image.open(image_path).convert("RGB").resize((1080, 1080))
        arr = np.array(img)
        clip = ImageClip(arr).set_duration(15)

        clips = [clip]

        # Hook teks di atas
        try:
            hook_clip = TextClip(
                hook_text[:60],
                fontsize=42,
                color="white",
                stroke_color="black",
                stroke_width=2,
                size=(980, None),
                method="caption"
            ).set_position(("center", 80)).set_duration(15)
            clips.append(hook_clip)
        except Exception as e:
            print(f"[VIDEO] Hook text error: {e}")

        # Caption di bawah
        try:
            cap_short = caption_text[:80]
            cap_clip = TextClip(
                cap_short,
                fontsize=36,
                color="white",
                stroke_color="black",
                stroke_width=2,
                size=(980, None),
                method="caption"
            ).set_position(("center", 870)).set_duration(15)
            clips.append(cap_clip)
        except Exception as e:
            print(f"[VIDEO] Caption text error: {e}")

        # Watermark
        try:
            wm = TextClip(
                "nalatek.gt.tc",
                fontsize=26,
                color="white",
                stroke_color="black",
                stroke_width=1
            ).set_position((20, 20)).set_duration(15)
            clips.append(wm)
        except Exception as e:
            print(f"[VIDEO] Watermark error: {e}")

        final = CompositeVideoClip(clips)
        final.write_videofile(
            output_path, fps=24, codec="libx264",
            audio=False, verbose=False, logger=None,
            ffmpeg_params=["-crf", "28"]
        )
        print(f"[VIDEO] Created: {output_path}")
        return output_path
    except Exception as e:
        print(f"[VIDEO] Error: {e}")
        return None

# ── AMBIL KONTEKS ─────────────────────────────────────────

async def get_context(client):
    insights = await sb_get(client, "market_insights", {
        "order": "created_at.desc", "limit": "3"
    })
    keywords = ", ".join([i.get("keyword", "") for i in insights]) if insights else "jasa pembuatan website"

    feedback = await sb_get(client, "content_performance", {
        "order": "created_at.desc", "limit": "3"
    })
    feedback_str = "Belum ada data sebelumnya."
    if feedback:
        lines = []
        for f in feedback:
            lines.append(f"- '{f.get('judul','?')}' skor={f.get('skor_ai',0)} saran={f.get('saran_analyzer','')[:80]}")
        feedback_str = "\n".join(lines)

    return keywords, feedback_str

# ── MAIN ──────────────────────────────────────────────────

async def main():
    print("[KREATOR KONTEN] Mulai...")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    async with httpx.AsyncClient(timeout=120) as client:

        # 1. Ambil konteks
        keywords, feedback = await get_context(client)
        print(f"[CTX] keywords={keywords[:60]}")

        # 2. Generate ide konten
        prompt_ide = f"""Kamu adalah kreator konten TikTok dan Instagram untuk bisnis jasa web development bernama Nalatek di Indonesia.

Keyword trending hari ini: {keywords}

Performa konten sebelumnya:
{feedback}

Buat 1 ide konten hari ini. Jawab HANYA dengan JSON ini:
{{
  "judul": "judul konten singkat menarik",
  "caption": "caption Instagram/TikTok max 150 kata dengan emoji dan hashtag #jasawebsite #nalatek #webdeveloper",
  "prompt_gambar": "english description for AI image: modern tech web design, vibrant professional, Indonesian business, clean UI mockup on devices",
  "hook": "kalimat pembuka video yang menarik dalam bahasa Indonesia, max 10 kata",
  "tips_posting": "satu tips posting hari ini untuk meningkatkan engagement"
}}"""

        print("[AI] Generate ide...")
        raw = await ask_ai(client, prompt_ide)
        print(f"[AI] {raw[:150]}")

        # Parse JSON
        try:
            clean = raw.strip()
            if "```json" in clean:
                clean = clean.split("```json")[1].split("```")[0].strip()
            elif "```" in clean:
                clean = clean.split("```")[1].split("```")[0].strip()
            ide = json.loads(clean)
        except Exception as e:
            print(f"[PARSE] Error {e}, pakai default")
            ide = {
                "judul": "Website Profesional untuk UMKM Indonesia",
                "caption": "Mau bisnis kamu makin dipercaya? Mulai dari website profesional! Nalatek siap bantu kamu dari nol. DM sekarang! #jasawebsite #webdeveloper #nalatek #umkm #bisnisdigital",
                "prompt_gambar": "modern professional website on laptop and phone screen, clean minimal design, blue white color, Indonesian business, tech startup",
                "hook": "Website bisnismu masih jelek? Ini solusinya!",
                "tips_posting": "Posting sore hari antara jam 16-18 untuk engagement terbaik"
            }

        judul   = ide.get("judul", "Konten Nalatek")
        caption = ide.get("caption", "")
        hook    = ide.get("hook", "")
        tips    = ide.get("tips_posting", "")
        prompt_img = ide.get("prompt_gambar", "modern web design professional")

        print(f"[IDE] {judul}")

        # 3. Generate gambar
        await tg_send_text(client, f"Sedang membuat konten hari ini...\nJudul: {judul}")
        img_path = await generate_image(client, prompt_img, f"konten_{ts}.jpg")

        # 4. Buat video
        video_path = None
        if img_path:
            video_path = create_video(
                img_path, caption, hook,
                f"/tmp/video_{ts}.mp4"
            )

        # 5. Kirim ke Telegram
        full_caption = (
            f"KONTEN HARI INI - {datetime.now().strftime('%d %b %Y')}\n"
            f"Judul: {judul}\n\n"
            f"Hook: {hook}\n\n"
            f"Caption siap pakai:\n{caption}\n\n"
            f"Tips: {tips}"
        )

        if img_path:
            await tg_send_photo(client, img_path, caption=f"GAMBAR - {judul}\n\nCaption:\n{caption[:800]}")
        else:
            await tg_send_text(client, "Gagal generate gambar, coba lagi nanti.")

        if video_path:
            await tg_send_video(client, video_path, caption=f"VIDEO - {judul}\n\nHook: {hook}")
        else:
            await tg_send_text(client, "Video gagal dibuat (mungkin imagemagick bermasalah di server), gambar sudah dikirim.")

        # Kirim caption sebagai pesan teks terpisah supaya mudah dicopy
        await tg_send_text(client, f"CAPTION SIAP COPY-PASTE:\n\n{caption}\n\nTips hari ini: {tips}")

        # 6. Simpan ke Supabase
        await sb_insert(client, "content_queue", {
            "content_type": "post",
            "platform": "instagram",
            "caption": caption,
            "media_url": "",
            "status": "draft",
            "performance_data": {
                "judul": judul,
                "hook": hook,
                "tips": tips,
                "keywords": keywords,
                "generated_at": ts
            }
        })

        # 7. Kirim ke analyzer
        await sb_insert(client, "agent_messages", {
            "from_agent": "kreator_konten",
            "to_agent": "konten_analyzer",
            "message_type": "task",
            "content": {
                "text": f"Konten baru: {judul}",
                "judul": judul,
                "caption": caption,
                "hook": hook,
                "keywords": keywords
            },
            "status": "pending"
        })

        # 8. Log
        await sb_insert(client, "agent_logs", {
            "agent_name": "kreator_konten",
            "action": "buat_konten_harian",
            "status": "success",
            "details": {
                "judul": judul,
                "gambar": "ok" if img_path else "gagal",
                "video": "ok" if video_path else "gagal"
            }
        })

        print("[KREATOR KONTEN] Selesai!")

if __name__ == "__main__":
    asyncio.run(main())

import os
import asyncio
import httpx
from datetime import datetime, timezone

# ── CONFIG ──────────────────────────────────────────────
SUPABASE_URL  = os.getenv("SUPABASE_URL", "https://xayvpweeghlnyzwummky.supabase.co")
SUPABASE_KEY  = os.getenv("SUPABASE_KEY", "")
BOT_TOKEN     = os.getenv("BOT_TOKEN", "")
CHAT_ID       = os.getenv("CHAT_ID", "")
GEMINI_KEY    = os.getenv("GEMINI_KEY", "")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "300"))  # detik, default 5 menit

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

# ── SUPABASE HELPERS ─────────────────────────────────────
async def sb_get(client: httpx.AsyncClient, table: str, params: dict = None):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    r = await client.get(url, headers=HEADERS, params=params or {})
    return r.json() if r.status_code == 200 else []

async def sb_insert(client: httpx.AsyncClient, table: str, data: dict):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    r = await client.post(url, headers={**HEADERS, "Prefer": "return=minimal"}, json=data)
    return r.status_code in (200, 201)

async def sb_update(client: httpx.AsyncClient, table: str, match: dict, data: dict):
    params = {k: f"eq.{v}" for k, v in match.items()}
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    r = await client.patch(url, headers={**HEADERS, "Prefer": "return=minimal"}, params=params, json=data)
    return r.status_code in (200, 204)

# ── TELEGRAM ─────────────────────────────────────────────
async def tg_send(client: httpx.AsyncClient, text: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    await client.post(url, json={
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    })
    print(f"[TG] {text[:80]}")

# ── GEMINI AI ─────────────────────────────────────────────
async def ask_gemini(client: httpx.AsyncClient, prompt: str) -> str:
    if not GEMINI_KEY:
        return "[AI tidak aktif — set GEMINI_KEY]"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}"
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        r = await client.post(url, json=body, timeout=30)
        data = r.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        return f"[Error AI: {e}]"

# ── LOG ke Supabase ───────────────────────────────────────
async def log_action(client: httpx.AsyncClient, agent: str, action: str, status: str, details: dict = None, error: str = None):
    await sb_insert(client, "agent_logs", {
        "agent_name": agent,
        "action": action,
        "status": status,
        "details": details or {},
        "error_message": error
    })

# ── PROSES PESAN MASUK DARI AGENT LAIN ───────────────────
async def process_messages(client: httpx.AsyncClient):
    msgs = await sb_get(client, "agent_messages", {
        "to_agent": "eq.asisten",
        "status": "eq.pending",
        "order": "created_at.asc",
        "limit": "10"
    })
    if not msgs:
        return

    print(f"[MSG] Ada {len(msgs)} pesan masuk")
    for msg in msgs:
        content = msg.get("content", {})
        from_agent = msg.get("from_agent", "unknown")
        msg_type = msg.get("message_type", "info")

        # Tandai sudah dibaca
        await sb_update(client, "agent_messages", {"id": msg["id"]}, {
            "status": "read",
            "read_at": datetime.now(timezone.utc).isoformat()
        })

        # Forward ke Telegram
        notif = (
            f"📨 *Pesan dari agent {from_agent.upper()}*\n"
            f"Tipe: `{msg_type}`\n"
            f"Isi: {content.get('text', str(content))[:300]}"
        )
        await tg_send(client, notif)
        await log_action(client, "asisten", f"proses_pesan_dari_{from_agent}", "success", {"msg_id": msg["id"]})

# ── CEK TASK SELESAI ──────────────────────────────────────
async def check_completed_tasks(client: httpx.AsyncClient):
    tasks = await sb_get(client, "agent_tasks", {
        "status": "eq.done",
        "order": "completed_at.desc",
        "limit": "5"
    })
    if not tasks:
        return

    for task in tasks:
        output = task.get("output_data", {})
        notif = (
            f"✅ *Task selesai!*\n"
            f"Agent: `{task.get('assigned_to', '-')}`\n"
            f"Judul: {task.get('title', '-')}\n"
            f"Hasil: {str(output.get('summary', output))[:200]}"
        )
        await tg_send(client, notif)
        # Tandai sudah dilaporkan
        await sb_update(client, "agent_tasks", {"id": task["id"]}, {"status": "reported"})

# ── LAPORAN HARIAN ────────────────────────────────────────
async def daily_report(client: httpx.AsyncClient):
    now = datetime.now(timezone.utc)
    if now.hour != 8:  # Kirim laporan jam 8 pagi UTC (jam 15 WIB)
        return

    # Hitung statistik
    tasks_done  = await sb_get(client, "agent_tasks",   {"status": "eq.reported"})
    tasks_fail  = await sb_get(client, "agent_tasks",   {"status": "eq.failed"})
    content_q   = await sb_get(client, "content_queue", {"status": "eq.draft"})
    insights    = await sb_get(client, "market_insights", {"order": "created_at.desc", "limit": "3"})
    projects    = await sb_get(client, "client_projects", {"status": "neq.done"})

    top_keywords = ", ".join([i.get("keyword", "-") for i in insights]) if insights else "Belum ada"

    report = (
        f"📊 *Laporan Harian Nalatek*\n"
        f"🗓 {now.strftime('%d %b %Y')}\n\n"
        f"✅ Task selesai  : {len(tasks_done)}\n"
        f"❌ Task gagal    : {len(tasks_fail)}\n"
        f"📝 Konten draft  : {len(content_q)}\n"
        f"🏗 Project aktif : {len(projects)}\n\n"
        f"🔥 Trending keywords: {top_keywords}\n\n"
        f"_Dikirim otomatis oleh Asisten AI Nalatek_"
    )
    await tg_send(client, report)
    await log_action(client, "asisten", "laporan_harian", "success")

# ── MAIN LOOP ─────────────────────────────────────────────
async def main():
    print("🤖 Nalatek Asisten AI mulai berjalan...")
    async with httpx.AsyncClient(timeout=20) as client:
        # Kirim notifikasi startup
        await tg_send(client, (
            "🚀 *Nalatek Asisten AI aktif!*\n"
            "Semua agent siap beroperasi.\n"
            f"_Polling setiap {POLL_INTERVAL} detik_"
        ))
        await log_action(client, "asisten", "startup", "success")

        loop_count = 0
        while True:
            try:
                print(f"\n[LOOP #{loop_count}] {datetime.now().strftime('%H:%M:%S')}")
                await process_messages(client)
                await check_completed_tasks(client)
                await daily_report(client)
                loop_count += 1
            except Exception as e:
                err = str(e)
                print(f"[ERROR] {err}")
                await log_action(client, "asisten", "loop_error", "error", error=err)

            await asyncio.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())

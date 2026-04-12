
Salin

import os
import asyncio
import httpx
from datetime import datetime, timezone
 
SUPABASE_URL  = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY  = os.getenv("SUPABASE_KEY", "")
BOT_TOKEN     = os.getenv("BOT_TOKEN", "")
CHAT_ID       = os.getenv("CHAT_ID", "")
GEMINI_KEY    = os.getenv("GEMINI_KEY", "")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "300"))
 
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}
 
async def sb_get(client, table, params=None):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    r = await client.get(url, headers=HEADERS, params=params or {})
    return r.json() if r.status_code == 200 else []
 
async def sb_insert(client, table, data):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    r = await client.post(url, headers={**HEADERS, "Prefer": "return=minimal"}, json=data)
    return r.status_code in (200, 201)
 
async def sb_update(client, table, match, data):
    params = {k: f"eq.{v}" for k, v in match.items()}
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    r = await client.patch(url, headers={**HEADERS, "Prefer": "return=minimal"}, params=params, json=data)
    return r.status_code in (200, 204)
 
async def tg_send(client, text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    r = await client.post(url, json={
        "chat_id": CHAT_ID,
        "text": text
    })
    result = r.json()
    print(f"[TG] ok={result.get('ok')} | {text[:60]}")
    if not result.get("ok"):
        print(f"[TG ERROR] {result}")
 
async def ask_gemini(client, prompt):
    if not GEMINI_KEY:
        return "[AI tidak aktif]"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}"
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        r = await client.post(url, json=body, timeout=30)
        data = r.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        return f"[Error AI: {e}]"
 
async def log_action(client, agent, action, status, details=None, error=None):
    try:
        await sb_insert(client, "agent_logs", {
            "agent_name": agent,
            "action": action,
            "status": status,
            "details": details or {},
            "error_message": error
        })
    except Exception as e:
        print(f"[LOG ERROR] {e}")
 
async def process_messages(client):
    msgs = await sb_get(client, "agent_messages", {
        "to_agent": "eq.asisten",
        "status": "eq.pending",
        "order": "created_at.asc",
        "limit": "10"
    })
    if not msgs:
        return
    print(f"[MSG] {len(msgs)} pesan masuk")
    for msg in msgs:
        content = msg.get("content", {})
        from_agent = msg.get("from_agent", "unknown")
        msg_type = msg.get("message_type", "info")
        await sb_update(client, "agent_messages", {"id": msg["id"]}, {
            "status": "read",
            "read_at": datetime.now(timezone.utc).isoformat()
        })
        text = (
            f"Pesan dari agent {from_agent.upper()}\n"
            f"Tipe: {msg_type}\n"
            f"Isi: {content.get('text', str(content))[:300]}"
        )
        await tg_send(client, text)
        await log_action(client, "asisten", f"proses_pesan_{from_agent}", "success")
 
async def check_completed_tasks(client):
    tasks = await sb_get(client, "agent_tasks", {
        "status": "eq.done",
        "order": "completed_at.desc",
        "limit": "5"
    })
    for task in tasks:
        output = task.get("output_data", {})
        text = (
            f"Task selesai!\n"
            f"Agent: {task.get('assigned_to', '-')}\n"
            f"Judul: {task.get('title', '-')}\n"
            f"Hasil: {str(output.get('summary', output))[:200]}"
        )
        await tg_send(client, text)
        await sb_update(client, "agent_tasks", {"id": task["id"]}, {"status": "reported"})
 
async def daily_report(client):
    now = datetime.now(timezone.utc)
    if now.hour != 8:
        return
    tasks_done = await sb_get(client, "agent_tasks", {"status": "eq.reported"})
    tasks_fail = await sb_get(client, "agent_tasks", {"status": "eq.failed"})
    content_q  = await sb_get(client, "content_queue", {"status": "eq.draft"})
    insights   = await sb_get(client, "market_insights", {"order": "created_at.desc", "limit": "3"})
    projects   = await sb_get(client, "client_projects", {"status": "neq.done"})
    keywords   = ", ".join([i.get("keyword", "-") for i in insights]) if insights else "Belum ada"
    text = (
        f"Laporan Harian Nalatek\n"
        f"{now.strftime('%d %b %Y')}\n\n"
        f"Task selesai  : {len(tasks_done)}\n"
        f"Task gagal    : {len(tasks_fail)}\n"
        f"Konten draft  : {len(content_q)}\n"
        f"Project aktif : {len(projects)}\n\n"
        f"Trending: {keywords}"
    )
    await tg_send(client, text)
    await log_action(client, "asisten", "laporan_harian", "success")
 
async def main():
    print("Nalatek Asisten AI mulai berjalan...")
    print(f"SUPABASE_URL  : {SUPABASE_URL[:30]}...")
    print(f"SUPABASE_KEY  : {SUPABASE_KEY[:20]}...")
    print(f"BOT_TOKEN     : {BOT_TOKEN[:20]}...")
    print(f"CHAT_ID       : {CHAT_ID}")
 
    async with httpx.AsyncClient(timeout=20) as client:
        await tg_send(client, (
            "Nalatek Asisten AI aktif!\n"
            "Semua agent siap beroperasi.\n"
            f"Polling setiap {POLL_INTERVAL} detik."
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
 

            await asyncio.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())

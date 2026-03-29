# LifeLens Backend

FastAPI + **Supabase Python Client** for auth and alerts.

## Setup

1. Create a project on [Supabase](https://supabase.com), open **SQL Editor**, and run the SQL in [`schema.sql`](schema.sql) (creates `users` and `alerts` tables).

2. In Supabase: go to **Project Settings → API** and copy:
   - **Project URL** → `SUPABASE_URL`
   - **Service Role (secret) key** → `SUPABASE_SECRET_KEY`

3. Local env:

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your SUPABASE_URL, SUPABASE_SECRET_KEY, and JWT_SECRET
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Your `.env` file

```env
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_SECRET_KEY=eyJ...   # Service Role key from Supabase Dashboard → Settings → API
JWT_SECRET=a-long-random-string-at-least-32-chars
```

> **Generate a JWT secret:**
> ```bash
> python -c "import secrets; print(secrets.token_hex(32))"
> ```

## Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/auth/register` | No | Create account with role (`caregiver` or `resident`) |
| POST | `/auth/login` | No | Returns JWT + user profile including role |
| GET | `/alerts` | JWT | Alerts for last 24 h. **Residents:** own alerts. **Caregivers:** pass `?resident_username=` (wearer’s login). |
| POST | `/alerts` | No | Create alert (called by relay pipeline) |
| DELETE | `/alerts/{id}` | JWT | Dismiss. Caregivers also pass `?resident_username=`. |
| GET | `/health` | No | Health check |

## Roles

- **caregiver** — Caregiver app: reports + video URLs for a monitored `resident_username`.
- **resident** — Resident app: glasses + stream; alerts use this account’s `username` as `resident_username`.

## Alert retention

The API only **returns** alerts from the last **24 hours**. Old rows can remain in Postgres until you add a scheduled `delete` (see comment in `schema.sql`) or a Supabase **Database → Cron** job.

## Sending alerts from the pipeline

When `analyze_video.py` / `segment_receiver.py` detects a fall, POST to:

```
POST http://<backend-host>:8000/alerts
Content-Type: application/json

{
  "resident_username": "alice",
  "message": "Possible fall detected in kitchen",
  "severity": "high",
  "video_url": "http://storage-server/clips/clip_042.mp4"
}
```

## Security notes

- `SUPABASE_SECRET_KEY` is the **service role** key — it bypasses Row Level Security (RLS). Never expose it to frontend/mobile clients.
- For mobile apps, use the **anon key** directly with Supabase Auth if you want RLS enforcement.
- Tokens are **Supabase Auth** session JWTs returned by `/auth/login` and `/auth/register`.

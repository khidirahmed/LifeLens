-- LifeLens schema — run in Supabase SQL Editor → New query → Run
--
-- NOTE: public.users extends Supabase's built-in auth.users table.
--       Passwords are managed entirely by Supabase Auth — no password_hash column needed.
--       The 'id' column here matches auth.users.id (set automatically on register).

-- ── Users profile table ───────────────────────────────────────────────────────
create table if not exists public.users (
  id        uuid primary key references auth.users (id) on delete cascade,
  username  text not null unique,
  email     text not null unique,
  full_name text,
  role      text not null check (role in ('caregiver', 'resident')),
  created_at timestamptz not null default now()
);

create index if not exists idx_users_username on public.users (username);
create index if not exists idx_users_email    on public.users (email);

-- ── Alerts table ──────────────────────────────────────────────────────────────
create table if not exists public.alerts (
  id                 uuid primary key default gen_random_uuid(),
  resident_username  text        not null,
  message            text        not null,
  severity           text        not null default 'high',
  video_url          text,
  thumbnail_url      text,
  event_at           timestamptz,
  created_at         timestamptz not null default now(),
  dismissed          boolean     not null default false
);

create index if not exists idx_alerts_resident_created
  on public.alerts (resident_username, created_at desc)
  where dismissed = false;

-- ── Row Level Security ────────────────────────────────────────────────────────
-- The backend uses the service role key which bypasses RLS automatically.
-- Enable RLS on both tables so the anon key cannot read raw data directly
-- from the client (extra safety layer).

alter table public.users  enable row level security;
alter table public.alerts enable row level security;

-- Service role bypasses RLS — no policies needed for backend access.
-- Add client-facing policies here if you ever expose Supabase directly to mobile:
-- create policy "users can read own profile"
--   on public.users for select using (auth.uid() = id);

-- ── Optional: purge alerts older than 24 h ───────────────────────────────────
-- Enable pg_cron in Supabase (Database → Extensions → pg_cron), then:
-- select cron.schedule('purge-old-alerts', '0 * * * *',
--   $$ delete from public.alerts where created_at < now() - interval '24 hours' $$);

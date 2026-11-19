-- PC Preț: database schema for Supabase (free tier).
-- Run once in Supabase Dashboard -> SQL Editor.
-- Every table has Row Level Security: a signed-in user can only see and change
-- their own rows. Status changes are done by the site owner in the dashboard.

create table if not exists public.offers (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  created_at timestamptz not null default now(),
  config jsonb not null,          -- chosen parts, condition, country
  estimate_ron integer not null,  -- estimate shown at save time
  snapshot_date timestamptz       -- which price snapshot it was based on
);

create table if not exists public.sell_requests (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  created_at timestamptz not null default now(),
  kind text not null check (kind in ('sell','contact')),
  status text not null default 'trimis' check (status in ('trimis','contactat','ridicat')),
  config jsonb not null,
  estimate_ron integer,
  snapshot_date timestamptz,
  name text not null check (char_length(name) <= 100),
  phone text not null check (char_length(phone) <= 30),
  country text check (country in ('RO','BG','HU')),
  city text check (char_length(city) <= 80),
  address text check (char_length(address) <= 300),
  courier text check (char_length(courier) <= 30),
  call_when text check (char_length(call_when) <= 100),
  notes text check (char_length(notes) <= 500)
);

alter table public.offers enable row level security;
alter table public.sell_requests enable row level security;

create policy "own offers select" on public.offers for select using (auth.uid() = user_id);
create policy "own offers insert" on public.offers for insert with check (auth.uid() = user_id);
create policy "own offers delete" on public.offers for delete using (auth.uid() = user_id);

create policy "own requests select" on public.sell_requests for select using (auth.uid() = user_id);
-- users can only create requests with the initial status
create policy "own requests insert" on public.sell_requests for insert
  with check (auth.uid() = user_id and status = 'trimis');
create policy "own requests delete" on public.sell_requests for delete using (auth.uid() = user_id);
-- no update policy: only the owner (service role / dashboard) changes status

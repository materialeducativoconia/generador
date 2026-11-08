-- A promotional video's MP4, rendered in the admin's browser and kept, so it is downloaded again without rendering.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('marketing', 'marketing', false, 209715200, array['video/mp4', 'video/webm'])
on conflict (id) do nothing;

alter table public.marketing_videos add column if not exists mp4_key text;
alter table public.marketing_videos add column if not exists rendered_at timestamptz;

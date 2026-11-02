-- The illustration style the user picked when creating the tome (app.house_styles); null lets the Designer choose.
alter table public.series add column house_style text;

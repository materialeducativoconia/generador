-- The platform's first administrator; more are named from the admin panel.
update public.profiles set platform_role = 'admin' where lower(email) = 'luis.varsa.pm@gmail.com';

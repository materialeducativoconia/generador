-- Library art from before the aspect column: tome pictures are portrait unless shown at half size, and the earlier
-- library is line art at full page, so portrait.
update public.assets set aspect = '3:4' where library and aspect is null;

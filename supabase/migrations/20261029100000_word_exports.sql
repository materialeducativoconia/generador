-- Word exports: the exports bucket also takes .docx files.
update storage.buckets
   set allowed_mime_types = array['application/pdf',
                                  'application/vnd.openxmlformats-officedocument.wordprocessingml.document']
 where id = 'exports';

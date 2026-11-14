-- The videos' voiceover (Gemini TTS through OpenRouter) is kept beside them, one WAV per scene.
update storage.buckets set allowed_mime_types = array['video/mp4', 'video/webm', 'image/png', 'image/jpeg', 'image/webp', 'audio/wav']
 where id = 'marketing';

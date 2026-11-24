BEGIN;
CREATE TABLE music.song_lyrics (
    song_id INTEGER PRIMARY KEY REFERENCES music.song(song_id),
    original_lrc TEXT NOT NULL,
    translated_lrc TEXT,
    original_name VARCHAR(255) NOT NULL,
    uploaded_by INTEGER NOT NULL REFERENCES music.app_user(user_id),
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
ALTER TABLE music.song_lyrics OWNER TO jp;
GRANT SELECT, INSERT, UPDATE, DELETE ON music.song_lyrics TO music_web;
COMMIT;

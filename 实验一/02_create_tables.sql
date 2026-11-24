-- 在 music_platform 数据库中，以 jp 执行。
-- 按分组逐段执行并截图；遇到错误先停止，不重复执行已成功的建表语句。
-- 显式使用 music schema，后续脚本也使用限定表名，避免 search_path 造成混淆。

-- A：平台用户与曲库
CREATE SCHEMA music AUTHORIZATION jp;

CREATE TABLE music.app_user (
    user_id INTEGER PRIMARY KEY,
    username VARCHAR(50) NOT NULL,
    nickname VARCHAR(50) NOT NULL,
    bio VARCHAR(300),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_user_username UNIQUE (username)
);

CREATE TABLE music.artist (
    artist_id INTEGER PRIMARY KEY,
    artist_name VARCHAR(100) NOT NULL,
    artist_type VARCHAR(10) NOT NULL,
    CONSTRAINT ck_artist_type CHECK (artist_type IN ('solo', 'band'))
);

CREATE TABLE music.album (
    album_id INTEGER PRIMARY KEY,
    album_title VARCHAR(150) NOT NULL,
    release_date DATE,
    description VARCHAR(500)
);

CREATE TABLE music.song (
    song_id INTEGER PRIMARY KEY,
    song_title VARCHAR(150) NOT NULL,
    album_id INTEGER,
    duration_seconds INTEGER NOT NULL,
    genre VARCHAR(40) NOT NULL DEFAULT 'Other',
    CONSTRAINT fk_song_album FOREIGN KEY (album_id)
        REFERENCES music.album (album_id),
    CONSTRAINT ck_song_duration CHECK (duration_seconds > 0)
);

CREATE TABLE music.song_artist (
    song_id INTEGER NOT NULL,
    artist_id INTEGER NOT NULL,
    CONSTRAINT pk_song_artist PRIMARY KEY (song_id, artist_id),
    CONSTRAINT fk_sa_song FOREIGN KEY (song_id)
        REFERENCES music.song (song_id),
    CONSTRAINT fk_sa_artist FOREIGN KEY (artist_id)
        REFERENCES music.artist (artist_id)
);

-- B：歌单与收录关系
  CREATE TABLE music.playlist (
      playlist_id INTEGER PRIMARY KEY,
      creator_id INTEGER NOT NULL,
      playlist_name VARCHAR(100) NOT NULL,
      description VARCHAR(500),
      visibility VARCHAR(10) NOT NULL DEFAULT 'public',
      created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
      CONSTRAINT fk_playlist_creator FOREIGN KEY (creator_id)
          REFERENCES music.app_user (user_id),
      CONSTRAINT ck_playlist_visibility CHECK (visibility IN ('public', 'private'))
  );

  CREATE TABLE music.playlist_song (
      playlist_id INTEGER NOT NULL,
      song_id INTEGER NOT NULL,
      position_no INTEGER NOT NULL,
      added_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
      CONSTRAINT pk_playlist_song PRIMARY KEY (playlist_id, song_id),
      CONSTRAINT uq_playlist_position UNIQUE (playlist_id, position_no),
      CONSTRAINT ck_playlist_position CHECK (position_no > 0),
      CONSTRAINT fk_ps_playlist FOREIGN KEY (playlist_id)
          REFERENCES music.playlist (playlist_id),
      CONSTRAINT fk_ps_song FOREIGN KEY (song_id)
          REFERENCES music.song (song_id)
  );

-- C：偏好与收藏
CREATE TABLE music.song_like (
    user_id INTEGER NOT NULL,
    song_id INTEGER NOT NULL,
    liked_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_song_like PRIMARY KEY (user_id, song_id),
    CONSTRAINT fk_sl_user FOREIGN KEY (user_id)
        REFERENCES music.app_user (user_id),
    CONSTRAINT fk_sl_song FOREIGN KEY (song_id)
        REFERENCES music.song (song_id)
);

CREATE TABLE music.playlist_favorite (
    user_id INTEGER NOT NULL,
    playlist_id INTEGER NOT NULL,
    favorited_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_playlist_favorite PRIMARY KEY (user_id, playlist_id),
    CONSTRAINT fk_pf_user FOREIGN KEY (user_id)
        REFERENCES music.app_user (user_id),
    CONSTRAINT fk_pf_playlist FOREIGN KEY (playlist_id)
        REFERENCES music.playlist (playlist_id)
);

-- D：核验九张表
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema = 'music' AND table_type = 'BASE TABLE'
ORDER BY table_name;

-- 以下为 gsql 元命令，单独执行，末尾不加分号。
-- \d music.song
-- \d music.playlist_song

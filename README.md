# Kaho

A NoneBot2-based bot for Link! Like! LoveLive! (Hasu no sora Jogakuin School Idol Club). This bot provides features for searching and displaying various game-related information using high-quality image generation.

## Features

- Card Search: Detailed statistics, skills, evolution materials, and high-quality card illustrations.
- Member Information: Comprehensive profiles including birthdays, hobbies, favorite foods, and available costumes.
- Music Database: Information on songs, stage effects, mastery levels, and chart details.
- Comic Viewer: Access to in-game 4-koma comics with character-based filtering.
- Data Management: Tools for maintaining and updating the local game database.

## Requirements

- Python 3.9 or higher.
- A self-hosted [AstrBot Text2Image Service](https://github.com/AstrBotDevs/astrbot-t2i-service) for high-quality HTML rendering (optional but recommended). For more information, see [this page](https://docs.astrbot.app/en/others/self-host-t2i.html).

## Installation and Usage

1. Clone the repository.
2. `uv sync`
3. Create a `.env` file and configure your NoneBot2 and game API environment variables.
4. Ensure the required directories are populated with the game data files.
5. Set up the asset directories (e.g., exports, assets) for images and icons.
6. Set the `T2I_SERVICE_URL` in your environment variables.
7. Run the bot using `uv run python bot.py`.

## Local Tests

- Lint: `uv run ruff check .`
- Fast tests (no real masterdata required): `uv run python scripts/run_fast_tests.py`
- Realdata tests (uses sampled real masterdata): `uv run python scripts/run_realdata_tests.py`
- Realdata tests with custom path: `uv run python scripts/run_realdata_tests.py <masterdata_path>`

## Commands

- `/list`: Display a list of characters.
- `/card [ID]`: Search for specific card details.
- `/find [Name/ID]`: Show all cards of a specific character.
- `/search [Query]`: Search for cards by keywords.
- `/chara [Name/ID]`: Display member profile and information.
- `/music [Title/ID]`: Search for song and stage details.
- `/comic [Query]`: Browse and search for in-game comics.
- `/live`: Generate the current With×MEETS/Fes×LIVE info image.
- `/live_detail [Index] [--spoiler]`: Generate a detail image for the indexed live entry.
- `/dbrebuild`: Rebuild the local game database (Superuser only).
- `/update with_live`: Refresh archive home snapshot and cache the latest archive detail (Superuser only).

## Drawing API Configuration

Optional external drawing service ([Kozue](https://github.com/bywhite0/EbyptEshiSan)). When configured, migrated commands render via the drawing API and automatically fall back to the legacy T2I pipeline on failure.

- `DRAW_API_BASE_URL`: Drawing service base URL (unset = disabled)
- `DRAW_API_TIMEOUT`: Request timeout in seconds (default: 15)
- `DRAW_API_MAX_CONNECTIONS`: Max HTTP connections (default: 10)

Currently migrated commands: `/list`.

## Game API Configuration

Required environment variables:

- `GAME_API_BASE_URL`: API base URL, ends with `/v1`
- `GAME_API_X_API_KEY`: API key

Optional environment variables:

- `GAME_API_HOST`: Host header override
- `GAME_API_UA_PREFIX`: UA prefix
- `GAME_API_DEVICE_TYPE`: Device type
- `GAME_API_USER_API_VERSION`: API version header

Credential file lookup order:

1. `LINKURA_CONFIG_PATH`
2. `cache/game_api/config.json`
3. `linkura-cli_config.json`
4. `%USERPROFILE%/.config/linkura-cli/config.json`

The service validates the current `session_token` before requests. If expired, it will call `/user/login`, update the token, and then continue.

## Live Archive Data

Post-EOS live archive metadata (398 archived lives with details) is vendored as a git submodule at `external/linkura-live-data` ([ChocoLZS/linkura-live-data — `data/`](https://github.com/ChocoLZS/linkura-live-data/tree/main/data)). Run `git submodule update --init` after cloning.

- `LIVE_ARCHIVE_DATA_DIR`: Optional override for the directory containing `archive.json` / `archive-details.json` (default: the submodule's `data/`)
- Covers are resolved locally from `cache/game_api/archive_covers/` by original UUID filename; no external requests are made.
- Comment counts are precomputed by `scripts/build_comment_counts.py` into `data/llll/comment_counts.json`.

## with_live Cache Snapshot

`/update with_live` writes to `cache/game_api/with_live.json` and keeps a backup at `cache/game_api/with_live.prev.json`.

Key fields in the snapshot:

- `updated_at` / `previous_updated_at`: latest and previous refresh timestamps
- `with_live_archive_live_home`: With Live records from `live_archive_list` (`live_type == 2`)
- `with_live_archive_trailer_home`: With Live records from `trailer_archive_list` (`live_type == 2`)
- `latest_archive`: latest candidate archive entry
- `latest_archive_detail`: detail payload from `archive/get_with_archive_data` (falls back to `latest_archive` on failure)
- `latest_archive_detail_meta`: detail source, stale flag, and fetch errors

## Special Thanks

- [linkura-cli](https://github.com/ChocoLZS/linkura-cli)

## License

This project is licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).

## Disclaimer

- This repository is an unofficial project and is not affiliated with the game operator or related rights holders.
- The repository contents are primarily intended for personal study, research, and tooling development.
- The author provides no warranty regarding correctness, completeness, long-term compatibility, or fitness for any particular purpose.
- Users are responsible for ensuring that their usage complies with local laws, platform rules, and third-party rights requirements.
- This software is provided "as is" without any warranty. Use at your own risk.

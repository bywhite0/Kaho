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
- `/dbrebuild`: Rebuild the local game database (Superuser only).
- `/update with_live`: Refresh archive home snapshot and cache the latest archive detail (Superuser only).

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

## with_live Cache Snapshot

`/update with_live` writes to `cache/game_api/with_live.json` and keeps a backup at `cache/game_api/with_live.prev.json`.

Key fields in the snapshot:

- `updated_at` / `previous_updated_at`: latest and previous refresh timestamps
- `with_live_archive_live_home`: With Live records from `live_archive_list` (`live_type == 2`)
- `with_live_archive_trailer_home`: With Live records from `trailer_archive_list` (`live_type == 2`)
- `latest_archive`: latest candidate archive entry
- `latest_archive_detail`: detail payload from `archive/get_with_archive_data` (falls back to `latest_archive` on failure)
- `latest_archive_detail_meta`: detail source, stale flag, and fetch errors

## License

This project is licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).

## Disclaimer

This project is an unofficial fan-made tool for Link! Like! LoveLive!. It is not affiliated with, endorsed by, or associated with Bandai Namco Music Live Inc., Odd No. Inc., or the Love Live! Project. All game assets, characters, and related intellectual property belong to their respective owners. This software is provided "as is" without any warranty. Use at your own risk.

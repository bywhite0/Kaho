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
2. Configure your NoneBot2 environment in `.env` or `.env.prod`.
3. Ensure the required directories are populated with the game data files.
4. Set up the asset directories (e.g., exports, assets) for images and icons.
5. Set the `T2I_SERVICE_URL` in your environment variables.
6. Run the bot using `uv run python bot.py`.

## Commands

- `/list`: Display a list of characters.
- `/card [ID]`: Search for specific card details.
- `/find [Name/ID]`: Show all cards of a specific character.
- `/search [Query]`: Search for cards by keywords.
- `/chara [Name/ID]`: Display member profile and information.
- `/music [Title/ID]`: Search for song and stage details.
- `/comic [Query]`: Browse and search for in-game comics.
- `/dbrebuild`: Rebuild the local game database (Superuser only).

## License

This project is licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).

## Disclaimer

This project is an unofficial fan-made tool for Link! Like! LoveLive!. It is not affiliated with, endorsed by, or associated with Bandai Namco Music Live Inc., Odd No. Inc., or the Love Live! Project. All game assets, characters, and related intellectual property belong to their respective owners. This software is provided "as is" without any warranty. Use at your own risk.

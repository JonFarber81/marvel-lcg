from core import *

from engine.file import FileManager
from engine.lib import Json
from engine.config import ConfigVariables

from aiohttp import web
from engine.device.web.server.server_base import GameServerBase

CATEGORY_NAME = "WEB"

DECK_FOLDERS = ConfigVariables.Folders('deck_folders')

class GameServerDeck(GameServerBase):

    # A deck name is free text: it comes from marvelcdb or from whatever the
    # player typed. Keep the characters that read well in a file name and drop
    # the rest, so a name can never walk out of the deck folder.
    @staticmethod
    def DeckFileName(name: str) -> str:
        keep = " ()[]-_.,'&+!"
        text = "".join(c for c in name if c.isalnum() or c in keep)
        text = text.strip(" .")
        return text[:100]

    async def save_deck(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception:
            return web.json_response({'error': "Invalid request"}, status=400)

        deck = data.get('deck')
        if not isinstance(deck, dict) or 'hero' not in deck:
            return web.json_response({'error': "No deck provided"}, status=400)

        file_name = self.DeckFileName(str(data.get('name') or deck.get('name') or ""))
        if not file_name:
            return web.json_response({'error': "The deck needs a name"}, status=400)

        folder = DECK_FOLDERS.value[0]
        FileManager.MakeDir(folder)
        file_path = FileManager.JoinPath(folder, f"{file_name}.json")

        if not data.get('overwrite', False) and FileManager.Exists(file_path):
            return web.json_response({'error': f"{file_name}.json already exists", 'exists': True}, status=409)

        with FileManager.OpenFile(file_path, write=True) as file:
            file.Write(Json.Dumps(deck, indent=4))

        return web.json_response({'result': "Deck saved", 'name': file_name, 'path': file_path})

    @override
    def __init__(self) -> None:
        super().__init__()
        self.AddPostSecurity('/save_deck', self.save_deck)

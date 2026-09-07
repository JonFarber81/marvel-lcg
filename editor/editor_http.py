from aiohttp import web
from urllib.parse import parse_qs

from engine.lib import Json
from engine.log import Log
from engine.network import WebServer
from engine.file import Cache
from engine.config import ConfigVariables

CATEGORY_NAME = "EDITOR"

CARDS_JSON_FILE = ConfigVariables.File('cards_json_file')

class EditorHttp(WebServer):
    def __init__(self) -> None:
        super().__init__()

        self.AddDefaultGet()

        self.AddHtmlSecurity('/', './public/editor.html')

        self.AddAwaitGetSecurity('/get_cards_json', self.handle_get_cards_json)

        self.AddAwaitGetSecurity('/{filename:.*}', self.handle_image)
        self.AddPostSecurity('/process', self.handle_post)

        self.cards_json_file = CARDS_JSON_FILE.value

    async def handle_get_cards_json(self, request: web.Request):
        data = Json.Load(self.cards_json_file)
        return web.json_response(data)

    async def handle_image(self, request: web.Request):
        # `Cache` already stands a landscape image up, and says what format the
        # bytes it hands back are in; the editor used to open every image again
        # to repeat the first half of that and then call the result a JPEG.
        image = Cache.LoadImageData(request.path)
        return web.Response(body=image.data, content_type=image.content_type)

    async def handle_post(self, request: web.Request):
        body = await request.read()
        data = parse_qs(body.decode())
        Log.Debug(CATEGORY_NAME, data)
        from editor.editor_create import DoEditor
        DoEditor(data)
        return web.Response(text=str(data))


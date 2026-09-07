from core import *

from engine.file import Cache
from engine.device.web import *

from aiohttp import web
from engine.device.web.server.server_base import GameServerBase

CATEGORY_NAME = "WEB"

class GameServerFiles(GameServerBase):

    async def handle_marvel(self, request: web.Request) -> web.StreamResponse:
        if request.query_string == '':
            return self.ReadFile('./public/main.html')
        else:
            return self.ReadFile('./public/marvel.html')

    async def handle_players_404(self, request: web.Request) -> web.StreamResponse:
        player = request.match_info.get('player')
        return web.Response(text=f"Please visiting /?p={player}", status=404)

    def ImageHeaders(self, card_id: str) -> Dict[str, str]:
        # A generated stand-in must not be cached by the browser: the real art
        # appears as soon as the asset pack is installed or the download
        # succeeds, and a year-long max-age would keep the grey box on screen.
        if Cache.IsPlaceholder(card_id):
            return {'Cache-Control': 'no-store'}
        return self.HeaderCache

    # Both image routes are awaited rather than handed to `TaskManager.ToThread`:
    # `Cache.LoadImageAsync` answers from memory without a thread at all, and
    # goes to the image pool when it has to read a file or ask a card server, so
    # a cold cache no longer occupies the executor the rest of the server shares.

    # The image is served in the format it is stored in - a set tile is a `.webp`
    # and stays one - so the content type comes from the cache entry. Both routes
    # used to answer `image/jpeg` whatever they were actually sending.

    async def handle_sets_image(self, request: web.Request) -> web.StreamResponse:
        file_path = request.path

        image = await Cache.LoadImageAsync(file_path)

        return web.Response(body=image.data, content_type=image.content_type,
                            headers=self.ImageHeaders(file_path))

    async def handle_image_request(self, request: web.Request) -> web.StreamResponse:
        # file_path = request.match_info['path']
        file_path = request.path
        file_path = file_path.split("/")[-1]

        image = await Cache.LoadImageAsync(file_path)

        self.device_manager.AddSize("Image", len(image.data))

        return web.Response(body=image.data, content_type=image.content_type,
                            headers=self.ImageHeaders(file_path))

    @override
    def __init__(self) -> None:
        super().__init__()

        self.AddDefaultGet()

        self.AddAwaitGetSecurity('/', self.handle_marvel)
        self.AddAwaitGetSecurity(r'/p={player:\d+}', self.handle_players_404)
        self.AddAwaitGetSecurity('/watch', self.handle_marvel)

        self.AddAwaitGetSecurity(r'/sets/{path:.+}', self.handle_sets_image)
        self.AddAwaitGetSecurity(r'/{path:.+}', self.handle_image_request)


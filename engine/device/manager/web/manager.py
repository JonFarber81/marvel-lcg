from core import *
from engine.config import ConfigVariables
from engine.log import Log
from engine.device import *
from engine.controller import *
from engine.device.manager.web.client import ClientManager
from engine.network.net_lib import NetLib
from engine.startup_error import StartupError

IP                  = ConfigVariables.Str('ip', "")
PORT                = ConfigVariables.Int('port', 2345)
SERVER_ADDRESSES    = ConfigVariables.ListStr('server_addresses', [
    "127.0.0.1:2345"
])
# How many ports past the asked-for one to try before giving that address up.
PORT_FALLBACK_TRIES = ConfigVariables.Int('port_fallback_tries', 10)

CATEGORY_NAME = "WEB_DEVICE_MANAGER"

class WebDeviceManager(DeviceManager):

    def __init__(self) -> None:
        from engine.device.web.server.server import GameServer

        super().__init__()

        self.client_manager = ClientManager()
        self.httpds : List[GameServer] = []

        server_addresses    = SERVER_ADDRESSES.value[:]
        port                = PORT.value
        ip_address          = IP.value
        if ip_address and port:
            if ':' in ip_address:
                server_addresses.append(f"[{ip_address}]:{port}")
            else:
                server_addresses.append(f"{ip_address}:{port}")

        for server_address in set(server_addresses):

            ip_port = NetLib.ExtractIpAndPort(server_address)
            if not ip_port:
                Log.Warn(CATEGORY_NAME, f"{server_address} is invalid")
                continue

            ip, port = ip_port
            free_port = WebDeviceManager.FindFreePort(ip, port)
            if free_port is None:
                tried_ports = WebDeviceManager.PortRange(port)
                span = f"{port}" if len(tried_ports) <= 1 else f"{port}-{tried_ports[-1]}"
                Log.Warn(CATEGORY_NAME, f"{ip}:{span} is in use - skipping this address")
                continue
            if free_port != port:
                Log.Warn(CATEGORY_NAME, f"{ip}:{port} is in use - serving on {ip}:{free_port} instead")
            port = free_port

            self.httpds.append(GameServer(self))
            self.httpds[-1].Run(ip, port, "Server")

        if not self.httpds:
            # Nothing is listening, so nothing can be played. Name the addresses
            # that were tried and how to pick another one; the stack that got us
            # here says nothing the player can act on.
            tried = ", ".join(sorted(set(server_addresses)))
            raise StartupError(f"No free address to serve on (tried {tried}). "
                               "Close the other copy of the game, or start this one "
                               "on a free port: py main.py -port 2400")

        self.stat_sent_size: Dict[str, int] = {}

    @staticmethod
    def PortRange(port: int) -> range:
        """The port that was asked for, then the fallbacks after it."""
        return range(port, min(port + max(PORT_FALLBACK_TRIES.value, 1), 65536))

    @staticmethod
    def FindFreePort(ip: str, port: int) -> int|None:
        """The asked-for port, or the first free one after it.

        A second copy of the game - or anything else holding 2345 - used to take
        the whole start-up down. Ports are cheap, so walk forward a few and let
        the caller report which one was actually taken."""
        for candidate in WebDeviceManager.PortRange(port):
            if NetLib.IsPortAvailable(ip, candidate):
                return candidate
        return None

    ################################################################################
    #
    @override
    def CreateDevices(self, controller: 'Controller') -> Tuple['OutputDevice', 'InputDevice']:
        from engine.device.web import WebDevice
        device = WebDevice(controller, self)
        return device, device

    @override
    def OnNewGame(self):
        super().OnNewGame()
        self.client_manager.ClearSync()
        self.stat_sent_size = {}

    @override
    def OnShutdown(self):
        for httpd in self.httpds:
            httpd.Shutdown()

    ################################################################################
    #
    def HasRunSite(self, ip: str, port: int) -> bool:
        for httpd in self.httpds:
            if httpd.ip == ip and httpd.port == port:
                return True
        return False

    def AddNewSiteInternal(self, ip: str, port: int) -> bool:
        from engine.device.web.server.server import GameServer
        if not self.HasRunSite(ip, port):
            httpd = GameServer(self)
            httpd.Run(ip, port, "Server")
            self.httpds.append(httpd)
            return True
        return False

    def AddLocalNetworkSite(self, port: int) -> str|None:
        ips = NetLib.ListLocalIpAddresses()
        for ip in ips:
            if ip.startswith("192.168"):
                self.AddNewSiteInternal(ip, port)
                return f"{ip}:{port}"
        assert False

    def AddOnlineSite(self, ip: str, port: int) -> str:
        self.AddLocalNetworkSite(port)
        self.AddNewSiteInternal(ip, port)
        return f"{ip}:{port}"

    ################################################################################
    #
    def KillConnect(self):
        self.client_manager.RemoveAll()
        Log.Debug(CATEGORY_NAME, "Kill Connects")

    def CheckSync(self, device: 'Device') -> bool:
        # num = 1 if Game.run.controller_manager.replay.is_replay else Game.run.controller_manager.total_players
        # All players are eliminate
        if not device.is_connected:
            Log.DebugSilent("SYNC", f"WaitSync Exit: disconnected")
            return True

        player_id = device.player_id
        controller = device.controller
        if not controller.world:
            Log.DebugSilent("SYNC", f"WaitSync Exit: not world")
            return True

        if not controller.game.state.is_running:
            Log.DebugSilent("SYNC", f"WaitSync Exit: not running")
            return True

        if self.client_manager.client_synced[player_id] >= controller.world.render.last_render_id:
            Log.DebugSilent("SYNC", f"WaitSync Exit: Sync {controller.world.render.last_render_id}")
            return True

        Log.DebugSilent("SYNC", f"WaitSync Exit: Failed")
        return False

    def ClientUpdateRenderId(self, player_id: int, render_id: int, game_id: int) -> None:
        if player_id >= len(self.controllers):
            return
        if game_id == self.controllers[player_id].game.session.game_id:
            self.client_manager.client_synced[player_id] = render_id
            self.notify.sync.NotifyAll()

    def CheckConnect(self, player_id: int) -> bool:
        def check_client_synced():
            if self.client_manager.GetClients(player_id) == []:
                return False
            return True
        return check_client_synced()

    ################################################################################
    #
    def AddSize(self, category: str, byte_size: int):
        if category not in self.stat_sent_size:
            self.stat_sent_size[category] = 0
        self.stat_sent_size[category] += byte_size
        size_mb = self.stat_sent_size[category] / (1024 * 1024)
        Log.DebugSilent(CATEGORY_NAME, f"Size: [{category}] {size_mb:.2f} MB ({byte_size})")


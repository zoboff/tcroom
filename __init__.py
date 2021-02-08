import websocket

try:
    import thread
except ImportError:
    import _thread as thread

import time
import json
import logging
import os
import requests
import asyncio

from logging.handlers import RotatingFileHandler
from logging import Formatter
from enum import Enum

# PORTS: c:\ProgramData\TrueConf\Room\web\default\config.json
# CONFIG_JSON_FILE = "c:\ProgramData\TrueConf\Room\web\default\config.json"

PRODUCT_NAME = 'TrueConf Room'
URL_SELF_PICTURE = "http://{}:{}/frames/?peerId=%23self%3A0&token={}"
URL_UPLOAD_FILE = "http://{}:{}/files/?token={}"
CONFIG_JSON_URL = "http://localhost:{}/public/default/config.json"
DEFAULT_WEBSOCKET_PORT = 8765
DEFAULT_HTTP_PORT = 8766
DEFAULT_ROOM_PORT = 80

logger = logging.getLogger('tcroom')
logger.setLevel(logging.DEBUG)

rotation_handler = logging.handlers.RotatingFileHandler(
    filename='tcroom.log',
    maxBytes=1024 ** 2 * 10,  # 10 MB
    backupCount=3
)
rotation_handler.setFormatter(Formatter('%(asctime)s - %(levelname)s - %(message)s'))

console_handler = logging.StreamHandler()
console_handler.setFormatter(Formatter('%(asctime)s - %(levelname)s - %(message)s'))

logger.addHandler(rotation_handler)
logger.addHandler(console_handler)


def getHttpPort(room_port: int) -> int:
    '''Get the current HTTP TrueConf Room's port. The TrueConf Room application must be launched'''
    try:
        json_file = requests.get(url=CONFIG_JSON_URL.format(room_port))
        data = json_file.json()
        port = data["config"]["http"]["port"]

        s = f'Room HTTP port: {port}'
        print(s)
        logger.debug(s)
    except:
        port = DEFAULT_HTTP_PORT
        s = f'Room HTTP port (default): {port}'
        print(s)
        logger.debug(s)

    return port


def getWebsocketPort(room_port: int) -> int:
    '''Get the current websocket TrueConf Room's port. The TrueConf Room application must be launched'''
    try:
        json_file = requests.get(url=CONFIG_JSON_URL.format(room_port))
        data = json_file.json()
        port = data["config"]["websocket"]["port"]

        s = f'Room WebSocket port: {port}'
        print(s)
        logger.debug(s)
    except:
        port = DEFAULT_WEBSOCKET_PORT
        s = f'Room WebSocket port (default): {port}'
        print(s)
        logger.debug(s)

    return port


class ConnectionStatus(Enum):
    unknown = 0
    started = 1
    connected = 2
    normal = 3
    close = 4


class RoomException(Exception):
    def __init__(self, message):
        super().__init__(message)
        logger.error(message)


class ConnectToRoomException(RoomException):
    pass


def check_schema(schema: dict, dictionary: dict, exclude_from_comparison: list = []) -> bool:
    schema_d = {k: v for k, v in dictionary.items() if k in schema.keys()}
    if len(schema) == len(schema_d):
        # Exclude some values from comparison
        #  all "key": None
        exclude = [k for k, v in schema.items() if v is None]
        #  and all specified
        exclude.extend(exclude_from_comparison)
        # Comparison        
        for k in schema:
            if k not in exclude:
                try:
                    if schema[k].lower() != schema_d[k].lower():
                        return False
                except:
                    return False
    else:
        return False

    return True


class Room:
    def __init__(self, debug_mode,
                 cb_OnChangeState,
                 cb_OnIncomingMessage,
                 cb_OnIncomingCommand,
                 cb_OnEvent,
                 cb_OnMethod):

        self.debug_mode = debug_mode

        self.connection_status = ConnectionStatus.unknown
        self.app_state = 0
        self.app_state_queue = []
        self.ip = ''
        self.pin = ''
        self.url = ''
        self.tokenForHttpServer = ''
        self.HttpPort = None

        self.systemInfo = {}
        self.settings = {}
        self.monitorsInfo = {}

        self.connection = None

        self.callback_OnChangeState = cb_OnChangeState
        self.callback_OnIncomingMessage = cb_OnIncomingMessage
        self.callback_OnIncomingCommand = cb_OnIncomingCommand
        self.callback_OnEvent = cb_OnEvent
        self.callback_OnMethod = cb_OnMethod

    def __del__(self):
        pass

    def dbg_print(self, value: str) -> None:
        logger.debug(value)
        if self.debug_mode:
            print(value)

    # ===================================================
    # Processing of the all incoming
    # ===================================================
    async def processMessage(self, msg: str):
        response = json.loads(msg)
        if await self.processAppStateChanged(response):
            self.dbg_print('Processed in processAppStateChanged')
        elif await self.processMethodAuth(response):
            self.dbg_print('Processed in processMethodAuth')
        elif await self.processIncomingMessage(response):
            self.dbg_print('Processed in processIncomingMessage')
        elif await self.processIncomingCommand(response):
            self.dbg_print('Processed in processIncomingCommand')
        elif await self.processErrorInResponse(response):
            self.dbg_print('Processed in processErrorInResponse')
        elif await self.processEvents(response):
            self.dbg_print('Processed in processEvents')
        elif await self.processMethods(response):
            self.dbg_print('Processed in processMethods')
        else:
            self.dbg_print(f'Warning! No one handled: {msg}')

    # ===================================================

    # EVENT: appStateChanged
    async def processAppStateChanged(self, response) -> bool:

        # add to queue
        def add_state_to_queue(state: int):
            self.app_state_queue.insert(0, state)
            if len(self.app_state_queue) > 10:
                self.app_state_queue = self.app_state_queue[0:10]

        result = False
        # CHECK SCHEMA
        if check_schema({"event": "appStateChanged", "appState": None}, response):
            result = True
            self.dbg_print(f'*** appStateChanged = {response["appState"]}')
            new_state = response["appState"]
            self.app_state = new_state
            # queue
            add_state_to_queue(self.app_state)

            if self.app_state == 3:  # Normal
                pass
            else:
                pass

            # Callback func
            if self.callback_OnChangeState:
                callback_func = asyncio.create_task(self.callback_OnChangeState(self.app_state))
                await callback_func
        elif check_schema({"appState": None, "method": "getAppState", "result": None}, response):
            result = True
            new_state = response["appState"]
            self.app_state = new_state

        return result

    # {"requestId":"","method":"auth","previleges":2,"token":"***","tokenForHttpServer":"***","result":true}
    async def processMethodAuth(self, response) -> bool:
        result = False
        # CHECK SCHEMA
        if check_schema({"method": "auth", "result": None}, response):
            if response["result"]:
                self.tokenForHttpServer = response["tokenForHttpServer"]
                self.dbg_print('Get auth successfully: tokenForHttpServer = %s' % "***")
                self.setConnectionStatus(ConnectionStatus.normal)
                result = True
                # requests Info
                self.requestAppState()
                self.requestSettings()
                self.requestSystemInfo()
                self.requestMonitorsInfo()
            else:
                result = True
                self.dbg_print('Get auth error')
                self.dbg_print(response)
                self.disconnect()
                self.caughtConnectionError()  # any connection errors

        return result

    # {"event":"incomingChatMessage","peerId":"azobov@team.trueconf.com","peerDn":"azobov@team.trueconf.com","message":"zzz","time":1603297004,"confId":"","method":"event"}
    async def processIncomingMessage(self, response) -> bool:
        result = False
        # CHECK SCHEMA
        if check_schema({"event": "incomingChatMessage", "message": None, "peerId": None, "peerDn": None}, response):
            result = True
            msg = response["message"]
            fromId = response["peerId"]
            fromDn = response["peerDn"]
            self.dbg_print(f"Message fromId: {fromId}, fromDn: {fromDn}, msg: {msg}")
            # Callback func
            if self.callback_OnIncomingMessage:
                callback_func = asyncio.create_task(self.callback_OnIncomingMessage(fromId, fromDn, msg))
                await callback_func

        return result

    # {"event": "commandReceived", "peerId": "user1@some.server", "command": "text", "method": "event"}
    async def processIncomingCommand(self, response) -> bool:
        result = False
        # CHECK SCHEMA
        if check_schema({"event": "commandReceived", "command": None, "peerId": None}, response):
            result = True
            cmd = response["command"]
            fromId = response["peerId"]
            self.dbg_print(f"Command fromId: {fromId}, cmd: {cmd}")
            # Callback func
            if self.callback_OnIncomingCommand:
                callback_func = asyncio.create_task(self.callback_OnIncomingCommand(fromId, cmd))
                await callback_func

        return result

    async def processErrorInResponse(self, response) -> bool:
        result = False
        # CHECK SCHEMA
        if check_schema({"error": None}, response):
            result = True
            s = f'Room error: {response["error"]}'
            self.dbg_print(s)
            logger.error(s)

        return result

    # Unprocessing events
    # {"event": None, "method": "event"}
    async def processEvents(self, response) -> bool:
        result = False
        # CHECK SCHEMA
        if check_schema({"event": None, "method": "event"}, response):
            result = True
            self.dbg_print(f'Event: {response["event"]}')
            # Callback func
            if self.callback_OnEvent:
                callback_func = asyncio.create_task(self.callback_OnEvent(response["event"], response))
                await callback_func

        return result

    # Unprocessing methods
    # {"method": None} and not {"event": None}
    async def processMethods(self, response) -> bool:
        result = check_schema({"method": None}, response) and not check_schema({"event": None}, response)
        if result:
            method_name = response["method"]
            self.dbg_print(f'Method: {method_name}')
            # self.dbg_print(f'  Response: {response}')

            # ================================================
            # for self
            # ================================================
            if "getSystemInfo".lower() == method_name.lower():
                self.systemInfo = response
            elif "getSettings".lower() == method_name.lower():
                self.settings = response
            elif "getMonitorsInfo".lower() == method_name.lower():
                self.monitorsInfo = response
            # ================================================

            # Callback func
            if self.callback_OnMethod:
                callback_func = asyncio.create_task(self.callback_OnMethod(method_name, response))
                await callback_func

        return result

    # ===================================================
    def on_message(self, message):
        asyncio.run(self.processMessage(message))

    def on_error(self, error):
        s = f'WebSocket connection error: {error}'
        print(s)
        logger.error(s)
        # raise ConnectToRoomException(s)

    def on_close(self):
        self.dbg_print("Close socket connection")
        self.setConnectionStatus(ConnectionStatus.close)
        self.tokenForHttpServer = ''

    def on_open(self):
        self.dbg_print('%s connection "%s" successfully' % (PRODUCT_NAME, self.url))
        self.setConnectionStatus(ConnectionStatus.connected)
        # self.setUsedApiVersion_1()
        time.sleep(0.1)
        # Auth
        self.auth(self.pin)

        def run(*args):
            while self.isConnected():
                time.sleep(0.1)
            self.connection.close()

        thread.start_new_thread(run, ())

    # ===================================================

    def send_command_to_room(self, command: dict):
        self.connection.send(json.dumps(command))
        self.dbg_print(f'Run command: {str(command)}')

    def connect(self, ip: str, port: int, pin: str = None) -> bool:
        self.ip = ip
        self.pin = pin
        self.in_stopping = False
        self.tokenForHttpServer = None

        self.wsPort = getWebsocketPort(port)
        self.httpPort = getHttpPort(port)
        # Connect
        self.url = f'ws://{self.ip}:{self.wsPort}'
        self.connection = websocket.WebSocketApp(self.url,
                                                 on_message=self.on_message,
                                                 on_error=self.on_error,
                                                 on_close=self.on_close)
        self.connection.on_open = self.on_open
        self.setConnectionStatus(ConnectionStatus.started)
        # Thread
        thread.start_new_thread(self.run, ())

    def disconnect(self):
        self.dbg_print('Connection is closing...')
        self.setConnectionStatus(ConnectionStatus.close)

    def run(self):
        self.connection.run_forever()

    def getTokenForHttpServer(self):
        return self.tokenForHttpServer

    def isReady(self):
        return self.connection_status == ConnectionStatus.normal

    def isConnected(self) -> bool:
        return self.connection_status in [ConnectionStatus.connected, ConnectionStatus.normal]

    def caughtConnectionError(self):
        raise ConnectToRoomException(
            '{} is not running or wrong IP address, PIN, Port. IP="{}"'.format(PRODUCT_NAME, self.ip))

    def setConnectionStatus(self, status):
        self.connection_status = status
        self.dbg_print("setStatus: " + self.connection_status.name)

    def save_picture_selfview_to_file(self, fileName: str) -> str:
        if self.isReady() and self.tokenForHttpServer:
            url = URL_SELF_PICTURE.format(self.ip, self.httpPort, self.tokenForHttpServer)
            with open(os.path.join(fileName), 'wb') as out_stream:
                req = requests.get(url, stream=True)
                for chunk in req.iter_content(10240):
                    out_stream.write(chunk)
        else:
            # raise RoomException('{} is not ready to take a picture'.format(PRODUCT_NAME, self.ip))
            return None

        return fileName

    ''' getAppState
       * none       = 0 (No connection to the server and the terminal does nothing),
       * connect    = 1 (the terminal tries to connect to the server),
       * login      = 2 (you need to login),
       * normal     = 3 (the terminal is connected to the server and logged in),
       * wait       = 4 (the terminal is pending: either it calls somebody or somebody calls it),
       * conference = 5 (the terminal is in the conference),
       * close      = 6 (the terminal is finishing the conference)
    '''

    def getAppState(self) -> int:
        return self.app_state

    # =============================================================
    def setUsedApiVersion_1(self):
        # make a command
        command = {"method": "setUsedApiVersion", "version": "1"}
        # send
        self.send_command_to_room(command)

    def auth(self, pin: str):
        if pin:
            command = {"method": "auth", "type": "secured", "credentials": pin}
        else:
            command = {"method": "auth", "type": "unsecured"}
        # send
        self.send_command_to_room(command)

    def call(self, peerId: str) -> None:
        # make a command        
        command = {"method": "call", "peerId": peerId}
        print(self.connection_status)
        # send    
        self.send_command_to_room(command)

    def accept(self):
        # make a command        
        command = {"method": "accept"}
        # send    
        self.send_command_to_room(command)

    def requestSettings(self):
        # make a command        
        command = {"method": "getSettings"}
        # send    
        self.send_command_to_room(command)

    def requestSystemInfo(self):
        # make a command        
        command = {"method": "getSystemInfo"}
        # send    
        self.send_command_to_room(command)

    def logout(self):
        # make a command        
        command = {"method": "logout"}
        # send    
        self.send_command_to_room(command)

    def moveVideoSlotToMonitor(self, callId: str, monitorIndex: int):
        # make a command
        command = {"method": "moveVideoSlotToMonitor", "callId": callId, "monitorIndex": monitorIndex}
        # send    
        self.send_command_to_room(command)

    def sendCommand(self, peerId: str, command: str):
        # make a command
        command = {"method": "sendCommand", "peerId": peerId, "command": command}
        # send    
        self.send_command_to_room(command)

    def hangUp(self, forAll: bool = False):
        # make a command
        command = {"method": "hangUp", "forAll": forAll}
        # send    
        self.send_command_to_room(command)

    def setBackground(self, filePath: str = ""):
        # Check on file empty
        if not filePath:
            print("Empty path")
            command = {"method": "setBackground"}
            self.send_command_to_room(command)
            return

        try:
            files = {'file': open(filePath, 'rb')}
        except IOError:
            print("File not accessible")
            return

        # make request
        url = URL_UPLOAD_FILE.format(self.ip, self.HttpPort, self.tokenForHttpServer)
        response = requests.post(url, files=files)
        if response.status_code == 200:
            data = response.headers
            command = {"method": "setBackground", "fileId": int(data["FileId"])}
            self.send_command_to_room(command)
        else:
            self.dbg_print(response.text)
        return

    ''' {
    "method" : "createConference"
    "title" : "Code review",
    "confType" : "symmetric",
    "autoAccept" : false,
    "inviteList" : [
        "user1@some.server",
        "user2@some.server",
        "user3@some.server"
    ]
    }'''

    def createConferenceSymmetric(self, title: str, autoAccept: bool, inviteList: []):
        # make a command
        command = {"method": "createConference", "title": title, "confType": "symmetric",
                   "autoAccept": autoAccept, "inviteList": inviteList}
        # send    
        self.send_command_to_room(command)

    def connectToServer(self, server: str, port: int = 4307):
        # make a command
        command = {"method": "connectToServer", "server": server, "port": port}
        # send    
        self.send_command_to_room(command)

    def requestAppState(self):
        # make a command
        command = {"method": "getAppState"}
        # send    
        self.send_command_to_room(command)

    def requestMonitorsInfo(self):
        # make a command
        command = {"method": "getMonitorsInfo"}
        # send    
        self.send_command_to_room(command)

    def setSettings(self, settings: dict):
        # make a command
        command = {"method": "setSettings", "settings": settings}
        # send    
        self.send_command_to_room(command)

    def shutdownRoom(self, forAll: bool):
        # make a command
        command = {"method": "shutdown", "forAll": forAll}
        # send    
        self.send_command_to_room(command)


# =====================================================================
def make_connection(pin=None, room_ip='127.0.0.1', port=80, debug_mode=False,
                    cb_OnChangeState=None,
                    cb_OnIncomingMessage=None,
                    cb_OnIncomingCommand=None,
                    cb_OnEvent=None,
                    cb_OnMethod=None):
    '''
    Connect to TrueConf Room. The TrueConf Room application must be launched
    '''

    room = Room(debug_mode, cb_OnChangeState, cb_OnIncomingMessage, cb_OnIncomingCommand, cb_OnEvent, cb_OnMethod)
    room.connect(ip=room_ip, pin=pin, port=port)

    # Wait for ~5 sec...
    WAIT_FOR_SEC, SLEEP = 5, 0.1
    for i in range(round(WAIT_FOR_SEC / SLEEP)):
        if room.isConnected():
            break
        time.sleep(0.1)
        if i >= round(WAIT_FOR_SEC / SLEEP) - 1:
            room.caughtConnectionError()

    return room
# =====================================================================

# coding=utf8
'''''
@author: zobov
'''
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
from enum import Enum, IntEnum

# PORTS: c:\ProgramData\TrueConf\Room\web\default\config.json
# CONFIG_JSON_FILE = "c:\ProgramData\TrueConf\Room\web\default\config.json"

PRODUCT_NAME = 'TrueConf Room'
URL_SELF_PICTURE = "http://{}:{}/frames/?peerId=%23self%3A0&token={}"
URL_UPLOAD_FILE = "http://{}:{}/files/?token={}"
CONFIG_JSON_URL = "http://{}:{}/public/default/config.json"
DEFAULT_WEBSOCKET_PORT = 8765
DEFAULT_HTTP_PORT = 8766
DEFAULT_ROOM_PORT = 80

SELF_VIEW_SLOT = "#self:0" #"VideoCaptureSlot"
SLIDE_SHOW_SLOT = "SlideShowSlot"

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


def getHttpPort(ip: str, room_port: int) -> int:
    """Get the current HTTP TrueConf Room port. The TrueConf Room application must be launched"""
    try:
        json_file = requests.get(url=CONFIG_JSON_URL.format(ip, room_port))
        data = json_file.json()
        port = data["config"]["http"]["port"]
        logger.info(f'Room HTTP port: {port}')
    except Exception as e:
        port = DEFAULT_HTTP_PORT
        logger.warning(f'Failed to fetch current HTTP Trueconf Room port. {e}')
        logger.info(f'Room HTTP port (default): {DEFAULT_HTTP_PORT}')

    return port


def getWebsocketPort(ip: str, room_port: int) -> int:
    """Get the current websocket TrueConf Room port. The TrueConf Room application must be launched"""
    try:
        json_file = requests.get(url=CONFIG_JSON_URL.format(ip, room_port))
        data = json_file.json()
        port = data["config"]["websocket"]["port"]
        logger.info(f'Room WebSocket port: {port}')
    except Exception as e:
        port = DEFAULT_WEBSOCKET_PORT
        logger.warning(f'Failed to fetch current websocket Trueconf Room port. {e}')
        logger.info(f'Room WebSocket port (default): {port}')

    return port


class ConnectionStatus(IntEnum):
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


def appStateToText(state: int):
    APP_STATES = {
            0: "none",       # No connection to the server and TrueConf Room does nothing
            1: "connect",    # TrueConf Room tries to connect to the server
            2: "login",      # you need to login
            3: "normal",     # TrueConf Room is connected to the server and logged in
            4: "wait",       # TrueConf Room is pending: either it calls somebody or somebody calls it
            5: "conference", # TrueConf Room is in the conference
            6: "close"       # TrueConf Room is finishing the conference
        }

    return APP_STATES.get(state, "none")


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
        self.currentConference = None

        self.callback_OnChangeState = cb_OnChangeState
        self.callback_OnIncomingMessage = cb_OnIncomingMessage
        self.callback_OnIncomingCommand = cb_OnIncomingCommand
        self.callback_OnEvent = cb_OnEvent
        self.callback_OnMethod = cb_OnMethod

    def __del__(self):
        pass

    def dbg_print(self, value: str) -> None:
        if self.debug_mode:
            logger.debug(value)

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
            # update a conference's info
            self.updateConferenceInfo()

            if self.app_state == 3:  # Normal
                pass
            elif self.app_state == 5:  # In conference
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
            # update a conference's info
            self.updateConferenceInfo() 

            # Callback func
            if self.callback_OnChangeState:
                callback_func = asyncio.create_task(self.callback_OnChangeState(self.app_state))
                await callback_func

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
            elif "getConferences".lower() == method_name.lower():
                self.currentConference = response
            # ================================================

            # Callback func
            if self.callback_OnMethod:
                callback_func = asyncio.create_task(self.callback_OnMethod(method_name, response))
                await callback_func

        return result

    # ===================================================
    def on_message(self, ws, message):
        asyncio.run(self.processMessage(message))

    def on_error(self, ws, error):
        logger.error(f'WebSocket connection error: {error}')

    def on_close(self, ws, *args):
        self.dbg_print('Close socket connection.')
        self.setConnectionStatus(ConnectionStatus.close)
        self.tokenForHttpServer = ""

    def on_open(self, ws):
        self.dbg_print(f'{PRODUCT_NAME} connection to {self.url} was open successfully')
        self.setConnectionStatus(ConnectionStatus.connected)
        time.sleep(0.1)
        self.auth(self.pin)

        def run(*args):
            while self.isConnected():
                time.sleep(0.1)
            self.connection.close()

        thread.start_new_thread(run, ())

    # ===================================================

    def send_command_to_room(self, command: dict):
        #logger.info(f'Sending command to room: {command}')
        self.dbg_print(f'Sending command to room: {command}')
        self.connection.send(json.dumps(command))

    def connect(self, ip: str, port: int, pin: str = None) -> bool:
        """Connect to the Room application"""
        self.ip = ip
        self.pin = pin
        self.in_stopping = False
        self.tokenForHttpServer = ""

        self.wsPort = getWebsocketPort(ip, port)
        self.httpPort = getHttpPort(ip, port)
        
        websocket.enableTrace(self.debug_mode)
        self.url = f'ws://{self.ip}:{self.wsPort}'
        self.connection = websocket.WebSocketApp(self.url,
                                                 on_open=self.on_open,
                                                 on_message=self.on_message,
                                                 on_error=self.on_error,
                                                 on_close=self.on_close)
        self.connection.on_open = self.on_open
        self.setConnectionStatus(ConnectionStatus.started)
        thread.start_new_thread(self.run, ())

    def disconnect(self):
        """Disconnect from the Room application"""
        logger.info('Connection is closing...')
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
        logger.info(f'Set connection status: {self.connection_status.name}')

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
        command = {"method": "setUsedApiVersion", "version": "1"}
        self.send_command_to_room(command)

    def auth(self, pin: str):
        if pin:
            command = {"method": "auth", "type": "secured", "credentials": pin}
        else:
            command = {"method": "auth", "type": "unsecured"}
        self.send_command_to_room(command)

    def call(self, peerId: str) -> None:
        """Make p2p call
        
        Parameters
        ----------
        peerId : str
            A unique user ID (TrueConfID)
        """
        command = {"method": "call", "peerId": peerId}
        logger.info(f'Connection status: {self.connection_status.name}')
        self.send_command_to_room(command)

    def accept(self):
        """Accept the call. The command is run immediately and the result of execution is received at once.
        
        Response example
        ----------
        {"event" : "commandExecution", "accept" : "ok"}

        """
        command = {"method": "accept"}
        self.send_command_to_room(command)

    def requestSettings(self):
        """Request the settings list"""
        command = {"method": "getSettings"}
        self.send_command_to_room(command)

    def requestSystemInfo(self):
        """Request the system information"""
        command = {"method": "getSystemInfo"}
        self.send_command_to_room(command)
        
    def requestConferenceParticipants(self):
        """Request current conference participants list"""
        command = {"method": "getConferenceParticipants"}
        self.send_command_to_room(command)

    def login(self, callId: str, password: str):
        """Login to TrueConf Server"""
        command = {"method" : "login",
            "login" : callId,
            "password" : password,
            "encryptPassword" : True}
        self.send_command_to_room(command)

    def logout(self):
        """Log out the current user"""
        command = {"method": "logout"}
        self.send_command_to_room(command)

    def moveVideoSlotToMonitor(self, callId: str, monitorIndex: int):
        """Move the user's video slot to specific monitor.
        
        Parameters
        ----------
        callId : str
            TrueConf ID
        monitorIndex : int
            Monitor index
        """
        command = {"method": "moveVideoSlotToMonitor", "callId": callId, "monitorIndex": monitorIndex}
        self.send_command_to_room(command)

    def sendCommand(self, peerId: str, command: str):
        command = {"method": "sendCommand", "peerId": peerId, "command": command}
        self.send_command_to_room(command)

    def hangUp(self, forAll: bool = False):
        """End a call or a conference. The command is used when the conference has already been created. 
        hangUp() format is used during a video call. During group conferences both formats are used. 
        By using hangUp(False) format, you leave the conference, but other participants remain in the conference. 
        By using hangUp(True) the conference ends for all the participants. 
        hangUp(True) is used only if you are the conference owner, otherwise a failure occurs. 
        Positive response ("ok") means the command has been accepted for execution but has not been run executed yet. 
        Execution result will be received separately via notification.
        
        Parameters
        ----------
            forAll: bool
                True - conference ends for all the participants;                 
                False - you leave the conference, but other participants remain in the conference.
        """
        command = {"method": "hangUp", "forAll": forAll}
        self.send_command_to_room(command)

    def setBackground(self, filePath: str = ""):
        # Check on file empty
        if not filePath:
            logger.info('Empty path')
            command = {"method": "setBackground"}
            self.send_command_to_room(command)
            return

        try:
            files = {'file': open(filePath, 'rb')}
        except IOError:
            logger.info('File not accessible')
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

    def updateConferenceInfo(self):
        # clear current conference info
        self.currentConference = None
        # update info
        if self.app_state == 5:
            self.requestGetConferences()
        
        
    def createConferenceSymmetric(self, title: str, autoAccept: bool, inviteList: []):
        command = {"method": "createConference", "title": title, "confType": "symmetric",
                   "autoAccept": autoAccept, "inviteList": inviteList}
        self.send_command_to_room(command)

    def connectToServer(self, server: str, port: int = 4307):
        """Connect to TrueConf Server
        
        Parameters
        ----------
            server: str
                Server address. For example, IP address;
            port: int
                Port. Default port is 4307.
        """
        command = {"method": "connectToServer", "server": server, "port": port}
        self.send_command_to_room(command)

    def requestAppState(self):
        """Request an application state"""
        command = {"method": "getAppState"}
        self.send_command_to_room(command)

    def requestMonitorsInfo(self):
        """Request the information about monitors."""
        command = {"method": "getMonitorsInfo"}
        self.send_command_to_room(command)

    def setSettings(self, settings: dict):
        """Set application settings.
        
        Parameters
        ----------
            settings: dict
                Settings. 
                For example, ```{"defaultP2PMatrix": 3}```
        """
        command = {"method": "setSettings", "settings": settings}
        self.send_command_to_room(command)

    def shutdownRoom(self, forAll: bool):
        """Shutdown application"""
        command = {"method": "shutdown", "forAll": forAll}
        self.send_command_to_room(command)
        
    def requestGetConferences(self):
        """Request the list of conferences."""
        command = {"method": "getConferences"}
        self.send_command_to_room(command)
        
    def changeVideoMatrix(self, matrixType: int, participants: list):
        """
        Specify video matrix and the ratio of video windows for available slots. It is used only in the conference.

        Parameters
        ----------
        matrixType: int 
            Matrix allocation type. There are the following matrix types:

            - even = 0, all the windows are of the same size (for multipoint conference);
            - big = 1, one window is big while others are small (for multipoint conference);
            - one = 2,  display only the video of the conference participant who is the first in the participants list (for any type of the conference); 
            - oneSelf = 3, big video of the conference participant and a small selfview in the corner (for video call).
        participants: list
            the list of video slots and conference participants

        Example
        -------
        ```
        import tcroom
        
        participants = ["user1@some.server", "user2@some.server", "user3@some.server"]
        room = tcroom.make_connection(pin = "123")
        room.changeVideoMatrix(2, participants)
        ```
        """
        
        # Replace logged ID to SELF_VIEW_SLOT - "VideoCaptureSlot"
        my_id = self.getMyId()
        if my_id:
            for i, user in enumerate(participants):
                if my_id == user:
                    participants[i] = SELF_VIEW_SLOT

        command = {"method": "changeVideoMatrix", "matrixType": matrixType, "participants": participants}
        self.send_command_to_room(command)
        
    def getMyId(self) -> str:
        """
        Get the current logged TrueConf ID
        """

        try:
            return self.systemInfo["authInfo"]["peerId"]
        except:
            return None
        
    def setPanPos(self, pos: int):
        command = {"method": "setPanPos", "pos": pos}
        self.send_command_to_room(command)

    def setTiltPos(self, pos: int):
        command = {"method": "setTiltPos", "pos": pos}
        self.send_command_to_room(command)
        
    def setZoomPos(self, pos: int):
        command = {"method": "setZoomPos", "pos": pos}
        self.send_command_to_room(command)
        
    def ptzStop(self):
        command = {"method": "ptzStop"}
        self.send_command_to_room(command)
     
    def ptzRight(self):
        command = {"method": "ptzRight"}
        self.send_command_to_room(command)
    
    def ptzLeft(self):
        command = {"method": "ptzLeft"}
        self.send_command_to_room(command)
     
    def ptzUp(self):
        command = {"method": "ptzUp"}
        self.send_command_to_room(command)
      
    def ptzDown(self):
        command = {"method": "ptzDown"}
        self.send_command_to_room(command)
     
    def ptzZoomInc(self):
        command = {"method": "ptzZoomInc"}
        self.send_command_to_room(command)
    
    def ptzZoomDec(self):
        command = {"method": "ptzZoomDec"}
        self.send_command_to_room(command)
        
    def getURL_SelfVideo(self):
        if self.isReady() and self.tokenForHttpServer:
            return URL_SELF_PICTURE.format(self.ip, self.httpPort, self.tokenForHttpServer)
        else:
            return None

    def showMainWindow(self, maximized: bool, stayOnTop: bool = True):
        # state:
        #   1 = minimized;
        #   2 = full screen mode.        
        state = 1 if not maximized else 2
        command = {"method": "changeWindowState", "windowState": state, "stayOnTop": stayOnTop}
        self.send_command_to_room(command)


# =====================================================================
def make_connection(pin=None, room_ip='127.0.0.1', port=80, debug_mode=False,
                    cb_OnChangeState=None,
                    cb_OnIncomingMessage=None,
                    cb_OnIncomingCommand=None,
                    cb_OnEvent=None,
                    cb_OnMethod=None):
    """Connect to TrueConf Room. The TrueConf Room application must be launched"""

    room = Room(debug_mode, cb_OnChangeState, cb_OnIncomingMessage, cb_OnIncomingCommand, cb_OnEvent, cb_OnMethod)
    room.connect(ip=room_ip, pin=pin, port=port)

    # Wait for ~5 sec...
    WAIT_FOR_SEC, SLEEP = 5, 0.1
    for i in range(round(WAIT_FOR_SEC / SLEEP)):
        if room.isConnected():
            break
        time.sleep(0.1)
        if i >= round(WAIT_FOR_SEC / SLEEP) - 1:
            logger.error('Connection timed out')
            room.caughtConnectionError()

    return room
# =====================================================================

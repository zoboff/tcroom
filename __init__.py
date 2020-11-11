import websocket
try:
    import thread
except ImportError:
    import _thread as thread

import time
import json
import logging
import threading
from enum import Enum
import os
import requests
import asyncio

PRODUCT_NAME = 'TrueConf Room'
URL_SELF_PICTURE = "http://{}:8766/frames/?peerId=%23self%3A0&token={}"

class ConnectionStatus(Enum):
    unknown = 0
    started = 1
    connected = 2
    normal = 3
    close = 4

class RoomException(Exception):
    pass

class Room:
    def __init__(self, debug_mode, 
                 cb_OnChangeState, 
                 cb_OnIncomingMessage, 
                 cb_OnIncomingCommand,
                 cb_OnEvent):

        self.debug_mode = debug_mode

        self.connection_status = ConnectionStatus.unknown
        self.ip = ''
        self.pin = ''
        self.url = ''
        self.tokenForHttpServer = ''

        self.connection = None
        
        self.callback_OnChangeState = cb_OnChangeState
        self.callback_OnIncomingMessage = cb_OnIncomingMessage
        self.callback_OnIncomingCommand = cb_OnIncomingCommand
        self.callback_OnEvent = cb_OnEvent

    def __del__(self):
        pass

    def dbg_print(self, value: str) -> None:
        if self.debug_mode:
            print(value)

    # ===================================================
    # Processing of the all incoming
    # ===================================================
    async def processMessage(self, msg: str):
        response = json.loads(msg)
        if await self.processAppStateChanged(response):
            pass
        elif await self.processMethodAuth(response):
            pass
        elif await self.processIncomingMessage(response):
            pass
        elif await self.processIncomingCommand(response):
            pass
        elif await self.processErrorInResponse(response):
            pass
        elif await self.processEvents(response):
            pass
    # ===================================================

    async def processAppStateChanged(self, response) -> bool:
        result = False
        if "event" in response:
            self.dbg_print(f'Event: {response["event"]}') # dbg_print
            # EVENT: appStateChanged
            if response["event"] == "appStateChanged" and "appState" in response:
                result = True
                self.dbg_print('*** appStateChanged = %s' % response["appState"]) # dbg_print
                new_state = response["appState"] 
                if new_state == 3: # Normal
                    pass
                else:
                    pass

                # Callback func
                if self.callback_OnChangeState:
                    callback_func = asyncio.create_task(self.callback_OnChangeState(new_state))
                    await callback_func

        return result

    async def processMethodAuth(self, response) -> bool:
        result = False
        if "method" in response and response["method"] == "auth":
            # {"requestId":"","method":"auth","previleges":2,"token":"***","tokenForHttpServer":"***","result":true} 
            if response["result"]:
                self.tokenForHttpServer = response["tokenForHttpServer"]
                self.dbg_print('Get auth successfully: tokenForHttpServer = %s' % "***") # dbg_print
                self.setConnectionStatus(ConnectionStatus.normal)
                result = True
            else:
                result = True
                self.dbg_print('Get auth error')
                self.disconnect()
                self.caughtConnectionError() # any connection errors

        return result

    # {"event":"incomingChatMessage","peerId":"azobov@team.trueconf.com","peerDn":"azobov@team.trueconf.com","message":"zzz","time":1603297004,"confId":"","method":"event"}
    async def processIncomingMessage(self, response) -> bool:
        result = False
        if "event" in response:
            self.dbg_print(f'Event: {response["event"]}') # dbg_print
            # EVENT: incomingChatMessage
            if response["event"] == "incomingChatMessage" and "message" in response:
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
        if "event" in response:
            self.dbg_print(f'Event: {response["event"]}') # dbg_print
            # EVENT: commandReceived
            if response["event"] == "commandReceived" and "command" in response:
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
        if "error" in response:
            result = True
            self.dbg_print("Room error: " + response["error"])
            self.caughtConnectionError() # any connection errors                           

        return result

    async def processEvents(self, response) -> bool:
        result = False
        if "event" in response and "method" in response and response["method"] == "event":
            result = True
            # Callback func
            if self.callback_OnEvent:
                callback_func = asyncio.create_task(self.callback_OnEvent(self, response["event"], response))
                await callback_func                                       

        return result
    # ===================================================
    def on_message(self, message):
        asyncio.run(self.processMessage(message))

    def on_error(self, error):
        self.dbg_print("WebSocket error: " + error)

    def on_close(self):
        self.dbg_print("Close socket connection")
        self.setConnectionStatus(ConnectionStatus.close)
        self.tokenForHttpServer = ''

    def on_open(self):
        self.dbg_print('%s connection "%s" successfully' % (PRODUCT_NAME, self.url)) # dbg_print
        self.setConnectionStatus(ConnectionStatus.connected)
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
        self.dbg_print('Run command: %s' % str(command)) # dbg_print

    def connect(self, ip: str, pin: str, ws_port:int = 8765) -> bool:
        self.ip = ip
        self.pin = pin
        self.in_stopping = False
        self.tokenForHttpServer = ''
        # Connect
        self.url = f'ws://{self.ip}:{ws_port}'
        self.connection = websocket.WebSocketApp(self.url,
                                  on_message = self.on_message,
                                  on_error = self.on_error,
                                  on_close = self.on_close)
        self.connection.on_open = self.on_open
        self.setConnectionStatus(ConnectionStatus.started)
        # Thread
        thread.start_new_thread(self.run, ())
        
    def disconnect(self):
        self.dbg_print('Connection is closing...') # dbg_print
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
        raise RoomException('{} is not running or wrong IP address or wrong PIN. IP="{}"'.format(PRODUCT_NAME, self.ip))
    
    def setConnectionStatus(self, status):
        self.connection_status = status
        self.dbg_print("setStatus: " + self.connection_status.name) # dbg_print
        
    def save_picture_selfview_to_file(self, fileName: str) -> str:
        if self.isReady:
            url = URL_SELF_PICTURE.format(self.ip, self.tokenForHttpServer)
            with open(os.path.join(fileName), 'wb') as out_stream:
                req = requests.get(url, stream=True)
                for chunk in req.iter_content(10240):
                    out_stream.write(chunk)
        else:
            raise RoomException('{} is not ready to take a picture'.format(PRODUCT_NAME, self.ip))
        
        return fileName
    # =============================================================
    def auth(self, pin: str):
        if pin:
            command = {"method" : "auth","type" : "secured", "credentials" : pin}
        else:
            command = {"method" : "auth","type" : "unsecured"}
        # send
        self.send_command_to_room(command)

    def call(self, peerId: str) -> None:
        # make a command        
        command = {"method": "call", "peerId": peerId}    
        # send    
        self.send_command_to_room(command)

    def accept(self):
        # make a command        
        command = {"method" : "accept"}    
        # send    
        self.send_command_to_room(command)
                
    def getSettings(self):
        # make a command        
        command = {"method" : "getSettings"}    
        # send    
        self.send_command_to_room(command)

    def logout(self):
        # make a command        
        command = {"method" : "logout"}    
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
        command = {"method" : "hangUp", "forAll" : forAll}
        # send    
        self.send_command_to_room(command)

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
        command = {"method" : "createConference", "title" : title, "confType" : "symmetric", 
                   "autoAccept": autoAccept, "inviteList": inviteList}
        # send    
        self.send_command_to_room(command)

# =====================================================================
def make_connection(pin, room_ip = '127.0.0.1', ws_port = 8765, debug_mode = False,
                    callback_OnChangeState = None, 
                    cb_OnIncomingMessage = None,
                    cb_OnIncomingCommand = None,
                    cb_OnEvent = None):

    room = Room(debug_mode, callback_OnChangeState, cb_OnIncomingMessage, cb_OnIncomingCommand, cb_OnEvent)
    room.connect(room_ip, pin, ws_port)

    # Wait for ~5 sec...
    WAIT_FOR_SEC, SLEEP = 5, 0.1
    for i in range(round(WAIT_FOR_SEC/SLEEP)): 
        if room.isConnected():
            break
        time.sleep(0.1)
        if i >= round(WAIT_FOR_SEC/SLEEP) - 1:
            room.caughtConnectionError()

    return room
# =====================================================================

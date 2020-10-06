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

PRODUCT_NAME = 'TrueConf Room'

class ConnectionStatus(Enum):
    unknown = 0
    started = 1
    connected = 2
    normal = 3
    close = 4

class RoomException(Exception):
    pass

class Room:
    def __init__(self, debug_mode = False):
        self.connection_status = ConnectionStatus.unknown
        self.ip = ''
        self.pin = ''
        self.address_request = ''
        self.connection = None
        self.tokenForHttpServer = ''
        self.debug_mode = debug_mode

    def __del__(self):
        pass

    def dbg_print(self, value: str) -> None:
        if self.debug_mode:
            print(value)

    def processMessage(self, msg: str):
        response = json.loads(msg)
        # events
        if "event" in response:
            self.dbg_print('Event: {}'.format(response["event"])) # dbg_print
            # EVENT: appStateChanged
            if response["event"] == "appStateChanged" and "appState" in response:
                self.dbg_print('*** appStateChanged = {}'.format(response["appState"])) # dbg_print
                if response["appState"] == 3:
                    pass
                else:
                    pass
        # "method": "auth"
        elif "method" in response and response["method"] == "auth":
            # {"requestId":"","method":"auth","previleges":2,"token":"***","tokenForHttpServer":"***","result":true} 
            if response["result"]:
                self.tokenForHttpServer = response["tokenForHttpServer"]
                self.dbg_print('Get auth successfully: tokenForHttpServer = {}'.format("***")) # dbg_print
                self.setConnectionStatus(ConnectionStatus.normal)
            else:
                self.dbg_print('Get auth error')
                self.caughtConnectionError() # any connection errors
        elif "error" in response:
            self.dbg_print("Room error: " + response["error"])
            self.caughtConnectionError() # any connection errors                           
            
    # ===================================================
    def on_message(self, message):
        self.processMessage(message)

    def on_error(self, error):
        self.dbg_print("WebSocket error: " + error)

    def on_close(self):
        self.dbg_print("Close socket connection")
        self.setConnectionStatus(ConnectionStatus.close)
        self.tokenForHttpServer = ''

    def on_open(self):
        self.dbg_print('{} connection "{}" successfully'.format(PRODUCT_NAME, self.address_request)) # dbg_print
        self.setConnectionStatus(ConnectionStatus.connected)
        # Auth
        self.auth(self.pin)

        def run(*args):
            while self.isReadyToWork():
                time.sleep(0.1)
            self.connection.close()

        thread.start_new_thread(run, ())
    # ===================================================

    def send_command_to_room(self, command: dict):
        self.connection.send(json.dumps(command))
        self.dbg_print('Run command: {}'.format(str(command))) # dbg_print

    def connect(self, ip: str, pin: str) -> bool:
        self.ip = ip
        self.pin = pin
        self.in_stopping = False
        self.tokenForHttpServer = ''
        # Connect
        self.address_request = 'ws://{}:8765'.format(self.ip)
        self.connection = websocket.WebSocketApp(self.address_request,
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
    
    def isReadyToWork(self) -> bool:
        return self.connection_status in [ConnectionStatus.connected, ConnectionStatus.normal]
    
    def caughtConnectionError(self):
        raise RoomException('{} is not running or wrong IP address or wrong PIN. IP="{}"'.format(PRODUCT_NAME, self.ip))
    
    def setConnectionStatus(self, status):
        self.connection_status = status
        print("setStatus: " + self.connection_status.name)
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

    def getLogin(self):
        # make a command        
        command = {"method" : "getLogin"}    
        # send    
        self.send_command_to_room(command)

# =====================================================================
def make_connection(room_ip, pin):
    room = Room(True)
    room.connect(room_ip, pin)

    # Wait for ~5 sec...
    WAIT_FOR_SEC, SLEEP = 5, 0.1
    for i in range(round(WAIT_FOR_SEC/SLEEP)): 
        if room.isReadyToWork():
            break
        time.sleep(0.1)
        if i >= round(WAIT_FOR_SEC/SLEEP) - 1:
            room.caughtConnectionError()

    return room
# =====================================================================

from websocket import create_connection, WebSocketAddressException
import json
import logging
import threading
import time

PRODUCT_NAME = 'TrueConf Room'

class RoomException(Exception):
    pass

def events_thread_function(name, room):
    print('Thread "{}": starting'.format(name))
    while not room.in_stopping:
        try:
            if room.is_connection_started:
                # Receive 
                rcv = room.connection.recv()        
                room.dbg_print('Received: {}'.format(rcv)) # dbg_print
                # json string to dictionary
                response = json.loads(rcv)
                # events
                if "event" in response:
                    room.dbg_print('Event: {}'.format(response["event"])) # dbg_print
                    # EVENT: appStateChanged
                    if response["event"] == "appStateChanged" and "appState" in response:
                        room.dbg_print('*** appStateChanged = {}'.format(response["appState"])) # dbg_print
                        if response["appState"] == 3:
                            pass
                        else:
                            pass
                elif "method" in response:
                    # {"requestId":"","method":"auth","previleges":2,"token":"***","tokenForHttpServer":"***","result":true} 
                    if response["method"] == "auth" and response["result"]:
                        room.dbg_print('*** Auth successfully: tokenForHttpServer = {}'.format(response["tokenForHttpServer"])) # dbg_print
                        room.tokenForHttpServer = response["tokenForHttpServer"]
                        room.is_connected = True
                    elif response["method"] == "auth" and not response["result"]:
                        room.caughtConnectionError() # any connection errors
                        print('Auth error.')
                        break

            time.sleep(0.2)
        except ConnectionResetError:
            room.caughtConnectionError()
            #raise RoomException('Room connection failed')
            print('Room connection failed')
            break 
        except Exception as e:
            print(e)
            break

class Room:
    def __init__(self, debug_mode = False):
        self.in_stopping = False
        self.debug_mode = debug_mode
        self.ip = ''
        self.address_request = ''
        self.connection = None
        self.events_thread = None
        self.is_connected = False
        self.tokenForHttpServer = ''
        self.is_connection_started = False
        
    def __del__(self):
        self.close_connection()

    def dbg_print(self, value: str) -> None:
        if self.debug_mode:
            print(value)
    
    def send_command_to_room(self, command: dict):
        if not self.connection:
            raise RoomException('Connection to {} is not initialized. Run before: create_connection() '.format(PRODUCT_NAME))

        self.connection.send(json.dumps(command))
        self.dbg_print('Run command: {}'.format(str(command))) # dbg_print

    def auth(self, pin: str):
        if pin:
            command = {"method" : "auth","type" : "secured", "credentials" : pin}
        else:
            command = {"method" : "auth","type" : "unsecured"}
        # send
        self.send_command_to_room(command)
    
    def create_connection(self, ip: str, pin: str = None) -> bool:
        self.ip = ip
        self.in_stopping = False
        self.tokenForHttpServer = ''
        # Connect
        self.address_request = 'ws://{}:8765'.format(self.ip)
        try:
            self.connection = create_connection(self.address_request)
        except ConnectionRefusedError:
            raise RoomException('Error connection to {}. IP="{}"'.format(PRODUCT_NAME, self.ip))
        except WebSocketAddressException:
            raise RoomException('{} is not running or wrong IP address . IP="{}"'.format(PRODUCT_NAME, self.ip))
        except:
            raise        
        
        self.dbg_print('{} connection "{}" successfully'.format(PRODUCT_NAME, self.address_request)) # dbg_print
        
        # Auth
        self.auth(pin)
        
        # start the events thread
        self.events_thread = threading.Thread(target=events_thread_function, args=("Events Thread", self))
        self.events_thread.start()
        self.dbg_print('Events Thread started') # dbg_print
        
        self.is_connection_started = True
        
    def close_connection(self):
        self.dbg_print('Connection is closing...') # dbg_print
        self.is_connection_started = False
        self.in_stopping = True
        self.is_connected = False

        if self.events_thread and self.events_thread.is_alive():
            self.dbg_print('Finishing Events thread ...') # dbg_print
            self.events_thread.join()
            self.dbg_print('Events thread is finished') # dbg_print

        if self.connection:
            self.connection.close()
            self.dbg_print('Close connection successfully') # dbg_print
            self.connection = None
            
        self.tokenForHttpServer = ''
        
    def getTokenForHttpServer(self):
        return self.tokenForHttpServer
    
    def isConnected(self):
        return self.is_connected
    
    def caughtConnectionError(self):
        self.in_stopping = True
        self.is_connected = False


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

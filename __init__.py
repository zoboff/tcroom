from websocket import create_connection
import json
import logging
import threading
import time

PRODUCT_NAME = 'TrueConf Room'

class TerminalException(Exception):
    pass

def events_thread_function(name, terminal):
    print("Thread {}: starting".format(name))
    while not terminal.stop:
        # Receive 
        rcv_str = terminal.connection.recv()        
        #terminal.dbg_print('Received: {}'.format(rcv_str)) # dbg_print
        # json string to dictionary
        rcv_dict = json.loads(rcv_str)
        # event
        if "event" in rcv_dict:
            terminal.dbg_print('Event: {}'.format(rcv_dict["event"])) # dbg_print
            if rcv_dict["event"] == "appStateChanged":
                terminal.dbg_print('*** appStateChanged = {}'.format(rcv_dict["appState"])) # dbg_print

        time.sleep(0.1)

class Room:
    def __init__(self, debug_mode = False):
        self.stop = False
        self.debug_mode = debug_mode
        self.ip = ''
        self.address_request = ''
        self.connection = None
        self.events_thread = None
        
    def __del__(self):
        self.close_connection()

    def dbg_print(self, value: str) -> None:
        if self.debug_mode:
            print(value)
    
    def send_command_to_terminal(self, command: dict):
        if not self.connection:
            raise TerminalException('Connection to {} is not initialized. Run before: create_connection() '.format(PRODUCT_NAME))

        self.connection.send(json.dumps(command))
        self.dbg_print('Run command: {}'.format(str(command))) # dbg_print
        self.dbg_print('Received: {}'.format(self.connection.recv())) # dbg_print

    def auth(self, pin: str):
        if pin:
            command = {"method" : "auth","type" : "secured", "credentials" : pin}
        else:
            command = {"method" : "auth","type" : "unsecured"}
        # send
        self.send_command_to_terminal(command)
    
    def create_connection(self, ip: str, pin: str = None) -> None:
        self.ip = ip
        # Connect
        self.address_request = 'ws://{}:8765'.format(self.ip)
        try:
            self.connection = create_connection(self.address_request)
        except ConnectionRefusedError:
            raise TerminalException('Error connection to {}. IP="{}"'.format(PRODUCT_NAME, self.ip))
        
        self.dbg_print('{} connection "{}" successfully'.format(PRODUCT_NAME, self.address_request)) # dbg_print
        
        # Auth
        self.auth(pin)
        #self.connection.send(str)
        
        self.stop = False
        self.dbg_print('Received: {}'.format(self.connection.recv())) # dbg_print
        # start the events thread
        self.events_thread = threading.Thread(target=events_thread_function, args=("Events Thread", self))
        self.events_thread.start()
        self.dbg_print('Events Thread started') # dbg_print
        
    def close_connection(self):
        self.stop = True
        if self.events_thread:
            self.dbg_print('Finishing Events thread ...') # dbg_print
            self.events_thread.join()
            self.dbg_print('Events thread is finished') # dbg_print
            self.events_thread = None

        if self.connection:
            self.connection.close()
            self.dbg_print('Close connection successfully') # dbg_print
            self.connection = None

    def call(self, peerId: str) -> None:
        # make a command        
        command = {"method": "call", "peerId": peerId}    
        # send    
        self.send_command_to_terminal(command)
        
    def accept(self):
        # make a command        
        command = {"method" : "accept"}    
        # send    
        self.send_command_to_terminal(command)
                

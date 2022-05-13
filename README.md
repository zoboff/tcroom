**This module is deprecated, please use https://github.com/zoboff/pyVideoSDK**

# tcroom

TrueConf Room API python module.

## Install TrueConf Room

* Visit [Download TrueConf Room](install_trueconf_room.md)

## Python

Download page: [Python 3.8.6](https://www.python.org/downloads/release/python-386/)

## Install packages

Commands:
```
pip install websocket-client==0.58
pip install requests
```

## How to use

### 1. Launch the *TrueConf Room* application with *-pin* parameter.

Windows:
```
"C:\Program Files\TrueConf\Room\TrueConfRoom.exe" -pin "123"
```

Linux:
```
$ trueconf-room -pin "123"
```

TrueConf Room main window:
![screanroom3](https://user-images.githubusercontent.com/33928051/159042119-e29003e4-4f34-4f83-b7aa-344a3e752f37.png)

### 2. Create and run a python script

```python
import tcroom

room = tcroom.make_connection(pin = "<PIN>", room_ip = "<IP>", debug_mode = True)
room.call("<Your friend's TrueConf ID>")
```

Example:

```python
import tcroom

# Making a connection to the TrueConf Room application
room = tcroom.make_connection(pin = "123", room_ip = "192.168.31.62", debug_mode = True)
# Calling "Echotest"
room.call("echotest@trueconf.com") # "echotest" is almost constantly online
```

# tcroom

TrueConf Room API python module.

## Python

[Python 3.8.6](https://www.python.org/downloads/release/python-386/)

## Install:

install packages:
```
pip install websocket-client==0.58
pip install requests
```

## How to use

### 1. Start **TrueConf Room** application with **-pin** parameter.

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

### 2. Make a simple script

```python
import tcroom

room = tcroom.make_connection(pin = "<PIN>", room_ip = "<IP>", debug_mode = True)
room.call("<Your friend's TrueConf ID>")
```

Example:

```python
import tcroom

# Making a connection with TrueConf Room application
room = tcroom.make_connection(pin = "123", room_ip = "192.168.31.62", debug_mode = True)
# Calling "Echotest"
room.call("echotest@trueconf.com") # "echotest" is almost constantly online
```

# tcroom
This module use TrueConf Room API

# Install required modules
```
pip install websocket-client
pip install requests
```

# Usage

## Step 1
Start **TrueConf Room** application with **-pin** parameter.

Example of launching from the command line :
```
"C:\Program Files\TrueConf\Room\TrueConfRoom.exe" -pin "123"
```

## Step 2
```
import tcroom

room = tcroom.make_connection(pin='123', room_ip='127.0.0.1', debug_mode=True)
room.call('echotest@trueconf.com')
```

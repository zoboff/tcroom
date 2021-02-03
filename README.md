# tcroom
This module use TrueConf Room API

# Install required modules
```
pip install websocket-client
pip install requests
```

# Usage
```
import tcroom

room = tcroom.make_connection(pin='123', room_ip='127.0.0.1', debug_mode=True)
room.call('echotest@trueconf.com')
room.disconnect()
```

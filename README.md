This module uses TrueConf Room API

# Prerequisites

1. [Python 3.8.6](https://www.python.org/downloads/release/python-386/)
1. [pipenv](https://pipenv.pypa.io/en/latest/)


# Installation
```
pipenv install
```

# Usage

Start **TrueConf Room** application with **-pin** parameter.

Example of launching from the command line :
```
"C:\Program Files\TrueConf\Room\TrueConfRoom.exe" -pin "123"
```

Connect to TrueConf Room:

```
import tcroom

room = tcroom.make_connection(pin='123', room_ip='127.0.0.1', debug_mode=True)
room.call('echotest@trueconf.com')
```

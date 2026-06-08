# Internet-Measurement-Network

Run opensearch
```sh
$ cd opensearch && docker compose up
```

Start nats and other services
```sh
$ docker compose up
```

Manually Start agent (If needed. The above docker compose comes with 2 agents)
```sh
$ python3 -m pip install -e . --break-system-packages
$ python3 -m aiori_agent
```

Start Server
```sh
cd server
/usr/bin/python3 -m pip install -r ./server/requirements.txt --break-system-packages
/usr/bin/python3 -m fastapi run server/main.py 
```
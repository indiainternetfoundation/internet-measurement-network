# Internet-Measurement-Network

Run opensearch
```sh
$ cd opensearch && docker compose up
```

1. Login on Opensearch Dashboard with Username & Password (Written Below).
2. Go To Settings > Manage Data > Data Sources
3. Create a Data Source by Click "Create Data Source Connection" and Select Prometheus
4. configure with :
   - A Name for the connection
   - The Prothemeus URL - `http://<PROMETHEUS-CORTEX-IP:9090>/prometheus`
5. Create another Data Source for Opensearch
6. Configure it with :
   - A Name for the connection
   - The endpoint URL `https://<OPENSEARCH-IP>:9200/`
   - Username & Password (Written Below)

7. Create a Workspace with the created data sources (Opensearch and Prometheus).
8. Create Index Patterns :
   - "Log Dataset - Opensearch" : logs-otel-v1*
   - "Service Map - Opensearch" : otel-v2-apm-service-map*
   - "Traces - Opensearch" : otel-v1-apm-span*


Opensearch Creds :
- **User :** admin
- **Password :** My_password_123!@#

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
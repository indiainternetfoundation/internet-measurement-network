


```sh
$ pipx install openapi-python-client --include-deps
$ curl -o openapi.json http://localhost:8000/openapi.json
$ openapi-python-client generate --path openapi.json
$ openapi-python-client generate --url http://localhost:8000/openapi.json --output-path ./python/aiori
```
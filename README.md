# Coordimate - Backend

First make sure to create your local `.env` file with secret variables, that won't be uploaded to github:
```
cp .env.example .env
```
Now you can fill in the variables in `.env` as needed.

To get the API and the database containers up and running, run the following docker command:
```
docker compose up -d
```

Once the containers are up, you can access the API locally over the following links:
- Main API entry point: http://127.0.0.1:8000
- Autogenerated FastAPI docs: http://127.0.0.1:8000/docs
- Mongo-Express - database manager web GUI http://127.0.0.1:8081 (login: admin, password: pass)

To stop the API and the database containers run:
```
docker compose down
```

## Developing the Backend

Most changes to the Backend code will force the API server in the container to restart automatically.

To force the container with the backend API to rebuild run the command:
```
docker compose build web
```

To view the logs of the containers run:
```
docker compose logs
```


## Run the application locally to attach a debugger

Note: debugger can also be attached directly to the app running within a docker container

Make sure to modify the mongodb url in the `.env` file.
```bash
MONGODB_URL="mongodb://root:example@0.0.0.0:27017"
```

Add this section to the end of `routes.py` and run the api on the host machine with `python3 routes.py`.
```python
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
``` 


## Running tests

Run tests with
`pytest tests`

If you don't point `pytest` to the `tests/` directory, it will treat `mongodb/`
directory as a python module and fail.

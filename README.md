# Coordimate - Backend API

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

## Developing the Backend API

Most changes to the Backend API code will force the API server in the container to restart automatically.

To force the container with the backend API to rebuild run the command:
```
docker compose build web
```

To view the logs of the containers run:
```
docker compose logs
```

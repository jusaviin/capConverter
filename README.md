# NHL Cap Converter

This is a small test project for converting NHL cap hit to equivelent cap hit on another season based on fraction of the salary cap.

## Setting up the python environment

To test things locally, you will first need to create the production environment:

```
python3 -m venv capConverterEnvironment
source capConverterEnvironment/bin/activate
pip install -e ".[all]"
```

## Setting up local test database

You will need to have your local PostgreSQL database running to be able to run this app. Instructions on how to manage the database are in the `README.md` file in `database_management` folder.

## Running the app


Once the environment is setup, you can run the debug server

```
python3 app.py
```

of test the production server

```
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

Once either of these servers are running, you can open the app in your favorite browser. Here are the addresses based on server type.

```
http://127.0.0.1:5000  # debug
localhost:8000         # production
```

## Unit tests

There are some unit tests for sanity purposes. If you are afraid you are going to break something, good to run the tests using command

```
python -m unittest discover -s tests -v
```

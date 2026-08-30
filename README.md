# NHL Cap Converter

This is a small test project for converting NHL cap hit to equivelent cap hit on another season based on fraction of the salary cap. To test things locally, you will first need to create a production environment

```
python3 -m venv capConverterEnvironment
source capConverterEnvironment/bin/activate
pip install -r requirements.txt
```

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

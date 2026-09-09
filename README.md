# NHL Cap Converter

This is a small test project for converting NHL cap hit to equivelent cap hit on another season based on fraction of the salary cap.

## Setting up the python environment

To test things locally, you will first need to create the production environment:

```
python3 -m venv capConverterEnvironment
source capConverterEnvironment/bin/activate
pip install -r requirements.txt
```

## Setting up local test database

The app reads data from PostgreSQL database. This choise was made because it is free and widely available when deploying to a server. You will need to complete the following steps to get the database running in your own computer.

1. Install PostgreSQL

On Mac, this can be easily done with Homebrew:

```
brew install postgresql
```

2. Start PostgreSQL server

Again, the instruction here is Mac-specific assuming you installed PostgreSQL via Homebrew.

```
brew services start postgresql@18
```

Note: you can stop the PostgreSQL server with command

```
brew services stop postgresql@18
```

Remember to adjust the PostgreSQL version to whichever version you are using.

3. Create a new database

```
createdb nhldb
psql -d nhldb -f databaseSchema_postgres.sql
```

4. Add the database URL to .env file

The exact line you need to add is

```
POSTGRES_URL=postgresql://username:password@localhost:5432/nhldb
```

If you ran these commands from the terminal, the username and password default to your regular terminal username and password

5. Fill the database

I am eventually combining this project with https://github.com/jusaviin/nhlAnalyzer. I am just using the database created with that project but converted from SQLite to PostgreSQL. Check the other project for now for instructions on how to fill the database.

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


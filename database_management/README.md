# Updating the existing database

This folder contains the infrastructure to update the tables in the existing database

## Update the cities table

First find all player home cities from NHL API and save them to a json file:

```
python3 createCityLocationFile.py
```

There are some formatting issues in NHL API. Run a script to fix them:

```
./trimCityNames.sh cityCoordinatesUpdatedAgain.json nhlPlayerHomeTownsFrom2008To2026.json
```

Once you have the cleaned json file, run the update script to register everything to the database:

```
python3 updateTables.py --tables cities
```

## Update the contracts table

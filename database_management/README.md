# Database management

This folder contains the infrastructure to create a new database and to update the tables in the existing database.

## Create a new database

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
psql -d nhldb -f viewSchema_postgres.sql
```

The first command creates a new Postgres database object and the other two commands define the tables and views that the app needs.

For remote databases, the commands to run to get the tables running are

```
psql "postgresql://username:password@remotehost:5432/dbname" -f databaseSchema_postgres.sql
psql "postgresql://username:password@remotehost:5432/dbname" -f viewSchema_postgres.sql
```

4. Add the database URL to .env file

The exact line you need to add is

```
POSTGRES_URL=postgresql://username:password@localhost:5432/nhldb
```

If you ran these commands from the terminal, the username and password default to your regular terminal username and password. If you are hosting a database on server, you also want to add:

```
REMOTE_URL=postgresql://username:password@remotehost:5432/dbname
```

You should be able to find this URL from whichever service you use to host your remote database. The scripts in this folder have been written in such a way that they can reach databases in both `POSTGRES_URL` and `REMOTE_URL`. 

5. Fill the database

The update scripts described below can be used also for the initial data input for the database. Notice then when using those scripts, you will need to follow a specific order in filling the tables to honor foreign key constraints or else the data input will fail.

## Update data in your database

This project reads information from several different sources. Much of the information comes from [NHL API](https://pypi.org/project/nhl-api-py/). All contract related data is provided by [CapWages API](https://capwages.com). All stats come from csv files than can be freely downloaded from [MoneyPuck](https://moneypuck.com/data.htm). The city coordinates are located using `Nominatim` from `geopy.geocoders`. There are still gaps in the data after all this, which I mainly supplement from [Wikipedia](https://en.wikipedia.org/wiki/Main_Page). This all gets a bit complicated, especially when combined with foreign key constraints in the tables. You must follow the below recipe in order to be able to successfully fill your database.

Note about the usage of the `updateTables.py` script. By default the script updates the database defined in environment variable `POSTGRES_URL`. If you pass it the flag `--remote`, it updates the database in `REMOTE_URL` instead. The instructions are only written without the `--remote` flag, just be aware that it is there available if you want it.

### Update the cities table

First find all player home cities from NHL API and save them to a json file. The script also geolocates the home cities such that we know the latitude and longitude of each city.

```
python3 createCityLocationFile.py
```

By default the city locations are only created for the current season. There are command line flags you can use to search also past seasons. Just run the command with --help flag and it will tell you what to do.

There are some formatting issues in NHL API. Run a script to fix them:

```
./trimCityNames.sh cityCoordinatesUpdatedAgain.json nhlPlayerHomeTownsFrom2008To2026.json
```

Once you have the cleaned json file, run the update script to register everything to the database:

```
python3 updateTables.py --tables cities
```

### Update the seasons table

All the season information is manually inserted via `NHLSeasonData` class in `manualDataEntry.py`. Thus when this is run once, you only need to rerun it if the information in this file is altered.

```
python3 updateTables.py --tables seasons
```

### Update the teams table

Much of the data to this table comes from `NHLTeamData` class in `manualDataEntry.py`, but some information about the teams is also read from NHL API. To update the teams for the current season, run the command

```
python3 updateTables.py --tables teams
```

Teams from 2008-2009 season are available in `NHLTeamData` class. To add older teams to the table, give arguments to the script to select previous seasons. Run the command with `--help` to learn more.

### Update the players table

Before players can have contracts or stats, they need to be in their own table. The bulk of the player information comes from NHL API. You can update all the information coming from the NHL API with the command

```
python3 updateTables.py --tables players
```

By default it updates all players from the current season. If you need previous seasons, please use --help argument and the script tells you how to do that.

Nationality of the players is not available from the NHL API. I use MoneyPuck player biography file to fill the nationality for the players. You can download it using the downloader in `moneyPuck` folder

```
cd moneyPuck
./moneyPuckDownloader.sh -b
cd ..
```

This creates a `playerBiography.csv` file to `moneyPuck` folder. Using this file, you can update nationalities for the players:

```
python3 updateTables.py --tables nationalities
```

Unfortunately there will be gaps in nationalities here, since the MoneyPuck does not have nationality information for all the players that are available in NHL API. You can find the list of players without a nationality in the database with the command

```
psql -d nhldb -c "SELECT id, first_name, last_name, birth_city FROM players WHERE nationality IS NULL;" > missingNationalities.txt
```

You will then need to create a csv file for these players to get the nationality information in. Doing this by hand gives the best results, but any AI agent is happy to help you if you give it an example format for the csv file and ask to transform the `missingNationalities.txt` file to a csv file `missingNationalities.csv`. Here is an example format the csv file needs to be in:

```
playerId,name,nationality
8459424,Chris Pronger,CAN
```

Here `name` column is optional, but makes it easier to check for human. Once you have the file in this format, update the missing nationalities to the database.

```
python3 updateTables.py --tables nationalities --nationalityfile moneyPuck/missingNationalities.csv
```

### Update statistics tables

There are three different tables for statistics in the database, one for skaters, one for goalies, and one for teams. They are all filled from MoneyPuck csv files. The first step to do is to obtain these csv files. These can be downloaded using `moneyPuckDownloader.sh`:

```
cd moneyPuck
./moneyPuckDownloader.sh -r
cd ..
```

The command here download the tables for current regular season. Please use the flag `-h` or `--help` to see all arguments. You will be able to download the files from past seasons until 2008-2009 season, and also for playoffs by defining different arguments for the script. After running the script, you should see files like `teams_2026_regular.csv`, `skaters_2026_regular.csv`, and `goalies_2026_regular.csv` appear to the `moneyPuck` folder. Once you have these, you can update the statistics tables:

```
python3 updateTables.py --tables all-stats --regular
```

As always, by default this command only fills the stats for the current season. See `--help` for all available option and how to fill also the tables individually, or the tables for playoffs.

The script warns you if some fills fail because the player for whom you are trying to fill the stats are missing from the players table. This can happen because sometimes players who have only played a handful of NHL games are not listed in the team roster in NHL API, but anyone who has played in a game is included in the MoneyPuck tables. You can find all the misses from created log files, for example `skipped_skater_season_stats.log`. To include these players to the tables, you need to run the `updateTables.py` and possibly also `createCityLocationFile.py` with specific arguments.

```
# Run these if the new players' home cities are missing from the table
python3 createCityLocationFile.py --logfile skipped_skater_season_stats.log
./trimCityNames.sh cityCoordinatesUpdatedAgain.json nhlPlayerHomeTownsFrom2008To2026.json
python3 updateTables.py --tables cities

# Run this to update the players table
python3 updateTables.py --tables players --logfile skipped_skater_season_stats.log
python3 updateTables.py --tables nationalities 

# Then check for missing nationalities and continue as normal with statistics fills. It is likely you will need to add nationalities manually for these fills.
```

### Update the contracts table

Finally, when you have the players data solidly in place, you can fill the contracts table. The contracts data comes from [CapWages API](https://capwages.com), and you will need to get an API key stored in environment variable `API_KEY` for the contract update to work. If you have made a lot of changes to the players table, it is probably worth running the update over all the contracts in the API:

```
python3 updateTables.py --tables contracts
```

By default all contracts are updated, and this process is likely to take a few hours. Later you should only run this for newly added players or newly added contracts. You can track which contracts are added to [CapWages API](https://capwages.com) from their Discord server. You can give a `--slugfile` argument to give a file which has one CapWages player slug (format firstname-lastname) in each line. Then the contracts are updated only for players whose slugs are on this file

```
python3 updateTables.py --tables contracts --slugfile slugs_to_update.txt
```

### Be happy

It is a bit of a struggle to keep the database updated as there are a lot of data sources you need to keep tracking. But if you have made it all the way down here, you should have a working database! Now it is time to be happy and fire your app!

## Copy local tables to remote database

When updating the whole players table or the whole contracts table, the procedure can take hours since API reads sleep for 1 second after each request. Please be polite and do not alter this in the code, it is rude to overwhelm APIs with a bunch of requests. If you have already ran an hours long operation to update your local database, you might not want to repeat this for the remote database. To solve this, this repository offers a table copy functionality where you are able to make a remote table and exact copy of a local table. This procedure takes away the API lag and makes things much faster. To use this functionality, run:

```
python3 promoteTables.py --tables contracts
```

The above command would promote the local contracts table to remote. You can run this for any database table, run the command with `--help` argument to learn more.

## Altering the database

Sometimes there is a need to do some patching up the database manually in a fashion that is not covered by the scripts. In these cases, write your SQL commands to a file following the example in `example_database_alter.sql`. Then run this command using

```
psql "DATABASE_URL" -f example_database_alter.sql
```

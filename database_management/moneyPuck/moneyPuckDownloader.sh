#!/opt/homebrew/bin/bash

# Download all the MoneyPuck data used in this project

# Define the current season and the first season MoneyPuck has data for
CURRENTYEAR=2026
FIRSTAVAILABLEYEAR=2008

# Usage instructions for the script
usage() {
  echo "Usage of the script:"
  echo "$0 [-h] [-r] [-p] [-b] [-f YEAR] [-l YEAR]"
  echo "-h, --help      = Print this usage information"
  echo "-r, --regular   = Download regular season csv files"
  echo "-p, --playoffs  = Download playoff csv files"
  echo "-b, --biography = Download the player biography csv file (playerBiography.csv)"
  echo "-f, --firstyear = First year to download (${FIRSTAVAILABLEYEAR}-${CURRENTYEAR}, default: ${CURRENTYEAR})"
  echo "-l, --lastyear  = Last year to download (${FIRSTAVAILABLEYEAR}-${CURRENTYEAR}, default: ${CURRENTYEAR})"
  echo "Please activate at least one of -r, -p or -b. Otherwise nothing will be downloaded."
}

if [ "$#" -lt 1 ]; then
  usage
  exit
fi

# Defaults: nothing is downloaded unless activated by a flag, years default to the current season
REGULAR=false
PLAYOFFS=false
BIOGRAPHY=false
FIRSTYEAR=${CURRENTYEAR}
LASTYEAR=${CURRENTYEAR}

# Read the optional arguments (short and long forms)
while [ "$#" -gt 0 ]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    -r|--regular)
      REGULAR=true
      shift
      ;;
    -p|--playoffs)
      PLAYOFFS=true
      shift
      ;;
    -b|--biography)
      BIOGRAPHY=true
      shift
      ;;
    -f|--firstyear)
      if [ "$#" -lt 2 ]; then
        echo "Option $1 requires a year as argument" >&2
        exit 1
      fi
      FIRSTYEAR="$2"
      shift 2
      ;;
    --firstyear=*)
      FIRSTYEAR="${1#*=}"
      shift
      ;;
    -l|--lastyear)
      if [ "$#" -lt 2 ]; then
        echo "Option $1 requires a year as argument" >&2
        exit 1
      fi
      LASTYEAR="$2"
      shift 2
      ;;
    --lastyear=*)
      LASTYEAR="${1#*=}"
      shift
      ;;
    *)
      echo "Invalid option $1" >&2
      usage
      exit 1
      ;;
  esac
done

# Validate the years
for YEARVALUE in "$FIRSTYEAR" "$LASTYEAR"; do
  if ! [[ "$YEARVALUE" =~ ^[0-9]{4}$ ]]; then
    echo "Invalid year '$YEARVALUE': years must have four digits" >&2
    exit 1
  fi
  if [ "$YEARVALUE" -lt "$FIRSTAVAILABLEYEAR" ] || [ "$YEARVALUE" -gt "$CURRENTYEAR" ]; then
    echo "Invalid year '$YEARVALUE': years must be between ${FIRSTAVAILABLEYEAR} and ${CURRENTYEAR}" >&2
    exit 1
  fi
done

if [ "$FIRSTYEAR" -gt "$LASTYEAR" ]; then
  echo "The first year ($FIRSTYEAR) cannot be after the last year ($LASTYEAR)" >&2
  exit 1
fi

if ! $REGULAR && ! $PLAYOFFS && ! $BIOGRAPHY; then
  echo "None of -r, -p or -b was given, so nothing will be downloaded."
  exit
fi

# Download the player biography file (not tied to a season, so it is downloaded only once)
# Sleep 1 second after the request to be polite and not overwhelm the servers
if $BIOGRAPHY; then
  curl -L -H "User-Agent: Mozilla/5.0" -o "playerBiography.csv" "https://moneypuck.com/moneypuck/playerData/playerBios/allPlayersLookup.csv"
  sleep 1
fi

# Download all files for the selected years
# Sleep 1 second after each request to be polite and not overwhelm the servers
for ((YEAR = FIRSTYEAR ; YEAR <= LASTYEAR ; YEAR++)); do
  if $REGULAR; then
    curl -L -H "User-Agent: Mozilla/5.0" -o "skaters_${YEAR}_regular.csv" "https://moneypuck.com/moneypuck/playerData/seasonSummary/${YEAR}/regular/skaters.csv"
    sleep 1
    curl -L -H "User-Agent: Mozilla/5.0" -o "goalies_${YEAR}_regular.csv" "https://moneypuck.com/moneypuck/playerData/seasonSummary/${YEAR}/regular/goalies.csv"
    sleep 1
    curl -L -H "User-Agent: Mozilla/5.0" -o "teams_${YEAR}_regular.csv" "https://moneypuck.com/moneypuck/playerData/seasonSummary/${YEAR}/regular/teams.csv"
    sleep 1
  fi

  if $PLAYOFFS; then
    curl -L -H "User-Agent: Mozilla/5.0" -o "skaters_${YEAR}_playoffs.csv" "https://moneypuck.com/moneypuck/playerData/seasonSummary/${YEAR}/playoffs/skaters.csv"
    sleep 1
    curl -L -H "User-Agent: Mozilla/5.0" -o "goalies_${YEAR}_playoffs.csv" "https://moneypuck.com/moneypuck/playerData/seasonSummary/${YEAR}/playoffs/goalies.csv"
    sleep 1
    curl -L -H "User-Agent: Mozilla/5.0" -o "teams_${YEAR}_playoffs.csv" "https://moneypuck.com/moneypuck/playerData/seasonSummary/${YEAR}/playoffs/teams.csv"
    sleep 1
  fi
done

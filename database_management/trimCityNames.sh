#!/opt/homebrew/bin/bash

if [ "$#" -lt 1 ]; then
  echo "Trim city names in an input file manually to be what I personally think they should be"
  echo "Usage of the script:"
  echo "$0 inputFile outputFile"
  echo "inputFile = json file with city names that need to be manually fixed"
  echo "outputFile = json file with city names that are manually fixed"
  echo "If outputFile is not specified, inputFile is directly modified"
  exit
fi

# Read the user input
INPUTFILE=$1
OUTPUTFILE="${2:-${INPUTFILE}}"

# If output file is specified, copy the input file to output file
if [ "$#" -gt 1 ]; then
  cp $INPUTFILE $OUTPUTFILE
fi

# Check which operating system we are using
# The sed command takes different arguments for Mac and Linux, so we need to adjust that accordingly
OS=$(uname)

# Note that sed arguments have to be provided in an array for the shell to expand the variables correctly
SEDARGS=(-i)
if [ "$OS" == "Darwin" ]; then
  # For Mac, we specify that no backup file is needed with the argument ''
  # For Linux, '' is not a valid argument, so it this should only be there for Mac
  SEDARGS+=("")
fi

# Make the manual city name modifications to the output file
sed "${SEDARGS[@]}" "s# Charter Township##" ${OUTPUTFILE}
sed "${SEDARGS[@]}" "s# Township##" ${OUTPUTFILE}
sed "${SEDARGS[@]}" "s# municipality##" ${OUTPUTFILE}
sed "${SEDARGS[@]}" "s# County##" ${OUTPUTFILE}
sed "${SEDARGS[@]}" "s# Peninsula##" ${OUTPUTFILE}
sed "${SEDARGS[@]}" "s#Montée de l'Église#L'Île-Bizard#" ${OUTPUTFILE}
sed "${SEDARGS[@]}" "s#City of ##" ${OUTPUTFILE}
sed "${SEDARGS[@]}" "s#Village of ##" ${OUTPUTFILE}
sed "${SEDARGS[@]}" "s#Town of ##" ${OUTPUTFILE}
sed "${SEDARGS[@]}" "s#Rural Municipality of ##" ${OUTPUTFILE}
sed "${SEDARGS[@]}" "s#Municipal District of ##" ${OUTPUTFILE}
sed "${SEDARGS[@]}" "s#Hamlet of ##" ${OUTPUTFILE}
sed "${SEDARGS[@]}" "s# Municipality##" ${OUTPUTFILE}
sed "${SEDARGS[@]}" "s# District##" ${OUTPUTFILE}
sed "${SEDARGS[@]}" "s#bergs kommun#berg#" ${OUTPUTFILE}
sed "${SEDARGS[@]}" "s#ryds kommun#ryd#" ${OUTPUTFILE}
sed "${SEDARGS[@]}" "s#sunds kommun#sund#" ${OUTPUTFILE}
sed "${SEDARGS[@]}" "s#dals kommun#dal#" ${OUTPUTFILE}
sed "${SEDARGS[@]}" "s#röms kommun#röm#" ${OUTPUTFILE}
sed "${SEDARGS[@]}" "s#älvs kommun#älv#" ${OUTPUTFILE}
sed "${SEDARGS[@]}" "s# kommun##" ${OUTPUTFILE}
sed "${SEDARGS[@]}" "s# distrikt##" ${OUTPUTFILE}
sed "${SEDARGS[@]}" "s# Kommune##" ${OUTPUTFILE}
sed "${SEDARGS[@]}" "s#Local\": \"Québec\"#Local\": \"Ville de Québec\"#" ${OUTPUTFILE}
sed "${SEDARGS[@]}" "s#English\": \"Quebec\"#English\": \"Quebec City\"#" ${OUTPUTFILE}
sed "${SEDARGS[@]}" "s# (région administrative)##" ${OUTPUTFILE}
sed "${SEDARGS[@]}" "s# (administrative region)##" ${OUTPUTFILE}
sed "${SEDARGS[@]}" "s#Héliport, Sainte-Agathe (Aim)#Sainte-Agathe#" ${OUTPUTFILE}
sed "${SEDARGS[@]}" "s#Ste-Agathe (Aim) Heliport#Ste-Agathe#" ${OUTPUTFILE}
sed "${SEDARGS[@]}" "s#городской округ ##" ${OUTPUTFILE}
sed "${SEDARGS[@]}" "s# (Blue Yonder) Airport##" ${OUTPUTFILE}
sed "${SEDARGS[@]}" "s#Arrondissement de ##" ${OUTPUTFILE}
sed "${SEDARGS[@]}" "s#Greater ##" ${OUTPUTFILE}
sed "${SEDARGS[@]}" "s#Grad ##" ${OUTPUTFILE}
sed "${SEDARGS[@]}" "s#Landkreis ##" ${OUTPUTFILE}
sed "${SEDARGS[@]}" "s#ᒨᓱᓃᐎ ᒥᓂᔅᑎᒃ ##" ${OUTPUTFILE}
sed "${SEDARGS[@]}" "s# (MRC)##" ${OUTPUTFILE}
sed "${SEDARGS[@]}" "s# (town)##" ${OUTPUTFILE}
sed "${SEDARGS[@]}" "s# (BE)##" ${OUTPUTFILE}
sed "${SEDARGS[@]}" "s# (Charlie Sinclair Memorial) Airport##" ${OUTPUTFILE}
sed "${SEDARGS[@]}" "s#Kaltern an der Weinstraße - Caldaro sulla Strada del Vino#Caldaro#" ${OUTPUTFILE}
sed "${SEDARGS[@]}" "s#Jakobstad#Pietarsaari#" ${OUTPUTFILE}
sed "${SEDARGS[@]}" "s#Nykarleby#Uusikaarlepyy#" ${OUTPUTFILE}

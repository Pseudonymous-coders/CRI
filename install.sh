#!/bin/bash

# Define the variables
CTEMP=/tmp
CGLOBS=$CTEMP/globs
URL="https://raw.githubusercontent.com/Pseudonymous-coders/CRI/master"
URLR="https://raw.githubusercontent.com/Pseudonymous-coders/CRI-resources/master"
CONFIGS="$URLR/configs"
GLOBS="$CONFIGS/globs"

# Pull the latest globs functions
sudo mkdir -p $CGLOBS
cd $CGLOBS
sudo curl -Ls "$GLOBS/globvar" -o $CGLOBS/globvar
sudo curl -Ls "$GLOBS/globfun" -o $CGLOBS/globfun
sudo curl -Ls "$CONFIGS/install_list.txt" -o $CTEMP/install_list.txt
sudo chmod 755 $CGLOBS/globvar $CGLOBS/globfun

# Clear the screen and begin the download
clear
source globvar
source globfun

echo "Welcome to the CRI installer!
Created By: $AUTHORS
Version: $VERSION
Url: $URL

System:
User: $USER
Arch: $ARCH
"
sleep 1

if [[ $ARCH != "i686" ]] && [[ $ARCH != "x86_64" ]]; then # Check if chromebook is compatible
  printf "Your device doesn't support CRI yet! :(\nExiting..."
  sleep 0.5
  exit 1
fi

printf "This installation will require internet conection\n\n"

if ask "Are you comfortable waiting a little bit"; then
    echo "Continuing..."
else
    echo "Exiting..."
    exit 1
fi

echo "Creating working directories..."
sudo mkdir -p $CTEMP $CPKG $CBUILD
sudo chown $USER:$USER $CTEMP $CPKG $CBUILD
PKGURL=$CONFIGS/libs

cd $CTEMP
printf "\nDownloading core files\n\n..." 
sudo chmod 755 install_list.txt #Makes the commands file have every permisson so that anyone can use it 
NAMES="$(< install_list.txt)" #names from names.txt file
LINES=$(lineCount)
NUMBERS=1

cd $CPKG

for NAME in $NAMES; do #Downloads all nessisary files from github to /usr/local/bin
    clear
    printf "Welcome to the CRI installer\nCreated By: $AUTHORS\nVersion: $VERSION\nFile $NUMBERS/$LINES...\n\n ${NAME##*/} \n"
    let "NUMBERS += 1"
    sudo curl -Ls "$PKGURL/$NAME" -o $CPKG/${NAME##*/}
    sudo chmod 755 *
    sudo chown $USER:$USER ${NAME##*/}
    sudo bash ${NAME##*/} # Run setup in seperate thread 
    fixowner 2&>/dev/null
done

wait # Wait for threads to update

clear

echo "Cleaning up everything..."

sudo rm -rf $CPKG
sudo rm -rf $CBUILD

echo "Thank you for installing CRI!"

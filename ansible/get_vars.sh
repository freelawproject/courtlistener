#!/usr/bin/env bash

# This script is needed because Ansible doesn't have a sane way of getting the
# value of a variable that's in a bash script. If it's in a yaml file? Fine. A
# json file? Sure. But a bash script? Impossible!

source /etc/courtlistener

# This code says, assign the first argument to this script to the variable v.
# Then, print the variable with the name of the value of v.
# More info: https://stackoverflow.com/questions/1921279/
v=$*
echo ${!v}

#!/bin/bash
# Build all docker images

cd "$(dirname "$0")"

# Build socket server
cd socketServer
./dockerize.bash
cd ..

# Build web server
cd webServer
./dockerize.bash
cd ..

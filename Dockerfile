# Set the base image
FROM ubuntu:22.04

# Update the package list and install Python
RUN apt-get update && apt-get install -y nodejs python3 python3-venv python3-pip npm

# Set the working directory
WORKDIR /app

RUN ln -s /usr/bin/python3 /usr/bin/python

# Copy the current directory contents into the container at /app
COPY . /app

WORKDIR /app/client

RUN npm install
RUN npm install -g grunt-cli
RUN grunt copy:sources

WORKDIR /app/backend

ENV PATH="/usr/bin/python3:${PATH}"
# ENV PATH=$PATH:$HOME/.local/bin

# RUN python3 -m venv .venv
# RUN . ./.venv/bin/activate
RUN pip3 install -r requirements/requirements-jammy.txt
# EXPOSE 8082 
RUN alias python='python3'
CMD ["bin/globaleaks"," -z","-n"]
# CMD ['pwd']
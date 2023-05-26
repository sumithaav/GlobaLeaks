# Set the base image
FROM ubuntu:22.04

RUN apt-get update && apt-get install -y nodejs python3 python3-venv python3-pip npm

WORKDIR /app

RUN ln -s /usr/bin/python3 /usr/bin/python

COPY . /app

WORKDIR /app/client

RUN npm install
RUN npm install -g grunt-cli
RUN grunt copy:sources

WORKDIR /app/backend

ENV PATH="/usr/bin/python3:${PATH}"

RUN pip3 install -r requirements/requirements-jammy.txt

RUN alias python='python3'

WORKDIR /app

CMD ["/backend/bin/globaleaks"," -z","-n"]

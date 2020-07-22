#!/usr/bin/env bash

SERVER=elastic:9200
WAIT_LOOPS=10
WAIT_SLEEP=5
WAIT_COMMAND='curl --write-out %{http_code} --silent --output /dev/null http://elastic:9200/_cat/health?h=st'
START_COMMAND='/usr/local/bin/gunicorn -k gevent --reload --workers 10 --worker-connections 10 --access-logfile=- --pythonpath /app -b :5000 server:app'

BASE=$(cd `dirname $0` && echo $PWD)

# wait for Elastic?
if [ "`grep -v '#' $BASE/config.yml | grep 'index:'`" != "" -a "`grep -v '#' $BASE/config.yml | egrep 'type:[ \t]+elastic'`" != "" ] ; then
    # wait for Elastic
    echo "Waiting for elastic ..."
    i=0
    while [ "`$WAIT_COMMAND`" != "200" ]; do
        i=`expr $i + 1`
        if [ $i -ge $WAIT_LOOPS ]; then
            echo "$(date) - still not ready, giving up"
            exit 1
        fi
        echo "$(date) - $i waiting to be ready"
        sleep $WAIT_SLEEP
    done
fi

$START_COMMAND


FROM python:3.7

COPY requirements.txt /
RUN pip install --no-cache-dir -r /requirements.txt

EXPOSE 5000

ADD . /app

VOLUME /data/archive

CMD /usr/local/bin/gunicorn -k gevent --reload --workers 5 --access-logfile=- --pythonpath /app -b :5000 server:app


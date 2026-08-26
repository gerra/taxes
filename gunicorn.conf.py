"""Gunicorn config for the taxes Flask app.

`timeout` covers the synchronous calculation endpoint: a full cgt-calc run over
15 years of history (including HMRC exchange-rate fetches on a cold cache) can
take a couple of minutes; gunicorn's 30s default would kill the worker mid-run.

Wired up via systemd: ExecStart=.../gunicorn -c gunicorn.conf.py app:app
"""

bind = "127.0.0.1:5002"
workers = 2
timeout = 300
accesslog = "-"
errorlog = "-"

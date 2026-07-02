"""
Gunicorn configuration for CarTracker backend.

OTP and geofence state are stored in process memory, so we run a single
worker process with threads for concurrency. This is sufficient for a
fleet platform with tens of concurrent users.
"""
import multiprocessing

# Single process keeps shared in-memory state (OTP store, geofence state).
workers = 1
worker_class = "gthread"
threads = multiprocessing.cpu_count() * 2 + 1

bind = "127.0.0.1:8000"
timeout = 60
keepalive = 5

# Logging
accesslog = "/var/log/cartracker/access.log"
errorlog  = "/var/log/cartracker/error.log"
loglevel  = "info"
access_log_format = '%(h)s "%(r)s" %(s)s %(b)s %(D)sµs'

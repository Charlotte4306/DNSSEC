# A single worker owns the lab lock/state; threads keep polling responsive.
bind = "127.0.0.1:18766"
workers = 1
worker_class = "gthread"
threads = 8
timeout = 180
graceful_timeout = 180
preload_app = False
forwarded_allow_ips = "127.0.0.1"
accesslog = "-"
errorlog = "-"
capture_output = True

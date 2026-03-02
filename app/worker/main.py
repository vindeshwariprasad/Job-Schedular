from worker.worker import worker_loop
from queues.redis_client import redis_client
from prometheus_client import start_http_server

if __name__ == "__main__":
    start_http_server(9101)
    worker_loop(redis_client)

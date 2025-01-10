SQLALCHEMY_DATABASE_URI = 'postgresql://rvcodehub_user:helloMERL@localhost:5433/rvcodehubdb'  # For PostgreSQL
CELERY_BROKER_URL = 'redis://localhost:6379/0'  # Or your broker URL
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'  # Or your result backend
# Celery configuration
CELERYD_TASK_SOFT_TIME_LIMIT = 3600  # 1 hour soft time limit
CELERYD_TASK_TIME_LIMIT = 7200  # 2 hours hard time limit
# Prevent worker from restarting after completing too many tasks
CELERY_WORKER_MAX_TASKS_PER_CHILD = None
# Set concurrency to prevent workers from being too aggressive in parallel processing
CELERY_WORKER_CONCURRENCY = 1  # Adjust as needed based on your resources
CELERY_ALWAYS_EAGER = False
CELERY_ACCEPT_CONTENT=['json']
CELERY_TASK_SERIALIZER='json'
CELERY_RESULT_SERIALIZER='json'
CELERY_TASK_RESULT_EXPIRES = None  # Disable expiry
from kombu import Exchange, Queue
CELERY_TASK_QUEUES = (
    Queue('run_sbt', Exchange('run_sbt'), routing_key='run_sbt'),
    Queue('run_rvv', Exchange('run_rvv'), routing_key='run_rvv'),
)
CELERY_TASK_ROUTES ={
    'app.celery.run_sbt':          {'queue': 'run_sbt'},
    'app.celery.run_rvv':          {'queue': 'run_rvv'},
}
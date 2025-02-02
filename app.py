from flask import Flask, request, jsonify
from celery import Celery, Task
import os, time
import subprocess
from celery.result import AsyncResult
from flask_cors import CORS
import redis
from celery import current_task
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.types import Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from icecream import ic

from lib import run_and_compare

app = Flask(__name__)
app.config.from_object('config')
CORS(app)

redis_client = redis.Redis(host='localhost', port=6379, db=0)

class CustomTask(Task):
    def apply_async(self, *args, **kwargs):
        task = super().apply_async(*args, **kwargs)
        redis_client.rpush('celery', task.id)
        return task

def make_celery(app):
    celery = Celery(
        app.import_name,
        broker=app.config['CELERY_BROKER_URL'],
        backend=app.config['CELERY_RESULT_BACKEND']
    )
    celery.conf.update(app.config)
    celery.Task = CustomTask
    return celery

celery = make_celery(app)

db = SQLAlchemy(app)



class Languages(db.Model):
    __tablename__ = 'core_languages'
    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False)

    def __str__(self):
        return self.name

class QuestionGroup(db.Model):
    __tablename__ = 'questions_questiongroup'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)

    def __str__(self):
        return self.name

class Question(db.Model):
    __tablename__ = 'questions_question'
    id = Column(Integer, primary_key=True)
    title = Column(String(100), default='Untitled Question')
    question = Column(Text, nullable=False)
    question_group_id = Column(Integer, ForeignKey('questions_questiongroup.id'), nullable=False)
    language_id = Column(Integer, ForeignKey('core_languages.id'), default=1)
    test_case = Column(Text, nullable=True)
    answer_template = Column(Text, nullable=True)

    question_group = relationship('QuestionGroup', back_populates='questions')
    language = relationship('Languages')

    def __str__(self):
        return self.title

QuestionGroup.questions = relationship('Question', order_by=Question.id, back_populates='question_group')

class User(db.Model):
    __tablename__ = 'auth_user'
    id = Column(Integer, primary_key=True)
    username = Column(String(50), nullable=False)

    def __str__(self):
        return self.username

class Submission(db.Model):
    __tablename__ = 'questions_submission'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('auth_user.id'), nullable=False)
    question_id = Column(Integer, ForeignKey('questions_question.id'), nullable=False)
    code = Column(Text, nullable=False)
    language_id = Column(Integer, ForeignKey('core_languages.id'), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    test_status = Column(Boolean, default=False)

    question = relationship('Question')
    language = relationship('Languages')
    user = relationship('User')

    def __str__(self):
        return f"{self.user.username} - {self.question.title}"

class Contest(db.Model):
    __tablename__ = 'questions_contest'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('auth_user.id'), nullable=False)
    question_group_id = Column(Integer, ForeignKey('questions_questiongroup.id'), nullable=False)
    start_time = Column(DateTime, nullable=True)
    duration = Column(Integer, default=3600)  # Duration in seconds, default 60 minutes

    user = relationship('User')
    question_group = relationship('QuestionGroup')

    def __str__(self):
        return f"Contest by {self.user.username} for {self.question_group.name}"

@celery.task(bind=True)
def run_chisel_task(self, chisel_code, test_case, user_id, question_id, language_id):
    current_task.update_state(state='STARTED', meta={'task_type': 'sbt'})
    chisel_template_dir = 'chisel-template'
    chisel_file_path = os.path.join(chisel_template_dir, 'src/main/scala/ChiselCode.scala')
    test_file_path = os.path.join(chisel_template_dir, 'src/test/scala/TestCase.scala')

    with open(chisel_file_path, 'w') as chisel_file:
        chisel_file.write(chisel_code)

    with open(test_file_path, 'w') as test_file:
        test_file.write(test_case)

    try:
        process = subprocess.Popen(
            ['sbt', 'test'], cwd=chisel_template_dir,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )

        test_status = True  # Default to true, will change if the process fails
        return_log = {'status': 'PASSED', 'output': ''}
        logList = ["SBT running....\n"]
        current_task.update_state(state='STARTED', meta={'task_type': 'sbt', "logList":"".join(logList)})
        # Print stdout in real-time
        for line in process.stdout:
            print(line, end="")  # Print each line as it appears
            return_log['output'] += line  # Store output
            logList.append(line)
            current_task.update_state(state='STARTED', meta={'task_type': 'sbt', "logList":"".join(logList)})

        # Print stderr in real-time
        for line in process.stderr:
            print(line, end="")
            return_log['output'] += line
            logList.append(line)
            current_task.update_state(state='STARTED', meta={'task_type': 'sbt', "logList":"".join(logList)})


        process.wait()  # Wait for the process to complete

        if process.returncode != 0:
            return_log['status'] = 'FAILED'
            test_status = False

        # Create or update a submission entry in the database within the application context
        with app.app_context():
            existing_submission = Submission.query.filter_by(user_id=user_id, question_id=question_id).first()
            if existing_submission:
                existing_submission.code = chisel_code
                existing_submission.language_id = language_id
                existing_submission.test_status = test_status
                existing_submission.created_at = datetime.utcnow()
                db.session.commit()
            else:
                new_submission = Submission(
                    user_id=user_id,
                    question_id=question_id,
                    code=chisel_code,
                    language_id=language_id,
                    test_status=test_status
                )
                db.session.add(new_submission)
                db.session.commit()

        current_task.update_state(state='SUCCESS', meta={'task_type': 'sbt', 'result': 'SBT process done', "log": return_log, "output": return_log})
        return return_log

    except Exception as e:
        return {'status': 'error', 'output': str(e)}

@celery.task(bind=True)
def run_rvv_task(self, code, test_case, user_id, question_id, language_id):
    current_task.update_state(state='STARTED', meta={'task_type': 'sbt'})
    print(test_case)
    print(code)
    try:
        logList= ["RVV running...\n"]
        current_task.update_state(state='STARTED', meta={'task_type': 'sbt', "logList":"".join(logList)})

        results = run_and_compare(
            code,
            test_case
            # {
            #     'a0': f'0x{"0" * 8}',
            #     'a1': f'0x{"0" * 8}',
            #     f'mem[0x8{"0" * 7}]': f'0x{"0" * 8}',
            #     **{f'v{i}': [f'0x{"0" * 16}' for _ in range(2)] for i in range(0, 7)}
            # }
        )

        return_log = {
            'status': ["PASSED" if results['test_pass'] else "FAILED"][0],
            'output': results['formatted_results']
        }
        test_status = results['test_pass']

        # Create or update a submission entry in the database within the application context
        with app.app_context():
            existing_submission = Submission.query.filter_by(user_id=user_id, question_id=question_id).first()
            if existing_submission:
                existing_submission.code = code
                existing_submission.language_id = language_id
                existing_submission.test_status = test_status
                existing_submission.created_at = datetime.utcnow()
                db.session.commit()
            else:
                new_submission = Submission(
                    user_id=user_id,
                    question_id=question_id,
                    code=code,
                    language_id=language_id,
                    test_status=test_status
                )
                db.session.add(new_submission)
                db.session.commit()

        current_task.update_state(state='SUCCESS', meta={'task_type': 'rvv', 'result': 'RVV process done', "log": return_log, "output": return_log})
        return return_log

    except Exception as e:
        return {'status': 'error', 'output': str(e)}

@app.route('/rvcodehub/api/run_sbt', methods=['POST'])
def run_sbt():
    data = request.get_json()
    chisel_code = data.get('chisel_code')
    test_case = data.get('test_case')
    user_id = data.get('user_id')
    question_id = data.get('question_id')
    language_id = data.get('language_id')
    task = run_chisel_task.apply_async(args=[chisel_code, test_case, user_id, question_id, language_id ], queue='run_sbt')
    task_id = task.id

    # Try adding the task to Redis sorted set and log result
    result = redis_client.zadd("pending_tasks", {task_id: time.time()})
    if result == 1:
        print(f"Task {task_id} successfully added to Redis queue.")
    else:
        print(f"Failed to add task {task_id} to Redis queue.")

    return jsonify({'task_id': task.id}), 202

@app.route('/rvcodehub/api/run_sbt/status/<task_id>', methods=['GET'])
def get_sbt_status(task_id):
    task_result = AsyncResult(task_id, app=celery)
    logList = []
    task_id_bytes = task_id.encode('utf-8')

    filtered_pending_tasks = []
    for t in redis_client.zrange("pending_tasks", 0, -1):
        decoded_task_id = t.decode('utf-8')
        async_result = AsyncResult(decoded_task_id, app=celery)
        
        # Only add tasks with 'PENDING' state to filtered list
        if async_result.state == 'PENDING':
            filtered_pending_tasks.append(t)

    # Check the position of the current task_id in the filtered pending tasks
    if task_id_bytes in filtered_pending_tasks:
        task_position = filtered_pending_tasks.index(task_id_bytes) + 1
    else:
        task_position = "Not in queue"

    # Determine the response status
    if task_result.state == 'PENDING':
        queue_position = task_position
    elif task_result.state == 'STARTED':
        logList = task_result.info.get('logList', [])
        # Remove from pending tasks and mark as "In Progress"
        redis_client.zrem("pending_tasks", task_id_bytes)
        queue_position = "In Progress"
    else:
        # Mark as "Completed" for finished or failed tasks
        queue_position = "Completed"
    
    return jsonify({
       
        'status': task_result.state,
        'result': task_result.result if task_result.state == 'SUCCESS' else None,
        'queue_position': queue_position,
         "logList": logList
    })

@app.route('/rvcodehub/api/run_rvv', methods=['POST'])
def run_rvv():
    data = request.get_json()
    code = data.get('code')
    test_case = data.get('test_case')
    user_id = data.get('user_id')
    question_id = data.get('question_id')
    language_id = data.get('language_id')
    task = run_rvv_task.apply_async(args=[code, test_case, user_id, question_id, language_id], queue='run_rvv')
    return jsonify({'task_id': task.id}), 202

@app.route('/rvcodehub/api/run_rvv/status/<task_id>', methods=['GET'])
def get_rvv_status(task_id):
    task_result = AsyncResult(task_id, app=celery)
    logList = []
    task_id_bytes = task_id.encode('utf-8')

    filtered_pending_tasks = []
    for t in redis_client.zrange("pending_tasks", 0, -1):
        decoded_task_id = t.decode('utf-8')
        async_result = AsyncResult(decoded_task_id, app=celery)
        
        # Only add tasks with 'PENDING' state to filtered list
        if async_result.state == 'PENDING':
            filtered_pending_tasks.append(t)

    # Check the position of the current task_id in the filtered pending tasks
    if task_id_bytes in filtered_pending_tasks:
        task_position = filtered_pending_tasks.index(task_id_bytes) + 1
    else:
        task_position = "Not in queue"

    # Determine the response status
    if task_result.state == 'PENDING':
        queue_position = task_position
    elif task_result.state == 'STARTED':
        logList = task_result.info.get('logList', [])
        # Remove from pending tasks and mark as "In Progress"
        redis_client.zrem("pending_tasks", task_id_bytes)
        queue_position = "In Progress"
    else:
        # Mark as "Completed" for finished or failed tasks
        queue_position = "Completed"
    
    return jsonify({
       
        'status': task_result.state,
        'result': task_result.result if task_result.state == 'SUCCESS' else None,
        'queue_position': queue_position,
         "logList": logList
    })


@app.route('/rvcodehub/api/contest/<int:contest_id>/remaining_time', methods=['GET'])
def get_remaining_time(contest_id):
    contest = Contest.query.get(contest_id)
    if not contest:
        return jsonify({'error': 'Contest not found'}), 404

    if not contest.start_time:
        return jsonify({'remaining_time': contest.duration})

    elapsed_time = (datetime.now(timezone.utc) - contest.start_time).total_seconds()
    remaining_time = contest.duration.total_seconds() - elapsed_time

    if remaining_time < 0:
        remaining_time = 0

    formatted_remaining_time = time.strftime('%H:%M:%S', time.gmtime(remaining_time))
    return jsonify({'remaining_time': formatted_remaining_time})



if __name__ == '__main__':
    app.run(debug=True)

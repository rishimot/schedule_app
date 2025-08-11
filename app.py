from werkzeug.routing import BaseConverter
from flask import Flask, render_template, request, redirect, jsonify
import json
import sqlite3
import datetime
import random
import os
import requests

app = Flask(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'schedule.db')
JST = datetime.timezone(datetime.timedelta(hours=9))
DATE_FORMAT = '%Y-%m-%d'
TIME_FORMAT = '%H:%M'
TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates_data')
TODAY_HOUR = 4

class DateConverter(BaseConverter):
    regex = r'\d{4}-\d{2}-\d{2}'
app.url_map.converters['date'] = DateConverter

def get_learning_times():
    response = requests.get("http://192.168.10.103:5003/api/get/learning_times")
    if response.status_code == 200:
        learning_time = response.json()
    else:
        learning_time = {}
    return learning_time

def get_remaining_times():
    response = requests.get("http://192.168.10.103:5003/api/get/remaining_times")
    if response.status_code == 200:
        remaining_time = response.json()
    else:
        remaining_time = {}
    return remaining_time

def get_target_times():
    response = requests.get("http://192.168.10.103:5003/api/get/target_times")
    if response.status_code == 200:
        target_time = response.json()
    else:
        target_time = {}
    return target_time

def generate_randomcolor():
    hue = random.randint(0, 359)
    return f'hsl({hue}, 70%, 60%)'

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                topic_id INTEGER NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                content TEXT
            )''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS topic (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                color TEXT NOT NULL DEFAULT "#ffffff"
            )''')
        conn.commit()

@app.route('/')
def index():
    today = get_today().strftime(DATE_FORMAT)
    return redirect(f'/{today}')

def get_schedules_from_DB(date):
    schedules = []

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT schedules.id, schedules.date, topic.title, schedules.start_time, schedules.end_time, schedules.content, topic.color
            FROM schedules
            INNER JOIN topic ON topic.id = schedules.topic_id
            WHERE date = ?
            ORDER BY date, start_time
        """, (date,))
        rows = cur.fetchall()
        for (schedule_id, date, topic, start_time, end_time, content, color) in rows:
            schedules.append({'id': schedule_id, 'date': date, 'topic': topic, 'start_time': start_time, 'end_time': end_time, 'duration': get_duration(date, start_time, end_time), 'content': content, 'color': color})
    return schedules

def get_duration(date, start_time, end_time):
    start_dt = datetime.datetime.strptime(f'{date} {start_time}', f'{DATE_FORMAT} {TIME_FORMAT}')
    end_dt = datetime.datetime.strptime(f'{date} {end_time}', f'{DATE_FORMAT} {TIME_FORMAT}')
    if end_dt < start_dt:
        next_date = (datetime.datetime.strptime(date, DATE_FORMAT) + datetime.timedelta(days=1)).strftime(DATE_FORMAT)
        end_dt =  datetime.datetime.strptime(f'{next_date} {end_time}', f'{DATE_FORMAT} {TIME_FORMAT}')
    return int((end_dt - start_dt).total_seconds() // 60)

@app.route('/<date:date>')
def get_schedules(date):
    schedules = get_schedules_from_DB(date)
    remaining_times = get_remaining_times()
    category = remaining_times.keys()
    is_today = (date == get_today().strftime(DATE_FORMAT))
    plan_times = { cate: 0 for cate in category }
    for schedule in schedules:
        if schedule["topic"] in category:
            duration = get_duration(schedule['date'], schedule['start_time'], schedule['end_time'])
            plan_times[schedule["topic"]] += duration

    if is_today:
        today_remaining_times = remaining_times.copy()
        now = datetime.datetime.now()
        for schedule in schedules:
            if schedule["topic"] in category:
                date = schedule['date']
                start_time = schedule['start_time']
                end_time = schedule['end_time']
                
                next_date = (datetime.datetime.strptime(date, DATE_FORMAT) + datetime.timedelta(days=1)).strftime(DATE_FORMAT)
                start_dt =  datetime.datetime.strptime(f'{next_date} {start_time}' if "00:00" <= start_time <= "04:00" else f'{date} {start_time}', f'{DATE_FORMAT} {TIME_FORMAT}')
                end_dt =  datetime.datetime.strptime(f'{next_date} {end_time}' if "00:00" <= end_time <= "04:00" else f'{date} {end_time}', f'{DATE_FORMAT} {TIME_FORMAT}')
                duration = int((end_dt - max(start_dt, now)).total_seconds() // 60)
                if duration > 0:
                    today_remaining_times[schedule["topic"]] -= int(duration * 0.8)

    template_names = [ f[:-5] for f in os.listdir("templates_data") if f.endswith(".json") ]
    return render_template('index.html', 
                           date=date, 
                           rows=schedules, 
                           category=list(category),
                           remaining_times=remaining_times, 
                           plan_times=plan_times, 
                           is_today=is_today, 
                           template_names=template_names, 
                           today_remaining_times=today_remaining_times if is_today else None,
                           TODAY_HOUR=int(TODAY_HOUR))

@app.route("/add_schedule", methods=["POST"])
def add_schedule():
    date = request.form['date']
    topic = request.form['topic']
    start_hour = request.form['start_hour']
    start_minute = request.form['start_minute']
    end_hour = request.form['end_hour']
    end_minute = request.form['end_minute']
    content = request.form['content']
    start_time = f"{start_hour}:{start_minute}"
    end_time = f"{end_hour}:{end_minute}"

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM topic WHERE title = ?", (topic,))
        result = cur.fetchone()
        if result is None:
            color = generate_randomcolor()
            cur.execute("INSERT INTO topic (title, color) VALUES (?, ?)", (topic, color))
            topic_id = cur.lastrowid
        else:
            topic_id, = result

        cur.execute("INSERT INTO schedules (date, topic_id, start_time, end_time, content) VALUES (?, ?, ?, ?, ?)", (date, topic_id, start_time, end_time, content))
        conn.commit()
    return redirect(f'/{date}')

@app.route("/update_schedule", methods=["POST"])
def update_schedule():
    schedule_id = request.form['id']
    date = request.form['date']
    topic = request.form['topic']
    start_hour = request.form['start_hour']
    start_minute = request.form['start_minute']
    end_hour = request.form['end_hour']
    end_minute = request.form['end_minute']
    content = request.form['content']
    start_time = f"{start_hour}:{start_minute}"
    end_time = f"{end_hour}:{end_minute}"

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM topic WHERE title = ?", (topic,))
        result = cur.fetchone()
        if result is None:
            color = generate_randomcolor()
            cur.execute("INSERT INTO topic (title, color) VALUES (?, ?)", (topic, color))
            topic_id = cur.lastrowid
        else:
            topic_id, = result

        cur.execute("UPDATE schedules set topic_id = ?, start_time = ?, end_time = ?, content = ? WHERE id = ?", (topic_id, start_time, end_time, content, schedule_id,))
        conn.commit()
    return redirect(f'/{date}')

@app.route("/update_content", methods=["POST"])
def update_content():
    data = request.json
    schedule_id = data['id']
    date = data['date']
    content = data['content']
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("UPDATE schedules set content = ? WHERE id = ?", (content, schedule_id,))
        conn.commit()
    return redirect(f'/{date}')

@app.route("/delete_schedule/<int:schedule_id>", methods=["DELETE"])
def delete_schedule(schedule_id):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
        conn.commit()
    return jsonify({"status": "success"})

def get_today():
    today_4am = datetime.datetime.combine(datetime.datetime.today(), datetime.time(TODAY_HOUR, 0), tzinfo=JST)
    now = datetime.datetime.now(JST)
    return datetime.datetime.today() if today_4am < now else datetime.datetime.today() - datetime.timedelta(1)

@app.route("/api/has_schedule", methods=["GET"])
def has_schedule():
    today = get_today().strftime(DATE_FORMAT)
    schedules = get_schedules_from_DB(today)
    remaining_times = get_remaining_times()
    for category in remaining_times.keys():
        for schedule in schedules:
            if category in schedule["topic"]:
                duration = get_duration(schedule['date'], schedule['start_time'], schedule['end_time'])
                remaining_times[category] -= duration
    has_schedule = sum([time for time in remaining_times.values()]) <= 0
    return jsonify({"has_schedule": has_schedule })

@app.route('/save_template', methods=['POST'])
def save_template():
    name = request.form['template-name']
    date = request.form['date']
    schedules = get_schedules_from_DB(date)
    
    with open(os.path.join(TEMPLATE_DIR, f'{name}.json'), 'w', encoding='utf-8') as f:
        json.dump(schedules, f, ensure_ascii=False, indent=2)
    return jsonify({'status': 'success', 'message': 'Template saved successfully.'})

@app.route("/load_template", methods=['POST'])
def load_template():
    name = request.form["template-name"]
    date = request.form['date']
    with open(os.path.join(TEMPLATE_DIR, f'{name}.json'), 'r', encoding='utf-8') as f:
        schedules = json.load(f)
        for schedule in schedules:
            topic = schedule['topic']
            start_time = schedule['start_time']
            end_time = schedule['end_time']
            content = schedule['content']

            with sqlite3.connect(DB_PATH) as conn:
                cur = conn.cursor()
                cur.execute("SELECT id FROM topic WHERE title = ?", (topic,))
                topic_id, = cur.fetchone()
                cur.execute("INSERT INTO schedules (date, topic_id, start_time, end_time, content) VALUES (?, ?, ?, ?, ?)", (date, topic_id, start_time, end_time, content))
                conn.commit()
    return redirect(f'/{date}')

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=3333, debug=True)
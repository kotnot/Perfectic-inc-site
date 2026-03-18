from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import sqlite3
import json
import os
from datetime import datetime, timedelta
import threading
import time

app = Flask(__name__, static_folder='static')
CORS(app)  # Разрешаем кросс-доменные запросы

# Путь к базе данных
DB_PATH = 'downloads.db'
JSON_PATH = 'stats.json'

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Таблица для приложений
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS apps (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            platform TEXT NOT NULL
        )
    ''')
    
    # Таблица для статистики скачиваний
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS downloads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            app_id TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            ip_address TEXT,
            user_agent TEXT,
            FOREIGN KEY (app_id) REFERENCES apps (id)
        )
    ''')
    
    # Таблица для ежедневной статистики
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_stats (
            date TEXT PRIMARY KEY,
            app_id TEXT NOT NULL,
            count INTEGER DEFAULT 0,
            FOREIGN KEY (app_id) REFERENCES apps (id)
        )
    ''')
    
    # Добавляем приложения, если их нет
    apps = [
        ('kotnotAI', 'KotnotAI', 'ai', 'web'),
        ('kotnotC', 'Kotnot-C', 'language', 'web'),
        ('kotnotC-compiler', 'Kotnot-C Компилятор', 'development', 'windows'),
        ('browser-zet', 'Browser Zet', 'browser', 'windows'),
        ('asmos', 'ASMOS Constructor', 'development', 'windows'),
        ('zetoshop', 'ZetoShop', 'graphics', 'windows'),
        ('gitrex-linux', 'Gitrex Message Linux', 'messenger', 'linux'),
        ('gitrex-windows', 'Gitrex Message Windows', 'messenger', 'windows'),
        ('map-game', 'Конструктор карт', 'game', 'web'),
        ('monsterfire-tanks', 'MonsterFire Tanks', 'game', 'windows'),
        ('kumys-simulator', 'Симулятор кумыса', 'game', 'windows'),
        ('russia-simulator', 'Симулятор властей РФ', 'game', 'windows'),
        ('school-simulator', 'School Simulator', 'game', 'windows'),
        ('hate-simulator', 'Симулятор ненависти', 'game', 'windows'),
        ('monsterfire-online', 'Monster Fire', 'game', 'web'),
        ('gitrexos', 'GitrexOS', 'os', 'x86')
    ]
    
    for app_id, name, category, platform in apps:
        cursor.execute('INSERT OR IGNORE INTO apps (id, name, category, platform) VALUES (?, ?, ?, ?)',
                      (app_id, name, category, platform))
    
    conn.commit()
    conn.close()

# Функция для обновления JSON-статистики
def update_json_stats():
    while True:
        try:
            stats = get_detailed_stats()
            with open(JSON_PATH, 'w', encoding='utf-8') as f:
                json.dump(stats, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Ошибка обновления JSON: {e}")
        time.sleep(60)  # Обновляем каждую минуту

# Получение детальной статистики
def get_detailed_stats():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Общая статистика по всем приложениям
    cursor.execute('''
        SELECT 
            a.id,
            a.name,
            a.category,
            a.platform,
            COUNT(d.id) as total,
            COUNT(CASE WHEN d.timestamp >= DATE('now', '-7 days') THEN 1 END) as weekly,
            COUNT(CASE WHEN d.timestamp >= DATE('now', '-30 days') THEN 1 END) as monthly
        FROM apps a
        LEFT JOIN downloads d ON a.id = d.app_id
        GROUP BY a.id
        ORDER BY total DESC
    ''')
    
    apps_stats = []
    total_all = 0
    
    for row in cursor.fetchall():
        total_all += row[4] if row[4] else 0
        apps_stats.append({
            'id': row[0],
            'name': row[1],
            'category': row[2],
            'platform': row[3],
            'total': row[4] if row[4] else 0,
            'weekly': row[5] if row[5] else 0,
            'monthly': row[6] if row[6] else 0
        })
    
    # Получаем статистику за последние 30 дней
    cursor.execute('''
        SELECT DATE(timestamp) as date, COUNT(*) as count
        FROM downloads
        WHERE timestamp >= DATE('now', '-30 days')
        GROUP BY DATE(timestamp)
        ORDER BY date
    ''')
    
    daily_stats = []
    for row in cursor.fetchall():
        daily_stats.append({
            'date': row[0],
            'count': row[1]
        })
    
    conn.close()
    
    return {
        'total_downloads': total_all,
        'apps': apps_stats,
        'daily': daily_stats,
        'last_updated': datetime.now().isoformat()
    }

# API для получения статистики
@app.route('/api/stats', methods=['GET'])
def get_stats():
    stats = get_detailed_stats()
    return jsonify(stats)

# API для получения статистики конкретного приложения
@app.route('/api/stats/<app_id>', methods=['GET'])
def get_app_stats(app_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT 
            a.id,
            a.name,
            a.category,
            a.platform,
            COUNT(d.id) as total,
            COUNT(CASE WHEN d.timestamp >= DATE('now', '-7 days') THEN 1 END) as weekly,
            COUNT(CASE WHEN d.timestamp >= DATE('now', '-30 days') THEN 1 END) as monthly
        FROM apps a
        LEFT JOIN downloads d ON a.id = d.app_id
        WHERE a.id = ?
        GROUP BY a.id
    ''', (app_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return jsonify({
            'id': row[0],
            'name': row[1],
            'category': row[2],
            'platform': row[3],
            'total': row[4] if row[4] else 0,
            'weekly': row[5] if row[5] else 0,
            'monthly': row[6] if row[6] else 0
        })
    else:
        return jsonify({'error': 'App not found'}), 404

# API для регистрации скачивания
@app.route('/api/download/<app_id>', methods=['POST'])
def register_download(app_id):
    try:
        data = request.get_json() or {}
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Проверяем существование приложения
        cursor.execute('SELECT id FROM apps WHERE id = ?', (app_id,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({'error': 'App not found'}), 404
        
        # Регистрируем скачивание
        cursor.execute('''
            INSERT INTO downloads (app_id, ip_address, user_agent)
            VALUES (?, ?, ?)
        ''', (app_id, request.remote_addr, request.headers.get('User-Agent')))
        
        conn.commit()
        conn.close()
        
        # Возвращаем обновленную статистику
        return get_app_stats(app_id)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# API для получения JSON-файла со статистикой
@app.route('/stats.json', methods=['GET'])
def get_stats_json():
    if os.path.exists(JSON_PATH):
        return send_from_directory('.', JSON_PATH)
    else:
        stats = get_detailed_stats()
        return jsonify(stats)

# API для получения топа популярных приложений
@app.route('/api/top', methods=['GET'])
def get_top_apps():
    limit = request.args.get('limit', 10, type=int)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT 
            a.id,
            a.name,
            a.category,
            COUNT(d.id) as total
        FROM apps a
        LEFT JOIN downloads d ON a.id = d.app_id
        GROUP BY a.id
        ORDER BY total DESC
        LIMIT ?
    ''', (limit,))
    
    top_apps = []
    for i, row in enumerate(cursor.fetchall(), 1):
        top_apps.append({
            'rank': i,
            'id': row[0],
            'name': row[1],
            'category': row[2],
            'total': row[3] if row[3] else 0
        })
    
    conn.close()
    return jsonify(top_apps)

# API для получения статистики по категориям
@app.route('/api/categories', methods=['GET'])
def get_category_stats():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT 
            a.category,
            COUNT(DISTINCT a.id) as apps_count,
            COUNT(d.id) as total_downloads
        FROM apps a
        LEFT JOIN downloads d ON a.id = d.app_id
        GROUP BY a.category
        ORDER BY total_downloads DESC
    ''')
    
    categories = []
    for row in cursor.fetchall():
        categories.append({
            'category': row[0],
            'apps_count': row[1],
            'total_downloads': row[2] if row[2] else 0
        })
    
    conn.close()
    return jsonify(categories)

# Главная страница (отдаем наш HTML)
@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

# Для обслуживания статических файлов
@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('static', path)

if __name__ == '__main__':
    # Инициализируем базу данных
    init_db()
    
    # Запускаем фоновый поток для обновления JSON
    json_thread = threading.Thread(target=update_json_stats, daemon=True)
    json_thread.start()
    
    # Запускаем сервер
    app.run(host='0.0.0.0', port=5000, debug=True)

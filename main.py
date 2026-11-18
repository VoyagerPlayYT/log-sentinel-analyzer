import os
import sqlite3
import json
import time
import asyncio
import random
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

DB_PATH = os.path.join(os.path.dirname(__file__), "sentinel_logs.db")

app = FastAPI(title="Log Sentinel Analyzer Backend", version="1.0.0")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS logs_archive (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            level TEXT NOT NULL,
            message TEXT NOT NULL,
            ip_address TEXT,
            latency_ms REAL,
            timestamp TEXT NOT NULL
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_log_level ON logs_archive(level)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_log_time ON logs_archive(timestamp)")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alert_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            level TEXT NOT NULL,
            threshold_count INTEGER NOT NULL,
            window_seconds INTEGER NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alert_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_name TEXT NOT NULL,
            details TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
    """)

    # Seed alert rules if empty
    cursor.execute("SELECT COUNT(*) FROM alert_rules")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
            INSERT INTO alert_rules (name, level, threshold_count, window_seconds)
            VALUES 
            ('High Error Rate Trigger', 'ERROR', 3, 30),
            ('Warning Spike Alert', 'WARN', 5, 45)
        """)

    conn.commit()
    conn.close()

init_db()

class AlertRuleCreate(BaseModel):
    name: str = Field(..., min_length=2)
    level: str = Field(default="ERROR")
    threshold_count: int = Field(default=3, ge=1)
    window_seconds: int = Field(default=30, ge=5)

class WebSocketLogManager:
    def __init__(self):
        self.active_sockets: List[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active_sockets.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active_sockets:
            self.active_sockets.remove(ws)

    async def broadcast(self, data: dict):
        for ws in list(self.active_sockets):
            try:
                await ws.send_json(data)
            except Exception:
                self.disconnect(ws)

ws_manager = WebSocketLogManager()

# Background Simulated / Disk Log Ingestor
SOURCES = ["nginx-edge", "auth-sentinel", "postgres-pool", "api-gateway", "worker-celery"]
SAMPLE_MESSAGES = {
    "INFO": [
        "HTTP/2 GET /api/v2/telemetry 200 OK",
        "Client handshake TLS 1.3 negotiated",
        "PostgreSQL connection checked out from pool (pool_size=16)",
        "Background task worker-04 finished processing job",
        "Cache hit on key: session:token:auth_token_948",
        "HTTP/1.1 POST /api/scores 201 Created"
    ],
    "WARN": [
        "Slow query detected: SELECT * FROM telemetry_events > 140ms",
        "High memory consumption threshold reached (84% RSS)",
        "Connection retry attempt 2/5 to upstream cluster",
        "Rate limit warning: client approaching 90% quota (90/100 req/min)",
        "Certificate expires in 14 days for domain *.forge.internal"
    ],
    "ERROR": [
        "PostgreSQL connection timeout: connection terminated by peer",
        "HTTP 502 Bad Gateway: Upstream socket connection refused on :8080",
        "I/O Exception: Disk write latency exceeding 500ms on SAS array",
        "Authentication failure: 5 consecutive invalid passwords for user admin",
        "Worker process PID 4192 terminated with signal SIGSEGV"
    ]
}

IP_LIST = ["192.168.1.101", "192.168.1.144", "10.0.0.12", "172.16.0.4", "192.168.1.205"]

async def log_generator_daemon():
    while True:
        await asyncio.sleep(random.uniform(0.6, 1.8))

        # Weighting: 75% INFO, 18% WARN, 7% ERROR
        r = random.random()
        level = "INFO" if r < 0.75 else "WARN" if r < 0.93 else "ERROR"
        source = random.choice(SOURCES)
        msg = random.choice(SAMPLE_MESSAGES[level])
        ip = random.choice(IP_LIST)
        latency = round(random.uniform(2.1, 48.5) if level == "INFO" else random.uniform(120.0, 680.0), 2)
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        # Insert to DB
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO logs_archive (source, level, message, ip_address, latency_ms, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (source, level, msg, ip, latency, ts))
        log_id = cursor.lastrowid
        conn.commit()

        # Check Alert Rules
        if level in ("ERROR", "WARN"):
            cursor.execute("SELECT name, level, threshold_count, window_seconds FROM alert_rules WHERE is_active = 1 AND level = ?", (level,))
            rules = cursor.fetchall()
            for r_name, r_level, r_thresh, r_window in rules:
                time_threshold = (datetime.utcnow() - timedelta(seconds=r_window)).strftime("%Y-%m-%d %H:%M:%S")
                cursor.execute("""
                    SELECT COUNT(*) FROM logs_archive 
                    WHERE level = ? AND timestamp >= ?
                """, (r_level, time_threshold))
                cnt = cursor.fetchone()[0]
                if cnt >= r_thresh:
                    # Trigger alert!
                    alert_desc = f"Threshold breached: {cnt} {r_level} events detected in last {r_window}s"
                    cursor.execute("""
                        INSERT INTO alert_history (rule_name, details, timestamp)
                        VALUES (?, ?, ?)
                    """, (r_name, alert_desc, ts))
                    conn.commit()

                    await ws_manager.broadcast({
                        "type": "ALERT",
                        "rule": r_name,
                        "details": alert_desc,
                        "timestamp": ts
                    })

        conn.close()

        # Broadcast live log entry
        await ws_manager.broadcast({
            "type": "LOG",
            "id": log_id,
            "source": source,
            "level": level,
            "message": msg,
            "ip": ip,
            "latency": latency,
            "timestamp": ts
        })

@app.on_event("startup")
def startup_event():
    asyncio.create_task(log_generator_daemon())

@app.get("/api/logs")
def get_logs(
    level: Optional[str] = None,
    source: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = 50
):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    sql = "SELECT * FROM logs_archive WHERE 1=1"
    params = []

    if level and level != "ALL":
        sql += " AND level = ?"
        params.append(level)
    if source and source != "ALL":
        sql += " AND source = ?"
        params.append(source)
    if query:
        sql += " AND (message LIKE ? OR ip_address LIKE ?)"
        params.extend([f"%{query}%", f"%{query}%"])

    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    cursor.execute(sql, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {"logs": rows}

@app.get("/api/metrics/spikes")
def get_spikes_histogram():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Aggregate by last 15 minutes
    time_limit = (datetime.utcnow() - timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        SELECT 
            strftime('%H:%M', timestamp) as minute_bucket,
            SUM(CASE WHEN level = 'ERROR' THEN 1 ELSE 0 END) as errors,
            SUM(CASE WHEN level = 'WARN' THEN 1 ELSE 0 END) as warnings,
            SUM(CASE WHEN level = 'INFO' THEN 1 ELSE 0 END) as infos
        FROM logs_archive
        WHERE timestamp >= ?
        GROUP BY minute_bucket
        ORDER BY minute_bucket ASC
        LIMIT 15
    """, (time_limit,))

    rows = cursor.fetchall()
    conn.close()

    buckets = []
    for r in rows:
        buckets.append({
            "minute": r[0],
            "errors": r[1],
            "warnings": r[2],
            "infos": r[3]
        })

    return {"buckets": buckets}

@app.get("/api/alerts")
def get_alerts():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM alert_history ORDER BY id DESC LIMIT 15")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {"alerts": rows}

@app.post("/api/alerts/rules")
def add_alert_rule(rule: AlertRuleCreate):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO alert_rules (name, level, threshold_count, window_seconds)
        VALUES (?, ?, ?, ?)
    """, (rule.name, rule.level, rule.threshold_count, rule.window_seconds))
    rid = cursor.lastrowid
    conn.commit()
    conn.close()
    return {"status": "created", "id": rid}

@app.get("/api/stats")
def get_system_stats():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM logs_archive")
    total = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM logs_archive WHERE level = 'ERROR'")
    errs = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM alert_history")
    alerts = cursor.fetchone()[0]
    conn.close()
    return {
        "total_logs": total,
        "error_logs": errs,
        "active_alerts_count": alerts
    }

@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keepalive receiver
            _ = await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)

static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
def read_root():
    return FileResponse(os.path.join(static_dir, "index.html"))

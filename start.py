#!/usr/bin/env python3
"""
start.py — Jalankan Bot Telegram + Dashboard Flask sekaligus
Gunakan: python start.py
Ctrl+C untuk stop semua.
"""
import subprocess
import sys
import signal
import os

procs = []

def stop_all(sig=None, frame=None):
    print('\n🛑 Menghentikan semua proses...')
    for p in procs:
        try:
            p.terminate()
        except Exception:
            pass
    sys.exit(0)

signal.signal(signal.SIGINT, stop_all)
signal.signal(signal.SIGTERM, stop_all)

python = sys.executable
cwd = os.path.dirname(os.path.abspath(__file__))

print('🤖 Memulai Bot Telegram...')
bot_proc = subprocess.Popen(
    [python, 'main.py'],
    cwd=cwd,
)
procs.append(bot_proc)

print('🌐 Memulai Dashboard Flask (http://localhost:5000)...')
dash_proc = subprocess.Popen(
    [python, 'dashboard.py'],
    cwd=cwd,
)
procs.append(dash_proc)

print('\n✅ Semua berjalan. Tekan Ctrl+C untuk stop.\n')

# Tunggu sampai salah satu berhenti (crash), lalu stop semua
try:
    while True:
        for p in procs:
            ret = p.poll()
            if ret is not None:
                name = 'Bot' if p == bot_proc else 'Dashboard'
                print(f'\n⚠️  {name} berhenti (exit {ret}). Menghentikan semua...')
                stop_all()
        import time; time.sleep(1)
except KeyboardInterrupt:
    stop_all()

"""
Jalankan sekali: python patch_wave3.py
Menambahkan Wave 3 stubs ke finance.py supaya bot bisa jalan.
"""
import os

STUBS = '''

# ─── WAVE 3 STUBS ────────────────────────────────────────────────────────────
def get_prediksi_saldo(wallet_id):
    return {"saldo_sekarang":0,"saldo_prediksi":0,"warning":False,"sisa_hari":0,
            "rate_keluar_harian":0,"proyeksi_keluar":0,"proyeksi_masuk":0,
            "pending_masuk":0,"pending_keluar":0}

def add_subscription(*a, **kw): return {"error": "Fitur belum tersedia"}
def get_subscriptions(wallet_id): return []
def delete_subscription(*a, **kw): return False
def toggle_subscription(*a, **kw): return {}
def get_upcoming_subscriptions(*a, **kw): return []
def get_subscription_summary(w):
    return {"total_bulanan":0,"total_tahunan":0,"by_category":{},"subscriptions":[]}

CHALLENGE_TYPES = {
    "52week": {"label":"52 Minggu","desc":"Menabung mingguan","total_steps":52,"base_amount":10000},
    "30day":  {"label":"30 Hari","desc":"Menabung harian","total_steps":30,"base_amount":10000},
    "nospend":{"label":"No-Spend Week","desc":"Tidak belanja","total_steps":7,"base_amount":0},
}
def create_challenge(*a, **kw): return {"error": "Fitur belum tersedia"}
def get_active_challenge(w): return None
def advance_challenge(w): return {}
def stop_challenge(w): return False

def get_coach_tips(w): return []

def create_group_wallet(*a, **kw): return {"error": "Fitur belum tersedia"}
def get_my_groups(w): return []
def join_group_wallet(*a, **kw): return {"error": "Fitur belum tersedia"}
def get_group_members(g): return []
def get_group_transactions(*a, **kw): return []
def get_group_summary(g): return {"masuk":0,"keluar":0,"members":0,"per_member":[]}
def leave_group_wallet(*a, **kw): return False
def regen_group_invite(*a, **kw): return ""
def generate_laporan_pdf(*a, **kw): raise ImportError("Install reportlab dulu: pip install reportlab")
# ─── END WAVE 3 STUBS ─────────────────────────────────────────────────────────
'''

finance_path = os.path.join("src", "core", "finance.py")

if not os.path.exists(finance_path):
    print(f"❌ File tidak ditemukan: {finance_path}")
    print("   Pastikan jalankan dari root folder project (sejajar main.py)")
    exit(1)

# Cek apakah sudah di-patch
with open(finance_path, "r", encoding="utf-8") as f:
    content = f.read()

if "WAVE 3 STUBS" in content:
    print("✅ finance.py sudah di-patch sebelumnya!")
    exit(0)

# Tambahkan stubs di akhir file
with open(finance_path, "a", encoding="utf-8") as f:
    f.write(STUBS)

print("✅ Wave 3 stubs berhasil ditambahkan ke finance.py!")
print("   Sekarang jalankan: python start.py atau python main.py")

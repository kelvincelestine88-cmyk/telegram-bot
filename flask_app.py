from flask import Flask, request, jsonify
import json
import logging
import sqlite3
import random
import string
from datetime import datetime, timedelta
import requests
import time
import re

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# ==================== CONFIGURATION ====================
TOKEN = "8952063648:AAHbLLkx-e5f1QzZLxLMmVZIRQDILJuZ6MU"
PROOF_GROUP_ID = -1003777181000
OWNER_ID = 7814414366

# ==================== PTERODACTYL CONFIG ====================
PTERODACTYL_URL = "https://slayers.kevinhosts.qzz.io"
PTERODACTYL_API_KEY = "ptla_2KCkntCt39LMHvUys2JzgcBhA9TWJ011VwSsOImWSrv"  # REPLACE THIS

# Egg IDs - REPLACE WITH YOUR ACTUAL IDs
EGG_IDS = {
    "python": "87bb02c5-f843-4920-9dd9-ec08033fa3d7",
    "php": "1586bb3b-09e1-4054-8ce2-fa0c342bdf9a",
    "nodejs": "37361d01-c725-471f-acaa-2988e7a1d4c0"
}

# Node IDs - REPLACE WITH YOUR ACTUAL IDs
NODE_IDS = {
    "1": "1586bb3b-09e1-4054-8ce2-fa0c342bdf9a"
}

REFERRALS_NEEDED = 5

# ==================== DATABASE ====================
def get_db():
    conn = sqlite3.connect('/home/kelvincele3/bot_database.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = sqlite3.connect('/home/kelvincele3/bot_database.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY,
                  username TEXT,
                  first_name TEXT,
                  referral_count INTEGER DEFAULT 0,
                  referred_by INTEGER DEFAULT 0,
                  join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS servers
                 (server_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  email TEXT,
                  username TEXT,
                  password TEXT,
                  node TEXT,
                  plan TEXT,
                  server_type TEXT,
                  panel_id TEXT,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  expires_at TIMESTAMP,
                  is_lifetime INTEGER DEFAULT 0,
                  is_suspended INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS referrals
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  referrer_id INTEGER,
                  referred_id INTEGER,
                  timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS mods
                 (user_id INTEGER PRIMARY KEY)''')
    conn.commit()
    conn.close()
    logging.info("Database initialized")

# ==================== USER FUNCTIONS ====================
def add_user(user_id, username, first_name, referred_by=None):
    conn = get_db()
    c = conn.cursor()

    # Check if user exists
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = c.fetchone()

    if not user:
        # Add new user
        c.execute("INSERT INTO users (user_id, username, first_name, referred_by) VALUES (?, ?, ?, ?)",
                 (user_id, username, first_name, referred_by))

        # If referred by someone, increment their referral count
        if referred_by:
            # Make sure referrer exists
            c.execute("SELECT * FROM users WHERE user_id = ?", (referred_by,))
            referrer = c.fetchone()
            if referrer:
                c.execute("UPDATE users SET referral_count = referral_count + 1 WHERE user_id = ?", (referred_by,))
                c.execute("INSERT INTO referrals (referrer_id, referred_id) VALUES (?, ?)", (referred_by, user_id))
                conn.commit()
                conn.close()
                return True, referred_by  # Return that referral was counted
            else:
                logging.warning(f"Referrer {referred_by} not found in database")
                conn.commit()
                conn.close()
                return True, None
        else:
            conn.commit()
            conn.close()
            return True, None
    else:
        # User already exists
        conn.close()
        return False, None

def get_referral_count(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT referral_count FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result['referral_count'] if result else 0

def get_referral_list(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM referrals WHERE referrer_id = ?", (user_id,))
    referrals = c.fetchall()
    conn.close()
    return referrals

def get_user_info(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result

# ==================== PTERODACTYL API ====================
def create_pterodactyl_panel(email, username, password, node, server_type):
    if not PTERODACTYL_API_KEY or PTERODACTYL_API_KEY == "ptlc_YOUR_ACTUAL_API_KEY_HERE":
        logging.error("API key not configured!")
        return None

    headers = {
        "Authorization": f"Bearer {PTERODACTYL_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    try:
        # Create user
        user_data = {
            "email": email,
            "username": username,
            "first_name": username[:20],
            "last_name": "User"
        }

        user_response = requests.post(
            f"{PTERODACTYL_URL}/api/application/users",
            headers=headers,
            json=user_data,
            timeout=30
        )
        user_response.raise_for_status()
        user_id = user_response.json()['data']['id']

        # Create server
        server_data = {
            "name": f"Panel_{username}",
            "user": user_id,
            "egg": EGG_IDS.get(server_type, EGG_IDS["python"]),
            "node": NODE_IDS.get(str(node), NODE_IDS["1"]),
            "limits": {"memory": 2048, "swap": 0, "disk": 10240, "io": 500, "cpu": 100},
            "feature_limits": {"databases": 1, "allocations": 1, "backups": 1},
            "allocation": {"default": 1},
            "start_on_completion": True
        }

        server_response = requests.post(
            f"{PTERODACTYL_URL}/api/application/servers",
            headers=headers,
            json=server_data,
            timeout=30
        )
        server_response.raise_for_status()

        return server_response.json()['data']['id']

    except Exception as e:
        logging.error(f"API error: {e}")
        return None

# ==================== TELEGRAM HELPERS ====================
def send_message(chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    try:
        return requests.post(url, data=data, timeout=10).json()
    except Exception as e:
        logging.error(f"Send error: {e}")
        return None

def edit_message(chat_id, message_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{TOKEN}/editMessageText"
    data = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    try:
        return requests.post(url, data=data, timeout=10).json()
    except Exception as e:
        logging.error(f"Edit error: {e}")
        return None

def answer_callback(callback_id):
    url = f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery"
    try:
        requests.post(url, data={"callback_query_id": callback_id}, timeout=5)
    except Exception as e:
        logging.error(f"Answer error: {e}")

def show_main_menu(chat_id, message_id=None):
    keyboard = {
        "inline_keyboard": [
            [{"text": "🖥️ Create Server", "callback_data": "create"}],
            [{"text": "📊 My Servers", "callback_data": "my_servers"}],
            [{"text": "🔄 Renew Server", "callback_data": "renew"}],
            [{"text": "💰 Balance", "callback_data": "balance"}],
            [{"text": "🆘 Support", "callback_data": "support"}],
            [{"text": "👑 Owner", "callback_data": "owner"}],
            [{"text": "📋 View All Servers", "callback_data": "view_all"}],
            [{"text": "📢 Proof Group", "callback_data": "proof_group"}]
        ]
    }
    text = "👋 Welcome to Pterodactyl Panel Bot!\n\nPlease select an option:"
    if message_id:
        edit_message(chat_id, message_id, text, keyboard)
    else:
        send_message(chat_id, text, keyboard)

# ==================== FLASK WEBHOOK ====================
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        logging.info(f"Webhook data received")

        if 'callback_query' in data:
            callback = data['callback_query']
            callback_id = callback['id']
            user_id = callback['from']['id']
            message_id = callback['message']['message_id']
            chat_id = callback['message']['chat']['id']
            callback_data = callback['data']

            answer_callback(callback_id)

            if callback_data == 'create':
                referrals = get_referral_count(user_id)

                if referrals < REFERRALS_NEEDED:
                    text = f"""❌ You need {REFERRALS_NEEDED} referrals to create a server!
You have: {referrals}

📊 Progress: {'█' * min(referrals, REFERRALS_NEEDED)}{'░' * (REFERRALS_NEEDED - min(referrals, REFERRALS_NEEDED))} {referrals}/{REFERRALS_NEEDED}

Invite: https://t.me/celepanel_bot?start={user_id}"""
                    edit_message(chat_id, message_id, text)
                    return 'ok', 200

                keyboard = {
                    "inline_keyboard": [
                        [{"text": "🌐 Node 1", "callback_data": "node_1"}],
                        [{"text": "🔙 Back", "callback_data": "back_to_main"}]
                    ]
                }
                edit_message(chat_id, message_id, "🌐 Select a node:", keyboard)

            elif callback_data.startswith('node_'):
                node = callback_data.split('_')[1]
                keyboard = {
                    "inline_keyboard": [
                        [{"text": "🐍 Python", "callback_data": "type_python"}],
                        [{"text": "🖥️ PHP", "callback_data": "type_php"}],
                        [{"text": "📦 Node.js", "callback_data": "type_nodejs"}],
                        [{"text": "🔙 Back", "callback_data": "create"}]
                    ]
                }
                edit_message(chat_id, message_id, f"Selected Node: {node}\nSelect type:", keyboard)

            elif callback_data.startswith('type_'):
                server_type = callback_data.split('_')[1]
                node = "1"

                email = f"cele{random.randint(1000000000, 9999999999)}@gmail.com"
                username = f"cele{random.randint(1000000000, 9999999999)}"
                password = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
                expires_at = (datetime.now() + timedelta(days=5)).strftime('%Y-%m-%d %H:%M:%S')

                panel_id = create_pterodactyl_panel(email, username, password, node, server_type)

                if panel_id is None:
                    edit_message(chat_id, message_id, "❌ Failed to create panel. Please check API key.")
                    return 'ok', 200

                conn = get_db()
                c = conn.cursor()
                c.execute("""INSERT INTO servers
                             (user_id, email, username, password, node, plan, server_type, panel_id, expires_at)
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                          (user_id, email, username, password, node, "2GB", server_type, panel_id, expires_at))
                conn.commit()
                conn.close()

                creds = f"""✅ Panel Created!
🔗 {PTERODACTYL_URL}
📧 {email}
👤 {username}
🔑 {password}
⏰ {expires_at}"""

                edit_message(chat_id, message_id, creds)

                proof = f"""✅ Panel Created
👤 {callback['from']['first_name']}
📧 {email}
🕒 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
                send_message(PROOF_GROUP_ID, proof)

            elif callback_data == 'my_servers':
                conn = get_db()
                c = conn.cursor()
                c.execute("SELECT * FROM servers WHERE user_id = ? AND is_suspended = 0", (user_id,))
                servers = c.fetchall()
                conn.close()

                if servers:
                    text = f"📊 Your Servers:\n\n🔗 {PTERODACTYL_URL}\n\n"
                    for server in servers:
                        text += f"""🔹 #{server['server_id']}
📧 {server['email']}
👤 {server['username']}
🔑 {server['password']}
⏰ {server['expires_at']}
──────────────────\n"""
                    edit_message(chat_id, message_id, text)
                else:
                    edit_message(chat_id, message_id, "❌ No servers.")

            elif callback_data == 'balance':
                referrals = get_referral_count(user_id)
                referral_list = get_referral_list(user_id)

                text = f"""💰 Your Balance

👥 Total Referrals: {referrals}
🎯 Required: {REFERRALS_NEEDED}
📊 Progress: {'█' * min(referrals, REFERRALS_NEEDED)}{'░' * (REFERRALS_NEEDED - min(referrals, REFERRALS_NEEDED))} {referrals}/{REFERRALS_NEEDED}

{'✅ You qualify!' if referrals >= REFERRALS_NEEDED else '❌ Need more referrals'}

Share your referral link:
https://t.me/celepanel_bot?start={user_id}"""

                if referral_list:
                    text += "\n\n📋 Your Referrals:\n"
                    for ref in referral_list[:10]:
                        text += f"• User ID: {ref['referred_id']}\n"
                    if len(referral_list) > 10:
                        text += f"... and {len(referral_list) - 10} more"

                edit_message(chat_id, message_id, text)

            elif callback_data == 'renew':
                referrals = get_referral_count(user_id)

                if referrals < REFERRALS_NEEDED:
                    text = f"""❌ Need {REFERRALS_NEEDED} referrals to renew!
You have: {referrals}

📊 Progress: {'█' * min(referrals, REFERRALS_NEEDED)}{'░' * (REFERRALS_NEEDED - min(referrals, REFERRALS_NEEDED))} {referrals}/{REFERRALS_NEEDED}

Invite: https://t.me/celepanel_bot?start={user_id}"""
                    edit_message(chat_id, message_id, text)
                else:
                    conn = get_db()
                    c = conn.cursor()
                    c.execute("SELECT * FROM servers WHERE user_id = ? AND is_suspended = 0", (user_id,))
                    servers = c.fetchall()
                    conn.close()

                    if not servers:
                        edit_message(chat_id, message_id, "❌ No active servers.")
                    else:
                        keyboard = {"inline_keyboard": []}
                        for server in servers:
                            if not server['is_lifetime']:
                                keyboard["inline_keyboard"].append([
                                    {"text": f"🔄 #{server['server_id']}", "callback_data": f"renew_server_{server['server_id']}"}
                                ])
                        keyboard["inline_keyboard"].append([{"text": "🔙 Back", "callback_data": "back_to_main"}])
                        edit_message(chat_id, message_id, "🔄 Select a server:", keyboard)

            elif callback_data.startswith('renew_server_'):
                server_id = int(callback_data.split('_')[2])
                new_expiry = (datetime.now() + timedelta(days=5)).strftime('%Y-%m-%d %H:%M:%S')

                conn = get_db()
                c = conn.cursor()
                c.execute("UPDATE servers SET expires_at = ? WHERE server_id = ? AND user_id = ?",
                         (new_expiry, server_id, user_id))
                conn.commit()
                conn.close()

                edit_message(chat_id, message_id, f"✅ Server #{server_id} renewed!\nNew: {new_expiry}")

            elif callback_data == 'owner':
                if user_id != OWNER_ID:
                    edit_message(chat_id, message_id, "❌ Only owner.")
                    return 'ok', 200

                keyboard = {
                    "inline_keyboard": [
                        [{"text": "🔍 Check Expired", "callback_data": "check_expiry"}],
                        [{"text": "📊 View All", "callback_data": "view_all"}],
                        [{"text": "📊 Referral Stats", "callback_data": "referral_stats"}],
                        [{"text": "🔙 Back", "callback_data": "back_to_main"}]
                    ]
                }
                edit_message(chat_id, message_id, "👑 Owner Panel:", keyboard)

            elif callback_data == 'check_expiry':
                if user_id != OWNER_ID:
                    edit_message(chat_id, message_id, "❌ Only owner.")
                    return 'ok', 200

                conn = get_db()
                c = conn.cursor()
                now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                c.execute("UPDATE servers SET is_suspended = 1 WHERE expires_at < ? AND is_suspended = 0 AND is_lifetime = 0", (now,))
                conn.commit()
                conn.close()

                edit_message(chat_id, message_id, "✅ Expired servers suspended.")

            elif callback_data == 'view_all':
                if user_id != OWNER_ID:
                    edit_message(chat_id, message_id, "❌ Only owner.")
                    return 'ok', 200

                conn = get_db()
                c = conn.cursor()
                c.execute("SELECT * FROM servers")
                servers = c.fetchall()
                conn.close()

                if servers:
                    text = "📋 All Servers:\n\n"
                    for server in servers[:20]:
                        status = "✅ Active" if not server['is_suspended'] else "⛔ Suspended"
                        text += f"#{server['server_id']}: {server['email']} | {status}\n"
                    edit_message(chat_id, message_id, text)
                else:
                    edit_message(chat_id, message_id, "📋 No servers.")

            elif callback_data == 'referral_stats':
                if user_id != OWNER_ID:
                    edit_message(chat_id, message_id, "❌ Only owner.")
                    return 'ok', 200

                conn = get_db()
                c = conn.cursor()
                c.execute("SELECT * FROM users ORDER BY referral_count DESC LIMIT 20")
                top_users = c.fetchall()
                conn.close()

                if top_users:
                    text = "📊 Top Referrers:\n\n"
                    for i, user in enumerate(top_users, 1):
                        text += f"{i}. User ID: {user['user_id']} - {user['referral_count']} referrals\n"
                    edit_message(chat_id, message_id, text)
                else:
                    edit_message(chat_id, message_id, "📊 No referrals yet.")

            elif callback_data == 'support':
                edit_message(chat_id, message_id, "🆘 Contact @th3real_cele0")

            elif callback_data == 'proof_group':
                edit_message(chat_id, message_id, f"📢 Proof Group\n🔗 {PTERODACTYL_URL}")

            elif callback_data == 'back_to_main':
                show_main_menu(chat_id, message_id)

            return 'ok', 200

        # ==================== HANDLE MESSAGES ====================
        elif 'message' in data:
            message = data['message']
            chat_id = message['chat']['id']
            user_id = message['from']['id']
            text = message.get('text', '')

            if text and text.startswith('/start'):
                username = message['from'].get('username')
                first_name = message['from'].get('first_name')

                # ✅ EXTRACT REFERRAL ID FROM /start COMMAND
                referred_by = None
                parts = text.split()
                if len(parts) > 1:
                    try:
                        referred_by = int(parts[1])
                        logging.info(f"REFERRAL DETECTED: {referred_by} referred {user_id}")
                    except ValueError:
                        logging.warning(f"Invalid referral ID in /start: {parts[1]}")

                # Add user and check if referral was counted
                user_added, referrer_id = add_user(user_id, username, first_name, referred_by)

                # ✅ SEND NOTIFICATION TO REFERRER IF THEY EXIST
                if referrer_id:
                    # Get referrer's info
                    referrer = get_user_info(referrer_id)
                    if referrer:
                        # Get updated referral count
                        new_count = get_referral_count(referrer_id)

                        # ✅ Send notification to referrer
                        notification = f"""🎉 New Referral!

User @{username or user_id} used your referral link!

📊 Your Progress: {new_count}/{REFERRALS_NEEDED}
{'✅ You can now create servers!' if new_count >= REFERRALS_NEEDED else f'❌ Need {REFERRALS_NEEDED - new_count} more'}

Keep sharing: https://t.me/celepanel_bot?start={referrer_id}"""

                        try:
                            send_message(referrer_id, notification)
                            logging.info(f"Referral notification sent to {referrer_id}")
                        except Exception as e:
                            logging.error(f"Failed to send notification: {e}")

                        # ✅ Send confirmation to new user
                        send_message(chat_id, f"✅ You were referred by @{referrer['username'] or referrer_id}!\nThey now have {new_count}/{REFERRALS_NEEDED} referrals.")

                show_main_menu(chat_id, None)
            else:
                send_message(chat_id, f"✅ I received: {text}")

            return 'ok', 200

        return 'ok', 200

    except Exception as e:
        logging.error(f"Webhook error: {e}")
        return 'error', 500

@app.route('/')
def index():
    return 'Bot is running!'

@app.route('/health')
def health():
    return jsonify({"status": "healthy"})

@app.route('/check-expiry')
def check_expiry_endpoint():
    try:
        conn = get_db()
        c = conn.cursor()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        c.execute("UPDATE servers SET is_suspended = 1 WHERE expires_at < ? AND is_suspended = 0 AND is_lifetime = 0", (now,))
        conn.commit()
        conn.close()
        return "✅ Expired servers suspended.", 200
    except Exception as e:
        return f"❌ Error: {e}", 500

# ==================== INIT ====================
init_db()
logging.info("Bot initialized")
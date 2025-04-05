import streamlit as st
import sqlite3
import hashlib
import stripe
from datetime import datetime, timedelta
import pytz
import extra_streamlit_components as stx  # Correct import

st.set_page_config(page_title="The Daily Dollar", page_icon=":moneybag:", initial_sidebar_state="collapsed")

# ========== Configuration ==========
DB_PATH = "daily_dollar.db"
stripe.api_key = "sk_test_51R9yN9CGGJzgCEPTGciHIWhNv5VVZjumDZbiaPSD5PHMYjTDMpJTdng7RfC2OBdaFLQnuGicYJYHoN8qYECkX8jy00nxZBNMFZ"

# ========== Cookie Manager ==========
cookie_manager = stx.CookieManager()

# ========== Database Initialization ==========
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            phone TEXT,
            password_hash TEXT NOT NULL,
            sms_opt_in BOOLEAN DEFAULT 0,
            auto_entry BOOLEAN DEFAULT 0,
            streak INTEGER DEFAULT 0,
            last_entry_date TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            entry_type TEXT CHECK(entry_type IN ('main', 'free')),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS winners (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            entry_type TEXT CHECK(entry_type IN ('main', 'free')),
            prize_amount REAL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ========== Helper Functions ==========
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def create_user(username, phone, password):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO users (username, phone, password_hash)
            VALUES (?, ?, ?)
        ''', (username, phone, hash_password(password)))
        conn.commit()
        return True, "Account created!"
    except sqlite3.IntegrityError:
        return False, "Username already exists."
    finally:
        conn.close()

def login_user(username, password):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE username = ? AND password_hash = ?', (username, hash_password(password)))
    user = cursor.fetchone()
    conn.close()
    return user

def is_within_entry_window():
    cst = pytz.timezone('US/Central')
    now_cst = datetime.now(pytz.utc).astimezone(cst)
    entry_start = now_cst.replace(hour=18, minute=1, second=0, microsecond=0)
    entry_end = now_cst.replace(hour=16, minute=59, second=0, microsecond=0)
    if now_cst.hour < 17:
        entry_start -= timedelta(days=1)
    else:
        entry_end += timedelta(days=1)
    return entry_start <= now_cst <= entry_end

def enter_daily_dollar(user_id, entry_type):
    if entry_type not in ['main', 'free']:
        return "Invalid entry type."
    if not is_within_entry_window():
        return "Entry window is currently closed."
    today = datetime.now(pytz.utc).astimezone(pytz.timezone('US/Central')).date().isoformat()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM entries WHERE user_id = ? AND date = ? AND entry_type = ?', (user_id, today, entry_type))
    if cursor.fetchone():
        conn.close()
        return "You have already entered for today."
    cursor.execute('INSERT INTO entries (user_id, date, entry_type) VALUES (?, ?, ?)', (user_id, today, entry_type))
    if entry_type == 'main':
        cursor.execute('SELECT last_entry_date, streak FROM users WHERE id = ?', (user_id,))
        last_entry_date, streak = cursor.fetchone()
        yesterday = (datetime.now(pytz.utc).astimezone(pytz.timezone('US/Central')).date() - timedelta(days=1)).isoformat()
        if last_entry_date == yesterday:
            streak += 1
        else:
            streak = 1
        cursor.execute('UPDATE users SET last_entry_date = ?, streak = ? WHERE id = ?', (today, streak, user_id))
    conn.commit()
    conn.close()
    return f"{entry_type.capitalize()} entry successful."

def create_checkout_session(price_id, username, mode="payment"):
    base_url = "https://your-app-name.streamlit.app"  # Replace with your real app URL
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        mode=mode,
        client_reference_id=username,
        success_url=f"{base_url}?success=true&user={username}",
        cancel_url=f"{base_url}?canceled=true"
    )
    return session.url

def get_username_by_id(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT username FROM users WHERE id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else "Unknown"

def get_yesterdays_winners():
    cst = pytz.timezone('US/Central')
    yesterday = (datetime.now(pytz.utc).astimezone(cst).date() - timedelta(days=1)).isoformat()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, entry_type, prize_amount FROM winners WHERE date = ?", (yesterday,))
    winners = cursor.fetchall()
    conn.close()
    return winners

def get_top_streaks():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT username, streak FROM users ORDER BY streak DESC LIMIT 10")
    top_users = cursor.fetchall()
    conn.close()
    return top_users

def update_phone(user_id, new_phone):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET phone = ? WHERE id = ?", (new_phone, user_id))
    conn.commit()
    conn.close()

def toggle_option(user_id, column, value):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(f"UPDATE users SET {column} = ? WHERE id = ?", (value, user_id))
    conn.commit()
    conn.close()

# ========== Streamlit UI ==========
st.title("The Daily Dollar")

cookie_user = cookie_manager.get("logged_user")
if "user" not in st.session_state:
    st.session_state.user = None
if "show_register" not in st.session_state:
    st.session_state.show_register = False

# Auto-login from cookie
if st.session_state.user is None and cookie_user:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (cookie_user,))
    user = cursor.fetchone()
    conn.close()
    if user:
        st.session_state.user = user

# Stripe success/cancel message
query_params = st.query_params
if query_params.get("success") == "true":
    st.success("Payment received! Youâve been entered into todayâs drawing.")
elif query_params.get("canceled") == "true":
    st.warning("Payment canceled. You were not entered.")

# Login/Register UI
if st.session_state.user is None:
    if st.session_state.show_register:
        st.subheader("Create Account")
        username = st.text_input("Username")
        phone = st.text_input("Phone Number (dashes optional)")
        password = st.text_input("Password", type="password")
        confirm = st.text_input("Confirm Password", type="password")

        if st.button("Register"):
            if len(password) < 7:
                st.warning("Password must be at least 7 characters.")
            elif password != confirm:
                st.warning("Passwords do not match.")
            else:
                success, message = create_user(username, phone, password)
                if success:
                    st.success(message)
                    st.session_state.show_register = False
                else:
                    st.error(message)

        st.markdown("---")
        if st.button("Already have an account? Log in"):
            st.session_state.show_register = False
            st.rerun()

    else:
        st.subheader("Login")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        remember = st.checkbox("Remember me")

        if st.button("Login"):
            user = login_user(username, password)
            if user:
                st.session_state.user = user
                cookie_manager.set("logged_user", user[1])
                st.success(f"Welcome back, {user[1]}!")
                st.rerun()
            else:
                st.error("Invalid username or password.")

        st.markdown("---")
        if st.button("Donât have an account? Create one"):
            st.session_state.show_register = True
            st.rerun()

# Dashboard/Profile
if st.session_state.user:
    st.sidebar.success(f"Logged in as: {st.session_state.user[1]}")
    profile_section = st.sidebar.radio("Navigation", ["Dashboard", "Profile"])
    user_id = st.session_state.user[0]

    if profile_section == "Dashboard":
        st.header("Dashboard")

        st.subheader("Enter Today's Drawing")
        entry_choice = st.radio("Choose Entry Type", ["Main ($1 via Stripe)", "Free Entry"])
        if entry_choice.startswith("Main"):
            if st.button("Pay & Enter via Stripe"):
                url = create_checkout_session("price_1R9yRkCGGJzgCEPTOnnnvEKi", st.session_state.user[1])
                st.markdown(f"[Click here to pay and enter]({url})", unsafe_allow_html=True)
        else:
            if st.button("Enter Free Drawing"):
                result = enter_daily_dollar(user_id, "free")
                st.success(result) if "successful" in result else st.warning(result)

        st.subheader("Yesterday's Winners")
        winners = get_yesterdays_winners()
        if winners:
            for user_id, entry_type, prize in winners:
                st.write(f"**{entry_type.capitalize()} Winner**: {get_username_by_id(user_id)} â ${prize}")
        else:
            st.write("No winners recorded yet.")

        st.subheader("Top 10 Entry Streaks")
        top_users = get_top_streaks()
        for rank, (username, streak) in enumerate(top_users, start=1):
            st.write(f"{rank}. {username} â {streak} day streak")

    elif profile_section == "Profile":
        st.header("Your Profile")
        username = st.session_state.user[1]
        phone = st.session_state.user[2]
        sms_opt_in = bool(st.session_state.user[4])
        auto_entry = bool(st.session_state.user[5])

        st.write(f"**Username:** {username}")
        new_phone = st.text_input("Phone Number", value=phone)
        if st.button("Update Phone"):
            update_phone(user_id, new_phone)
            st.success("Phone number updated!")

        sms_toggle = st.checkbox("Receive SMS notifications", value=sms_opt_in)
        auto_toggle = st.checkbox("Enable auto-entry", value=auto_entry)

        if sms_toggle != sms_opt_in:
            toggle_option(user_id, "sms_opt_in", int(sms_toggle))
            st.success("SMS preference updated!")

        if auto_toggle != auto_entry:
            toggle_option(user_id, "auto_entry", int(auto_toggle))
            st.success("Auto-entry preference updated!")

        st.markdown("---")
        st.markdown("**Want to automate your $1 entries?**")
        if st.button("Subscribe to Daily Auto-Entry"):
            url = create_checkout_session("price_1RAEQmCGGJzgCEPTrhWZ904P", username, mode="subscription")
            st.markdown(f"[Click here to subscribe]({url})", unsafe_allow_html=True)

        if st.button("Sign Out"):
            cookie_manager.delete("logged_user")
            st.session_state.user = None
            st.rerun()

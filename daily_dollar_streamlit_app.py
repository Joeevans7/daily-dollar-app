
import streamlit as st
import sqlite3
import hashlib
import stripe
from datetime import datetime, timedelta
import pytz
import extra_streamlit_components as stx

# ========== App Configuration ==========
st.set_page_config(page_title="The Daily Dollar", page_icon=":moneybag:", initial_sidebar_state="collapsed")
DB_PATH = "daily_dollar.db"
stripe.api_key = "sk_test_51R9yN9CGGJzgCEPTGciHIWhNv5VVZjumDZbiaPSD5PHMYjTDMpJTdng7RfC2OBdaFLQnuGicYJYHoN8qYECkX8jy00nxZBNMFZ"

# ========== Cookie Management ==========
cookie_manager = stx.CookieManager()
cookie_user = cookie_manager.get("logged_user")

# ========== Session Initialization ==========
if "user" not in st.session_state:
    st.session_state.user = None
if "show_register" not in st.session_state:
    st.session_state.show_register = False

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
    now = datetime.now(pytz.utc).astimezone(cst)
    start = now.replace(hour=18, minute=1, second=0, microsecond=0)
    end = now.replace(hour=16, minute=59, second=0, microsecond=0)
    if now.hour < 17:
        start -= timedelta(days=1)
    else:
        end += timedelta(days=1)
    return start <= now <= end

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
        streak = streak + 1 if last_entry_date == yesterday else 1
        cursor.execute('UPDATE users SET last_entry_date = ?, streak = ? WHERE id = ?', (today, streak, user_id))
    conn.commit()
    conn.close()
    return f"{entry_type.capitalize()} entry successful."

def create_checkout_session(price_id, username, mode="payment", redirect="Dashboard"):
    base_url = "https://thedailydollar.streamlit.app"
    success_url = f"{base_url}?success=true&user={username}&redirect={redirect}"
    cancel_url = f"{base_url}?canceled=true&redirect={redirect}"
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        mode=mode,
        client_reference_id=username,
        success_url=success_url,
        cancel_url=cancel_url
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

# Handle Stripe success/cancel messages and routing
query_params = st.query_params
redirect_target = query_params.get("redirect", ["Dashboard"])[0]

# Restore session after payment
if query_params.get("success") == "true":
    st.success("Payment received! You’ve been entered into today’s drawing.")
    st.session_state.profile_section = redirect_target
    st.experimental_set_query_params()
    st.rerun()
elif query_params.get("canceled") == "true":
    st.warning("Payment canceled. You were not entered.")
    st.session_state.profile_section = redirect_target
    st.experimental_set_query_params()
    st.rerun()

# Auto-login from cookie
if st.session_state.user is None and cookie_user:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (cookie_user,))
    user = cursor.fetchone()
    conn.close()
    if user:
        st.session_state.user = user

# Login/Register UI
if st.session_state.user is None:
    st.title("The Daily Dollar")
    if st.session_state.show_register:
        st.subheader("Create Account")
        username = st.text_input("Username")
        phone = st.text_input("Phone Number")
        password = st.text_input("Password", type="password")
        confirm = st.text_input("Confirm Password", type="password")
        if st.button("Register"):
            if len(password) < 7:
                st.warning("Password must be at least 7 characters.")
            elif password != confirm:
                st.warning("Passwords do not match.")
            else:
                success, msg = create_user(username, phone, password)
                if success:
                    conn = sqlite3.connect(DB_PATH)
                    cursor = conn.cursor()
                    user = cursor.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
                    conn.close()
                    st.session_state.user = user
                    cookie_manager.set("logged_user", user[1])
                    st.success("Account created! You're now logged in.")
                    st.rerun()
                else:
                    st.error(msg)
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
                if remember:
                    cookie_manager.set("logged_user", user[1])
                st.success("Welcome back!")
                st.rerun()
            else:
                st.error("Invalid username or password.")
        if st.button("Don't have an account? Create one"):
            st.session_state.show_register = True
            st.rerun()

# Logged-in UI
if st.session_state.user:
    st.sidebar.success(f"Logged in as: {st.session_state.user[1]}")

    if "profile_section" not in st.session_state:
        st.session_state.profile_section = "About"

    profile_section = st.sidebar.radio(
        "Navigation",
        ["About", "Dashboard", "Profile"],
        index=["About", "Dashboard", "Profile"].index(st.session_state.profile_section)
    )

    user_id = st.session_state.user[0]

    if profile_section == "About":
        st.title("The Daily Dollar")
        st.header("About The Daily Dollar")
        st.markdown("""
        - **$1 Entry**: Enter the daily drawing for a chance to win the pot.
        - **Free Entry**: Enter for free and win 3% of the main prize.
        - **Streaks**: Consecutive daily entries build your streak and leaderboard position.
        - **Entry Time**: From 6:01 PM (CST) to 4:59 PM the next day.
        - **Auto-Entry**: In the Profile page, enable Auto-Entry and be entered automatically each day.
        - **Daily Draw**: Winners picked at 5 PM CST, announced at 5:30 PM.
        - **Platform Fee**: 7% taken from pot to fund operations.
        """)

    elif profile_section == "Dashboard":
        st.title("The Daily Dollar")
        st.header("Enter Today's Drawing")
        entry_choice = st.radio("Choose Entry Type", ["Main ($1 via Stripe)", "Free Entry"])

        today = datetime.now(pytz.utc).astimezone(pytz.timezone('US/Central')).date().isoformat()
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM entries WHERE user_id = ? AND date = ? AND entry_type = "main"', (user_id, today))
        already_entered_main = cursor.fetchone() is not None
        conn.close()

        if entry_choice.startswith("Main"):
            if already_entered_main:
                st.button("You’ve already entered!", disabled=True)
            else:
                url = create_checkout_session("price_1R9yRkCGGJzgCEPTOnnnvEKi", st.session_state.user[1], redirect="Dashboard")
                st.markdown(
                    f'''
                    <a href="{url}" target="_blank" style="text-decoration:none;">
                        <button style='width:100%;background-color:#4CAF50;color:white;padding:10px 24px;font-size:16px;border:none;border-radius:4px;cursor:pointer;'>
                            Pay & Enter via Stripe
                        </button>
                    </a>
                    ''',
                    unsafe_allow_html=True
                )
        elif entry_choice == "Free Entry":
            if st.button("Enter Free Drawing"):
                result = enter_daily_dollar(user_id, "free")
                st.success(result) if "successful" in result else st.warning(result)

        st.subheader("Yesterday's Winners")
        for uid, entry_type, prize in get_yesterdays_winners():
            st.write(f"**{entry_type.capitalize()} Winner**: {get_username_by_id(uid)} — ${prize:.2f}")

        st.subheader("Top 10 Entry Streaks")
        for rank, (username, streak) in enumerate(get_top_streaks(), start=1):
            st.write(f"{rank}. {username} — {streak} day streak")

    elif profile_section == "Profile":
        st.title("The Daily Dollar")
        st.header("Your Profile")
        username = st.session_state.user[1]
        phone = st.session_state.user[2]
        sms_opt_in = bool(st.session_state.user[4])

        st.write(f"**Username:** {username}")
        new_phone = st.text_input("Phone Number", value=phone)
        if st.button("Update Phone"):
            update_phone(user_id, new_phone)
            st.success("Phone number updated!")

        sms_toggle = st.checkbox("Receive SMS notifications", value=sms_opt_in)
        if sms_toggle != sms_opt_in:
            toggle_option(user_id, "sms_opt_in", int(sms_toggle))
            st.success("SMS preference updated!")

        st.markdown("---")
        st.markdown("**Daily Auto-Entry** — Never miss a $1 draw!")
        url = create_checkout_session("price_1RAEQmCGGJzgCEPTrhWZ904P", username, mode="subscription", redirect="Profile")
        st.markdown(
            f'''
            <a href="{url}" target="_blank" style="text-decoration:none;">
                <button style='width:100%;background-color:#008CBA;color:white;padding:10px 24px;font-size:16px;border:none;border-radius:4px;cursor:pointer;'>
                    Enable Auto-Entry (Subscribe)
                </button>
            </a>
            ''',
            unsafe_allow_html=True
        )

        if st.button("Sign Out"):
            cookie_manager.delete("logged_user")
            st.session_state.user = None
            st.session_state.show_register = False
            st.rerun()

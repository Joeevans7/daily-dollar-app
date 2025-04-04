import streamlit as st
import json
import uuid
from decimal import Decimal
from datetime import datetime, date, time
from pathlib import Path
from passlib.hash import bcrypt
import secrets
import stripe

# Stripe Configuration
stripe.api_key = "sk_test_51R9yN9CGGJzgCEPTGciHIWhNv5VVZjumDZbiaPSD5PHMYjTDMpJTdng7RfC2OBdaFLQnuGicYJYHoN8qYECkX8jy00nxZBNMFZ" 
STRIPE_PRICE_ID = "price_1R9yRkCGGJzgCEPTOnnnvEKi" 
STRIPE_SUCCESS_URL = "https://the-daily-dollar.streamlit.app?success=true"
STRIPE_CANCEL_URL = "https://the-daily-dollar.streamlit.app/?cancel=true"

USERS_FILE = "users.json"
ENTRIES_FILE = "entries.json"
DRAWS_FILE = "draw_results.json"

# -------------------- Models --------------------

class User:
    def __init__(self, user_id, username, phone, password_hash, auto_entry=False):
        self.user_id = user_id
        self.username = username
        self.phone = phone
        self.password_hash = password_hash
        self.auto_entry = auto_entry

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "username": self.username,
            "phone": self.phone,
            "password_hash": self.password_hash,
            "auto_entry": self.auto_entry
        }

    @staticmethod
    def from_dict(data):
        return User(
            data["user_id"],
            data["username"],
            data["phone"],
            data["password_hash"],
            data.get("auto_entry", False)
        )

    def verify_password(self, password):
        return bcrypt.verify(password, self.password_hash)


class Entry:
    def __init__(self, user_id, entry_type, amount=Decimal("0.00"), timestamp=None):
        self.user_id = user_id
        self.entry_type = entry_type
        self.amount = amount
        self.timestamp = timestamp or datetime.now()

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "entry_type": self.entry_type,
            "amount": str(self.amount),
            "timestamp": self.timestamp.isoformat()
        }

    @staticmethod
    def from_dict(data):
        return Entry(
            user_id=data["user_id"],
            entry_type=data["entry_type"],
            amount=Decimal(data["amount"]),
            timestamp=datetime.fromisoformat(data["timestamp"])
        )


class DrawResult:
    def __init__(self, date, draw_type, winner_username, prize):
        self.date = date
        self.draw_type = draw_type
        self.winner_username = winner_username
        self.prize = prize

    def to_dict(self):
        return {
            "date": self.date.isoformat(),
            "draw_type": self.draw_type,
            "winner_username": self.winner_username,
            "prize": str(self.prize)
        }

    @staticmethod
    def from_dict(data):
        return DrawResult(
            date=datetime.fromisoformat(data["date"]),
            draw_type=data["draw_type"],
            winner_username=data["winner_username"],
            prize=Decimal(data["prize"])
        )

# -------------------- File I/O --------------------

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def load_json(path):
    if not Path(path).exists():
        return []
    with open(path, "r") as f:
        return json.load(f)

def load_users():
    return [User.from_dict(u) for u in load_json(USERS_FILE)]

def load_entries():
    return [Entry.from_dict(e) for e in load_json(ENTRIES_FILE)]

def load_draws():
    return [DrawResult.from_dict(d) for d in load_json(DRAWS_FILE)]

def save_users(users):
    save_json(USERS_FILE, [u.to_dict() for u in users])

def save_entries(entries):
    save_json(ENTRIES_FILE, [e.to_dict() for e in entries])

def save_draws(draws):
    save_json(DRAWS_FILE, [d.to_dict() for d in draws])

def get_user_by_phone(phone, users):
    return next((u for u in users if u.phone == phone), None)

def has_already_entered(user, entry_type, entries):
    today = date.today()
    return any(
        e.user_id == user.user_id and
        e.entry_type == entry_type and
        e.timestamp.date() == today
        for e in entries
    )

def is_entry_window_open():
    now = datetime.now().time()
    return now >= time(17, 0) or now <= time(15, 0)

def enter_draw(user, entry_type, entries):
    if not is_entry_window_open():
        return False, "Entry window closed. You’ll have to wait for the next drawing."
    if has_already_entered(user, entry_type, entries):
        return False, f"You've already entered the {entry_type} draw today!"
    amount = Decimal("1.00") if entry_type == "main" else Decimal("0.00")
    entries.append(Entry(user.user_id, entry_type, amount))
    return True, f"Successfully entered the {entry_type} draw!"

def calculate_dashboard(entries):
    today = date.today()
    main_entries = [e for e in entries if e.entry_type == "main" and e.timestamp.date() == today]
    mini_entries = [e for e in entries if e.entry_type == "mini" and e.timestamp.date() == today]
    pot = sum(e.amount for e in main_entries)
    fee = (pot * Decimal("0.10")).quantize(Decimal("0.01"))
    mini_prize = (pot * Decimal("0.02")).quantize(Decimal("0.01"))
    return len(main_entries), len(mini_entries), pot, fee, mini_prize

def select_winner(entries):
    return secrets.choice(entries) if entries else None

def run_draw(draw_type, entries, users):
    today = date.today()
    filtered = [e for e in entries if e.entry_type == draw_type and e.timestamp.date() == today]
    if not filtered:
        return None
    winner_entry = select_winner(filtered)
    user = next((u for u in users if u.user_id == winner_entry.user_id), None)
    if draw_type == "main":
        pot = sum(e.amount for e in filtered)
        prize = (pot * Decimal("0.90")).quantize(Decimal("0.01"))
    else:
        pot = sum(e.amount for e in entries if e.entry_type == "main" and e.timestamp.date() == today)
        prize = (pot * Decimal("0.02")).quantize(Decimal("0.01"))
    return DrawResult(date=today, draw_type=draw_type, winner_username=user.username, prize=prize)

def auto_run_daily_draw(draws, entries, users):
    now = datetime.now()
    today = date.today()
    already_drawn = any(d.date.date() == today for d in draws)
    if now.hour >= 16 and not already_drawn:
        main = run_draw("main", entries, users)
        mini = run_draw("mini", entries, users)
        if main: draws.append(main)
        if mini: draws.append(mini)
        save_draws(draws)
        return main, mini
    return None, None

# -------------------- Streamlit App --------------------

st.set_page_config(page_title="The Daily Dollar", layout="centered")
st.title("The Daily Dollar")

users = load_users()
entries = load_entries()
draws = load_draws()

main_draw_result, mini_draw_result = auto_run_daily_draw(draws, entries, users)

# Login / Register
st.sidebar.header("Login or Register")
auth_mode = st.sidebar.radio("Choose mode", ["Login", "Register"])
phone = st.sidebar.text_input("Phone Number")
password = st.sidebar.text_input("Password", type="password")

if auth_mode == "Register":
    username = st.sidebar.text_input("Username")
    if st.sidebar.button("Create Account"):
        if get_user_by_phone(phone, users):
            st.sidebar.error("Phone number already registered.")
        elif not username or not phone or not password:
            st.sidebar.error("All fields are required.")
        else:
            hashed_pw = bcrypt.hash(password)
            new_user = User(str(uuid.uuid4())[:8], username, phone, hashed_pw)
            users.append(new_user)
            save_users(users)
            st.session_state.user = new_user.to_dict()
            st.sidebar.success("Account created. You're logged in!")

elif auth_mode == "Login":
    if st.sidebar.button("Log In"):
        user = get_user_by_phone(phone, users)
        if not user or not user.verify_password(password):
            st.sidebar.error("Invalid credentials.")
        else:
            st.session_state.user = user.to_dict()
            st.sidebar.success("Logged in successfully!")

# If logged in
if "user" in st.session_state and st.session_state.user:
    current_user = User.from_dict(st.session_state.user)
    st.subheader(f"Welcome, {current_user.username}!")

    query_params = st.experimental_get_query_params()
    if "success" in query_params:
        success, msg = enter_draw(current_user, "main", entries)
        if success:
            st.balloons()
        st.success(msg)
        save_entries(entries)
    elif "cancel" in query_params:
        st.warning("Payment was canceled.")

if st.button("Pay $1 to Enter Main Draw"):
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="payment",
            line_items=[{
                "price": STRIPE_PRICE_ID,
                "quantity": 1,
            }],
            success_url=STRIPE_SUCCESS_URL,
            cancel_url=STRIPE_CANCEL_URL,
            )
            checkout_url = session.url
            if checkout_url:
                st.markdown(f"[Click here to complete payment]({checkout_url})", unsafe_allow_html=True)
    except Exception as e:
        st.error(f"Stripe Checkout error: {str(e)}")

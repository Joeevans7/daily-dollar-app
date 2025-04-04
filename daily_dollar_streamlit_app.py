import streamlit as st
import json
import uuid
from decimal import Decimal
from datetime import datetime, date, time
from pathlib import Path
from passlib.hash import bcrypt
import secrets

# --- Stripe Checkout helper ---
import stripe

stripe.api_key = "sk_test_51R9yN9CGGJzgCEPTGciHIWhNv5VVZjumDZbiaPSD5PHMYjTDMpJTdng7RfC2OBdaFLQnuGicYJYHoN8qYECkX8jy00nxZBNMFZ"

def create_checkout_session(success_url, cancel_url, price_id):
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="payment",
            line_items=[{
                "price": price_id,
                "quantity": 1,
            }],
            success_url=success_url,
            cancel_url=cancel_url,
        )
        return session.url
    except Exception as e:
        return str(e)

USERS_FILE = "users.json"
ENTRIES_FILE = "entries.json"
DRAWS_FILE = "draw_results.json"

# Stripe config
STRIPE_PRICE_ID = "prod_S46fPdAEtIqZwD"
STRIPE_SUCCESS_URL = "https://your-app-name.streamlit.app/?success=true"
STRIPE_CANCEL_URL = "https://your-app-name.streamlit.app/?cancel=true"

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
        return User(data["user_id"], data["username"], data["phone"], data["password_hash"], data.get("auto_entry", False))

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

# ---------- Data Helpers ----------

def save_json(filepath, data):
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)

def load_json(filepath):
    if not Path(filepath).exists():
        return []
    with open(filepath, "r") as f:
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

# ---------- Entry + Draw Logic ----------

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

# ---------- Streamlit UI ----------

st.set_page_config(page_title="The Daily Dollar", layout="centered")
st.title("The Daily Dollar")

users = load_users()
entries = load_entries()
draws = load_draws()

# Auto run daily draw
main_draw_result, mini_draw_result = auto_run_daily_draw(draws, entries, users)

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

# ---------- Logged-in UI ----------

if "user" in st.session_state and st.session_state.user:
    current_user = User.from_dict(st.session_state.user)
    st.subheader(f"Welcome, {current_user.username}!")

    # Handle Stripe success return
    query_params = st.experimental_get_query_params()
    if "success" in query_params:
        success, msg = enter_draw(current_user, "main", entries)
        if success:
            st.balloons()
        st.success(msg)
        save_entries(entries)
    elif "cancel" in query_params:
        st.warning("Payment was canceled.")

    # Auto-entry option
    current_user.auto_entry = st.checkbox("Auto-enter me into future draws", value=current_user.auto_entry)
    save_users(users)

    # Dashboard
    main_count, mini_count, pot, fee, mini_prize = calculate_dashboard(entries)
    st.metric("Daily Dollar Entries", main_count)
    st.metric("Free Entries", mini_count)
    st.metric("Total Pot", f"${pot}")
    st.metric("Platform Fee", f"${fee}")
    st.metric("Mini Draw Prize", f"${mini_prize}")

# Stripe Main Draw Button
if st.button("Pay $1 to Enter Main Draw"):
    checkout_url = create_checkout_session(
        success_url=STRIPE_SUCCESS_URL,
        cancel_url=STRIPE_CANCEL_URL,
        price_id=STRIPE_PRICE_ID
    )

    if isinstance(checkout_url, str) and checkout_url.startswith("http"):
        st.success("Redirecting to Stripe...")
        st.markdown(f"[Click here to complete payment]({checkout_url})", unsafe_allow_html=True)
    else:
        st.error("There was a problem starting your payment session.")
    if st.button("Enter Mini Draw (Free)"):
        success, msg = enter_draw(current_user, "mini", entries)
        st.success(msg) if success else st.warning(msg)
        save_entries(entries)

    # Profile
    st.markdown("### Your Entry Profile")
    total_days = len({e.timestamp.date() for e in entries if e.user_id == current_user.user_id})
    st.write(f"You’ve entered on **{total_days} unique days**.")
    if main_draw_result and main_draw_result.winner_username == current_user.username:
        st.balloons()
        st.success("You won the MAIN draw today!")
    if mini_draw_result and mini_draw_result.winner_username == current_user.username:
        st.balloons()
        st.success("You won the MINI draw today!")

    # Yesterday leaderboard
    st.markdown("### Yesterday’s Winners")
    yesterday = date.today().toordinal() - 1
    for d in draws:
        if d.date.date().toordinal() == yesterday:
            st.info(f"{d.draw_type.upper()} - {d.winner_username} won ${d.prize}")
else:
    st.warning("Please log in or register to play.")

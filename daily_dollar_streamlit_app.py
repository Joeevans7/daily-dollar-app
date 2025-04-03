import streamlit as st
import json
import uuid
from decimal import Decimal
from datetime import datetime, date
from pathlib import Path
import secrets

# ---------------- Core Logic ----------------

USERS_FILE = "users.json"
ENTRIES_FILE = "entries.json"

# --------- Models ---------

class User:
    def __init__(self, user_id, email, username):
        self.user_id = user_id
        self.email = email
        self.username = username

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "email": self.email,
            "username": self.username
        }

    @staticmethod
    def from_dict(data):
        return User(data["user_id"], data["email"], data["username"])


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


# --------- Data Management ---------

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

def save_users(users):
    save_json(USERS_FILE, [u.to_dict() for u in users])

def save_entries(entries):
    save_json(ENTRIES_FILE, [e.to_dict() for e in entries])


# --------- Business Logic ---------

def get_user_by_username(username, users):
    return next((u for u in users if u.username == username), None)

def has_already_entered(user, entry_type, entries):
    today = date.today()
    return any(
        e.user_id == user.user_id and
        e.entry_type == entry_type and
        e.timestamp.date() == today
        for e in entries
    )

def enter_draw(user, entry_type, entries):
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

# ---------------- Streamlit UI ----------------

st.set_page_config(page_title="The Daily Dollar", layout="centered")
st.title("The Daily Dollar")

users = load_users()
entries = load_entries()

# ----- Authentication -----
st.sidebar.header("Login or Register")
username = st.sidebar.text_input("Username")
email = st.sidebar.text_input("Email (only for new users)")
if st.sidebar.button("Log In / Register"):
    user = get_user_by_username(username, users)
    if not user:
        if username and email:
            user = User(str(uuid.uuid4())[:8], email, username)
            users.append(user)
            save_users(users)
            st.success(f"Welcome, {username}! You've been registered.")
        else:
            st.error("To register, you must enter both username and email.")
    else:
        st.success(f"Welcome back, {username}!")
    st.session_state.user = user.to_dict() if user else None

# If logged in
if "user" in st.session_state and st.session_state.user:
    current_user = User.from_dict(st.session_state.user)

    st.subheader(f"Logged in as: {current_user.username}")

    # Show dashboard
    st.markdown("### Today's Dashboard")
    main_count, mini_count, pot, fee, mini_prize = calculate_dashboard(entries)
    st.metric("Main Draw Entries", main_count)
    st.metric("Mini Draw Entries", mini_count)
    st.metric("Total Pot", f"${pot}")
    st.metric("Platform Fee (10%)", f"${fee}")
    st.metric("Mini Draw Prize (2%)", f"${mini_prize}")

    # Entry buttons
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Enter Main Draw ($1)"):
            success, msg = enter_draw(current_user, "main", entries)
            st.success(msg) if success else st.warning(msg)
    with col2:
        if st.button("Enter Mini Draw (Free)"):
            success, msg = enter_draw(current_user, "mini", entries)
            st.success(msg) if success else st.warning(msg)

    # Save on action
    save_entries(entries)

else:
    st.warning("Please log in or register using the sidebar.")
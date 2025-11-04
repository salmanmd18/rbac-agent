from __future__ import annotations

import os
from typing import Dict, List

import requests
import streamlit as st
from requests.auth import HTTPBasicAuth


DEFAULT_BACKEND_URL = os.getenv("FINCHAT_BACKEND_URL", "http://localhost:8000")


st.set_page_config(
    page_title="FinSolve RBAC Chatbot",
    layout="wide",
)


def get_backend_url() -> str:
    return st.session_state.get("backend_url", DEFAULT_BACKEND_URL)


def initialize_state() -> None:
    st.session_state.setdefault("backend_url", DEFAULT_BACKEND_URL)
    st.session_state.setdefault("auth", None)
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("top_k", 4)


def login(username: str, password: str) -> Dict[str, str]:
    response = requests.get(
        f"{get_backend_url()}/login",
        auth=HTTPBasicAuth(username, password),
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    return {"username": username, "password": password, "role": payload.get("role")}


def chat(message: str, top_k: int) -> Dict[str, object]:
    auth = st.session_state["auth"]
    response = requests.post(
        f"{get_backend_url()}/chat",
        json={"message": message, "top_k": top_k},
        auth=HTTPBasicAuth(auth["username"], auth["password"]),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def render_sidebar() -> None:
    st.sidebar.title("Configuration")
    backend_url = st.sidebar.text_input("Backend URL", value=get_backend_url())
    if backend_url != get_backend_url():
        st.session_state["backend_url"] = backend_url
    st.sidebar.markdown("---")
    if st.session_state["auth"]:
        st.sidebar.success(
            f"Logged in as {st.session_state['auth']['username']} "
            f"({st.session_state['auth']['role']})"
        )
        st.session_state["top_k"] = st.sidebar.slider("Top K", min_value=1, max_value=8, value=st.session_state["top_k"])
        if st.sidebar.button("Log out"):
            st.session_state["auth"] = None
            st.session_state["messages"] = []
            st.experimental_rerun()
    else:
        st.sidebar.info("Login to start chatting.")


def render_login() -> None:
    st.header("Login")
    with st.form("login-form", clear_on_submit=False):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")
        if submitted:
            if not username or not password:
                st.error("Please provide username and password.")
                return
            try:
                st.session_state["auth"] = login(username, password)
                st.success("Login successful! You can now start chatting.")
                st.experimental_rerun()
            except requests.HTTPError as exc:
                if exc.response.status_code == 401:
                    st.error("Invalid credentials. Please try again.")
                else:
                    st.error(f"Login failed: {exc}")
            except requests.RequestException as exc:
                st.error(f"Unable to reach backend: {exc}")


def render_chat() -> None:
    st.header("FinSolve RBAC Chatbot")
    st.caption("Ask questions and the assistant will reply with role-aware context.")

    for message in st.session_state["messages"]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            references: List[Dict[str, object]] = message.get("references", [])
            if references:
                st.markdown("**References:**")
                for ref in references:
                    score_text = f" (score: {ref['score']:.2f})" if ref.get("score") is not None else ""
                    st.markdown(f"- `{ref['department']}` - {ref['source']}{score_text}")

    if prompt := st.chat_input("Ask something about the documents..."):
        st.session_state["messages"].append({"role": "user", "content": prompt})
        try:
            response = chat(prompt, st.session_state["top_k"])
            assistant_message = {
                "role": "assistant",
                "content": response["answer"],
                "references": response.get("references", []),
            }
        except requests.HTTPError as exc:
            assistant_message = {
                "role": "assistant",
                "content": f"Request failed: {exc}",
                "references": [],
            }
        except requests.RequestException as exc:
            assistant_message = {
                "role": "assistant",
                "content": f"Unable to reach backend: {exc}",
                "references": [],
            }
        st.session_state["messages"].append(assistant_message)
        st.experimental_rerun()


def main() -> None:
    initialize_state()
    render_sidebar()
    if not st.session_state["auth"]:
        render_login()
    else:
        render_chat()


if __name__ == "__main__":
    main()

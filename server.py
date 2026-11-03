"""Punctul de intrare al serverului: aplicatia Streamlit (app.py) cu middleware-ul Tailscale (tsauth).
Pornire: streamlit run server.py --server.port=8501 ... (Streamlit gaseste obiectul `app` si ruleaza in mod ASGI)."""
import streamlit as st
from starlette.middleware import Middleware

import tsauth

app = st.App("app.py", middleware=[Middleware(tsauth.Middleware)])

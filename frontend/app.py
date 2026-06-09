import json

import requests
import streamlit as st

BACKEND = "http://localhost:8000"

st.set_page_config(page_title="RAG Chatbot", page_icon="📄")
st.title("📄 RAG Chatbot")

if "messages" not in st.session_state:
    st.session_state.messages = []

with st.sidebar:
    st.header("Documents")

    uploaded = st.file_uploader("Upload a PDF or TXT", type=["pdf", "txt"])
    if uploaded is not None and st.button("Ingest", use_container_width=True):
        with st.spinner("Ingesting..."):
            resp = requests.post(
                f"{BACKEND}/upload",
                files={"file": (uploaded.name, uploaded.getvalue())},
                timeout=300,
            )
        if resp.ok:
            data = resp.json()
            st.success(
                f"Ingested {data['filename']} ({data['chunks_count']} chunks)"
            )
        else:
            st.error(f"Upload failed: {resp.text}")

    try:
        docs = requests.get(f"{BACKEND}/documents", timeout=30).json()
    except requests.RequestException:
        docs = []
        st.warning("Backend is not reachable at " + BACKEND)

    options = {"All documents": None}
    for d in docs:
        options[f"{d['filename']} ({d['doc_id'][:8]})"] = d["doc_id"]
    choice = st.selectbox("Chat with", list(options))
    doc_id = options[choice]

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if question := st.chat_input("Ask a question about your documents"):
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    def sse_stream():
        resp = requests.post(
            f"{BACKEND}/chat",
            json={
                "question": question,
                "doc_id": doc_id,
                "history": st.session_state.messages[:-1],
            },
            stream=True,
            timeout=300,
        )
        resp.raise_for_status()
        for line in resp.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            payload = line[len("data: "):]
            if payload == "[DONE]":
                break
            yield json.loads(payload)["content"]

    with st.chat_message("assistant"):
        answer = st.write_stream(sse_stream())
    st.session_state.messages.append({"role": "assistant", "content": answer})
